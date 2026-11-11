from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblTestError
from cbltest.api.loadbalancer import DEFAULT_PUBLIC_PORT, LoadBalancer, caddy_config, load_balancer_address
from cbltest.api.syncgateway import SyncGateway


def _sync_gateway(hostname: str, public_port: int = 4984, secure: bool = False) -> SyncGateway:
    """Only the address fields the load balancer reads, so no session is opened."""
    node = SimpleNamespace(hostname=hostname, public_port=public_port, port=public_port + 1, secure=secure)
    return cast(SyncGateway, node)


@asynccontextmanager
async def _caddy_admin(
    handler: Callable[[web.Request], Awaitable[web.Response]],
) -> AsyncIterator[LoadBalancer]:
    """A load balancer whose Caddy admin API is a stand-in answering /load with `handler`."""
    app = web.Application()
    app.router.add_post("/load", handler)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        assert server.port is not None
        yield LoadBalancer(f"127.0.0.1:{server.port - 6}")
    finally:
        await server.close()


def _routes(config: dict[str, Any], server: str) -> list[dict[str, Any]]:
    return config["apps"]["http"]["servers"][server]["routes"]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("10.0.0.5", ("10.0.0.5", DEFAULT_PUBLIC_PORT)),
        ("localhost:4884", ("localhost", 4884)),
    ],
)
def test_load_balancer_address(entry: str, expected: tuple[str, int]) -> None:
    assert load_balancer_address(entry) == expected


@pytest.mark.parametrize("entry", ["", ":4884"])
def test_load_balancer_address_rejects_missing_host(entry: str) -> None:
    with pytest.raises(ValueError, match="host or host:port"):
        load_balancer_address(entry)


def test_ports_and_urls() -> None:
    lb = LoadBalancer("localhost:4884")
    assert (lb.port, lb.admin_port, lb.caddy_admin_port) == (4884, 4885, 4890)
    assert lb.caddy_admin_url == "http://localhost:4890"
    assert lb.replication_url("db1") == "ws://localhost:4884/db1"
    assert LoadBalancer("10.0.0.5").caddy_admin_port == 4990


def test_caddy_config_pins_each_node_and_pools_them_all() -> None:
    sgs = [_sync_gateway("sg1.example.com"), _sync_gateway("localhost", public_port=4994)]
    config = caddy_config(sgs)

    public = _routes(config, "public")
    pinned = {route["match"][0]["header"]["X-Backend"][0]: route["handle"][1]["upstreams"] for route in public[:2]}
    assert pinned == {
        "sg1.example.com:4984": [{"dial": "sg1.example.com:4984"}],
        "localhost:4994": [{"dial": "host.docker.internal:4994"}],
    }
    assert public[2]["handle"][0]["status_code"] == 500
    pool = public[3]["handle"][1]
    assert pool["upstreams"] == [{"dial": "sg1.example.com:4984"}, {"dial": "host.docker.internal:4994"}]
    assert pool["load_balancing"]["retries"] == 2

    admin_pool = _routes(config, "admin")[3]["handle"][1]
    assert admin_pool["upstreams"] == [{"dial": "sg1.example.com:4985"}, {"dial": "host.docker.internal:4995"}]


def test_caddy_config_with_no_upstreams_answers_503() -> None:
    routes = _routes(caddy_config([]), "public")
    assert [route["handle"][-1].get("status_code") for route in routes] == [500, 503]


def test_caddy_config_skips_tls_checks_for_tls_nodes() -> None:
    config = caddy_config([_sync_gateway("sg1.example.com", secure=True)])
    assert _routes(config, "public")[0]["handle"][1]["transport"]["tls"] == {"insecure_skip_verify": True}


def test_caddy_config_rejects_mixed_tls() -> None:
    sgs = [_sync_gateway("a.example.com", secure=True), _sync_gateway("b.example.com")]
    with pytest.raises(CblTestError, match="both TLS and non-TLS"):
        caddy_config(sgs)


@pytest.mark.asyncio
async def test_configure_loads_the_config_and_enables_pins() -> None:
    loaded: list[dict[str, Any]] = []

    async def load(request: web.Request) -> web.Response:
        loaded.append(await request.json())
        return web.Response(status=200)

    sg1, sg2 = _sync_gateway("sg1.example.com"), _sync_gateway("sg2.example.com")
    async with _caddy_admin(load) as lb:
        with pytest.raises(CblTestError, match="not an upstream"):
            lb.pin(sg1)

        await lb.configure([sg1, sg2])
        assert loaded == [caddy_config([sg1, sg2])]
        assert lb.pin(sg2) == {"X-Backend": "sg2.example.com:4984"}

        await lb.reset()
        assert loaded[-1] == caddy_config([])
        with pytest.raises(CblTestError, match="not an upstream"):
            lb.pin(sg2)


@pytest.mark.asyncio
async def test_configure_reports_a_rejected_config() -> None:
    async def reject(request: web.Request) -> web.Response:
        return web.Response(status=400, text="bad config")

    async with _caddy_admin(reject) as lb:
        with pytest.raises(CblTestError, match="400.*bad config"):
            await lb.configure([])
