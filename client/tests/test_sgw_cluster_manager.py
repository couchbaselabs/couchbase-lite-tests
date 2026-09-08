"""Tests for the Sync Gateway managers and the sg_cluster_manager fixture that owns them."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.plugins.sgw_cluster_manager import (
    SyncGatewayClusterManager,
    SyncGatewayManager,
    sg_cluster_manager,
)
from conftest import fake_sync_gateways

SidecarCall = tuple[str, str, str | None]


class _FakeCBLPyTest:
    """Stands in for CBLPyTest, which the fixture only uses to reach the cluster."""

    def __init__(self, cluster: SyncGatewayCluster) -> None:
        self.sync_gateway_cluster = cluster


async def _open_fixture(cblpytest: Any) -> tuple[Any, SyncGatewayClusterManager]:
    """Run the fixture's setup the way pytest would, returning the generator and what it yielded."""
    generator = sg_cluster_manager.__wrapped__(cblpytest)  # ty: ignore[unresolved-attribute]
    return generator, await anext(generator)


async def _close_fixture(generator: Any) -> None:
    """Run the fixture's teardown and assert it finishes rather than yielding again."""
    with pytest.raises(StopAsyncIteration):
        await anext(generator)


@asynccontextmanager
async def _manager_for(sync_gateways: list[SyncGateway]) -> AsyncIterator[SyncGatewayClusterManager]:
    """
    A cluster manager over the given nodes, built and torn down the only way there is.

    Leaving the block runs the fixture's teardown, which is what closes the per-node
    sidecar sessions, so a test that asserts on teardown does so after the block.
    """
    generator, manager = await _open_fixture(_FakeCBLPyTest(SyncGatewayCluster(sync_gateways)))
    try:
        yield manager
    finally:
        await _close_fixture(generator)


def _stub_sidecar(monkeypatch: pytest.MonkeyPatch, manager: SyncGatewayClusterManager) -> list[SidecarCall]:
    """
    Record what each node manager sends to its sidecar, and treat the node's REST API as
    immediately ready, so nothing reaches the network.
    """
    calls: list[SidecarCall] = []

    for index, node in enumerate(manager.nodes):

        async def _call_sidecar(
            method: str, path: str, data: str | None = None, timeout: int = 120, index: int = index
        ) -> None:
            calls.append((f"{index}:{method}", path, data))

        monkeypatch.setattr(node, "_call_sidecar", _call_sidecar)

    return calls


def _stub_node_queries(
    monkeypatch: pytest.MonkeyPatch, sync_gateways: list[SyncGateway], serving: bool = False
) -> None:
    """Answer the node-level queries the managers make, without touching the network."""
    for sg in sync_gateways:

        async def wait_for_rest_api() -> None:
            return None

        async def is_serving(serving: bool = serving) -> bool:
            return serving

        monkeypatch.setattr(sg, "wait_for_rest_api", wait_for_rest_api)
        monkeypatch.setattr(sg, "is_serving", is_serving)


@pytest.mark.parametrize("manager_class", [SyncGatewayClusterManager, SyncGatewayManager])
def test_managers_cannot_be_constructed_outside_the_fixture(manager_class: type) -> None:
    """The fixture is what guarantees the reset, so it must be the only way in."""
    with fake_sync_gateways(2) as sync_gateways:
        target = SyncGatewayCluster(sync_gateways) if manager_class is SyncGatewayClusterManager else sync_gateways[0]
        with pytest.raises(CblTestError, match="sg_cluster_manager fixture"):
            manager_class(target)


@pytest.mark.asyncio
async def test_restart_posts_the_config_and_waits_for_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """The config name is the request body, and the restart is not done until the API answers."""
    with fake_sync_gateways(1) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)
        waited: list[bool] = []

        async def wait_for_rest_api() -> None:
            waited.append(True)

        monkeypatch.setattr(sync_gateways[0], "wait_for_rest_api", wait_for_rest_api)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.nodes[0].restart_with_config("bootstrap-alternate")

            assert calls == [("0:post", "/restart-sgw", "bootstrap-alternate")]
            assert waited == [True], "a restart that has not come back up is not finished"


@pytest.mark.asyncio
async def test_upload_certificate_sends_name_then_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sidecar's protocol is the cert name on the first line, content after it."""
    with fake_sync_gateways(1) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.nodes[0].upload_certificate(b"-----BEGIN CERTIFICATE-----", "ca.pem")

            assert calls == [("0:post", "/upload-cert", "ca.pem\n-----BEGIN CERTIFICATE-----")]


@pytest.mark.asyncio
async def test_start_skips_a_node_that_is_already_serving(monkeypatch: pytest.MonkeyPatch) -> None:
    with fake_sync_gateways(1) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways, serving=True)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.nodes[0].start()

            assert calls == []


