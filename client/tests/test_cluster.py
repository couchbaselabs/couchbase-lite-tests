from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from cbltest import CBLPyTest
from cbltest.api import couchbaseserver
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig, ScopeConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.configparser import ParsedConfig
from cbltest.requests import RequestFactory
from conftest import fake_sync_gateways, set_using_rosmar

SCOPES = {"_default": ScopeConfig(collections={"_default": {}})}


@contextmanager
def fake_sync_gateway() -> Iterator[SyncGateway]:
    with fake_sync_gateways(1) as gateways:
        yield gateways[0]


@pytest.mark.asyncio
async def test_cluster_without_couchbase_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a Couchbase Server, Sync Gateway gets the database with no bucket work first."""
    sent: list[DatabaseConfig] = []

    async def capture(db_name: str, config: DatabaseConfig) -> None:
        sent.append(config)

    config = DatabaseConfig(bucket="data-bucket", scopes=SCOPES)
    with fake_sync_gateway() as sync_gateway:
        set_using_rosmar(sync_gateway, True)
        cluster = CouchbaseCluster([sync_gateway], [])
        monkeypatch.setattr(cluster.sync_gateway_cluster, "create_database", capture)
        await cluster.create_database("db", config)

    assert len(cluster.couchbase_servers) == 0
    assert sent == [config]


def test_cluster_with_couchbase_server() -> None:
    with (
        patch("cbltest.api.couchbaseserver.Cluster", autospec=True),
        patch("cbltest.api.couchbaseserver.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.couchbaseserver.Shell2HttpClient", autospec=True),
    ):
        cbs = couchbaseserver.CouchbaseServer(
            url="https://example.com",
            username="user",
            password="pass",
        )
    with fake_sync_gateway() as sync_gateway:
        cluster = CouchbaseCluster([sync_gateway], [cbs])
    assert cluster.couchbase_servers[0] is cbs


def test_cluster_with_multiple_sync_gateways() -> None:
    with (
        patch("cbltest.api.couchbaseserver.Cluster", autospec=True),
        patch("cbltest.api.couchbaseserver.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.couchbaseserver.Shell2HttpClient", autospec=True),
    ):
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


@contextmanager
def cluster_on_couchbase_server(
    monkeypatch: pytest.MonkeyPatch, kv_nodes: int, rosmar: bool = False
) -> Iterator[CouchbaseCluster]:
    """A cluster whose Couchbase Server reports `kv_nodes` nodes and creates buckets for free."""
    with (
        patch("cbltest.api.couchbaseserver.Cluster", autospec=True),
        patch("cbltest.api.couchbaseserver.AsyncHTTPClient", autospec=True),
        patch("cbltest.api.couchbaseserver.Shell2HttpClient", autospec=True),
    ):
        cbs = couchbaseserver.CouchbaseServer(url="https://example.com", username="user", password="pass")
    node = {"services": ["kv", "index", "n1ql"], "clusterMembership": "active", "status": "healthy"}

    async def cluster_info() -> dict[str, Any]:
        return {"nodes": [node] * kv_nodes}

    async def create_bucket(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(cbs, "_get_cluster_info", cluster_info)
    monkeypatch.setattr(cbs, "create_bucket", create_bucket)
    with fake_sync_gateway() as sync_gateway:
        set_using_rosmar(sync_gateway, rosmar)
        cluster = CouchbaseCluster([sync_gateway], [cbs])
        monkeypatch.setattr(cluster, "create_collections", lambda config: None)
        yield cluster


async def created_config(
    monkeypatch: pytest.MonkeyPatch, kv_nodes: int, config: DatabaseConfig, rosmar: bool = False
) -> DatabaseConfig | None:
    """The config `create_database` ends up sending to Sync Gateway."""
    sent: list[DatabaseConfig] = []

    async def capture(db_name: str, config: DatabaseConfig) -> None:
        sent.append(config)

    with cluster_on_couchbase_server(monkeypatch, kv_nodes, rosmar) as cluster:
        monkeypatch.setattr(cluster.sync_gateway_cluster, "create_database", capture)
        await cluster.create_database("db", config)
    return sent[0] if sent else None


@pytest.mark.asyncio
async def test_rosmar_skips_a_configured_couchbase_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rosmar makes its own buckets, so a Couchbase Server in the config gets no bucket work."""
    config = DatabaseConfig(bucket="data-bucket", scopes=SCOPES)
    assert await created_config(monkeypatch, 2, config, rosmar=True) == config


@pytest.mark.asyncio
async def test_index_replicas_follow_the_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    config = await created_config(monkeypatch, 2, DatabaseConfig(bucket="data-bucket", scopes=SCOPES))
    assert config is not None and config.index is not None
    assert config.index.num_replicas == 1


@pytest.mark.asyncio
async def test_single_node_cluster_gets_no_index_replica(monkeypatch: pytest.MonkeyPatch) -> None:
    config = await created_config(monkeypatch, 1, DatabaseConfig(bucket="data-bucket", scopes=SCOPES))
    assert config is not None and config.index is not None
    assert config.index.num_replicas == 0


@pytest.mark.asyncio
async def test_a_stated_index_replica_count_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    stated = DatabaseConfig(bucket="data-bucket", scopes=SCOPES, index=IndexConfig(num_replicas=0))
    config = await created_config(monkeypatch, 2, stated)
    assert config is not None and config.index is not None
    assert config.index.num_replicas == 0


@pytest.mark.asyncio
async def test_the_deprecated_field_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sync Gateway rejects a config that sets both, so one using the old field gets no index."""
    legacy = DatabaseConfig(bucket="data-bucket", scopes=SCOPES, num_index_replicas=0)
    config = await created_config(monkeypatch, 2, legacy)
    assert config is not None
    assert config.index is None
    assert config.num_index_replicas == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("server", ["couchbases://cbs.example.com", "rosmar:///tmp/rosmar"])
async def test_create_needs_couchbase_server_unless_rosmar(monkeypatch: pytest.MonkeyPatch, server: str) -> None:
    """A config with no Couchbase Server is only valid when Sync Gateway runs on Rosmar."""

    async def get_config(*args: Any, **kwargs: Any) -> dict:
        return {"bootstrap": {"server": server}}

    async def start(self: RequestFactory) -> None:
        raise _Started()

    monkeypatch.setattr(SyncGateway, "_send_request", get_config)
    monkeypatch.setattr(RequestFactory, "start", start)
    config = ParsedConfig({"sync-gateways": [{"hostname": "sgw.example.com"}]})
    expected = (
        pytest.raises(_Started)
        if server.startswith("rosmar")
        else pytest.raises(CblTestError, match="Couchbase Server must be provided if Sync Gateway")
    )
    with fake_sync_gateways(0), expected:
        await CBLPyTest.create(config)


class _Started(Exception):
    """Raised in place of starting the request factory, once create() is past validation."""
