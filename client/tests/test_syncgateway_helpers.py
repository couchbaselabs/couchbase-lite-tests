"""Unit tests for SyncGateway helper plumbing: _send_request's error reporting,
get_all_databases_verbose's one-pass list validation, and wait_for_db_online's
timeout diagnostics.

These exercise the real aiohttp ClientSession/ClientResponse machinery against
a real (loopback) aiohttp test server, rather than mocking the HTTP layer. The
only stand-in is the synchronous `requests.get` call SyncGateway.__init__ makes
against SGW's /_config endpoint during bootstrap, which is orthogonal to the
async helpers under test here.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import DatabaseState, SyncGateway
from cbltest.httplog import _HttpLogWriter
from pydantic import ValidationError


class _FakeConfigResponse:
    """Stands in for requests.Response from the sync GET /_config bootstrap
    call in SyncGateway.__init__ - unrelated to the async helpers under test."""

    def json(self) -> dict:
        return {"bootstrap": {"server": "rosmar"}}

    def raise_for_status(self) -> None:
        return None


@pytest_asyncio.fixture(loop_scope="function")
async def sync_gateway(monkeypatch, tmp_path) -> AsyncIterator[tuple[SyncGateway, list[dict]]]:
    """A SyncGateway backed by a real aiohttp test server, so _send_request and
    everything built on it (get_all_databases_verbose, wait_for_db_online, ...) runs
    against real ClientSession/ClientResponse objects. `specs` controls what the
    server responds with: while it holds more than one entry, each request pops
    the next one; with exactly one entry left, that response repeats (useful for
    polling loops like wait_for_db_online)."""
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")
    monkeypatch.setattr(
        "cbltest.api.syncgateway.requests.get",
        lambda *args, **kwargs: _FakeConfigResponse(),
    )

    specs: list[dict] = []

    async def handle(request: web.Request) -> web.Response:
        spec = specs.pop(0) if len(specs) > 1 else specs[0]
        if "text" in spec:
            return web.Response(
                status=spec["status"],
                text=spec["text"],
                content_type=spec.get("content_type", "text/plain"),
            )
        return web.json_response(spec["json"], status=spec["status"])

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handle)
    server = TestServer(app)
    await server.start_server()
    assert server.port is not None

    sg = SyncGateway(url=server.host, username="user", password="pass", port=server.port)

    yield sg, specs

    await sg.close()
    await server.close()


class TestSendRequest:
    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_success(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [{"status": 200, "json": {"ok": True}}]

        result = await sg._send_request("get", "/_status")

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_error_includes_json_response_body(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 503,
                "json": {"error": "Service Unavailable", "reason": "db offline"},
            }
        ]

        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._send_request("get", "/db/")

        message = str(exc_info.value)
        assert "get /db/ returned 503" in message
        assert "Service Unavailable" in message
        assert "db offline" in message

    @pytest.mark.asyncio
    async def test_error_includes_non_json_response_body(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 500,
                "text": "internal server error",
                "content_type": "text/plain",
            }
        ]

        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._send_request("get", "/db/")

        assert "internal server error" in str(exc_info.value)


class TestGetAllDatabasesVerbose:
    @pytest.mark.asyncio
    async def test_parses_valid_entries(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [
                    {"bucket": "b1", "db_name": "db1", "state": "Online"},
                    {"bucket": "b2", "db_name": "db2", "state": "Starting"},
                ],
            }
        ]

        entries = await sg.get_all_databases_verbose()

        assert "db1" in entries
        assert "db2" in entries
        assert entries["db1"].state == DatabaseState.ONLINE
        assert entries["db2"].state == DatabaseState.STARTING

    @pytest.mark.asyncio
    async def test_validates_whole_list_in_one_pass(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [
                    {"bucket": "b1", "db_name": "db1", "state": "NotARealState"},
                    {"bucket": "b2", "db_name": "db2", "state": "Online"},
                    {"bucket": "b3", "db_name": "db3", "state": "AlsoNotReal"},
                ],
            }
        ]

        with pytest.raises(ValidationError) as exc_info:
            await sg.get_all_databases_verbose()

        message = str(exc_info.value)
        # Both bad entries (index 0 and index 2) are reported by a single
        # validation pass, not just the first one encountered.
        assert "2 validation errors" in message
        assert "0.state" in message
        assert "2.state" in message


class TestWaitForDbUp:
    @pytest.mark.asyncio
    async def test_succeeds_when_database_is_online(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [{"bucket": "b1", "db_name": "db1", "state": "Online"}],
            }
        ]

        await sg._wait_for_db_online("db1", max_retries=1, retry_delay=0)

    @pytest.mark.asyncio
    async def test_timeout_reports_last_seen_state(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [{"bucket": "b1", "db_name": "db1", "state": "Starting"}],
            }
        ]

        with pytest.raises(TimeoutError) as exc_info:
            await sg._wait_for_db_online("db1", max_retries=2, retry_delay=0)

        assert "state=<DatabaseState.STARTING" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_reports_database_error(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [
                    {
                        "bucket": "b1",
                        "db_name": "db1",
                        "state": "Offline",
                        "database_error": {
                            "error_code": 500,
                            "error_message": "vBucket UUID mismatch",
                        },
                    }
                ],
            }
        ]

        with pytest.raises(TimeoutError) as exc_info:
            await sg._wait_for_db_online("db1", max_retries=2, retry_delay=0)

        message = str(exc_info.value)
        assert "error_code=500" in message
        assert "vBucket UUID mismatch" in message

    @pytest.mark.asyncio
    async def test_timeout_reports_database_never_seen(self, sync_gateway):
        sg, specs = sync_gateway
        specs[:] = [{"status": 200, "json": []}]

        with pytest.raises(TimeoutError) as exc_info:
            await sg._wait_for_db_online("db1", max_retries=2, retry_delay=0)

        assert "database not present in /_all_dbs?verbose=true" in str(exc_info.value)
