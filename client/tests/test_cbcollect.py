"""Tests for run_cbcollects, the best-effort multi-node collection the cbcollect_session
fixture runs at session end when CouchbaseCluster.create_database flagged a CBG-5733-shaped
timeout (see test_cluster.py for where that flag gets set)."""

import asyncio
from pathlib import Path

import pytest
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblTestError
from cbltest.plugins.cbcollect_fixture import run_cbcollects


class FakeCouchbaseServer(CouchbaseServer):
    """Test-only server: the real constructor opens a session to a host that is not there."""

    def __init__(self, hostname: str, barrier: asyncio.Barrier | None = None, fail: bool = False) -> None:
        self._hostname = hostname
        self._barrier = barrier
        self._fail = fail

    def __str__(self) -> str:
        return self._hostname

    async def collect_logs(self, output_dir: Path) -> Path:
        if self._barrier is not None:
            await self._barrier.wait()
        if self._fail:
            raise CblTestError(f"{self._hostname} is unreachable")

        return output_dir / f"cbcollect-{self._hostname}.zip"


def archives(directory: Path, *hostnames: str) -> list[Path]:
    return [directory / f"cbcollect-{hostname}.zip" for hostname in hostnames]


@pytest.mark.asyncio
async def test_every_node_is_collected_at_once(tmp_path: Path) -> None:
    # A barrier every node must reach: nothing is released until all three are in flight, so
    # collecting them one after another would hang here rather than pass slowly.
    barrier = asyncio.Barrier(3)
    servers = [FakeCouchbaseServer(f"cbs{index}.example.com", barrier) for index in range(3)]

    collected = await asyncio.wait_for(run_cbcollects(servers, tmp_path), timeout=10)

    assert collected == archives(tmp_path, "cbs0.example.com", "cbs1.example.com", "cbs2.example.com")


@pytest.mark.asyncio
async def test_a_node_that_fails_does_not_stop_the_others(tmp_path: Path) -> None:
    servers = [
        FakeCouchbaseServer("cbs0.example.com"),
        FakeCouchbaseServer("cbs1.example.com", fail=True),
        FakeCouchbaseServer("cbs2.example.com"),
    ]

    collected = await run_cbcollects(servers, tmp_path)

    assert collected == archives(tmp_path, "cbs0.example.com", "cbs2.example.com"), (
        "one unreachable host costs its own archive, not the whole collection"
    )


@pytest.mark.asyncio
async def test_every_node_failing_is_raised(tmp_path: Path) -> None:
    servers = [FakeCouchbaseServer(f"cbs{index}.example.com", fail=True) for index in range(2)]

    with pytest.raises(ExceptionGroup) as info:
        await run_cbcollects(servers, tmp_path)

    assert [str(e) for e in info.value.exceptions] == [
        "cbs0.example.com is unreachable",
        "cbs1.example.com is unreachable",
    ], "every node's failure is reported, not just the first"


@pytest.mark.asyncio
async def test_no_couchbase_servers_is_a_no_op(tmp_path: Path) -> None:
    assert await run_cbcollects([], tmp_path) == []
