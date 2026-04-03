from contextlib import contextmanager
from unittest.mock import patch

import pytest
from cbltest.api import couchbaseserver, syncgateway
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblTestError


@contextmanager
def fake_sync_gateway():
    with (
        patch("cbltest.api.syncgateway.ClientSession", autospec=True),
        patch("cbltest.api.syncgateway.requests.get", autospec=True),
    ):
        yield syncgateway.SyncGateway(
            url="https://example.com",
            username="user",
            password="pass",
        )


def test_cloud_without_couchbase_server():
    with fake_sync_gateway() as sync_gateway:
        sync_gateway.using_rosmar = False
        with pytest.raises(
            CblTestError,
            match="Couchbase Server must be provided if Sync Gateway",
        ):
            CouchbaseCloud(sync_gateway, None)

    with fake_sync_gateway() as sync_gateway:
        cloud = CouchbaseCloud(sync_gateway, None)
    with pytest.raises(
        CblTestError,
        match="Couchbase Server is not available",
    ):
        cloud.couchbase_server


def test_cloud_with_couchbase_server():
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        cbs = couchbaseserver.CouchbaseServer(
            url="https://example.com",
            username="user",
            password="pass",
        )
    with fake_sync_gateway() as sync_gateway:
        cloud = CouchbaseCloud(sync_gateway, cbs)
    assert cloud.couchbase_server is cbs
