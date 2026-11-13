import shutil
import socket
import subprocess
import time
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblTestError
from cbltest.api.loadbalancer import LoadBalancer, caddy_config
from cbltest.api.syncgateway import SyncGateway
from cbltest.configparser import LoadBalancerInfo

_AWS_LB = LoadBalancerInfo({"hostname": "10.0.0.5"})
_CADDY_IMAGE = "caddy:2.10.2"


def _sync_gateway(
    hostname: str, public_port: int = 4984, secure: bool = False, internal_hostname: str | None = None
) -> SyncGateway:
    """Only the address fields the load balancer reads, so no session is opened."""
    node = SimpleNamespace(
        hostname=hostname,
        internal_hostname=internal_hostname or hostname,
        public_port=public_port,
        port=public_port + 1,
        secure=secure,
    )
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
        yield LoadBalancer(LoadBalancerInfo({"hostname": "127.0.0.1", "caddy_admin_port": server.port}))
    finally:
        await server.close()


def test_info_defaults_to_the_aws_ports() -> None:
    assert (_AWS_LB.port, _AWS_LB.admin_port, _AWS_LB.caddy_admin_port) == (4984, 4985, 20000)


def test_ports_and_urls_come_from_the_config_entry() -> None:
    info = LoadBalancerInfo({"hostname": "localhost", "port": 4884, "admin_port": 4885, "caddy_admin_port": 19900})
    lb = LoadBalancer(info)
    assert lb.port == 4884
    assert lb.caddy_admin_url == "http://localhost:19900"
    assert lb.replication_url("db1") == "ws://localhost:4884/db1"

    caddyfile = caddy_config(info, [])
    assert "admin 0.0.0.0:19900" in caddyfile
    assert ":4884 {" in caddyfile and ":4885 {" in caddyfile


def test_caddy_config_dials_internal_hostnames_and_routes_by_public_address() -> None:
    sg = _sync_gateway("54.1.2.3", internal_hostname="10.0.1.5")
    caddyfile = caddy_config(_AWS_LB, [sg])
    assert "@backend0 header X-Backend 54.1.2.3:4984" in caddyfile
    assert "reverse_proxy @backend0 10.0.1.5:4984 {" in caddyfile
    assert "reverse_proxy @backend0 10.0.1.5:4985 {" in caddyfile


def test_caddy_config_skips_tls_checks_only_for_tls_nodes() -> None:
    assert "tls_insecure_skip_verify" in caddy_config(_AWS_LB, [_sync_gateway("a", secure=True)])
    assert "tls_insecure_skip_verify" not in caddy_config(_AWS_LB, [_sync_gateway("a")])


def test_caddy_config_rejects_mixed_tls() -> None:
    sgs = [_sync_gateway("a.example.com", secure=True), _sync_gateway("b.example.com")]
    with pytest.raises(CblTestError, match="both TLS and non-TLS"):
        caddy_config(_AWS_LB, sgs)


@pytest.mark.asyncio
async def test_configure_loads_a_caddyfile_and_enables_backend_ids() -> None:
    loaded: list[tuple[str, str]] = []

    async def load(request: web.Request) -> web.Response:
        loaded.append((request.content_type, await request.text()))
        return web.Response(status=200)

    sg1, sg2 = _sync_gateway("sg1.example.com"), _sync_gateway("sg2.example.com")
    async with _caddy_admin(load) as lb:
        with pytest.raises(CblTestError, match="not an upstream"):
            lb.pin(sg1)

        await lb.configure([sg1, sg2])
        assert loaded[-1][0] == "text/caddyfile"
        assert "reverse_proxy sg1.example.com:4984 sg2.example.com:4984 {" in loaded[-1][1]
        assert lb.pin(sg2) == {"X-Backend": "sg2.example.com:4984"}

        await lb.reset()
        assert 'respond "No upstreams" 503' in loaded[-1][1]
        with pytest.raises(CblTestError, match="not an upstream"):
            lb.pin(sg2)


