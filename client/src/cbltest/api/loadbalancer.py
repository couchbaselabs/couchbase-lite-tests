"""
A Caddy load balancer in front of Sync Gateway nodes, whose upstreams a test sets at run time.

Each load balancer listens on three ports: the public API on its `load-balancers` config port (4984
when the entry names none), the Sync Gateway admin API on the next port, and Caddy's own admin API
6 ports above the public one.  :meth:`LoadBalancer.configure` posts a whole new config
to Caddy's admin API, which applies it before it answers.

Routing:

- A request with no ``X-Backend`` header goes round robin to every upstream.  A request whose
  connection is refused moves on to the next upstream.
- A request with the header from :meth:`LoadBalancer.pin` goes to that one upstream, with no retry.
- Any other ``X-Backend`` value, an empty one included, gets a 500.
"""

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SyncGateway
from cbltest.httpclient import AsyncHTTPClient
from cbltest.logging import cbl_info

DEFAULT_PUBLIC_PORT = 4984
"""The public port of a load balancer whose `load-balancers` config entry names none."""

PIN_HEADER = "X-Backend"
MAX_REQUEST_BODY_BYTES = 20 * 1024 * 1024
# A gone node black-holes the connection, so this is how long the pool waits before trying the next.
_DIAL_TIMEOUT = "5s"
# Inside the load balancer's container, the ports it listens on are always the defaults.
_PUBLIC_LISTEN, _ADMIN_LISTEN, _CADDY_ADMIN_LISTEN = 4984, 4985, 4990
_CADDY_ADMIN_OFFSET = _CADDY_ADMIN_LISTEN - _PUBLIC_LISTEN
# A load balancer in Docker reaches a Sync Gateway on its own host through this name.
_DOCKER_HOST = "host.docker.internal"
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def load_balancer_address(load_balancer: str) -> tuple[str, int]:
    """
    Splits a `load-balancers` config entry, `host` or `host:port`, into its host and public port.

    :param load_balancer: The config entry
    """
    parsed = urlsplit(f"//{load_balancer}")
    if not parsed.hostname:
        raise ValueError(f"Invalid load balancer entry {load_balancer!r}, expected host or host:port")
    return parsed.hostname, parsed.port or DEFAULT_PUBLIC_PORT


def _upstream(sg: SyncGateway, port: int) -> str:
    host = _DOCKER_HOST if sg.hostname in _LOCAL_HOSTS else sg.hostname
    return f"{host}:{port}"


def _proxy(upstreams: Sequence[str], tls: bool, retry: bool) -> dict[str, Any]:
    transport: dict[str, Any] = {"protocol": "http", "dial_timeout": _DIAL_TIMEOUT}
    if tls:
        transport["tls"] = {"insecure_skip_verify": True}
    handler: dict[str, Any] = {
        "handler": "reverse_proxy",
        "upstreams": [{"dial": upstream} for upstream in upstreams],
        "transport": transport,
        "headers": {"request": {"set": {"Host": ["{http.reverse_proxy.upstream.hostport}"]}}},
    }
    if retry:
        handler["load_balancing"] = {
            "selection_policy": {"policy": "round_robin"},
            "retries": max(2, len(upstreams)),
        }
        # Caddy can only resend a body it buffered, so a retried POST needs the whole body held.
        handler["request_buffers"] = MAX_REQUEST_BODY_BYTES
    return handler


def _routes(pins: dict[str, str], tls: bool) -> list[dict[str, Any]]:
    body_limit = {"handler": "request_body", "max_size": MAX_REQUEST_BODY_BYTES}
    routes: list[dict[str, Any]] = [
        {
            "match": [{"header": {PIN_HEADER: [pin]}}],
            "handle": [body_limit, _proxy([upstream], tls, retry=False)],
            "terminal": True,
        }
        for pin, upstream in pins.items()
    ]
    routes.append(
        {
            "match": [{"header_regexp": {PIN_HEADER: {"pattern": ".*"}}}],
            "handle": [{"handler": "static_response", "status_code": 500, "body": f"Unknown {PIN_HEADER}\n"}],
            "terminal": True,
        }
    )
    if pins:
        routes.append({"handle": [body_limit, _proxy(list(pins.values()), tls, retry=True)]})
    else:
        routes.append({"handle": [{"handler": "static_response", "status_code": 503, "body": "No upstreams\n"}]})
    return routes


