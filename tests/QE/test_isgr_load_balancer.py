import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
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
    Gives a test two independent backends, SG1 and SG2, with the same database and user, kept in sync by ISGR. Each
    lives in its own cluster because `create_database` applies one config to every node of a cluster. Returns only once
    both ISGR legs are up, since each leg moves the counters the tests measure when it first connects.
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

    # pushAndPull covers both directions; a second link started from SG2 would fight this one.
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
    # Channel-less, so no CBL user ever replicates them.
    for writer, reader, doc_id in ((sg1, sg2, "isgr_push_leg_up"), (sg2, sg1, "isgr_pull_leg_up")):
        await writer.update_documents(db_name, [DocumentUpdateEntry(id=doc_id, revision=None, body={})])
        await _wait_for_propagation(reader, db_name, [doc_id], link_owner=sg1)
    return sg1, sg2


async def _wait_for_propagation(
    secondary: SyncGateway,
    db_name: str,
    doc_ids: list[str],
    link_owner: SyncGateway,
) -> None:
    """Waits for `doc_ids` to reach `secondary` via ISGR, so a broken link fails with its status, not a bare timeout."""
    try:
        await secondary.wait_for_documents(db_name, doc_ids)
    except TimeoutError as e:
        status = await link_owner.get_isgr_status(db_name, _ISGR_REPLICATION_ID)
        raise AssertionError(f"{e} -- ISGR status on {link_owner.hostname}: {status}") from e


async def _assert_no_isgr_reconnect(link_owner: SyncGateway, db_name: str, connects_before: int) -> None:
    """Fails if the ISGR link reconnected, which can move the same counters a pinned CBL call is judged by."""
    connects_after = await link_owner.get_isgr_connect_attempts(db_name, _ISGR_REPLICATION_ID)
    assert connects_after == connects_before, (
        f"ISGR link on {link_owner.hostname} reconnected {connects_after - connects_before} time(s) during the pinned"
        " replication, so the counters read around it are unreliable"
    )


async def _pinned_replication(
    db: Database,
    repl_url: str,
    user_name: str,
    user_password: str,
    pin: dict[str, str],
    replicator_type: ReplicatorType,
) -> Replicator:
    """
    Runs one replication pinned to one backend. Repeated calls share one checkpoint ID across both backends, which is
    what these tests measure, so never pass `reset=True`.
    """
    replicator = Replicator(
        db,
        repl_url,
        replicator_type=replicator_type,
        continuous=False,
        authenticator=ReplicatorBasicAuthenticator(user_name, user_password),
        enable_document_listener=replicator_type == ReplicatorType.PULL,
        headers=pin,
    )
    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is None, (
        f"Pinned {replicator_type} ({pin}) failed: ({status.error.domain} / {status.error.code}) {status.error.message}"
    )
    return replicator


