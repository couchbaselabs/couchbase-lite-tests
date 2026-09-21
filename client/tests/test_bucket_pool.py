from typing import cast

import pytest
from cbltest.api.couchbaseserver import BucketPool, CouchbaseServer


class FakeServer:
    """A stand-in for CouchbaseServer that records what the pool asks it to do."""

    def __init__(self, existing: list[str] | None = None) -> None:
        self.buckets: list[str] = list(existing or [])
        self.created: list[str] = []
        self.deleted: list[str] = []

    def get_bucket_names(self) -> list[str]:
        return list(self.buckets)

    def _create_bucket(self, name: str, num_replicas: int, retries: int, interval: float) -> bool:
        if name in self.buckets:
            return False
        self.buckets.append(name)
        self.created.append(name)
        return True

    def delete_bucket(self, name: str) -> None:
        self.buckets.remove(name)
        self.deleted.append(name)

    def _block_until_bucket_deleted(self, name: str) -> None:
        pass


def make_pool(server: FakeServer, max_buckets: int = 3) -> BucketPool:
    return BucketPool(cast(CouchbaseServer, server), max_buckets=max_buckets)


def test_reuses_an_existing_bucket() -> None:
    """A second request for the same bucket must not recreate it."""
    server = FakeServer()
    pool = make_pool(server)

    assert pool.create_bucket("data-bucket") is True
    assert pool.create_bucket("data-bucket") is False

    assert server.created == ["data-bucket"]
    assert server.deleted == []


def test_evicts_the_least_recently_used_bucket_when_full() -> None:
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        pool.create_bucket(name)
    pool.create_bucket("fourth")

    assert server.deleted == ["first"]
    assert pool.bucket_names == ["second", "third", "fourth"]


def test_reuse_moves_a_bucket_out_of_the_firing_line() -> None:
    """A bucket every test reuses must outlive one that has gone untouched."""
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        pool.create_bucket(name)
    pool.create_bucket("first")
    pool.create_bucket("fourth")

    assert server.deleted == ["second"]
    assert pool.bucket_names == ["third", "first", "fourth"]


def test_adopted_buckets_are_evicted_first() -> None:
    """
    Buckets left behind by an interrupted run must not push the cluster over its cap, and
    they are the least valuable thing to keep.
    """
    server = FakeServer(existing=["leftover"])
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second"]:
        pool.create_bucket(name)
    pool.create_bucket("third")

    assert server.deleted == ["leftover"]
    assert pool.bucket_names == ["first", "second", "third"]


def test_forgets_buckets_deleted_outside_the_pool() -> None:
    """A bucket a test deleted itself must not count against the cap."""
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        pool.create_bucket(name)
    server.delete_bucket("first")
    server.deleted.clear()

    pool.create_bucket("fourth")

    assert server.deleted == []
    assert pool.bucket_names == ["second", "third", "fourth"]


def test_rejects_a_pool_that_can_hold_nothing() -> None:
    with pytest.raises(ValueError):
        make_pool(FakeServer(), max_buckets=0)