@pytest.mark.asyncio
async def test_reset_skips_admin_api_when_never_configured() -> None:
    async def load(request: web.Request) -> web.Response:
        raise AssertionError("reset() called Caddy's admin API with no upstreams to remove")

    async with _caddy_admin(load) as lb:
        await lb.reset()


@pytest.mark.asyncio
async def test_configure_reports_a_rejected_config() -> None:
    async def reject(request: web.Request) -> web.Response:
        return web.Response(status=400, text="bad config")

    async with _caddy_admin(reject) as lb:
        with pytest.raises(CblTestError, match="400.*bad config"):
            await lb.configure([])


# The tests below route real requests through Caddy to stand-in Sync Gateway nodes.


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def real_caddy() -> Iterator[LoadBalancerInfo]:
    """A Caddy container with no config yet, listening on the same free ports inside and out."""
    if not _docker_available():
        pytest.skip("Docker is not available")

    info = LoadBalancerInfo(
        {"hostname": "127.0.0.1", "port": _free_port(), "admin_port": _free_port(), "caddy_admin_port": _free_port()}
    )
    ports = [info.port, info.admin_port, info.caddy_admin_port]
    name = f"cbltest-caddy-{info.caddy_admin_port}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "--add-host", "host.docker.internal:host-gateway"]
        + ["-e", f"CADDY_ADMIN=0.0.0.0:{info.caddy_admin_port}"]
        + [arg for port in ports for arg in ("-p", f"127.0.0.1:{port}:{port}")]
        + [_CADDY_IMAGE, "caddy", "run"],
        check=True,
        capture_output=True,
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{info.caddy_admin_port}/config/", timeout=2)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield info
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@asynccontextmanager
async def _stand_in(name: str) -> AsyncIterator[tuple[TestServer, SyncGateway]]:
    """A Sync Gateway stand-in that answers every request with its own name, on all interfaces for Docker."""

    async def answer(request: web.Request) -> web.Response:
        return web.Response(text=name)

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", answer)
    server = TestServer(app, host="0.0.0.0")
    await server.start_server()
    assert server.port is not None
    node = SimpleNamespace(
        hostname="127.0.0.1",
        internal_hostname="host.docker.internal",
        public_port=server.port,
        port=server.port,
        secure=False,
    )
    try:
        yield server, cast(SyncGateway, node)
    finally:
        await server.close()


async def _get(info: LoadBalancerInfo, headers: dict[str, str] | None = None) -> tuple[int, str]:
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"http://127.0.0.1:{info.port}/db/", headers=headers) as resp,
    ):
        return resp.status, await resp.text()


@pytest.mark.asyncio
async def test_real_caddy_routes_pins_pool_and_unknown_ids(real_caddy: LoadBalancerInfo) -> None:
    lb = LoadBalancer(real_caddy)
    async with _stand_in("sg1") as (_, sg1), _stand_in("sg2") as (_, sg2):
        await lb.configure([sg1, sg2])

        for _ in range(3):
            assert await _get(real_caddy, lb.pin(sg2)) == (200, "sg2")
        assert {(await _get(real_caddy))[1] for _ in range(4)} == {"sg1", "sg2"}
        assert (await _get(real_caddy, {"X-Backend": "nobody:1"}))[0] == 500
        assert (await _get(real_caddy, {"X-Backend": ""}))[0] == 500

        await lb.reset()
        assert await _get(real_caddy) == (503, "No upstreams")


@pytest.mark.asyncio
async def test_real_caddy_pool_skips_a_node_that_is_down(real_caddy: LoadBalancerInfo) -> None:
    lb = LoadBalancer(real_caddy)
    async with _stand_in("sg1") as (down, sg1), _stand_in("sg2") as (_, sg2):
        await lb.configure([sg1, sg2])
        await down.close()

        assert [await _get(real_caddy) for _ in range(4)] == [(200, "sg2")] * 4
        assert (await _get(real_caddy, lb.pin(sg1)))[0] == 502
