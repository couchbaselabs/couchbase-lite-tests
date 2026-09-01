import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.plugins.cluster_cleanup import delete_all_databases
from conftest import fake_sync_gateways

DeleteDatabase = Callable[[str], Coroutine[Any, Any, None]]


def _stub_node(
    monkeypatch: pytest.MonkeyPatch,
    sg: SyncGateway,
    db_names: list[str],
    delete_database: DeleteDatabase,
) -> None:
    """Have sg report db_names and delete them via delete_database, skipping Rosmar buckets."""

    async def get_all_databases_verbose() -> dict[str, Any]:
        return dict.fromkeys(db_names, object())

    monkeypatch.setattr(sg, "get_all_databases_verbose", get_all_databases_verbose)
    monkeypatch.setattr(sg, "_delete_database", delete_database)
    # requests.get is patched out, so using_rosmar defaults to a truthy mock.
    monkeypatch.setattr(sg, "using_rosmar", False)


@pytest.mark.asyncio
async def test_delete_all_databases_covers_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node that never learned about a database is not covered by deleting it elsewhere."""
    with fake_sync_gateways(2) as sync_gateways:
        deleted: list[tuple[int, str]] = []

        for index, sg in enumerate(sync_gateways):

            async def delete_database(db_name: str, index: int = index) -> None:
                deleted.append((index, db_name))

            _stub_node(monkeypatch, sg, ["db1", "db2"], delete_database)

        await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert sorted(deleted) == [(0, "db1"), (0, "db2"), (1, "db1"), (1, "db2")]


@pytest.mark.asyncio
async def test_delete_all_databases_fails_fast_and_unwinds_siblings(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The sibling must be cancelled and unwound before returning, or it runs on into the next
    test on the session-scoped loop.
    """
    with fake_sync_gateways(2) as sync_gateways:
        failing, slow = sync_gateways
        cancelled = asyncio.Event()

        async def delete_and_fail(db_name: str) -> None:
            raise RuntimeError("SGW returned 500")

        async def delete_slowly(db_name: str) -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        _stub_node(monkeypatch, failing, ["db"], delete_and_fail)
        _stub_node(monkeypatch, slow, ["db"], delete_slowly)

        with pytest.raises(BaseExceptionGroup) as raised:
            await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert cancelled.is_set(), "sibling was left running instead of being cancelled"
        # The original error survives the nesting, rather than flattening into a string.
        assert raised.value.subgroup(RuntimeError) is not None


@pytest.mark.asyncio
async def test_delete_all_databases_reports_every_simultaneous_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures that land together are all reported, not just the first one seen."""
    with fake_sync_gateways(3) as sync_gateways:
        for index, sg in enumerate(sync_gateways):

            async def delete_and_fail(db_name: str, index: int = index) -> None:
                raise RuntimeError(f"SGW {index} returned 500")

            _stub_node(monkeypatch, sg, ["db"], delete_and_fail)

        with pytest.raises(BaseExceptionGroup) as raised:
            await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert len(raised.value.exceptions) == 3


@pytest.mark.asyncio
async def test_delete_all_databases_lets_outer_cancellation_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation of the caller is control flow, not a cleanup failure."""
    with fake_sync_gateways(1) as sync_gateways:

        async def delete_slowly(db_name: str) -> None:
            await asyncio.sleep(30)

        _stub_node(monkeypatch, sync_gateways[0], ["db"], delete_slowly)

        task = asyncio.ensure_future(delete_all_databases(SyncGatewayCluster(sync_gateways)))
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
