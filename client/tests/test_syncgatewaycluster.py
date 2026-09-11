import pytest
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import DatabaseConfig
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.globals import CBLPyTestGlobal
from conftest import fake_sync_gateways


def test_round_robin_node_cycles_through_all_nodes() -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        picks = [cluster.round_robin_node for _ in range(7)]
        assert picks == [
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
        ]


def test_round_robin_node_single_node() -> None:
    with fake_sync_gateways(1) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(3):
            assert cluster.round_robin_node is sync_gateways[0]


def test_random_node_returns_a_cluster_member() -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(20):
            assert cluster.random_node in sync_gateways


class TestCbcollectNeededOnDatabaseTimeout:
    """SyncGatewayCluster._put_database: sets CBLPyTestGlobal.cbcollect_needed only for a
    TimeoutError, and only when the cluster isn't using Rosmar (a cluster with using_rosmar
    false is always backed by at least one real Couchbase Server -- CouchbaseCluster.__init__
    enforces that for every cluster the framework builds, so no separate CBS-present check
    is needed here) -- CBG-5733 must not turn into 'collect on any test failure' again.

    This lives here, not in test_cluster.py, because the trigger itself lives in
    SyncGatewayCluster._put_database: it must fire for every caller of
    SyncGatewayCluster.create_database, not just CouchbaseCluster's own call site, since
    several tests (e.g. tests/QE/edge_server/test_changes_feed.py) call it directly.
    Actual collection happens later, once, at session end (see test_cbcollect.py for
    run_cbcollects, the function the cbcollect_session fixture calls when this flag is set).
    """

    def teardown_method(self) -> None:
        CBLPyTestGlobal.cbcollect_needed = False

    @pytest.mark.asyncio
    async def test_sets_flag_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with fake_sync_gateways(1) as sync_gateways:
            sync_gateways[0].using_rosmar = False
            cluster = SyncGatewayCluster(sync_gateways)

            async def _raise(db_name: str, config: DatabaseConfig) -> str | None:
                raise TimeoutError()

            monkeypatch.setattr(sync_gateways[0], "_put_database", _raise)

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is True, "a timeout with a real CBS present must flag for collection"

    @pytest.mark.asyncio
    async def test_does_not_set_flag_on_a_different_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with fake_sync_gateways(1) as sync_gateways:
            sync_gateways[0].using_rosmar = False
            cluster = SyncGatewayCluster(sync_gateways)

            async def _raise(db_name: str, config: DatabaseConfig) -> str | None:
                raise CblTestError("some unrelated failure")

            monkeypatch.setattr(sync_gateways[0], "_put_database", _raise)

            with pytest.raises(CblTestError, match="some unrelated failure"):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, (
            "this must stay narrow to CBG-5733's timeout signature, not any create_database failure"
        )

    @pytest.mark.asyncio
    async def test_does_not_set_flag_on_post_put_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A timeout from wait_for_db_online -- after the PUT already succeeded -- must
        not trigger cbcollect; only a stuck PUT itself is CBG-5733's signature."""
        with fake_sync_gateways(1) as sync_gateways:
            sync_gateways[0].using_rosmar = False
            cluster = SyncGatewayCluster(sync_gateways)

            async def _put_ok(db_name: str, config: DatabaseConfig) -> str | None:
                return None

            async def _wait_times_out(
                db_name: str, version: str | None = None, max_retries: int = 70, retry_delay: int = 1
            ) -> None:
                raise TimeoutError()

            monkeypatch.setattr(sync_gateways[0], "_put_database", _put_ok)
            monkeypatch.setattr(cluster, "wait_for_db_online", _wait_times_out)

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, (
            "a timeout after the PUT already succeeded is not CBG-5733's signature"
        )

    @pytest.mark.asyncio
    async def test_does_not_set_flag_when_using_rosmar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rosmar has no indexer to stall, so a PUT timeout must not flag for collection."""
        with fake_sync_gateways(1) as sync_gateways:
            sync_gateways[0].using_rosmar = True
            cluster = SyncGatewayCluster(sync_gateways)

            async def _raise(db_name: str, config: DatabaseConfig) -> str | None:
                raise TimeoutError()

            monkeypatch.setattr(sync_gateways[0], "_put_database", _raise)

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, "Rosmar has no indexer to stall"
