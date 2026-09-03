"""
Changes to Edge Server state, and the `EdgeServer` clients that talk to it.

A client is fixed to one config: the port, the scheme and the credentials it talks on come
from the config it was built with, so take a fresh client after every restart.  The manager
closes every client it hands out.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiofiles
from aiohttp import ClientSession
from opentelemetry.trace import get_tracer

from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError, CblTestError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.configparser import EdgeServerInfo
from cbltest.httplog import get_next_writer
from cbltest.utils import SHELL2HTTP_PORT
from cbltest.version import VERSION


async def _read_config(config_file: str) -> dict:
    """Read a local Edge Server config file."""
    async with aiofiles.open(config_file) as f:
        return json.loads(await f.read())


class EdgeServerManager:
    """Changes one Edge Server through the shell2http sidecar on its host."""

    def __init__(self, info: EdgeServerInfo) -> None:
        # What the host was provisioned with, which reset_to_initial_state() goes back to.
        self.__info = info
        self.__tracer = get_tracer(__name__, VERSION)
        self.__shell2http_session = ClientSession(f"http://{info.hostname}:{SHELL2HTTP_PORT}")
        self.__config_file = info.config_path
        self.__clients: list[EdgeServer] = []

    def __str__(self) -> str:
        return self.__info.hostname

    def get_admin_client(self) -> EdgeServer:
        """A client that authenticates as the admin user, closed when the manager is."""
        client = EdgeServer(
            self.__info.hostname, self.__info.admin_user, self.__info.admin_password, self.__config_file
        )
        self.__clients.append(client)
        return client

    async def close(self) -> None:
        """Close the sidecar session and every client handed out."""
        await self.__shell2http_session.close()
        for client in self.__clients:
            await client.close()
        self.__clients.clear()

    async def _call_sidecar(self, method: str, path: str, payload: JSONDictionary | None = None) -> None:
        """Call a shell2http endpoint on the Edge Server host, raising on anything but a 2xx."""
        data = "" if payload is None else payload.serialize()
        headers = {"Content-Type": "application/json"} if payload is not None else None
        writer = get_next_writer()
        writer.write_begin(f"Edge Server host [{self.__info.hostname}] -> {method.upper()} {path}", data)
        resp = await self.__shell2http_session.request(method, path, data=data, headers=headers)
        body = await resp.text()
        writer.write_end(
            f"Edge Server host [{self.__info.hostname}] <- {method.upper()} {path} {resp.status}",
            body,
        )
        if not resp.ok:
            raise CblEdgeServerBadResponseError(resp.status, f"{method} {path} returned {resp.status}", body=body)

    async def kill_server(self) -> None:
        """Stop the Edge Server process."""
        with self.__tracer.start_as_current_span("kill edge server"):
            await self._call_sidecar("post", "/kill-edgeserver")

    async def __start_process(self, config_file: str | None) -> None:
        """Start the Edge Server on `config_file`, or on whatever the host already holds."""
        config = await _read_config(config_file) if config_file else {}
        await self._call_sidecar("post", "/start-edgeserver", JSONDictionary(config))
        if config_file is not None:
            self.__config_file = config_file

    async def start_server(self, config_file: str | None = None) -> EdgeServer:
        """
        Start the Edge Server process, and return a client on the config it now runs.

        :param config_file: Config to write out before starting, or None to start on
            whatever config the host already holds
        """
        with self.__tracer.start_as_current_span("start edge server"):
            await self.__start_process(config_file)
            return self.get_admin_client()

    async def configure_dataset(self, db_name: str = "db", config_file: str | None = None) -> EdgeServer:
        """
        Restart the Edge Server on `config_file` with a freshly seeded database, and return
        a client for it.

        :param db_name: Dataset to seed, without the .cblite2 extension
        :param config_file: Config to start on, or None for the provisioned one
        """
        with self.__tracer.start_as_current_span("configure edge server dataset"):
            await self.kill_server()
            await self._call_sidecar("post", "/reset-db", JSONDictionary({"filename": f"{db_name}.cblite2"}))
            await self.__start_process(config_file or self.__info.config_path)
            return self.get_admin_client()

    async def add_user(self, name: str, password: str, role: str = "admin") -> None:
        """
        Add a user, restarting the Edge Server so it takes effect.  To talk to the Edge
        Server as that user, use :func:`create_user_client`.

        :param name: The user to add
        :param password: That user's password
        :param role: The role to give the user
        """
        with self.__tracer.start_as_current_span("add edge server user"):
            await self.kill_server()
            payload = {"name": name, "password": password, "role": role}
            await self._call_sidecar("post", "/add-user", JSONDictionary(payload))
            await self.__start_process(None)

    @asynccontextmanager
    async def get_user_client(self, username: str, password: str) -> AsyncIterator[EdgeServer]:
        """
        Yields a client that authenticates as an existing `username`, closing it on exit.
        To add the user first, use :func:`create_user_client`.

        :param username: The user to authenticate as
        :param password: That user's password
        """
        client = EdgeServer(self.__info.hostname, username, password, self.__config_file)
        try:
            if not client.needs_auth:
                raise CblTestError(
                    f"Edge Server [{self.__info.hostname}] is running a config that declares no users, "
                    "so a user client would send no credentials and prove nothing"
                )
            yield client
        finally:
            await client.close()

    @asynccontextmanager
    async def get_anonymous_client(self) -> AsyncIterator[EdgeServer]:
        """Yields a client that sends no credentials, closing it on exit."""
        client = EdgeServer(self.__info.hostname, config_file=self.__config_file)
        try:
            yield client
        finally:
            await client.close()

    @asynccontextmanager
    async def create_user_client(self, username: str, password: str, role: str = "admin") -> AsyncIterator[EdgeServer]:
        """
        Add a user, then yield a client that authenticates as them, closing it on exit.

        :param username: The user to add
        :param password: That user's password
        :param role: The role to give the user
        """
        # The client comes first, so a config that declares no users is rejected before
        # add_user restarts the Edge Server.
        async with self.get_user_client(username, password) as client:
            await self.add_user(username, password, role)
            yield client

    async def write_file(self, path: str, content: str) -> None:
        """
        Write a file on the Edge Server host, for the certificates and tokens a config
        names by path.

        :param path: Absolute path on the host
        :param content: File content
        """
        with self.__tracer.start_as_current_span("write file on edge server host"):
            await self._call_sidecar("post", "/write-file", JSONDictionary({"path": path, "content": content}))

    async def set_firewall_rules(self, allow: list[str] | None = None, deny: list[str] | None = None) -> None:
        """
        Add firewall rules to the host, to cut it off from a Sync Gateway.

        :param allow: The IPs allowed to reach the Edge Server
        :param deny: The IPs denied access to the Edge Server
        """
        with self.__tracer.start_as_current_span("set edge server firewall rules"):
            payload: dict[str, list[str]] = {}
            if allow:
                payload["allow"] = allow
            if deny:
                payload["deny"] = deny
            await self._call_sidecar("post", "/firewall", JSONDictionary(payload))

    async def reset_firewall(self) -> None:
        """Drop every firewall rule on the host."""
        with self.__tracer.start_as_current_span("reset edge server firewall"):
            await self._call_sidecar("post", "/firewall")

    async def reset_to_initial_state(self) -> None:
        """
        Restore the config, admin credentials and databases the host was provisioned with.
        Files written through :func:`write_file`, and users added, remain.
        """
        with self.__tracer.start_as_current_span("reset edge server"):
            # First: a leftover DROP rule hides the host from everything below.
            await self.reset_firewall()
            await self.kill_server()
            await self._call_sidecar("post", "/reset-all-dbs")
            await self.__start_process(self.__info.config_path)
