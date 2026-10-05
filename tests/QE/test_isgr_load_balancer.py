from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorType,
)
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    ISGRPayload,
    ScopeConfig,
    SyncGateway,
)
from cbltest.api.test_functions import compare_local_and_remote

_ISGR_REPLICATION_ID = "isgr-lb-link"
_SG1_PIN = {"X-Backend": "sg-0"}
_SG2_PIN = {"X-Backend": "sg-1"}
_DEFAULT_COLLECTION = "_default._default"


@asynccontextmanager
async def _setup_isgr_pair(
    cblpytest: CBLPyTest,
    db_name: str,
    channels: list[str],
    user_name: str,
    user_password: str,
) -> AsyncIterator[tuple[SyncGateway, SyncGateway]]:
    """
    Configures a same-named database on each of the first two Sync Gateway nodes (separate
    buckets, so they are genuinely independent backends), a matching user on both, and a
    continuous bidirectional ISGR link from the first to the second.  Stops the link on exit.
    """
    cluster = cblpytest.clusters[0]
    sg1, sg2 = cluster.sync_gateways[0], cluster.sync_gateways[1]

    for sg, bucket_name in ((sg1, "bucket-isgr-lb-1"), (sg2, "bucket-isgr-lb-2")):
        await cluster.create_database(
            db_name,
            DatabaseConfig(
                bucket=bucket_name,
                num_index_replicas=0,
                scopes={"_default": ScopeConfig(collections={"_default": {}})},
            ),
        )
        await sg.reset_user(db_name, user_name, user_password, channels)

    # One pushAndPull replication already covers both directions -- do not also start one
    # from SG2, that would just be a second, redundant link fighting the first.
    await sg1.start_isgr(
        db_name,
        ISGRPayload(
            replication_id=_ISGR_REPLICATION_ID,
            remote_url=sg2.http_url,
            remote_db=db_name,
            direction="pushAndPull",
            continuous=True,
            remote_username="admin",
            remote_password="password",
        ),
    )
    try:
        yield sg1, sg2
    finally:
        await sg1.stop_isgr(db_name, _ISGR_REPLICATION_ID, continuous=True)


async def _write_native(
    primary: SyncGateway,
    secondary: SyncGateway,
    db_name: str,
    docs: list[DocumentUpdateEntry],
) -> None:
    """
    Writes docs only on `primary`, relying on ISGR to propagate them to `secondary`.  A write
    with the same id on both would be a genuine write conflict, not the clean one-directional
    propagation these tests measure, and would silently invalidate what's being asserted.  Checks
    BEFORE the write (not after, and not just before an ISGR wait) since ISGR is continuous and
    could already have propagated by any later point -- pre-write is the only race-free check.
    """
    for entry in docs:
        try:
            await secondary.get_document(db_name, entry.id)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 404:
                raise
        else:
            raise AssertionError(
                f"Doc '{entry.id}' already exists on the secondary backend before the native "
                "write -- that would be a genuine write conflict, not clean ISGR propagation"
            )
    await primary.update_documents(db_name, docs)


async def _pinned_pull(
    db: Database,
    repl_url: str,
    user_name: str,
    user_password: str,
    pin: dict[str, str],
) -> Replicator:
    """
    Runs one one-shot pull pinned to a specific backend and returns the Replicator so callers can
    inspect both its transferred-document count and the resulting local documents.  A fresh
    Replicator object every call, but always the SAME db and repl_url across a loop -- a CBL
    checkpoint ID is a hash of that tuple (never of the X-Backend pin or the Python object
    identity), so this is what keeps a series of pinned pulls sharing one checkpoint across both
    backends.  Never pass reset=True: that would force a fresh checkpoint on every call and make
    every pull look like first-ever contact, silently turning a loop into a vacuous test.
    """
    replicator = Replicator(
        db,
        repl_url,
        replicator_type=ReplicatorType.PULL,
        continuous=False,
        authenticator=ReplicatorBasicAuthenticator(user_name, user_password),
        enable_document_listener=True,
        headers=pin,
    )
    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is None, (
        f"Pinned pull ({pin}) failed: ({status.error.domain} / {status.error.code}) {status.error.message}"
    )
    return replicator


