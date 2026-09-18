import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.plugins.cluster_cleanup import delete_all_databases
from conftest import fake_sync_gateways

DeleteDatabase = Callable[[str], Coroutine[Any, Any, None]]


def _stub_cluster(
    monkeypatch: pytest.MonkeyPatch,
    sync_gateways: list[SyncGateway],
    served: list[list[str]],
    delete_database: DeleteDatabase,
) -> None:
    """
    Have each node report its own list of databases and delete them via delete_database.

    A delete removes the database from every node, the way deleting the config from the
    bucket makes the other nodes drop it on their next config re-read.  Rosmar is off, so
    no bucket dropping runs.
    """
    reported = [list(names) for names in served]

    for index, sg in enumerate(sync_gateways):

        async def get_all_databases_verbose(index: int = index) -> dict[str, Any]:
            return dict.fromkeys(reported[index], object())

        async def delete_and_forget(db_name: str) -> None:
            await delete_database(db_name)
            for names in reported:
                if db_name in names:
                    names.remove(db_name)

        monkeypatch.setattr(sg, "get_all_databases_verbose", get_all_databases_verbose)
        monkeypatch.setattr(sg, "_delete_database", delete_and_forget)
        # requests.get is patched out, so using_rosmar defaults to a truthy mock.
        monkeypatch.setattr(sg, "using_rosmar", False)


@pytest.mark.asyncio
async def test_delete_all_databases_deletes_each_database_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Sync Gateway keeps one registry document per bucket, so deleting the same database
    from every node at once makes those writes collide on it.
    """
    with fake_sync_gateways(3) as sync_gateways:
        deleted: list[str] = []

        async def delete_database(db_name: str) -> None:
            deleted.append(db_name)

        _stub_cluster(monkeypatch, list(sync_gateways), [["db1", "db2"]] * 3, delete_database)

        await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert sorted(deleted) == ["db1", "db2"]


@pytest.mark.asyncio
async def test_delete_all_databases_covers_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database that only one node learned about still has to be deleted."""
    with fake_sync_gateways(3) as sync_gateways:
        deleted: list[str] = []

        async def delete_database(db_name: str) -> None:
            deleted.append(db_name)

        _stub_cluster(monkeypatch, list(sync_gateways), [["db1"], [], ["db1", "db3"]], delete_database)

        await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert sorted(deleted) == ["db1", "db3"]


@pytest.mark.asyncio
async def test_delete_all_databases_fails_fast_and_unwinds_siblings(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The sibling must be cancelled and unwound before returning, or it runs on into the next
    test on the session-scoped loop.
    """
    with fake_sync_gateways(1) as sync_gateways:
        cancelled = asyncio.Event()

        async def delete_database(db_name: str) -> None:
            if db_name == "db_fails":
                raise RuntimeError("SGW returned 500")
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        _stub_cluster(monkeypatch, list(sync_gateways), [["db_fails", "db_slow"]], delete_database)

        with pytest.raises(BaseExceptionGroup) as raised:
            await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert cancelled.is_set(), "sibling was left running instead of being cancelled"
        # The original error survives the nesting, rather than flattening into a string.
        assert raised.value.subgroup(RuntimeError) is not None


@pytest.mark.asyncio
async def test_delete_all_databases_reports_every_simultaneous_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures that land together are all reported, not just the first one seen."""
    with fake_sync_gateways(3) as sync_gateways:

        async def delete_database(db_name: str) -> None:
            raise RuntimeError(f"SGW returned 500 for {db_name}")

        _stub_cluster(monkeypatch, list(sync_gateways), [["db1", "db2", "db3"], [], []], delete_database)

        with pytest.raises(BaseExceptionGroup) as raised:
            await delete_all_databases(SyncGatewayCluster(sync_gateways))

        assert len(raised.value.exceptions) == 3


@pytest.mark.asyncio
async def test_delete_all_databases_lets_outer_cancellation_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation of the caller is control flow, not a cleanup failure."""
    with fake_sync_gateways(1) as sync_gateways:

        async def delete_database(db_name: str) -> None:
            await asyncio.sleep(30)

        _stub_cluster(monkeypatch, list(sync_gateways), [["db"]], delete_database)

        task = asyncio.ensure_future(delete_all_databases(SyncGatewayCluster(sync_gateways)))
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