def _pin_value(sg: SyncGateway) -> str:
    return f"{sg.hostname}:{sg.public_port}"


def caddy_config(sync_gateways: Sequence[SyncGateway]) -> dict[str, Any]:
    """
    The Caddy config for a load balancer in front of the given Sync Gateway nodes.

    :param sync_gateways: The upstreams.  An empty list makes every request fail with a 503.
    """
    if len({sg.secure for sg in sync_gateways}) > 1:
        raise CblTestError("A load balancer cannot front both TLS and non-TLS Sync Gateway nodes")
    tls = any(sg.secure for sg in sync_gateways)
    public = {_pin_value(sg): _upstream(sg, sg.public_port) for sg in sync_gateways}
    admin = {_pin_value(sg): _upstream(sg, sg.port) for sg in sync_gateways}
    return {
        "admin": {"listen": f"0.0.0.0:{_CADDY_ADMIN_LISTEN}"},
        "apps": {
            "http": {
                "servers": {
                    "public": {"listen": [f":{_PUBLIC_LISTEN}"], "routes": _routes(public, tls)},
                    "admin": {"listen": [f":{_ADMIN_LISTEN}"], "routes": _routes(admin, tls)},
                }
            }
        },
    }


class LoadBalancer:
    """A load balancer from the `load-balancers` config, which fronts no node until :meth:`configure`."""

    def __init__(self, entry: str) -> None:
        """
        :param entry: The `load-balancers` config entry, `host` or `host:port`
        """
        self.__hostname, self.__port = load_balancer_address(entry)
        self.__pins: dict[str, str] = {}

    def __str__(self) -> str:
        return f"LoadBalancer {self.__hostname}:{self.__port}"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the load balancer"""
        return self.__hostname

    @property
    def port(self) -> int:
        """Gets the public API port of the load balancer"""
        return self.__port

    @property
    def admin_port(self) -> int:
        """Gets the port that forwards to the Sync Gateway admin API"""
        return self.__port + 1

    @property
    def caddy_admin_port(self) -> int:
        """Gets the port of Caddy's own admin API"""
        return self.__port + _CADDY_ADMIN_OFFSET

    @property
    def caddy_admin_url(self) -> str:
        """Gets the URL of Caddy's own admin API"""
        return f"http://{self.__hostname}:{self.caddy_admin_port}"

    def replication_url(self, db_name: str) -> str:
        """
        Gets the replicator URL for a database, through this load balancer

        :param db_name: The database to replicate with
        """
        return f"ws://{self.__hostname}:{self.__port}/{db_name}"

    def pin(self, sg: SyncGateway) -> dict[str, str]:
        """
        Gets the header that sends a request through this load balancer to one node only

        :param sg: A node from the last :meth:`configure` call
        """
        value = _pin_value(sg)
        if value not in self.__pins:
            raise CblTestError(f"{sg} is not an upstream of {self}, which has: {', '.join(self.__pins) or 'none'}")
        return {PIN_HEADER: value}

    async def configure(self, sync_gateways: Sequence[SyncGateway]) -> None:
        """
        Replaces the upstreams.  Caddy applies the new routes before this returns.

        :param sync_gateways: The nodes to put behind the load balancer, in round robin order
        """
        config = caddy_config(sync_gateways)
        async with AsyncHTTPClient() as session:
            resp = await session.post(f"{self.caddy_admin_url}/load", json=config)
            async with resp:
                if resp.status != 200:
                    raise CblTestError(f"{self} rejected its new config ({resp.status}): {await resp.text()}")
        self.__pins = {_pin_value(sg): sg.hostname for sg in sync_gateways}
        cbl_info(f"{self} now fronts: {', '.join(self.__pins) or 'none'}")

    async def reset(self) -> None:
        """Removes every upstream, so every request fails with a 503 until the next :meth:`configure`."""
        await self.configure([])
