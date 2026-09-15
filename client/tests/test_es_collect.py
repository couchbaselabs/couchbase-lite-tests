"""Tests for run_es_collects, which pulls Edge Server logs when a session has failures."""

import asyncio
from pathlib import Path

import pytest
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblTestError
from cbltest.plugins.es_collect_fixture import run_es_collects


class FakeEdgeServerManager(EdgeServerManager):
    """Test-only manager: the real constructor opens a session to a host that is not there."""

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

        return output_dir / f"es-collect-{self._hostname}.tar.gz"


def archives(directory: Path, *hostnames: str) -> list[Path]:
    return [directory / f"es-collect-{hostname}.tar.gz" for hostname in hostnames]


@pytest.mark.asyncio
async def test_every_node_is_collected_at_once(tmp_path: Path) -> None:
    # A barrier every node must reach: nothing is released until all three are in flight, so
    # collecting them one after another would hang here rather than pass slowly.
    barrier = asyncio.Barrier(3)
    managers = [FakeEdgeServerManager(f"es{index}.example.com", barrier) for index in range(3)]

    collected = await asyncio.wait_for(run_es_collects(managers, tmp_path), timeout=10)

    assert collected == archives(tmp_path, "es0.example.com", "es1.example.com", "es2.example.com")


@pytest.mark.asyncio
async def test_a_node_that_fails_does_not_stop_the_others(tmp_path: Path) -> None:
    managers = [
        FakeEdgeServerManager("es0.example.com"),
        FakeEdgeServerManager("es1.example.com", fail=True),
        FakeEdgeServerManager("es2.example.com"),
    ]

    collected = await run_es_collects(managers, tmp_path)

    assert collected == archives(tmp_path, "es0.example.com", "es2.example.com"), (
        "one unreachable host costs its own archive, not the whole collection"
    )


@pytest.mark.asyncio
async def test_every_node_failing_is_raised(tmp_path: Path) -> None:
    managers = [FakeEdgeServerManager(f"es{index}.example.com", fail=True) for index in range(2)]

    with pytest.raises(ExceptionGroup) as info:
        await run_es_collects(managers, tmp_path)

    assert [str(e) for e in info.value.exceptions] == [
        "es0.example.com is unreachable",
        "es1.example.com is unreachable",
    ], "every node's failure is reported, not just the first"


@pytest.mark.asyncio
async def test_no_edge_servers_is_a_no_op(tmp_path: Path) -> None:
    assert await run_es_collects([], tmp_path) == []
