"""
A Caddy load balancer in front of Sync Gateway nodes, whose upstreams a test sets at run time.

Each load balancer listens on the three ports of its `load-balancers` config entry
(:class:`LoadBalancerInfo`): one for the Sync Gateway public API, one for the Sync Gateway admin
API, and one for Caddy's own admin API.  :meth:`LoadBalancer.configure` posts a whole new Caddyfile
to Caddy's admin API, which applies it before it answers.

Routing:

- A request with no ``X-Backend`` header goes round robin to every upstream.  A request whose
  connection is refused moves on to the next upstream.
- A request with the header from :meth:`LoadBalancer.pin` goes to that one upstream, with no retry.
- Any other ``X-Backend`` value, an empty one included, gets a 500.
"""

from collections.abc import Sequence
from string import Template
from textwrap import indent

from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SyncGateway
from cbltest.configparser import LoadBalancerInfo
from cbltest.httpclient import AsyncHTTPClient
from cbltest.logging import cbl_info

BACKEND_ID_HEADER = "X-Backend"

# The Caddyfile is a global block, an `upstream` snippet that every reverse_proxy imports, and one site per port.
# A gone node black-holes the connection, so dial_timeout is how long Caddy waits before it tries the next one.
_CADDYFILE = Template("""\
{
    admin 0.0.0.0:$caddy_admin_port
    auto_https off
}

(upstream) {
    header_up Host {upstream_hostport}
    transport http {
        dial_timeout 5s
        $tls
    }
}

$public_site
$admin_site""")

# A site's routes, in the order Caddy tries them.  Each template is one route.
_BODY_LIMIT_ROUTE = """\
request_body {
    max_size 20MiB
}"""

_PINNED_ROUTE = Template("""\
@$matcher header $header $backend_id
reverse_proxy @$matcher $upstream {
    import upstream
}""")

_UNKNOWN_BACKEND_ROUTE = Template("""\
@unknown header_regexp $header .*
respond @unknown "Unknown $header" 500""")

# Caddy can only resend a body it buffered, so request_buffers lets a retried POST keep its body.
_ROUND_ROBIN_ROUTE = Template("""\
reverse_proxy $upstreams {
    import upstream
    lb_policy round_robin
    lb_retries $retries
    request_buffers 20MiB
}""")

_NO_UPSTREAMS_ROUTE = 'respond "No upstreams" 503'


def _site(port: int, upstreams: dict[str, str]) -> str:
    """
    A Caddy site that listens on one port and forwards to the given upstreams.

    :param port: The port the site listens on
    :param upstreams: Maps each upstream's `X-Backend` value to the address that Caddy dials
    """
    routes = [_BODY_LIMIT_ROUTE]
    routes += [
        _PINNED_ROUTE.substitute(
            matcher=f"backend{index}", header=BACKEND_ID_HEADER, backend_id=backend_id, upstream=upstream
        )
        for index, (backend_id, upstream) in enumerate(upstreams.items())
    ]
    routes.append(_UNKNOWN_BACKEND_ROUTE.substitute(header=BACKEND_ID_HEADER))
    if upstreams:
        routes.append(
            _ROUND_ROBIN_ROUTE.substitute(upstreams=" ".join(upstreams.values()), retries=max(2, len(upstreams)))
        )
    else:
        routes.append(_NO_UPSTREAMS_ROUTE)
    # `route` runs the directives in the order written, rather than in Caddy's own order.
    body = indent("\n".join(routes), " " * 8)
    return f":{port} {{\n    route {{\n{body}\n    }}\n}}\n"


def _backend_id(sg: SyncGateway) -> str:
    """The `X-Backend` value that sends a request to this node alone"""
    return f"{sg.hostname}:{sg.public_port}"


def caddy_config(info: LoadBalancerInfo, sync_gateways: Sequence[SyncGateway]) -> str:
    """
    The Caddyfile for a load balancer in front of the given Sync Gateway nodes.

    :param info: The load balancer's config entry, whose ports Caddy listens on
    :param sync_gateways: The upstreams.  An empty list makes every request fail with a 503.
    """
    if len({sg.secure for sg in sync_gateways}) > 1:
        raise CblTestError("A load balancer cannot front both TLS and non-TLS Sync Gateway nodes")
    public = {_backend_id(sg): f"{sg.internal_hostname}:{sg.public_port}" for sg in sync_gateways}
    admin = {_backend_id(sg): f"{sg.internal_hostname}:{sg.port}" for sg in sync_gateways}
    return _CADDYFILE.substitute(
        caddy_admin_port=info.caddy_admin_port,
        tls="tls_insecure_skip_verify" if any(sg.secure for sg in sync_gateways) else "",
        public_site=_site(info.port, public),
        admin_site=_site(info.admin_port, admin),
    )


class LoadBalancer:
    """A load balancer from the `load-balancers` config, which fronts no node until :meth:`configure`."""

    def __init__(self, info: LoadBalancerInfo) -> None:
        """
        :param info: The load balancer's `load-balancers` config entry
        """
        self.__info = info
        self.__backend_ids: set[str] = set()

    def __str__(self) -> str:
        return f"LoadBalancer {self.hostname}:{self.port}"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the load balancer"""
        return self.__info.hostname

    @property
    def port(self) -> int:
        """Gets the port that forwards to the Sync Gateway public API"""
        return self.__info.port

    @property
    def caddy_admin_url(self) -> str:
        """Gets the URL of Caddy's own admin API"""
        return f"http://{self.hostname}:{self.__info.caddy_admin_port}"

    def replication_url(self, db_name: str) -> str:
        """
        Gets the replicator URL for a database, through this load balancer

        :param db_name: The database to replicate with
        """
        return f"ws://{self.hostname}:{self.port}/{db_name}"

    def pin(self, sg: SyncGateway) -> dict[str, str]:
        """
        Gets the header that sends a request through this load balancer to one node only

        :param sg: A node from the last :meth:`configure` call
        """
        value = _backend_id(sg)
        if value not in self.__backend_ids:
            raise CblTestError(
                f"{sg} is not an upstream of {self}, which has: {', '.join(self.__backend_ids) or 'none'}"
            )
        return {BACKEND_ID_HEADER: value}

    async def configure(self, sync_gateways: Sequence[SyncGateway]) -> None:
        """
        Replaces the upstreams.  Caddy applies the new routes before this returns.

        :param sync_gateways: The nodes to put behind the load balancer, in round robin order
        """
        config = caddy_config(self.__info, sync_gateways)
        async with AsyncHTTPClient() as session:
            resp = await session.post(
                f"{self.caddy_admin_url}/load", data=config, headers={"Content-Type": "text/caddyfile"}
            )
            async with resp:
                if resp.status != 200:
                    raise CblTestError(f"{self} rejected its new config ({resp.status}): {await resp.text()}")
        self.__backend_ids = {_backend_id(sg) for sg in sync_gateways}
        cbl_info(f"{self} now fronts: {', '.join(self.__backend_ids) or 'none'}")

    async def reset(self) -> None:
        """
        Removes every upstream, so every request fails with a 503 until the next :meth:`configure`.
        Does nothing when this process set no upstreams, so tests that never configure one don't need its admin API.
        """
        if self.__backend_ids:
            await self.configure([])