@pytest.mark.sgw
@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_load_balancers(1)
class TestISGRLoadBalancer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_checkpoint_divergence_behind_load_balancer(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        db_name = "db_isgr_lb"
        channels = ["isgr_lb_test"]
        user_name, user_password = "isgr_lb_user", "pass"

        self.mark_test_step("Set up same-named DB + user on both SGWs, and a continuous bidirectional ISGR link")
        async with _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password) as (sg1, sg2):
            self.mark_test_step("Add one seed doc directly on SG1 (native), and wait for it to reach SG2 via ISGR")
            await _write_native(
                sg1,
                sg2,
                db_name,
                [DocumentUpdateEntry(id="seed_doc", revision=None, body={"channels": channels})],
            )
            await sg2.wait_for_document_count(db_name, 1)

            self.mark_test_step("Create an empty local CBL database")
            db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
            repl_url = cblpytest.clusters[0].sync_gateways[0].replication_url(db_name, cblpytest.load_balancers[0])

            async def pinned_pull(pin: dict[str, str]) -> int:
                """Runs one pinned pull and returns how many docs it transferred."""
                replicator = await _pinned_pull(db, repl_url, user_name, user_password, pin)
                return len(replicator.document_updates)

            self.mark_test_step(
                "First-ever contact with each backend: pull pinned to SG1, then to SG2 -- "
                "expect a non-empty transfer on both"
            )
            assert await pinned_pull(_SG1_PIN) > 0, "Expected SG1's first-ever contact to transfer the seed doc"
            assert await pinned_pull(_SG2_PIN) > 0, "Expected SG2's first-ever contact to transfer the seed doc"

            self.mark_test_step(
                "Repeat against both already-known backends with no new writes -- expect zero transfer every time"
            )
            for _ in range(2):
                assert await pinned_pull(_SG1_PIN) == 0, "Expected no redundant transfer on an already-known backend"
                assert await pinned_pull(_SG2_PIN) == 0, "Expected no redundant transfer on an already-known backend"

            self.mark_test_step("Add one more doc directly on SG1, and wait for it to reach SG2 via ISGR")
            await _write_native(
                sg1,
                sg2,
                db_name,
                [DocumentUpdateEntry(id="second_doc", revision=None, body={"channels": channels})],
            )
            await sg2.wait_for_document_count(db_name, 2)

            self.mark_test_step(
                "Each backend's next contact after the new write -- expect a non-empty transfer on both (and only these two)"
            )
            assert await pinned_pull(_SG1_PIN) > 0, "Expected SG1's next contact to transfer the new doc"
            assert await pinned_pull(_SG2_PIN) > 0, "Expected SG2's next contact to transfer the new doc"

            self.mark_test_step("Repeat once more with no further writes -- expect zero transfer again")
            assert await pinned_pull(_SG1_PIN) == 0, "Expected no redundant transfer after convergence"
            assert await pinned_pull(_SG2_PIN) == 0, "Expected no redundant transfer after convergence"

            self.mark_test_step(
                "Verify the local CBL database and both SGWs (queried directly, bypassing the load balancer) "
                "agree on the full document set"
            )
            await compare_local_and_remote(
                db, sg1, ReplicatorType.PULL, bucket=db_name, collections=[_DEFAULT_COLLECTION]
            )
            await compare_local_and_remote(
                db, sg2, ReplicatorType.PULL, bucket=db_name, collections=[_DEFAULT_COLLECTION]
            )

            self.mark_test_step("Verify the SG1-to-SG2 ISGR link itself is still healthy")
            link_status = await sg1.get_isgr_status(db_name, _ISGR_REPLICATION_ID)
            assert link_status.get("status") != "error", f"ISGR link entered an error state: {link_status}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_isgr_pull_preserves_channel_set(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        db_name = "db_isgr_lb_channels"
        channels = ["isgr_lb_channel_test"]
        user_name, user_password = "isgr_lb_channel_user", "pass"
        doc_id = "channel_set_doc"

        self.mark_test_step("Set up same-named DB + user on both SGWs, and a continuous bidirectional ISGR link")
        async with _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password) as (sg1, sg2):
            self.mark_test_step("Add one brand-new doc with an explicit channel assignment directly on SG1")
            await _write_native(
                sg1,
                sg2,
                db_name,
                [DocumentUpdateEntry(id=doc_id, revision=None, body={"channels": channels})],
            )

            self.mark_test_step("Wait for the doc to reach SG2 via ISGR")
            await sg2.wait_for_document_count(db_name, 1)

            self.mark_test_step("Verify the doc is visible through a _changes call scoped to that channel on SG2")
            async with sg2.create_user_client(db_name, user_name, user_password, channels) as scoped_user:
                changes = await scoped_user.get_changes(db_name)
                doc_ids = {entry.id for entry in changes.results}
                assert doc_id in doc_ids, (
                    f"Doc invisible on SG2's channel-scoped _changes feed despite no error: {doc_ids}"
                )

            self.mark_test_step(
                "Pull the doc through a real CBL client pinned to SG2, and verify its channel assignment arrives intact"
            )
            db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
            repl_url = cblpytest.clusters[0].sync_gateways[0].replication_url(db_name, cblpytest.load_balancers[0])
            replicator = await _pinned_pull(db, repl_url, user_name, user_password, _SG2_PIN)
            assert len(replicator.document_updates) > 0, "Expected the pull pinned to SG2 to transfer the doc"

            pulled = await db.get_document(DocumentEntry(_DEFAULT_COLLECTION, doc_id))
            assert pulled.body.get("channels") == channels, (
                f"Doc arrived at the CBL client with the wrong channel assignment: {pulled.body}"
            )
