from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from cbltest.api import couchbaseserver
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.globals import CBLPyTestGlobal
from conftest import fake_sync_gateways


@contextmanager
def fake_sync_gateway() -> Iterator[SyncGateway]:
    with fake_sync_gateways(1) as gateways:
        yield gateways[0]


class FakeCouchbaseServer(CouchbaseServer):
    """Test-only server: the real constructor opens a session to a host that is not there."""

    def __init__(self) -> None:
        pass

    def __str__(self) -> str:
        return "fake-cbs"

    async def create_bucket(self, name: str, num_replicas: int = 0, retries: int = 60, interval: float = 2.0) -> bool:
        return True

    async def wait_for_indexes_removed(self, bucket: str) -> None:
        return None


def cluster_that_times_out_on_create_database(
    monkeypatch: pytest.MonkeyPatch, sync_gateway: SyncGateway, cbs: CouchbaseServer, *, error: Exception
) -> CouchbaseCluster:
    """A cluster whose Sync Gateway side always raises `error` from the PUT phase of
    create_database, so tests can drive CouchbaseCluster.create_database's except-and-
    maybe-collect branch without a real timeout."""
    sync_gateway.using_rosmar = False
    cluster = CouchbaseCluster([sync_gateway], [cbs])

    async def _raise(db_name: str, config: DatabaseConfig) -> str | None:
        raise error

    monkeypatch.setattr(cluster.sync_gateway_cluster, "_put_database", _raise)
    return cluster


class TestCbcollectNeededOnDatabaseTimeout:
    """CouchbaseCluster.create_database: sets CBLPyTestGlobal.cbcollect_needed only for a
    TimeoutError, and only with a real Couchbase Server present -- CBG-5733 must not turn
    into 'collect on any test failure' again. Actual collection happens later, once, at
    session end (see test_cbcollect.py for run_cbcollects, the function the cbcollect_session
    fixture calls when this flag is set)."""

    def teardown_method(self) -> None:
        CBLPyTestGlobal.cbcollect_needed = False

    @pytest.mark.asyncio
    async def test_sets_flag_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cbs = FakeCouchbaseServer()
        with fake_sync_gateway() as sync_gateway:
            cluster = cluster_that_times_out_on_create_database(monkeypatch, sync_gateway, cbs, error=TimeoutError())

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is True, "a timeout with a real CBS present must flag for collection"

    @pytest.mark.asyncio
    async def test_does_not_set_flag_on_a_different_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cbs = FakeCouchbaseServer()
        with fake_sync_gateway() as sync_gateway:
            cluster = cluster_that_times_out_on_create_database(
                monkeypatch, sync_gateway, cbs, error=CblTestError("some unrelated failure")
            )

            with pytest.raises(CblTestError, match="some unrelated failure"):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, (
            "this must stay narrow to CBG-5733's timeout signature, not any create_database failure"
        )

    @pytest.mark.asyncio
    async def test_does_not_set_flag_on_post_put_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A timeout from wait_for_db_online -- after the PUT already succeeded -- must
        not trigger cbcollect; only a stuck PUT itself is CBG-5733's signature."""
        cbs = FakeCouchbaseServer()
        with fake_sync_gateway() as sync_gateway:
            sync_gateway.using_rosmar = False
            cluster = CouchbaseCluster([sync_gateway], [cbs])

            async def _put_ok(db_name: str, config: DatabaseConfig) -> str | None:
                return None

            async def _wait_times_out(db_name: str, version: str | None = None) -> None:
                raise TimeoutError()

            monkeypatch.setattr(cluster.sync_gateway_cluster, "_put_database", _put_ok)
            monkeypatch.setattr(cluster.sync_gateway_cluster, "wait_for_db_online", _wait_times_out)

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, (
            "a timeout after the PUT already succeeded is not CBG-5733's signature"
        )

    @pytest.mark.asyncio
    async def test_does_not_set_flag_when_using_rosmar_despite_configured_cbs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cluster can carry CBS entries in its topology while its Sync Gateway node is
        actually running against Rosmar (using_rosmar is read live per-node, independent of
        which CBS nodes are grouped into the cluster) -- Rosmar has no indexer to stall, so
        this must not flag for collection even though couchbase_servers is non-empty."""
        cbs = FakeCouchbaseServer()
        with fake_sync_gateway() as sync_gateway:
            sync_gateway.using_rosmar = True
            cluster = CouchbaseCluster([sync_gateway], [cbs])

            async def _raise(db_name: str, config: DatabaseConfig) -> str | None:
                raise TimeoutError()

            monkeypatch.setattr(cluster.sync_gateway_cluster, "_put_database", _raise)

            with pytest.raises(TimeoutError):
                await cluster.create_database("db", DatabaseConfig(bucket="a-bucket"))

        assert CBLPyTestGlobal.cbcollect_needed is False, (
            "Rosmar has no indexer to stall even if CBS entries happen to be configured"
        )


def test_cluster_without_couchbase_server() -> None:
    with fake_sync_gateway() as sync_gateway:
        sync_gateway.using_rosmar = False
        with pytest.raises(
            CblTestError,
            match="Couchbase Server must be provided if Sync Gateway",
        ):
            CouchbaseCluster([sync_gateway], [])

    with fake_sync_gateway() as sync_gateway:
        cluster = CouchbaseCluster([sync_gateway], [])

    assert len(cluster.couchbase_servers) == 0


def test_cluster_with_couchbase_server() -> None:
    cbs = couchbaseserver.CouchbaseServer(
        url="https://example.com",
        username="user",
        password="pass",
    )
    with fake_sync_gateway() as sync_gateway:
        cluster = CouchbaseCluster([sync_gateway], [cbs])
    assert cluster.couchbase_servers[0] is cbs


def test_cluster_with_multiple_sync_gateways() -> None:
    cbs = couchbaseserver.CouchbaseServer(
        url="https://example.com",
        username="user",
        password="pass",
    )
    with fake_sync_gateways(3) as sync_gateways:
        cluster = CouchbaseCluster(sync_gateways, [cbs])
        assert cluster.sync_gateways == sync_gateways
        assert isinstance(cluster.sync_gateway_cluster, SyncGatewayCluster)
        assert cluster.sync_gateway_cluster.sync_gateways == sync_gateways


def test_cluster_multiple_sync_gateways_requires_couchbase_server() -> None:
    with (
        fake_sync_gateways(2) as sync_gateways,
        pytest.raises(
            CblTestError,
            match="Couchbase Server must be provided when configuring multiple Sync Gateway nodes",
        ),
    ):
        CouchbaseCluster(sync_gateways, [])
