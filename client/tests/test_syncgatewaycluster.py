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


def _record_node_calls(monkeypatch: pytest.MonkeyPatch, nodes: list[SyncGateway]) -> list[tuple[str, int]]:
    """Record the per-node calls the cluster helpers make, as (method name, node index)."""
    calls: list[tuple[str, int]] = []

    def recorder(name: str) -> Callable[..., Awaitable[None]]:
        async def fake(node: SyncGateway, db_name: str, *args: object, **kwargs: object) -> None:
            calls.append((name, next(i for i, n in enumerate(nodes) if n is node)))

        return fake

    for name in (
        "_put_database",
        "_update_database_config",
        "_refresh_database_config",
        "_wait_for_db_state_online",
    ):
        monkeypatch.setattr(SyncGateway, name, recorder(name))

    return calls


@pytest.mark.asyncio
async def test_create_database_brings_every_node_online(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_sync_gateways(3) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        calls = _record_node_calls(monkeypatch, sync_gateways)

        await cluster.create_database("db1", DatabaseConfig(bucket="b1"))

    assert calls[0][0] == "_put_database"
    writer = calls[0][1]
    others = [i for i in range(3) if i != writer]

    # The writing node already has the config, so only the others re-read it, but every
    # node comes online in the background and so has to be waited on.
    assert sorted(calls[1:3]) == [("_refresh_database_config", i) for i in others]
    assert sorted(calls[3:]) == [("_wait_for_db_state_online", i) for i in range(3)]


@pytest.mark.asyncio
async def test_update_database_config_brings_every_node_online(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_sync_gateways(2) as sync_gateways:
        cluster = SyncGatewayCluster(sync_gateways)
        calls = _record_node_calls(monkeypatch, sync_gateways)

        await cluster.update_database_config("db1", DatabaseConfig(bucket="b1"))

    assert calls[0][0] == "_update_database_config"
    writer = calls[0][1]

    assert calls[1] == ("_refresh_database_config", 1 - writer)
    assert sorted(calls[2:]) == [("_wait_for_db_state_online", i) for i in range(2)]
