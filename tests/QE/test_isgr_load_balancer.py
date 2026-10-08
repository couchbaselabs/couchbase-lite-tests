from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.database_types import DocumentEntry
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
    UnsupportedSettings,
)
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.responses import ServerVariant

_ISGR_REPLICATION_ID = "isgr-lb-link"
_SG1_PIN = {"X-Backend": "sg-0"}
_SG2_PIN = {"X-Backend": "sg-1"}
_DEFAULT_COLLECTION = "_default._default"


async def _setup_isgr_pair(
    cblpytest: CBLPyTest,
    db_name: str,
    channels: list[str],
    user_name: str,
    user_password: str,
) -> tuple[SyncGateway, SyncGateway]:
    """
    Configures a same-named database on two GENUINELY SEPARATE Couchbase clusters (not just two buckets within one
    shared cluster) -- CouchbaseCluster.create_database() is cluster-wide: it writes the config once and then makes
    every node in that SAME cluster's sync_gateways apply it, so looping two different bucket configs over one shared
    cluster would make both nodes fight over the same database instead of being independent backends. Configures a
    matching user on each, then starts a continuous bidirectional ISGR link from the first to the second. The link is
    left running; `cluster_cleanup` deletes both databases, which stops it, before the next test.
    """
    cluster1, cluster2 = cblpytest.clusters[1], cblpytest.clusters[2]
    sg1, sg2 = cluster1.sync_gateways[0], cluster2.sync_gateways[0]

    for cluster, sg, bucket_name in (
        (cluster1, sg1, "bucket-isgr-lb-1"),
        (cluster2, sg2, "bucket-isgr-lb-2"),
    ):
        await cluster.create_database(
            db_name,
            DatabaseConfig(
                bucket=bucket_name,
                num_index_replicas=0,
                scopes={"_default": ScopeConfig(collections={"_default": {}})},
                unsupported=UnsupportedSettings(sgr_tls_skip_verify=True),
            ),
        )
        await sg.reset_user(db_name, user_name, user_password, channels)

    # One pushAndPull replication already covers both directions -- do not also start one from SG2, that would just be a
    # second, redundant link fighting the first.
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
    return sg1, sg2


async def _wait_for_propagation(
    secondary: SyncGateway,
    db_name: str,
    doc_ids: list[str],
    link_owner: SyncGateway,
) -> None:
    """Waits for `doc_ids` to reach `secondary` via ISGR, attaching `link_owner`'s ISGR status on a timeout."""
    try:
        await secondary.wait_for_documents(db_name, doc_ids)
    except TimeoutError as e:
        status = await link_owner.get_isgr_status(db_name, _ISGR_REPLICATION_ID)
        raise AssertionError(f"{e} -- ISGR status on {link_owner.hostname}: {status}") from e


