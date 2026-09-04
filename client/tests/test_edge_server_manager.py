"""Tests for EdgeServerManager and the es_manager fixture that resets them."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import encode_basic_auth
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblTestError
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.configparser import EdgeServerInfo
from cbltest.plugins.cluster_cleanup import reset_all_edge_servers

HOSTNAME = "es.example.com"

SidecarCall = tuple[str, str, Any]


@contextmanager
def no_network() -> Iterator[None]:
    """Keep every session an Edge Server or a manager opens off the network."""
    with (
        patch("cbltest.api.edgeserver.ClientSession", autospec=True),
        patch("cbltest.api.caddy.ClientSession", autospec=True),
        patch("cbltest.api.edgeservermanager.ClientSession", autospec=True),
        # A TLS config reads client certificates out of ~/.cbl_certs, which exist only on a
        # machine that has provisioned an Edge Server topology.
        patch("cbltest.api.edgeserver.ssl.create_default_context", autospec=True),
        patch("cbltest.api.edgeserver.TCPConnector", autospec=True),
    ):
        yield


def write_config(directory: Path, name: str, port: int, https: bool = False, users: bool = False) -> str:
    """Write a minimal Edge Server config, and return its path."""
    config: dict[str, Any] = {"interface": f"0.0.0.0:{port}", "databases": {"db": {"path": "db.cblite2"}}}
    if users:
        config["users"] = "/etc/users.json"
    if https:
        config["https"] = {"tls_cert_path": "/cert.pem", "tls_key_path": "/key.pem"}
    path = directory / name
    path.write_text(json.dumps(config))
    return str(path)


def edge_server_info(config_file: str) -> EdgeServerInfo:
    return EdgeServerInfo(
        {
            "hostname": HOSTNAME,
            "admin_user": "admin_user",
            "admin_password": "password",
            "config_path": config_file,
        }
    )


@asynccontextmanager
async def managers_for(config_files: list[str]) -> AsyncIterator[list[EdgeServerManager]]:
    """Managers over the given hosts, closed on the way out."""
    with no_network():
        managers = [EdgeServerManager(edge_server_info(config_file)) for config_file in config_files]
        try:
            yield managers
        finally:
            for manager in managers:
                await manager.close()


def stub_sidecar(monkeypatch: pytest.MonkeyPatch, manager: EdgeServerManager) -> list[SidecarCall]:
    """Record what a manager sends to its sidecar, so nothing reaches the network."""
    calls: list[SidecarCall] = []

    async def _call_sidecar(method: str, path: str, payload: JSONSerializable | None = None) -> None:
        calls.append((method, path, None if payload is None else payload.to_json()))

    monkeypatch.setattr(manager, "_call_sidecar", _call_sidecar)
    return calls


@pytest.mark.asyncio
async def test_configure_dataset_seeds_the_database_and_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        calls = stub_sidecar(monkeypatch, managers[0])

        await managers[0].configure_dataset(db_name="travel", config_file=write_config(tmp_path, "test.json", 60000))

    assert [(method, path) for method, path, _ in calls] == [
        ("post", "/kill-edgeserver"),
        ("post", "/reset-db"),
        ("post", "/start-edgeserver"),
    ]
    assert calls[1][2] == {"filename": "travel.cblite2"}
    assert calls[2][2]["interface"] == "0.0.0.0:60000"


@pytest.mark.asyncio
async def test_configure_dataset_returns_an_edge_server_on_the_new_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        manager = managers[0]
        stub_sidecar(monkeypatch, manager)
        replaced = manager.get_admin_client()

        edge_server = await manager.configure_dataset(config_file=write_config(tmp_path, "tls.json", 60000, https=True))

        assert edge_server is not replaced, "a config change is a new Edge Server, not a mutated one"
        assert edge_server.replication_url("db") == f"wss://{HOSTNAME}:60000/db"


@pytest.mark.asyncio
async def test_close_closes_every_client_handed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    closed = []

    async def close_one(client: object) -> None:
        closed.append(client)

    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        manager = managers[0]
        stub_sidecar(monkeypatch, manager)
        handed_out = [
            manager.get_admin_client(),
            await manager.configure_dataset(config_file=write_config(tmp_path, "tls.json", 60000, https=True)),
        ]
        for client in handed_out:
            monkeypatch.setattr(client, "close", lambda client=client: close_one(client))

    assert closed == handed_out, "every client the manager handed out is closed with it"


@pytest.mark.asyncio
async def test_reset_returns_to_the_provisioned_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        manager = managers[0]
        calls = stub_sidecar(monkeypatch, manager)
        await manager.configure_dataset(config_file=write_config(tmp_path, "tls.json", 60000, https=True))
        calls.clear()

        await manager.reset_to_initial_state()

        assert manager.get_admin_client().replication_url("db") == f"ws://{HOSTNAME}:59840/db"

    assert [(method, path) for method, path, _ in calls] == [
        ("post", "/firewall"),
        ("post", "/kill-edgeserver"),
        ("post", "/reset-all-dbs"),
        ("post", "/start-edgeserver"),
    ]
    assert calls[3][2]["interface"] == "0.0.0.0:59840"


@pytest.mark.asyncio
async def test_reset_all_covers_every_edge_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configs = [write_config(tmp_path, f"initial{index}.json", 59840 + index) for index in range(3)]
    async with managers_for(configs) as managers:
        calls = [stub_sidecar(monkeypatch, manager) for manager in managers]

        await reset_all_edge_servers(managers)

        assert all(len(host_calls) == 4 for host_calls in calls)


@pytest.mark.asyncio
async def test_no_edge_servers_is_a_no_op() -> None:
    await reset_all_edge_servers([])


class FakeResponse:
    """The little of an aiohttp response that `EdgeServer._send_request` reads."""

    content_type = "application/json"
    status = 200
    ok = True

    async def json(self) -> list:
        return []


class FakeSession:
    """Records the requests made on it, and the headers it was built with."""

    def __init__(self, base_url: str | None = None, headers: dict[str, str] | None = None, **kwargs: Any) -> None:
        self.headers = headers or {}
        self.requests: list[tuple[str, str]] = []
        self.closed = False

    async def request(self, method: str, path: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, path))
        return FakeResponse()

    async def close(self) -> None:
        self.closed = True


@contextmanager
def fake_sessions() -> Iterator[None]:
    """Serve every Edge Server request from a FakeSession, so its headers are readable."""
    with (
        patch("cbltest.api.edgeserver.ClientSession", FakeSession),
        patch("cbltest.api.caddy.ClientSession", autospec=True),
        patch("cbltest.api.edgeservermanager.ClientSession", autospec=True),
        # A TLS config reads client certificates out of ~/.cbl_certs, which exist only on a
        # machine that has provisioned an Edge Server topology.
        patch("cbltest.api.edgeserver.ssl.create_default_context", autospec=True),
        patch("cbltest.api.edgeserver.TCPConnector", autospec=True),
    ):
        yield


def client_session(client: Any) -> FakeSession:
    """The session a client requests on."""
    return client._EdgeServer__session


@asynccontextmanager
async def fake_session_manager(config_file: str) -> AsyncIterator[EdgeServerManager]:
    """A manager whose Edge Servers request on a FakeSession."""
    with fake_sessions():
        manager = EdgeServerManager(edge_server_info(config_file))
        try:
            yield manager
        finally:
            await manager.close()


@pytest.mark.asyncio
async def test_create_user_client_adds_the_user_and_authenticates_as_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with fake_session_manager(write_config(tmp_path, "initial.json", 59840, users=True)) as manager:
        calls = stub_sidecar(monkeypatch, manager)

        async with manager.create_user_client("username8", "password8") as client:
            assert client is not manager.get_admin_client(), "the user gets a client of its own"
            await client.get_all_dbs()
            assert client_session(client).headers["Authorization"] == encode_basic_auth(
                "username8", "password8", "ascii"
            )

        assert client_session(client).closed, "leaving the block closes the client"

    assert [(method, path) for method, path, _ in calls] == [
        ("post", "/kill-edgeserver"),
        ("post", "/add-user"),
        ("post", "/start-edgeserver"),
    ]
    assert calls[1][2] == {"name": "username8", "password": "password8", "role": "admin"}


@pytest.mark.asyncio
async def test_user_client_needs_a_config_that_declares_users(tmp_path: Path) -> None:
    async with fake_session_manager(write_config(tmp_path, "initial.json", 59840)) as manager:
        with pytest.raises(CblTestError, match="declares no users"):
            async with manager.get_user_client("username8", "password8"):
                pass


@pytest.mark.asyncio
async def test_anonymous_client_sends_no_credentials(tmp_path: Path) -> None:
    async with (
        fake_session_manager(write_config(tmp_path, "initial.json", 59840, users=True)) as manager,
        manager.get_anonymous_client() as client,
    ):
        await client.get_all_dbs()
        assert "Authorization" not in client_session(client).headers
