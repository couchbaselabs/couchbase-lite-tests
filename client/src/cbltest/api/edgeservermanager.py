"""
Changes to Edge Server state, alongside the `EdgeServer` client that talks to it.

A config change is a new `EdgeServer`, not a mutated one: the port, scheme and credentials
an `EdgeServer` talks on all come from the config it was built with.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiofiles
from aiohttp import ClientSession
from opentelemetry.trace import get_tracer

from cbltest.api.edgeserver import EdgeServer
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.syncgateway import SHELL2HTTP_PORT
from cbltest.configparser import EdgeServerInfo
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
        self.__session = ClientSession(f"http://{info.hostname}:{SHELL2HTTP_PORT}")
        self.__edge_server = EdgeServer(info.hostname, info.admin_user, info.admin_password, info.config_path)

    def __str__(self) -> str:
        return self.__info.hostname

    @property
    def edge_server(self) -> EdgeServer:
        """The Edge Server as it is configured now."""
        return self.__edge_server

    async def close(self) -> None:
        """Close the sidecar session and the Edge Server."""
        await self.__session.close()
        await self.__edge_server.close()

    async def _call_sidecar(self, method: str, path: str, payload: JSONDictionary | None = None) -> None:
        """Call a sidecar endpoint, raising on anything but a 2xx."""
        await self.__edge_server._send_request(method, path, payload, session=self.__session)

    async def _replace_edge_server(self, config_file: str, admin_user: str, admin_password: str) -> EdgeServer:
        """Point at a restarted Edge Server, closing the one it replaces."""
        replaced = self.__edge_server
        self.__edge_server = EdgeServer(self.__info.hostname, admin_user, admin_password, config_file)
        await replaced.close()
        return self.__edge_server

    async def kill_server(self) -> None:
        """Stop the Edge Server process."""
        with self.__tracer.start_as_current_span("kill edge server"):
            await self._call_sidecar("post", "/kill-edgeserver")

    async def start_server(self, config: dict | None = None) -> None:
        """
        Start the Edge Server process.

        :param config: Config to write out before starting, or None to start on whatever
            config the host already holds
        """
        with self.__tracer.start_as_current_span("start edge server"):
            await self._call_sidecar("post", "/start-edgeserver", JSONDictionary(config if config else {}))

    async def configure_dataset(self, db_name: str = "db", config_file: str | None = None) -> EdgeServer:
        """
        Restart the Edge Server on `config_file` with a freshly seeded database, and return
        a client for it, replacing the one returned before.

        :param db_name: Dataset to seed, without the .cblite2 extension
        :param config_file: Config to start on, or None for the provisioned one
        """
        if not config_file:
            config_file = self.__info.config_path

        with self.__tracer.start_as_current_span("configure edge server dataset"):
            await self.kill_server()
            await self._call_sidecar("post", "/reset-db", JSONDictionary({"filename": f"{db_name}.cblite2"}))
            await self.start_server(await _read_config(config_file))
            return await self._replace_edge_server(config_file, self.__info.admin_user, self.__info.admin_password)

    async def add_user(self, name: str, password: str, role: str = "admin") -> None:
        """
        Add a user, restarting the Edge Server so it takes effect. The client keeps its own
        credentials: :func:`create_user_client` hands back one that talks as the new user.

        :param name: The user to add
        :param password: That user's password
        :param role: The role to give the user
        """
        with self.__tracer.start_as_current_span("add edge server user"):
            await self.kill_server()
            payload = {"name": name, "password": password, "role": role}
            await self._call_sidecar("post", "/add-user", JSONDictionary(payload))
            await self.start_server()

    @asynccontextmanager
    async def create_user_client(self, username: str, password: str, role: str = "admin") -> AsyncIterator[EdgeServer]:
        """
        Add a user, then yield a client that authenticates as them, closing it on exit.

        :param username: The user to add
        :param password: That user's password
        :param role: The role to give the user
        """
        await self.add_user(username, password, role)
        async with self.__edge_server.get_user_client(username, password) as client:
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
            await self.start_server(await _read_config(self.__info.config_path))
            await self._replace_edge_server(self.__info.config_path, self.__info.admin_user, self.__info.admin_password)
