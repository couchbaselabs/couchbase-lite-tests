from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from cbltest.api import couchbaseserver
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SyncGateway
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