@pytest.mark.asyncio
async def test_restart_with_config_restarts_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaving a node on the previous config is what CBG-5790 was: every node must restart."""
    with fake_sync_gateways(3) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.restart_with_config("bootstrap-alternate")

            assert sorted(calls) == [
                ("0:post", "/restart-sgw", "bootstrap-alternate"),
                ("1:post", "/restart-sgw", "bootstrap-alternate"),
                ("2:post", "/restart-sgw", "bootstrap-alternate"),
            ]


@pytest.mark.asyncio
async def test_upload_certificate_reaches_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node without the certificate cannot load a config that points at it."""
    with fake_sync_gateways(3) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.upload_certificate(b"cert", "ca.pem")

            assert sorted(call[0] for call in calls) == ["0:post", "1:post", "2:post"]
            assert {call[1] for call in calls} == {"/upload-cert"}


@pytest.mark.asyncio
async def test_nodes_are_addressable_individually(monkeypatch: pytest.MonkeyPatch) -> None:
    """Taking one node out is the whole point of the per-node manager; the others stay up."""
    with fake_sync_gateways(3) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            assert len(manager.nodes) == len(sync_gateways)
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.nodes[1].stop()
            await manager.nodes[1].start()

            assert calls == [
                ("1:get", "/stop-sgw", None),
                ("1:get", "/start-sgw?config=bootstrap", None),
            ]


@pytest.mark.parametrize(
    ("node_support", "expected"),
    [
        ([True, True, True], True),
        ([False, False], False),
    ],
)
@pytest.mark.asyncio
async def test_has_shell2http_sidecar_reports_the_whole_cluster(
    monkeypatch: pytest.MonkeyPatch, node_support: list[bool], expected: bool
) -> None:
    """Every node has the sidecar or none of them do, and the property says which."""
    with fake_sync_gateways(len(node_support)) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)
        for sg, supported in zip(sync_gateways, node_support, strict=True):
            sg.has_shell2http_sidecar = supported

        async with _manager_for(sync_gateways) as manager:
            _stub_sidecar(monkeypatch, manager)
            assert manager.has_shell2http_sidecar is expected
            assert [node.has_shell2http_sidecar for node in manager.nodes] == node_support


@pytest.mark.asyncio
async def test_a_partly_managed_cluster_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node without the sidecar cannot be restored, so silently skipping it would strand it."""
    with fake_sync_gateways(3) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)
        sync_gateways[1].has_shell2http_sidecar = False

        with pytest.raises(CblTestError, match=re.escape(str(sync_gateways[1]))):
            await _open_fixture(_FakeCBLPyTest(SyncGatewayCluster(sync_gateways)))


@pytest.mark.asyncio
async def test_teardown_restores_every_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A test left mid-change must not hand a stale config -- or a downed node -- to the tests
    that follow it. A restart covers both, since the sidecar's stop step no-ops when the
    node is already down.
    """
    with fake_sync_gateways(3) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)
            await manager.nodes[1].stop()
            calls.clear()

        assert sorted(calls) == [
            ("0:post", "/restart-sgw", "bootstrap"),
            ("1:post", "/restart-sgw", "bootstrap"),
            ("2:post", "/restart-sgw", "bootstrap"),
        ]


@pytest.mark.asyncio
async def test_teardown_noops_without_the_sidecar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the sidecar the test skipped, so there is nothing to restore."""
    with fake_sync_gateways(2) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)
        for sg in sync_gateways:
            sg.has_shell2http_sidecar = False

        async with _manager_for(sync_gateways) as manager:
            calls = _stub_sidecar(monkeypatch, manager)

        assert calls == []


@pytest.mark.asyncio
async def test_teardown_closes_every_sidecar_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manager holds a session per node, so leaving them open would leak every test."""
    with fake_sync_gateways(2) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        async with _manager_for(sync_gateways) as manager:
            _stub_sidecar(monkeypatch, manager)
            nodes = list(manager.nodes)
            assert not any(node.closed for node in nodes)

        assert all(node.closed for node in nodes)


@pytest.mark.asyncio
async def test_sessions_are_closed_even_if_the_restore_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A restore that raises is the case where a leaked session is easiest to miss."""
    with fake_sync_gateways(2) as sync_gateways:
        _stub_node_queries(monkeypatch, sync_gateways)

        generator, manager = await _open_fixture(_FakeCBLPyTest(SyncGatewayCluster(sync_gateways)))
        nodes = list(manager.nodes)

        async def _call_sidecar(*args: Any, **kwargs: Any) -> None:
            raise CblTestError("sidecar is gone")

        for node in manager.nodes:
            monkeypatch.setattr(node, "_call_sidecar", _call_sidecar)

        with pytest.raises(ExceptionGroup):
            await anext(generator)

        assert all(node.closed for node in nodes)
