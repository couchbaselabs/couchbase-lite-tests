"""
Cover both values of ``--bucketpool``: a bucket is either dropped between tests, or emptied
in place and kept.
"""

from typing import cast
from unittest.mock import patch

import pytest
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.couchbaseserver import MAX_BUCKETS, BucketCleanupMode, BucketPool, CouchbaseServer
from cbltest.plugins.cluster_cleanup import clean_all_buckets

ALL_MODES = [BucketCleanupMode.DELETE, BucketCleanupMode.PURGE]


class FakeCluster:
    """A stand-in for CouchbaseCluster holding a single node."""

    def __init__(self, server: CouchbaseServer) -> None:
        self.couchbase_servers = [server]


class Recorder:
    """Replaces the bucket operations of a CouchbaseServer so none of them reach a cluster."""

    def __init__(self, server: CouchbaseServer, monkeypatch: pytest.MonkeyPatch) -> None:
        self.buckets: list[str] = []
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.purged: list[str] = []

        monkeypatch.setattr(server, "_create_bucket", self._create_bucket)
        monkeypatch.setattr(server, "delete_bucket", self._delete_bucket)
        monkeypatch.setattr(server, "purge_bucket", self._purge_bucket)
        monkeypatch.setattr(server, "wait_for_bucket_deleted", self._wait_for_bucket_deleted)
        monkeypatch.setattr(server, "_block_until_bucket_deleted", lambda name, **kwargs: None)
        monkeypatch.setattr(server, "get_bucket_names", lambda: list(self.buckets))

    def _create_bucket(self, name: str, num_replicas: int = 0, retries: int = 60, interval: float = 2.0) -> bool:
        self.created.append(name)
        if name in self.buckets:
            return False
        self.buckets.append(name)
        return True

    def _delete_bucket(self, name: str) -> None:
        self.deleted.append(name)
        if name in self.buckets:
            self.buckets.remove(name)

    async def _purge_bucket(self, name: str, timeout: float = 120.0) -> str:
        self.purged.append(name)
        return f"purged {name}"

    async def _wait_for_bucket_deleted(self, name: str, max_retries: int = 30, retry_delay: float = 2.0) -> None:
        pass


def make_server(mode: BucketCleanupMode, monkeypatch: pytest.MonkeyPatch) -> tuple[CouchbaseServer, Recorder]:
    with patch("cbltest.api.couchbaseserver.Cluster", autospec=True):
        server = CouchbaseServer("cbs.example.com", "user", "pass", mode)
    return server, Recorder(server, monkeypatch)


@pytest.mark.parametrize("mode", ALL_MODES)
def test_only_purging_needs_a_pool(mode: BucketCleanupMode, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deleting a bucket between tests leaves nothing to reuse, so nothing needs capping."""
    server, _ = make_server(mode, monkeypatch)

    if mode is BucketCleanupMode.PURGE:
        assert isinstance(server.bucket_pool, BucketPool)
    else:
        assert server.bucket_pool is None


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.asyncio
async def test_clean_bucket_follows_the_mode(mode: BucketCleanupMode, monkeypatch: pytest.MonkeyPatch) -> None:
    server, recorder = make_server(mode, monkeypatch)

    await server.clean_bucket("data-bucket")

    if mode is BucketCleanupMode.PURGE:
        assert (recorder.purged, recorder.deleted) == (["data-bucket"], [])
    else:
        assert (recorder.purged, recorder.deleted) == ([], ["data-bucket"])


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.asyncio
async def test_cleanup_empties_every_bucket(mode: BucketCleanupMode, monkeypatch: pytest.MonkeyPatch) -> None:
    server, recorder = make_server(mode, monkeypatch)
    server.create_bucket("first")
    server.create_bucket("second")

    await clean_all_buckets(cast(CouchbaseCluster, FakeCluster(server)))

    emptied = recorder.purged if mode is BucketCleanupMode.PURGE else recorder.deleted
    assert sorted(emptied) == ["first", "second"]


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.asyncio
async def test_only_purging_caps_the_bucket_count(mode: BucketCleanupMode, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Purged buckets outlive the test that made them, so the pool evicts the least recently
    used one to stay under the cap.  Deleted buckets are already gone, so nothing is evicted.
    """
    server, recorder = make_server(mode, monkeypatch)

    for index in range(MAX_BUCKETS + 1):
        server.create_bucket(f"bucket-{index}")

    assert recorder.deleted == (["bucket-0"] if mode is BucketCleanupMode.PURGE else [])
