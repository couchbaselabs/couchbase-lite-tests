"""
Changes to Sync Gateway node state -- bootstrap config, certificates, and whether a node
is up -- that are undone when the test ends.

`SyncGatewayClusterManager` changes every node; `SyncGatewayManager` changes one, for
tests that mean to leave the cluster uneven. Both come only from the `sg_cluster_manager`
fixture, which is what restores the cluster afterwards.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine, Sequence
from typing import Any

import pytest_asyncio
from aiohttp import ClientSession, ClientTimeout
from cbltest import CBLPyTest
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SHELL2HTTP_PORT, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info
from cbltest.version import VERSION
from opentelemetry.trace import get_tracer

DEFAULT_CONFIG_NAME = "bootstrap"

# Held by the fixture alone, so a manager it did not build cannot be constructed.
_FIXTURE_TOKEN = object()


def _check_token(token: object, class_name: str) -> None:
    """Reject a manager built outside the fixture."""
    if token is not _FIXTURE_TOKEN:
        raise CblTestError(
            f"{class_name} is only available through the sg_cluster_manager fixture, "
            "which returns the cluster to its default state once the test is over"
        )


def _check_uniform_sidecars(sync_gateways: Sequence[SyncGateway]) -> None:
    """Reject a cluster where only some nodes expose the sidecar, since it cannot be restored."""
    missing = [str(sg) for sg in sync_gateways if not sg.has_shell2http_sidecar]
    if missing and len(missing) != len(sync_gateways):
        raise CblTestError(
            "Every Sync Gateway node must expose the shell2http sidecar, or none of them may. "
            f"These nodes are missing it: {', '.join(missing)}"
        )


class SyncGatewayManager:
    """
    Changes one Sync Gateway node's config, certificates, or running state.

    Reached through `SyncGatewayClusterManager.nodes`. Prefer the cluster-wide methods
    unless leaving the cluster uneven is the point of the test.
    """

    def __init__(self, node: SyncGateway, token: object = None) -> None:
        _check_token(token, type(self).__name__)
        self.__node = node
        self.__tracer = get_tracer(__name__, VERSION)
        self.__session = ClientSession(f"http://{node.hostname}:{SHELL2HTTP_PORT}")

    def __str__(self) -> str:
        return str(self.__node)

    @property
    def closed(self) -> bool:
        """Whether this node's sidecar session has been closed."""
        return self.__session.closed

    async def close(self) -> None:
        """Close this node's sidecar session. The fixture calls this at teardown."""
        await self.__session.close()

    @property
    def has_shell2http_sidecar(self) -> bool:
        """Whether this node exposes the shell2http sidecar every operation here goes through."""
        return self.__node.has_shell2http_sidecar

    async def _call_sidecar(self, method: str, path: str, data: str | None = None, timeout: int = 120) -> None:
        """
        Call a sidecar endpoint, raising on anything but a 200.

        :param method: HTTP method to use
        :param path: Sidecar path, including any query string
        :param data: Request body, for the endpoints that take one
        :param timeout: Total timeout in seconds
        """
        headers = {"Content-Type": "text/plain"} if data is not None else None
        async with self.__session.request(
            method,
            path,
            data=data,
            headers=headers,
            timeout=ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise CblTestError(f"{method.upper()} {path} failed on {self}: {resp.status} - {body}")

    async def restart_with_config(self, config_name: str = DEFAULT_CONFIG_NAME) -> None:
        """
        Restart this node with the given bootstrap config, returning once it serves again.
        Starts the node if it is stopped.

        :param config_name: Config file name (without .json), which must exist on the host
        """
        with self.__tracer.start_as_current_span("restart_with_config", attributes={"cbl.config.name": config_name}):
            await self._call_sidecar("post", "/restart-sgw", data=config_name)
        await self.__node.wait_for_rest_api()

    async def upload_certificate(self, cert_content: bytes, cert_name: str) -> None:
        """
        Upload a certificate to this node.

        :param cert_content: Certificate content as bytes (PEM format)
        :param cert_name: Name for the certificate file (e.g., 'ca.pem', 'server.crt')
        """
        with self.__tracer.start_as_current_span("upload_certificate", attributes={"cbl.cert.name": cert_name}):
            # The sidecar expects the name on the first line, the content after it.
            body = f"{cert_name}\n{cert_content.decode('utf-8')}"
            await self._call_sidecar("post", "/upload-cert", data=body, timeout=30)
        cbl_info(f"Certificate '{cert_name}' uploaded to {self}")

    async def stop(self) -> None:
        """Stop this node."""
        with self.__tracer.start_as_current_span("stop_sgw"):
            await self._call_sidecar("get", "/stop-sgw", timeout=60)

    async def start(self, config_name: str = DEFAULT_CONFIG_NAME) -> None:
        """
        Start this node, returning once it serves. Does nothing if it is already up.

        :param config_name: Config file name (without .json)
        """
        if await self.__node.is_serving():
            cbl_info(f"{self} is already running, skipping start")
            return

        with self.__tracer.start_as_current_span("start_sgw", attributes={"cbl.config.name": config_name}):
            await self._call_sidecar("get", f"/start-sgw?config={config_name}")
        await self.__node.wait_for_rest_api()


NodeAction = Callable[[SyncGatewayManager], Coroutine[Any, Any, None]]


class SyncGatewayClusterManager:
    """
    Changes every Sync Gateway node of a cluster at once.

    Comes from the `sg_cluster_manager` fixture; constructing one directly raises.
    """

    def __init__(self, cluster: SyncGatewayCluster, token: object = None) -> None:
        _check_token(token, type(self).__name__)
        # Checked before the node managers exist, so a rejected cluster opens no sessions.
        _check_uniform_sidecars(cluster.sync_gateways)
        self.__nodes = [SyncGatewayManager(sg, token) for sg in cluster.sync_gateways]

    @property
    def nodes(self) -> Sequence[SyncGatewayManager]:
        """The per-node managers, in the same order as the cluster's nodes."""
        return self.__nodes

    @property
    def has_shell2http_sidecar(self) -> bool:
        """
        Whether the nodes expose the shell2http sidecar. Tests skip when it is missing,
        rather than failing on a connection error. A cluster where only some nodes expose
        it is rejected when the manager is built, so this is all of them or none.
        """
        return all(node.has_shell2http_sidecar for node in self.__nodes)

    async def __on_every_node(self, action: NodeAction) -> None:
        """Run action against every node at once, failing if any node fails."""
        async with asyncio.TaskGroup() as group:
            for node in self.__nodes:
                group.create_task(action(node))

    async def close(self) -> None:
        """Close every node's sidecar session. The fixture calls this at teardown."""
        await self.__on_every_node(lambda node: node.close())

    async def restart_with_config(self, config_name: str = DEFAULT_CONFIG_NAME) -> None:
        """
        Restart every node with the given bootstrap config, returning once all serve again.

        :param config_name: Config file name (without .json), which must exist on every node
        """
        await self.__on_every_node(lambda node: node.restart_with_config(config_name))

    async def upload_certificate(self, cert_content: bytes, cert_name: str) -> None:
        """
        Upload a certificate to every node, so any of them can load a config naming it.

        :param cert_content: Certificate content as bytes (PEM format)
        :param cert_name: Name for the certificate file (e.g., 'ca.pem', 'server.crt')
        """
        await self.__on_every_node(lambda node: node.upload_certificate(cert_content, cert_name))


@pytest_asyncio.fixture(scope="function")
async def sg_cluster_manager(cblpytest: CBLPyTest) -> AsyncGenerator[SyncGatewayClusterManager]:
    """
    Yields the only handle that can change Sync Gateway node state, and puts every node
    back on the default config, and running, once the test is over.

    The restore runs whether or not the test changed anything, since a test that failed
    midway is the one most likely to have left the cluster broken.
    """
    manager = SyncGatewayClusterManager(cblpytest.sync_gateway_cluster, _FIXTURE_TOKEN)
    try:
        yield manager
        # No sidecar on any node means the test skipped and changed nothing.
        if manager.has_shell2http_sidecar:
            cbl_info(f"Restoring all Sync Gateway nodes to the '{DEFAULT_CONFIG_NAME}' config and running")
            await manager.restart_with_config()
    finally:
        await manager.close()