@pytest.mark.sgw
@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_load_balancers(2)
@pytest.mark.min_clusters(3)
class TestISGRLoadBalancer(CBLTestClass):
    async def _skip_if_unfixed_sgw(self, cblpytest: CBLPyTest) -> None:
        """Skips SGW without the ISGR channel-loss fix (CBG-5772 in 4.0.8, CBG-5773 in 4.1.2; 4.1.0.1 lacks it)."""
        await self.skip_if_sgw_not(
            cblpytest.clusters[1].sync_gateways[0],
            "!=4.0.0,!=4.0.1,!=4.0.2,!=4.0.3,!=4.0.4,!=4.0.5,!=4.0.6,!=4.0.7,!=4.1.0.*,!=4.1.1",
        )

    async def _skip_if_unpinnable(self, cblpytest: CBLPyTest) -> None:
        """Skips the JS test server, which can't send the X-Backend pin header, and SGW without the channel-loss fix."""
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS)
        await self._skip_if_unfixed_sgw(cblpytest)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_checkpoint_divergence_behind_load_balancer(self, cblpytest: CBLPyTest) -> None:
        await self._skip_if_unpinnable(cblpytest)

        db_name = "db_isgr_lb"
        channels = ["isgr_lb_test"]
        user_name, user_password = "isgr_lb_user", "pass"

        self.mark_test_step("Create the database and user on SG1 and SG2, and start the ISGR link")
        sg1, sg2 = await _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password)
        self.mark_test_step("Add a seed doc on SG1 and wait for it on SG2")
        await sg1.update_documents(
            db_name,
            [DocumentUpdateEntry(id="seed_doc", revision=None, body={"channels": channels})],
            wait_for_caching_feed=True,
        )
        await _wait_for_propagation(sg2, db_name, ["seed_doc"], link_owner=sg1)

        self.mark_test_step("Create an empty local database")
        db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
        repl_url = sg1.replication_url(db_name, cblpytest.load_balancers[1])

        async def pinned_pull(pin: dict[str, str], sg: SyncGateway, other: SyncGateway) -> tuple[int, int]:
            """Returns (docs transferred, `sg`'s since-zero delta) of a pull pinned to `sg`; fails if it hit `other`."""
            connects = await sg1.get_isgr_connect_attempts(db_name, _ISGR_REPLICATION_ID)
            before = await sg.get_pull_repl_since_zero_count(db_name)
            other_before = await other.get_pull_repl_since_zero_count(db_name)
            replicator = await _pinned_replication(db, repl_url, user_name, user_password, pin, ReplicatorType.PULL)
            await _assert_no_isgr_reconnect(sg1, db_name, connects)
            other_delta = await other.get_pull_repl_since_zero_count(db_name) - other_before
            assert other_delta == 0, (
                f"Pull pinned with {pin} moved {other.hostname}'s since-zero count by {other_delta}, so the pin"
                f" reached {other.hostname} instead of {sg.hostname}"
            )
            return len(replicator.document_updates), await sg.get_pull_repl_since_zero_count(db_name) - before

        self.mark_test_step("Pull pinned to SG1, then to SG2, the first contact with each")
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1, sg2)
        assert sg1_docs > 0, "Expected SG1's first-ever contact to transfer the seed doc"
        assert sg1_since_zero == 1, "Expected SG1's first-ever contact to start from since=0"
        _, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2, sg1)
        assert sg2_since_zero == 1, "Expected SG2's first-ever contact to also start from since=0"

        self.mark_test_step("Twice, pull pinned to SG1 then SG2 with no new writes")
        for _ in range(2):
            sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1, sg2)
            assert sg1_docs == 0, "Expected no redundant transfer"
            assert sg1_since_zero == 0, "Expected SG1 to continue, not restart from since=0"
            sg2_docs, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2, sg1)
            assert sg2_docs == 0, "Expected no redundant transfer"
            assert sg2_since_zero == 0, "Expected SG2 to continue, not restart from since=0"

        self.mark_test_step("Add a doc on SG1 and wait for it on SG2")
        await sg1.update_documents(
            db_name,
            [DocumentUpdateEntry(id="second_doc", revision=None, body={"channels": channels})],
            wait_for_caching_feed=True,
        )
        await _wait_for_propagation(sg2, db_name, ["second_doc"], link_owner=sg1)

        self.mark_test_step("Pull pinned to SG1, then to SG2, after the new write")
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1, sg2)
        assert sg1_docs > 0, "Expected SG1's next contact to transfer the new doc"
        assert sg1_since_zero == 0, "Expected SG1 to continue, not restart from since=0"
        _, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2, sg1)
        assert sg2_since_zero == 0, "Expected SG2 to continue, not restart from since=0"

        self.mark_test_step("Pull pinned to SG1 then SG2 once more")
        sg1_docs, sg1_since_zero = await pinned_pull(_SG1_PIN, sg1, sg2)
        assert sg1_docs == 0, "Expected no redundant transfer"
        assert sg1_since_zero == 0, "Expected SG1 to continue, not restart from since=0"
        sg2_docs, sg2_since_zero = await pinned_pull(_SG2_PIN, sg2, sg1)
        assert sg2_docs == 0, "Expected no redundant transfer"
        assert sg2_since_zero == 0, "Expected SG2 to continue, not restart from since=0"

        self.mark_test_step("Verify the local database matches SG1 and SG2 exactly")
        for sg in (sg1, sg2):
            await compare_local_and_remote(
                db, sg, ReplicatorType.PUSH_AND_PULL, db_name, [_DEFAULT_COLLECTION], doc_ids=["seed_doc", "second_doc"]
            )

        self.mark_test_step("Verify the ISGR link is not in an error state")
        link_status = await sg1.get_isgr_status(db_name, _ISGR_REPLICATION_ID)
        assert link_status.get("status") != "error", f"ISGR link entered an error state: {link_status}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_checkpoint_divergence_behind_load_balancer(self, cblpytest: CBLPyTest) -> None:
        await self._skip_if_unpinnable(cblpytest)

        db_name = "db_isgr_lb_push"
        channels = ["isgr_lb_push_test"]
        user_name, user_password = "isgr_lb_push_user", "pass"
        doc_ids = [f"push_doc_{i}" for i in range(1, 6)]
        new_doc_id = "push_doc_6"

        self.mark_test_step("Create the database and user on SG1 and SG2, and start the ISGR link")
        sg1, sg2 = await _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password)

        self.mark_test_step("Create an empty local database with 5 docs in the user's channel")
        db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
        async with db.batch_updater() as updater:
            for doc_id in doc_ids:
                updater.upsert_document(_DEFAULT_COLLECTION, doc_id, [{"channels": channels}])
        repl_url = sg1.replication_url(db_name, cblpytest.load_balancers[1])

        async def pinned_push(pin: dict[str, str], sg: SyncGateway) -> int:
            """
            Returns `sg`'s propose-count delta for one push pinned to `sg`. Only a push pinned to SG2 can prove where it
            went, because ISGR also raises SG2's count.
            """
            connects = await sg1.get_isgr_connect_attempts(db_name, _ISGR_REPLICATION_ID)
            sg1_before = await sg1.get_push_propose_change_count(db_name)
            sg2_before = await sg2.get_push_propose_change_count(db_name)
            await _pinned_replication(db, repl_url, user_name, user_password, pin, ReplicatorType.PUSH)
            await _assert_no_isgr_reconnect(sg1, db_name, connects)
            sg1_delta = await sg1.get_push_propose_change_count(db_name) - sg1_before
            if sg is sg1:
                return sg1_delta
            assert sg1_delta == 0, (
                f"Push pinned with {pin} moved {sg1.hostname}'s propose count by {sg1_delta}, so the pin reached"
                f" {sg1.hostname} instead of {sg2.hostname}"
            )
            return await sg2.get_push_propose_change_count(db_name) - sg2_before

        self.mark_test_step("Push pinned to SG1, the first contact, and wait for the docs on SG2")
        assert await pinned_push(_SG1_PIN, sg1) == 5, "Expected SG1's first-ever contact to propose all 5 local docs"
        await _wait_for_propagation(sg2, db_name, doc_ids, link_owner=sg1)

        self.mark_test_step("Push pinned to SG2, the first contact")
        assert await pinned_push(_SG2_PIN, sg2) == 5, "Expected SG2's first-ever contact to propose all 5 docs again"

        self.mark_test_step("Twice, push pinned to SG1 then SG2 with no new writes")
        for _ in range(2):
            assert await pinned_push(_SG1_PIN, sg1) == 0, "Expected SG1 to continue, not re-propose"
            assert await pinned_push(_SG2_PIN, sg2) == 0, "Expected SG2 to continue, not re-propose"

        self.mark_test_step("Add a local doc, and push pinned to SG1 then SG2")
        async with db.batch_updater() as updater:
            updater.upsert_document(_DEFAULT_COLLECTION, new_doc_id, [{"channels": channels}])
        assert await pinned_push(_SG1_PIN, sg1) == 1, "Expected SG1 to propose only the new doc"
        await _wait_for_propagation(sg2, db_name, [new_doc_id], link_owner=sg1)
        assert await pinned_push(_SG2_PIN, sg2) == 1, "Expected SG2 to propose only the new doc, not restart"

        self.mark_test_step("Verify the local database matches SG1 and SG2 exactly")
        for sg in (sg1, sg2):
            await compare_local_and_remote(
                db, sg, ReplicatorType.PUSH_AND_PULL, db_name, [_DEFAULT_COLLECTION], doc_ids=[*doc_ids, new_doc_id]
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_isgr_pull_preserves_channel_set(self, cblpytest: CBLPyTest) -> None:
        await self._skip_if_unfixed_sgw(cblpytest)

        db_name = "db_isgr_lb_channels"
        channels = ["isgr_lb_channel_test"]
        user_name, user_password = "isgr_lb_channel_user", "pass"
        doc_id = "channel_set_doc"

        self.mark_test_step("Create the database and user on SG1 and SG2, and start the ISGR link")
        sg1, sg2 = await _setup_isgr_pair(cblpytest, db_name, channels, user_name, user_password)
        self.mark_test_step("Add a new doc with a channel on SG2")
        await sg2.update_documents(
            db_name, [DocumentUpdateEntry(id=doc_id, revision=None, body={"channels": channels})]
        )

        self.mark_test_step("Wait for the doc on SG1")
        await _wait_for_propagation(sg1, db_name, [doc_id], link_owner=sg1)

        self.mark_test_step("Verify the channel-restricted user sees the doc on SG1's _changes feed")
        async with sg1.get_user_client(user_name, user_password) as scoped_user:
            changes = await scoped_user.get_changes(db_name, request_plus=True)
            doc_ids = {entry.id for entry in changes.results}
            assert doc_id in doc_ids, f"Doc invisible on SG1's channel-scoped _changes feed despite no error: {doc_ids}"

        self.mark_test_step("Pull the doc through CBL directly from SG1, and verify it transferred")
        db: Database = (await cblpytest.test_servers[0].create_and_reset_db([db_name]))[0]
        replicator = Replicator(
            db,
            sg1.replication_url(db_name),
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator(user_name, user_password),
            pinned_server_cert=sg1.tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Pull from SG1 failed: {status.error}"
        pulled = {update.document_id for update in replicator.document_updates}
        assert doc_id in pulled, f"Expected the pull from SG1 to transfer {doc_id}, got {pulled}"
