"""Tests for the EdgeServer client and EdgeServerConfig, the config file it parses."""

import json
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import tenacity
from aiohttp import web
from aiohttp.test_utils import TestServer
from cbltest.api.edgeserver import EdgeServer, EdgeServerConfig, LiteCoreErrorDomain, ReplicationActivity
from cbltest.api.error import CblEdgeServerBadResponseError, CblTestError
from cbltest.httplog import _HttpLogWriter

HOSTNAME = "es.example.com"
AUDIT_LOG = "/home/ec2-user/audit/EdgeServerAuditLog.txt"


@contextmanager
def no_network() -> Iterator[None]:
    """Keep the sessions an Edge Server client opens off the network."""
    with (
        patch("cbltest.httpclient.ClientSession", autospec=True),
        patch("cbltest.httpclient.DummyCookieJar", autospec=True),
    ):
        yield


def write_config(directory: Path, name: str, config: dict[str, Any]) -> str:
    path = directory / name
    path.write_text(json.dumps(config))
    return str(path)


def test_reads_the_parts_the_framework_needs(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(
        write_config(
            tmp_path,
            "mtls.json",
            {
                "interface": "0.0.0.0:60000",
                "users": "/home/ec2-user/user/users.json",
                "https": {
                    "tls_cert_path": "/cert.pem",
                    "tls_key_path": "/key.pem",
                    "client_cert_path": "/ca.pem",
                },
                "logging": {"audit": {"file": AUDIT_LOG, "enable": "*"}},
            },
        )
    )

    assert config.port == 60000
    assert config.is_tls
    assert config.is_mtls
    assert config.declares_users
    assert config.audit_log == AUDIT_LOG


def test_defaults_where_the_config_is_silent(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(write_config(tmp_path, "bare.json", {}))

    assert config.port == 59840
    assert not config.is_tls
    assert not config.is_mtls
    assert not config.declares_users
    assert config.audit_log is None


def test_tls_without_a_client_certificate_is_not_mtls(tmp_path: Path) -> None:
    config = EdgeServerConfig.load(
        write_config(tmp_path, "tls.json", {"https": {"tls_cert_path": "/cert.pem", "tls_key_path": "/key.pem"}})
    )

    assert config.is_tls
    assert not config.is_mtls


@pytest.mark.parametrize(
    "logging_block",
    [{}, {"console": False}, {"audit": {"enable": "*"}}],
    ids=["no logging keys", "logging without audit", "audit without a file"],
)
def test_no_audit_log_reads_as_none(tmp_path: Path, logging_block: dict) -> None:
    config = EdgeServerConfig.load(write_config(tmp_path, "quiet.json", {"logging": logging_block}))

    assert config.audit_log is None


def test_keeps_the_keys_it_does_not_declare(tmp_path: Path) -> None:
    """Edge Server adds config keys between versions, so an unknown one must not be rejected."""
    config = EdgeServerConfig.load(
        write_config(
            tmp_path,
            "future.json",
            {"databases": {"db": {"path": "/db.cblite2"}}, "a_key_from_a_later_release": 7},
        )
    )

    assert config.model_extra == {
        "databases": {"db": {"path": "/db.cblite2"}},
        "a_key_from_a_later_release": 7,
    }


def test_reads_json5(tmp_path: Path) -> None:
    """Edge Server accepts JSON5, so a config may carry comments and trailing commas."""
    path = tmp_path / "json5.json"
    path.write_text('{\n  // the port a test picked\n  "interface": "0.0.0.0:60001",\n}\n')

    assert EdgeServerConfig.load(str(path)).port == 60001


def test_audit_log_path_comes_from_the_running_config(tmp_path: Path) -> None:
    config_file = write_config(tmp_path, "audit.json", {"logging": {"audit": {"file": AUDIT_LOG}}})
    with no_network():
        client = EdgeServer(HOSTNAME, config_file=config_file)

    assert client.audit_log_path == AUDIT_LOG


def test_audit_log_path_raises_without_an_audit_log(tmp_path: Path) -> None:
    config_file = write_config(tmp_path, "quiet.json", {"logging": {"console": False}})
    with no_network():
        client = EdgeServer(HOSTNAME, config_file=config_file)

    with pytest.raises(CblTestError, match="declares no audit log"):
        _ = client.audit_log_path


@pytest.mark.asyncio
async def test_failure_writes_an_error_and_logs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A request that gets no usable response still leaves a record of why."""
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")

    async def not_json(request: web.Request) -> web.Response:
        return web.Response(text="not json", content_type="application/json")

    app = web.Application()
    app.router.add_get("/", not_json)
    server = TestServer(app)
    await server.start_server()
    config_file = write_config(tmp_path, "local.json", {"interface": f"{server.host}:{server.port}"})
    client = EdgeServer(server.host, config_file=config_file)
    try:
        with caplog.at_level(logging.ERROR, logger="CBL"), pytest.raises(ValueError):
            await client._send_request("get", "/")
    finally:
        await client.close()
        await server.close()

    errors = list((tmp_path / "http_log").rglob("*_error.txt"))
    assert len(errors) == 1
    assert errors[0].read_text().startswith(f"Edge Server [{server.host}] <- GET / failed: ")
    assert [r.getMessage() for r in caplog.records] == [errors[0].read_text()]


def replication(status: str, **extra: Any) -> dict[str, Any]:
    return {"task_id": 1, "status": status, "source": "ws://sgw/db", "target": "db", "age_secs": 0, **extra}


@asynccontextmanager
async def replicate_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, responses: Sequence[dict[str, Any] | None]
) -> AsyncIterator[EdgeServer]:
    """
    An Edge Server whose ``/_replicate/1`` answers with each of ``responses`` in turn, then
    keeps repeating the last one.  None answers 404, as Edge Server does for an unlisted task.
    """
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")
    monkeypatch.setattr(tenacity, "wait_fixed", lambda _: tenacity.wait_none())
    remaining = list(responses)

    async def status(request: web.Request) -> web.Response:
        body = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return web.json_response({"error": "Not Found"}, status=404) if body is None else web.json_response(body)

    async def start(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "task_id": 3}, status=202)

    app = web.Application()
    app.router.add_get("/_replicate/1", status)
    app.router.add_post("/_replicate", start)
    server = TestServer(app)
    await server.start_server()
    config_file = write_config(tmp_path, "local.json", {"interface": f"{server.host}:{server.port}"})
    client = EdgeServer(server.host, config_file=config_file)
    try:
        yield client
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_wait_for_idle_returns_once_the_replication_is_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [replication("Connecting"), replication("Active"), replication("Idle")]
    async with replicate_server(tmp_path, monkeypatch, responses) as client:
        result = await client.wait_for_idle(replication_id=1)
    assert result.status == ReplicationActivity.IDLE


@pytest.mark.asyncio
async def test_wait_for_idle_fails_fast_on_a_stopped_replication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {"error": "Session Invalid", "x-litecore-domain": 6, "x-litecore-code": 401}
    responses = [replication("Connecting"), replication("Stopped", error=error)]
    async with replicate_server(tmp_path, monkeypatch, responses) as client:
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await client.wait_for_idle(replication_id=1, timeout=60)
    assert e.value.code == 401


@pytest.mark.asyncio
async def test_wait_for_replication_error_returns_the_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    error = {"error": "Invalid login", "x-litecore-domain": 6, "x-litecore-code": 401}
    responses = [replication("Idle"), replication("Stopped", error=error)]
    async with replicate_server(tmp_path, monkeypatch, responses) as client:
        result = await client.wait_for_replication_error(
            replication_id=1, domain=LiteCoreErrorDomain.WEBSOCKET, code=401
        )
    assert result.message == "Invalid login"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stopped",
    [
        replication("Stopped"),
        replication("Stopped", error={"error": "Forbidden", "x-litecore-domain": 6, "x-litecore-code": 403}),
        replication("Stopped", error={"error": "SSL EOF", "x-litecore-domain": 5, "x-litecore-code": 6}),
    ],
    ids=["no_error", "other_code", "other_domain"],
)
async def test_wait_for_replication_error_rejects_a_different_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stopped: dict
) -> None:
    async with replicate_server(tmp_path, monkeypatch, [stopped]) as client:
        with pytest.raises(AssertionError, match="without a WEBSOCKET 401 error"):
            await client.wait_for_replication_error(replication_id=1, domain=LiteCoreErrorDomain.WEBSOCKET, code=401)


@pytest.mark.asyncio
async def test_wait_for_replication_status_retries_until_the_replication_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with replicate_server(tmp_path, monkeypatch, [None, replication("Idle")]) as client:
        result = await client.wait_for_idle(replication_id=1)
    assert result.status == ReplicationActivity.IDLE


@pytest.mark.asyncio
async def test_wait_for_replication_status_times_out_on_an_unlisted_replication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with replicate_server(tmp_path, monkeypatch, [None]) as client:
        with pytest.raises(TimeoutError, match="is not listed"):
            await client.wait_for_idle(replication_id=1, timeout=0.2)


@pytest.mark.asyncio
async def test_wait_for_replication_status_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with replicate_server(tmp_path, monkeypatch, [replication("Active")]) as client:
        with pytest.raises(TimeoutError, match="is Active"):
            await client.wait_for_idle(replication_id=1, timeout=0.2)


@pytest.mark.asyncio
async def test_start_replication_returns_the_task_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with replicate_server(tmp_path, monkeypatch, [None]) as client:
        task_id = await client.start_replication("ws://sgw/db", "db", "user", "pass", False, True)
    assert task_id == 3
