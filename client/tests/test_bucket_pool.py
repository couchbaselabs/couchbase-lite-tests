import asyncio
from typing import cast

import pytest
from cbltest.api.couchbaseserver import BucketPool, CouchbaseServer


class FakeServer:
    """A stand-in for CouchbaseServer that records what the pool asks it to do."""

    def __init__(self, existing: list[str] | None = None) -> None:
        self.buckets: list[str] = list(existing or [])
        self.created: list[str] = []
        self.deleted: list[str] = []

    async def get_bucket_names(self) -> list[str]:
        return list(self.buckets)

    async def _create_bucket(self, name: str, num_replicas: int | None, retries: int, interval: float) -> bool:
        # Yield as a real cluster call would, so concurrent callers can interleave.
        await asyncio.sleep(0)
        if name in self.buckets:
            return False
        self.buckets.append(name)
        self.created.append(name)
        return True

    def delete_bucket(self, name: str) -> None:
        self.buckets.remove(name)
        self.deleted.append(name)

    async def wait_for_bucket_deleted(self, name: str) -> None:
        pass


def make_pool(server: FakeServer, max_buckets: int = 3) -> BucketPool:
    return BucketPool(cast(CouchbaseServer, server), max_buckets=max_buckets)


@pytest.mark.asyncio
async def test_reuses_an_existing_bucket() -> None:
    """A second request for the same bucket must not recreate it."""
    server = FakeServer()
    pool = make_pool(server)

    assert await pool.create_bucket("data-bucket") is True
    assert await pool.create_bucket("data-bucket") is False

    assert server.created == ["data-bucket"]
    assert server.deleted == []


@pytest.mark.asyncio
async def test_evicts_the_least_recently_used_bucket_when_full() -> None:
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        await pool.create_bucket(name)
    await pool.create_bucket("fourth")

    assert server.deleted == ["first"]
    assert pool.bucket_names == ["second", "third", "fourth"]


@pytest.mark.asyncio
async def test_reuse_moves_a_bucket_out_of_the_firing_line() -> None:
    """A bucket every test reuses must outlive one that has gone untouched."""
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        await pool.create_bucket(name)
    await pool.create_bucket("first")
    await pool.create_bucket("fourth")

    assert server.deleted == ["second"]
    assert pool.bucket_names == ["third", "first", "fourth"]


@pytest.mark.asyncio
async def test_adopted_buckets_are_evicted_first() -> None:
    """
    Buckets left behind by an interrupted run must not push the cluster over its cap, and
    they are the least valuable thing to keep.
    """
    server = FakeServer(existing=["leftover"])
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second"]:
        await pool.create_bucket(name)
    await pool.create_bucket("third")

    assert server.deleted == ["leftover"]
    assert pool.bucket_names == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_forgets_buckets_deleted_outside_the_pool() -> None:
    """A bucket a test deleted itself must not count against the cap."""
    server = FakeServer()
    pool = make_pool(server, max_buckets=3)

    for name in ["first", "second", "third"]:
        await pool.create_bucket(name)
    server.delete_bucket("first")
    server.deleted.clear()

    await pool.create_bucket("fourth")

    assert server.deleted == []
    assert pool.bucket_names == ["second", "third", "fourth"]


@pytest.mark.asyncio
async def test_concurrent_requests_stay_under_the_cap() -> None:
    server = FakeServer()
    pool = make_pool(server, max_buckets=2)

    await asyncio.gather(*(pool.create_bucket(name) for name in ["first", "second", "third", "fourth"]))

    assert len(server.buckets) == 2
    assert pool.bucket_names == ["third", "fourth"]


def test_rejects_a_pool_that_can_hold_nothing() -> None:
    with pytest.raises(ValueError):
        make_pool(FakeServer(), max_buckets=0)
