from collections.abc import Awaitable, Callable

import pytest
from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from conftest import fake_sync_gateways


def test_round_robin_node_cycles_through_all_nodes() -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        picks = [cluster.round_robin_node for _ in range(7)]
        assert picks == [
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
            sync_gateways[1],
            sync_gateways[2],
            sync_gateways[0],
        ]


def test_round_robin_node_single_node() -> None:
    with fake_sync_gateways(1) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(3):
            assert cluster.round_robin_node is sync_gateways[0]


def test_random_node_returns_a_cluster_member() -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        for _ in range(20):
            assert cluster.random_node in sync_gateways


# What the faked writes return, so that the waits can be checked against it.
_SENTINEL = "config-sentinel"


def _record_node_calls(
    monkeypatch: pytest.MonkeyPatch, nodes: list[SyncGateway]
) -> tuple[list[tuple[str, int]], list[object]]:
    """Record the per-node calls the cluster helpers make, as (method name, node index),
    along with the sentinel every _wait_for_database_config call was handed."""
    calls: list[tuple[str, int]] = []
    awaited_sentinels: list[object] = []

    def recorder(name: str) -> Callable[..., Awaitable[str]]:
        async def fake(node: SyncGateway, db_name: str, *args: object, **kwargs: object) -> str:
            calls.append((name, next(i for i, n in enumerate(nodes) if n is node)))
            if name == "_wait_for_database_config":
                awaited_sentinels.append(args[0] if args else kwargs.get("sentinel"))
            return _SENTINEL

        return fake

    for name in (
        "_put_database",
        "_update_database_config",
        "_wait_for_database_config",
        "_wait_for_db_state_online",
    ):
        monkeypatch.setattr(SyncGateway, name, recorder(name))

    return calls, awaited_sentinels


@pytest.mark.asyncio
async def test_create_database_brings_every_node_online(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        calls, awaited_sentinels = _record_node_calls(monkeypatch, sync_gateways)

        await cluster.create_database("db1", DatabaseConfig(bucket="b1"))

    assert calls[0][0] == "_put_database"

    # Every node has to pick the config up on its own, and comes online in the background
    # afterwards, so both waits cover the whole cluster.
    assert sorted(calls[1:4]) == [("_wait_for_database_config", i) for i in range(3)]
    assert sorted(calls[4:]) == [("_wait_for_db_state_online", i) for i in range(3)]

    # Every node waits for the config the write returned, not just for any config.
    assert awaited_sentinels == [_SENTINEL] * 3


@pytest.mark.asyncio
async def test_update_database_config_brings_every_node_online(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_sync_gateways(2) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        calls, awaited_sentinels = _record_node_calls(monkeypatch, sync_gateways)

        await cluster.update_database_config("db1", DatabaseConfig(bucket="b1"))

    assert calls[0][0] == "_update_database_config"

    assert sorted(calls[1:3]) == [("_wait_for_database_config", i) for i in range(2)]
    assert sorted(calls[3:]) == [("_wait_for_db_state_online", i) for i in range(2)]

    assert awaited_sentinels == [_SENTINEL] * 2
