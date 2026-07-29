from contextlib import contextmanager
from unittest.mock import patch

import pytest
from cbltest.api import couchbaseserver
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblTestError
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from conftest import fake_sync_gateways


@contextmanager
def fake_sync_gateway():
    with fake_sync_gateways(1) as gateways:
        yield gateways[0]


def test_cloud_without_couchbase_server():
    with fake_sync_gateway() as sync_gateway:
        sync_gateway.using_rosmar = False
        with pytest.raises(
            CblTestError,
            match="Couchbase Server must be provided if Sync Gateway",
        ):
            CouchbaseCloud([sync_gateway], None)

    with fake_sync_gateway() as sync_gateway:
        cloud = CouchbaseCloud([sync_gateway], None)
    with pytest.raises(
        CblTestError,
        match="Couchbase Server is not available",
    ):
        _ = cloud.couchbase_server


def test_cloud_with_couchbase_server():
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        cbs = couchbaseserver.CouchbaseServer(
            url="https://example.com",
            username="user",
            password="pass",
        )
    with fake_sync_gateway() as sync_gateway:
        cloud = CouchbaseCloud([sync_gateway], cbs)
    assert cloud.couchbase_server is cbs


def test_cloud_with_multiple_sync_gateways():
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        cbs = couchbaseserver.CouchbaseServer(
            url="https://example.com",
            username="user",
            password="pass",
        )
    with fake_sync_gateways(3) as sync_gateways:
        cloud = CouchbaseCloud(sync_gateways, cbs)
        assert cloud.sync_gateways == sync_gateways
        assert isinstance(cloud.sync_gateway_cluster, SyncGatewayCluster)
        assert cloud.sync_gateway_cluster.sync_gateways == sync_gateways


def test_cloud_multiple_sync_gateways_requires_couchbase_server():
    with (
        fake_sync_gateways(2) as sync_gateways,
        pytest.raises(
            CblTestError,
            match="Couchbase Server must be provided when configuring multiple Sync Gateway nodes",
        ),
    ):
        CouchbaseCloud(sync_gateways, None)