async def _pinned_pull(
    db: Database,
    repl_url: str,
    user_name: str,
    user_password: str,
    pin: dict[str, str],
) -> Replicator:
    """
    Runs one one-shot pull pinned to a specific backend and returns the Replicator so callers can inspect both its
    transferred-document count and the resulting local documents. A fresh Replicator object every call, but always the
    SAME db and repl_url across a loop, so this is what keeps a series of pinned pulls sharing one checkpoint across
    both backends. Never pass reset=True: that would force a fresh checkpoint on every call and make every pull look
    like first-ever contact, silently turning a loop into a vacuous test.
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
@pytest.mark.min_load_balancers(2)
@pytest.mark.min_clusters(3)
class TestISGRLoadBalancer(CBLTestClass):
    async def _skip_if_unsupported(self, cblpytest: CBLPyTest) -> None:
        """
        Skips on the JS test server, whose Websocket library cannot send the X-Backend header these tests pin with, and
        on SGW versions without the ISGR channel-loss fix (CBG-5772 in 4.0.8, CBG-5773 in 4.1.2; 4.1.0.1 lacks it).
        """
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS)
        await self.skip_if_sgw_not(
            cblpytest.clusters[1].sync_gateways[0],
            "!=4.0.0,!=4.0.1,!=4.0.2,!=4.0.3,!=4.0.4,!=4.0.5,!=4.0.6,!=4.0.7,!=4.1.0.*,!=4.1.1",
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_checkpoint_divergence_behind_load_balancer(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self._skip_if_unsupported(cblpytest)

        db_name = "db_isgr_lb"
        channels = ["isgr_lb_test"]
        user_name, user_password = "isgr_lb_user", "pass"

        self.mark_test_step("Set up same-named DB + user on both SGWs, and a continuous bidirectional ISGR link")
        sg1, sg2 = await _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password)
        self.mark_test_step(
            "Add one seed doc directly on SG1 (native), and wait for SG1's changes feed to show it and for it"
            " to reach SG2 via ISGR"
        )
        await sg1.update_documents(
            db_name,
            [DocumentUpdateEntry(id="seed_doc", revision=None, body={"channels": channels})],
            wait_for_caching_feed=True,
        )
        await _wait_for_propagation(sg2, db_name, ["seed_doc"], link_owner=sg1)

        self.mark_test_step("Create an empty local CBL database")
        db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
        repl_url = sg1.replication_url(db_name, cblpytest.load_balancers[1])

        async def pinned_pull(pin: dict[str, str], sg: SyncGateway) -> tuple[int, int]:
            """
            Runs one pinned pull and returns (docs transferred, `sg`'s own since-zero-pull-count delta).
            The transfer count alone can't distinguish a genuine incremental continuation from a redundant
            full resync that happens not to transfer anything new (the puller already holds an identical
            revision for everything proposed either way) -- the since-zero delta is server-observed and
            unaffected by that ambiguity, since it reflects whether `sg` served this pull from
            `/_changes?since=0` regardless of what the puller already had.
            """
            before = await sg.get_pull_repl_since_zero_count(db_name)
            replicator = await _pinned_pull(db, repl_url, user_name, user_password, pin)
            after = await sg.get_pull_repl_since_zero_count(db_name)
            return len(replicator.document_updates), after - before

        self.mark_test_step(
            "First-ever contact with SG1, then with SG2 -- expect a non-empty transfer and a since=0 proposal"
            " on SG1; SG2 also gets a since=0 proposal, but its transfer count is not asserted"
        )
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1)
        assert sg1_docs > 0, "Expected SG1's first-ever contact to transfer the seed doc"
        assert sg1_since_zero == 1, "Expected SG1's first-ever contact to start from since=0"
        _, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2)
        assert sg2_since_zero == 1, "Expected SG2's first-ever contact to also start from since=0"

        self.mark_test_step(
            "Repeat against both already-known backends with no new writes -- expect zero transfer and no"
            " since=0 proposal every time"
        )
        for _ in range(2):
            sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1)
            assert sg1_docs == 0, "Expected no redundant transfer on an already-known backend"
            assert sg1_since_zero == 0, "Expected SG1 to continue incrementally, not restart from since=0"
            sg2_docs, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2)
            assert sg2_docs == 0, "Expected no redundant transfer on an already-known backend"
            assert sg2_since_zero == 0, "Expected SG2 to continue incrementally, not restart from since=0"

        self.mark_test_step(
            "Add one more doc directly on SG1, and wait for SG1's changes feed to show it and for it to reach"
            " SG2 via ISGR"
        )
        await sg1.update_documents(
            db_name,
            [DocumentUpdateEntry(id="second_doc", revision=None, body={"channels": channels})],
            wait_for_caching_feed=True,
        )
        await _wait_for_propagation(sg2, db_name, ["second_doc"], link_owner=sg1)

        self.mark_test_step(
            "Each backend's next contact after the new write: SG1, then SG2 -- expect a non-empty transfer on"
            " SG1 only, and an incremental (not since=0) continuation on both"
        )
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1)
        assert sg1_docs > 0, "Expected SG1's next contact to transfer the new doc"
        assert sg1_since_zero == 0, "Expected SG1's next contact to continue incrementally, not restart from since=0"
        _, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2)
        assert sg2_since_zero == 0, "Expected SG2's next contact to continue incrementally, not restart from since=0"

        self.mark_test_step(
            "Repeat once more with no further writes -- expect zero transfer and no since=0 proposal again"
        )
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1)
        assert sg1_docs == 0, "Expected no redundant transfer after convergence"
        assert sg1_since_zero == 0, "Expected SG1 to remain an incremental continuation after convergence"
        sg2_docs, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2)
        assert sg2_docs == 0, "Expected no redundant transfer after convergence"
        assert sg2_since_zero == 0, "Expected SG2 to remain an incremental continuation after convergence"

        self.mark_test_step(
            "Verify the local CBL database and both SGWs (queried directly, bypassing the load balancer) agree on"
            " the full document set"
        )
        await compare_local_and_remote(
            db, sg1, ReplicatorType.PUSH_AND_PULL, bucket=db_name, collections=[_DEFAULT_COLLECTION]
        )
        await compare_local_and_remote(
            db, sg2, ReplicatorType.PUSH_AND_PULL, bucket=db_name, collections=[_DEFAULT_COLLECTION]
        )

        self.mark_test_step("Verify the SG1-to-SG2 ISGR link itself is still healthy")
        link_status = await sg1.get_isgr_status(db_name, _ISGR_REPLICATION_ID)
        assert link_status.get("status") != "error", f"ISGR link entered an error state: {link_status}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_isgr_pull_preserves_channel_set(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self._skip_if_unsupported(cblpytest)

        db_name = "db_isgr_lb_channels"
        channels = ["isgr_lb_channel_test"]
        user_name, user_password = "isgr_lb_channel_user", "pass"
        doc_id = "channel_set_doc"

        self.mark_test_step("Set up same-named DB + user on both SGWs, and a continuous bidirectional ISGR link")
        sg1, sg2 = await _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password)
        self.mark_test_step("Add one brand-new doc with an explicit channel assignment directly on SG2")
        await sg2.update_documents(
            db_name, [DocumentUpdateEntry(id=doc_id, revision=None, body={"channels": channels})]
        )

        self.mark_test_step("Wait for the doc to reach SG1 via ISGR")
        await _wait_for_propagation(sg1, db_name, [doc_id], link_owner=sg1)

        self.mark_test_step("Verify the doc is visible through a _changes call scoped to that channel on SG1")
        async with sg1.create_user_client(db_name, user_name, user_password, channels) as scoped_user:
            changes = await scoped_user.get_changes(db_name, request_plus=True)
            doc_ids = {entry.id for entry in changes.results}
            assert doc_id in doc_ids, f"Doc invisible on SG1's channel-scoped _changes feed despite no error: {doc_ids}"

        self.mark_test_step(
            "Pull the doc through a real CBL client pinned to SG1, and verify its channel assignment arrives intact"
        )
        db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
        repl_url = sg1.replication_url(db_name, cblpytest.load_balancers[1])
        replicator = await _pinned_pull(db, repl_url, user_name, user_password, _SG1_PIN)
        assert len(replicator.document_updates) > 0, "Expected the pull pinned to SG1 to transfer the doc"

        pulled = await db.get_document(DocumentEntry(_DEFAULT_COLLECTION, doc_id))
        assert pulled.body.get("channels") == channels, (
            f"Doc arrived at the CBL client with the wrong channel assignment: {pulled.body}"
        )
