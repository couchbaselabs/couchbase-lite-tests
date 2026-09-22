from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from cbltest.api import couchbaseserver
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig, ScopeConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from conftest import fake_sync_gateways


@contextmanager
def fake_sync_gateway() -> Iterator[SyncGateway]:
    with fake_sync_gateways(1) as gateways:
        yield gateways[0]


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
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        cbs = couchbaseserver.CouchbaseServer(
            url="https://example.com",
            username="user",
            password="pass",
        )
    with fake_sync_gateway() as sync_gateway:
        cluster = CouchbaseCluster([sync_gateway], [cbs])
    assert cluster.couchbase_servers[0] is cbs


def test_cluster_with_multiple_sync_gateways() -> None:
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
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
def cluster_on_couchbase_server(monkeypatch: pytest.MonkeyPatch, kv_nodes: int) -> Iterator[CouchbaseCluster]:
    """A cluster whose Couchbase Server reports `kv_nodes` nodes and creates buckets for free."""
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        cbs = couchbaseserver.CouchbaseServer(url="https://example.com", username="user", password="pass")
    node = {"services": ["kv", "index", "n1ql"], "clusterMembership": "active", "status": "healthy"}
    monkeypatch.setattr(cbs, "_get_cluster_info", lambda: {"nodes": [node] * kv_nodes})
    monkeypatch.setattr(cbs, "create_bucket", lambda *args, **kwargs: False)
    with fake_sync_gateway() as sync_gateway:
        sync_gateway.using_rosmar = False
        cluster = CouchbaseCluster([sync_gateway], [cbs])
        monkeypatch.setattr(cluster, "create_collections", lambda config: None)
        yield cluster


async def created_config(
    monkeypatch: pytest.MonkeyPatch, kv_nodes: int, config: DatabaseConfig
) -> DatabaseConfig | None:
    """The config `create_database` ends up sending to Sync Gateway."""
    sent: list[DatabaseConfig] = []

    async def capture(db_name: str, config: DatabaseConfig) -> None:
        sent.append(config)

    with cluster_on_couchbase_server(monkeypatch, kv_nodes) as cluster:
        monkeypatch.setattr(cluster.sync_gateway_cluster, "create_database", capture)
        await cluster.create_database("db", config)
    return sent[0] if sent else None


SCOPES = {"_default": ScopeConfig(collections={"_default": {}})}


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
