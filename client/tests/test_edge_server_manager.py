"""Tests for EdgeServerManager and the es_manager fixture that resets them."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import tenacity
from aiohttp import encode_basic_auth
from cbltest.api.caddy import Caddy
from cbltest.api.edgeserver import EdgeServer, ReplicationStatus
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblTestError
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.api.syncgateway import get_basic_auth_headers
from cbltest.configparser import EdgeServerInfo
from cbltest.plugins.cluster_cleanup import reset_all_edge_servers
from cbltest.shell2http import DEFAULT_SHELL2HTTP_TIMEOUT

HOSTNAME = "es.example.com"

SidecarCall = tuple[str, str, Any]


@contextmanager
def no_network() -> Iterator[None]:
    """Keep every session an Edge Server or a manager opens off the network."""
    with (
        patch("cbltest.httpclient.ClientSession", autospec=True),
        # A TLS config reads client certificates out of ~/.cbl_certs, which exist only on a
        # machine that has provisioned an Edge Server topology.
        patch("cbltest.api.edgeserver.ssl.create_default_context", autospec=True),
        patch("cbltest.api.edgeserver.TCPConnector", autospec=True),
        # Starting an Edge Server polls it until it answers, which is a real request.
        patch("cbltest.api.edgeservermanager.EdgeServerManager._EdgeServerManager__wait_until_serving", autospec=True),
    ):
        yield


def write_config(
    directory: Path, name: str, port: int, https: bool = False, users: bool = False, replications: int = 0
) -> str:
    """Write a minimal Edge Server config, and return its path."""
    config: dict[str, Any] = {"interface": f"0.0.0.0:{port}", "databases": {"db": {"path": "db.cblite2"}}}
    if users:
        config["users"] = "/etc/users.json"
    if replications:
        config["replications"] = [{"source": f"ws://sgw:4984/db{i}", "target": "db"} for i in range(replications)]
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

    async def _call_sidecar(
        method: str,
        path: str,
        payload: JSONSerializable | None = None,
        timeout: float = DEFAULT_SHELL2HTTP_TIMEOUT,
        changes_state: bool = True,
    ) -> str:
        calls.append((method, path, None if payload is None else payload.to_json()))
        return ""

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
async def test_collect_logs_downloads_the_archive_the_sidecar_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads: list[tuple[str, Path]] = []

    async def fake_download(self: Caddy, filename: str, local_path: str | Path) -> Path:
        downloads.append((filename, Path(local_path)))
        return Path(local_path)

    monkeypatch.setattr(Caddy, "download", fake_download)

    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        manager = managers[0]
        calls = stub_sidecar(monkeypatch, manager)

        archive = await manager.collect_logs(tmp_path)

    assert [(method, path) for method, path, _ in calls] == [("post", "/collect-logs")]
    filename = calls[0][2]["filename"]
    assert filename.startswith("es-collect-es-example-com-"), filename
    assert filename.endswith(".tar.gz"), filename
    assert downloads == [(f"collect/{filename}", tmp_path / filename)], (
        "the archive is fetched from the collect directory through an Edge Server client's Caddy"
    )
    assert archive == tmp_path / filename


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


def stub_shell2http(monkeypatch: pytest.MonkeyPatch, manager: EdgeServerManager) -> list[str]:
    """
    Record the paths a manager calls on its sidecar, below `_call_sidecar`, so that its
    bookkeeping of what changed the host still runs.
    """
    paths: list[str] = []

    async def call(method: str, path: str, **_: Any) -> str:
        paths.append(path)
        return ""

    monkeypatch.setattr(getattr(manager, "_EdgeServerManager__sidecar"), "call", call)  # noqa: B009
    return paths


@pytest.mark.asyncio
async def test_changed_since_reset_follows_sidecar_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        manager = managers[0]
        stub_shell2http(monkeypatch, manager)
        assert manager.changed_since_reset, "A host a previous run may have left dirty starts out changed"

        await manager.reset_to_initial_state()
        assert not manager.changed_since_reset

        await manager._call_sidecar("post", "/collect-logs", changes_state=False)
        assert not manager.changed_since_reset, "Reading the host must not count as changing it"

        await manager.configure_dataset(config_file=write_config(tmp_path, "test.json", 60000))
        assert manager.changed_since_reset


@pytest.mark.asyncio
async def test_reset_all_only_changed_skips_untouched_edge_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configs = [write_config(tmp_path, f"initial{index}.json", 59840 + index) for index in range(2)]
    async with managers_for(configs) as managers:
        paths = [stub_shell2http(monkeypatch, manager) for manager in managers]
        await reset_all_edge_servers(managers)
        await managers[1].set_firewall_rules(deny=["10.0.0.1"])
        for host_paths in paths:
            host_paths.clear()

        await reset_all_edge_servers(managers, only_changed=True)

        assert paths[0] == [], "An Edge Server nothing changed must not be restarted"
        assert "/reset-all-dbs" in paths[1]


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
        patch("cbltest.api.edgeserver.AsyncHTTPClient", FakeSession),
        patch("cbltest.httpclient.ClientSession", autospec=True),
        # A TLS config reads client certificates out of ~/.cbl_certs, which exist only on a
        # machine that has provisioned an Edge Server topology.
        patch("cbltest.api.edgeserver.ssl.create_default_context", autospec=True),
        patch("cbltest.api.edgeserver.TCPConnector", autospec=True),
        # Starting an Edge Server polls it until it answers, which FakeSession cannot serve.
        patch("cbltest.api.edgeservermanager.EdgeServerManager._EdgeServerManager__wait_until_serving", autospec=True),
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
async def test_changed_since_reset_follows_clients_handed_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with fake_session_manager(write_config(tmp_path, "initial.json", 59840)) as manager:
        stub_shell2http(monkeypatch, manager)
        await manager.reset_to_initial_state()
        assert not manager.changed_since_reset, "The client a reset probes with must not count"

        manager.get_admin_client()
        assert manager.changed_since_reset, "A test may start a replication with it, which outlives the test"

        await manager.reset_to_initial_state()
        async with manager.get_anonymous_client():
            assert manager.changed_since_reset


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
            async with manager.get_user_client(get_basic_auth_headers("username8", "password8")):
                pass


@pytest.mark.asyncio
async def test_anonymous_client_sends_no_credentials(tmp_path: Path) -> None:
    async with (
        fake_session_manager(write_config(tmp_path, "initial.json", 59840, users=True)) as manager,
        manager.get_anonymous_client() as client,
    ):
        await client.get_all_dbs()
        assert "Authorization" not in client_session(client).headers


@pytest.mark.asyncio
@pytest.mark.parametrize("users", [True, False])
async def test_admin_client_sends_credentials_only_to_a_config_that_declares_users(tmp_path: Path, users: bool) -> None:
    async with fake_session_manager(write_config(tmp_path, "initial.json", 59840, users=users)) as manager:
        headers = client_session(manager.get_admin_client()).headers
        assert ("Authorization" in headers) == users


def replication(task_id: int, status: str, error: dict[str, Any] | None = None) -> ReplicationStatus:
    return ReplicationStatus.model_validate(
        {"task_id": task_id, "status": status, "source": f"ws://sgw:4984/db{task_id}", "target": "db", "error": error}
    )


OFFLINE = replication(1, "Offline", {"error": "Connection refused", "x-litecore-domain": 2, "x-litecore-code": 111})
STOPPED = replication(2, "Stopped", {"error": "Login required", "x-litecore-domain": 6, "x-litecore-code": 401})


def stub_replicate_list(monkeypatch: pytest.MonkeyPatch, *lists: list[ReplicationStatus]) -> list[int]:
    """
    Answer each ``GET /_replicate`` with the next of ``lists``, then keep repeating the last, and
    poll without waiting.  Returns a list that grows by one entry per poll.
    """
    polls: list[int] = []

    async def all_replication_status(self: EdgeServer) -> list[ReplicationStatus]:
        polls.append(len(polls))
        return lists[min(len(polls) - 1, len(lists) - 1)]

    monkeypatch.setattr(EdgeServer, "all_replication_status", all_replication_status)
    monkeypatch.setattr(tenacity, "wait_fixed", lambda _: tenacity.wait_none())
    return polls


@pytest.mark.asyncio
async def test_start_does_not_poll_replications_for_a_config_without_any(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    polls = stub_replicate_list(monkeypatch, [])
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        stub_sidecar(monkeypatch, managers[0])

        await managers[0].configure_dataset(config_file=write_config(tmp_path, "test.json", 60000))

    assert polls == []


@pytest.mark.asyncio
async def test_start_waits_until_every_configured_replication_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replication that cannot connect is still listed, so it ends the wait like a working one."""
    polls = stub_replicate_list(monkeypatch, [], [OFFLINE], [OFFLINE, STOPPED])
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        stub_sidecar(monkeypatch, managers[0])

        await managers[0].configure_dataset(config_file=write_config(tmp_path, "test.json", 60000, replications=2))

    assert len(polls) == 3


@pytest.mark.asyncio
async def test_restart_on_the_running_config_waits_for_its_replications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        stub_sidecar(monkeypatch, managers[0])
        stub_replicate_list(monkeypatch, [OFFLINE])
        await managers[0].configure_dataset(config_file=write_config(tmp_path, "test.json", 60000, replications=1))
        polls = stub_replicate_list(monkeypatch, [], [OFFLINE])

        await managers[0].start_server()

    assert len(polls) == 2


@pytest.mark.asyncio
async def test_start_times_out_on_a_replication_edge_server_never_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge Server drops a replication it rejects, such as one whose target database is not in the config."""
    stub_replicate_list(monkeypatch, [OFFLINE])
    monkeypatch.setattr(tenacity, "stop_after_delay", lambda _: tenacity.stop_after_attempt(3))
    async with managers_for([write_config(tmp_path, "initial.json", 59840)]) as managers:
        stub_sidecar(monkeypatch, managers[0])

        with pytest.raises(TimeoutError, match="lists 1 of the 2 replications in .*test.json"):
            await managers[0].configure_dataset(config_file=write_config(tmp_path, "test.json", 60000, replications=2))
