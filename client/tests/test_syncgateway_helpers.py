"""Unit tests for SyncGateway helper plumbing: _send_request's error reporting,
get_all_databases_verbose's one-pass list validation, and wait_for_db_online's
timeout diagnostics.

These exercise the real aiohttp ClientSession/ClientResponse machinery against
a real (loopback) aiohttp test server, rather than mocking the HTTP layer. The
only stand-in is the synchronous `requests.get` call SyncGateway.__init__ makes
against SGW's /_config endpoint during bootstrap, which is orthogonal to the
async helpers under test here.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator
from json import loads
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
import tenacity
from aiohttp import encode_basic_auth, web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblSyncGatewayBadResponseError, CblTestError
from cbltest.api.syncgateway import (
    ChangesResponse,
    DatabaseConfig,
    DatabaseState,
    DocumentUpdateEntry,
    ScopeConfig,
    SyncGateway,
    SyncGatewayUserClient,
)
from cbltest.httpclient import AsyncHTTPClient
from cbltest.httplog import _HttpLogWriter
from cbltest.utils import async_retry_assert
from pydantic import ValidationError

# (SyncGateway, response specs the test server serves, headers the server saw)
SyncGatewayFixture = tuple[SyncGateway, list[dict], list[dict[str, str]]]

# Key under which each `received` entry carries the request target (path plus query string).
_URL_KEY = "__url__"

# Key under which each `received` entry carries the request body, as text.
_BODY_KEY = "__body__"


class _FakeConfigResponse:
    """Stands in for requests.Response from the sync GET /_config bootstrap
    call in SyncGateway.__init__ - unrelated to the async helpers under test."""

    def json(self) -> dict:
        return {"bootstrap": {"server": "rosmar"}}

    def raise_for_status(self) -> None:
        return None


@pytest_asyncio.fixture(loop_scope="function")
async def sync_gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[SyncGatewayFixture]:
    """A SyncGateway backed by a real aiohttp test server, so _send_request and
    everything built on it (get_all_databases_verbose, wait_for_db_online, ...) runs
    against real ClientSession/ClientResponse objects. `specs` controls what the
    server responds with: while it holds more than one entry, each request pops
    the next one; with exactly one entry left, that response repeats (useful for
    polling loops like wait_for_db_online). `received` accumulates the headers of
    every request the server saw (plus its target under `_URL_KEY` and its body under
    `_BODY_KEY`), so tests can assert on what went out on the wire."""
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")
    monkeypatch.setattr(
        "cbltest.api.syncgateway.requests.get",
        lambda *args, **kwargs: _FakeConfigResponse(),
    )

    specs: list[dict] = []
    received: list[dict[str, str]] = []

    async def handle(request: web.Request) -> web.Response:
        received.append(dict(request.headers) | {_URL_KEY: str(request.rel_url), _BODY_KEY: await request.text()})
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

    yield sg, specs, received

    await sg.close()
    await server.close()


class TestSessionAuth:
    """Sessions carry credentials as an Authorization header, which has to reach the
    wire alongside the per-request headers _send_request sets."""

    @pytest.mark.asyncio
    async def test_admin_session_sends_auth_header(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"ok": True}}]

        await sg._send_request("put", "/db/_config", payload=DatabaseConfig(bucket="bucket"))

        assert received[0].get("Authorization") == encode_basic_auth("user", "pass", "ascii")
        assert received[0].get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    async def test_create_session_sets_the_auth_header_only_when_given_credentials(
        self, sync_gateway: SyncGatewayFixture
    ) -> None:
        """The public-port reachability probe in start_sgw builds an anonymous session, so
        _create_session has to leave the Authorization header off when handed no credentials."""
        sg, _, _ = sync_gateway

        with patch("cbltest.api.syncgateway.AsyncHTTPClient", wraps=AsyncHTTPClient) as client_class:
            async with sg._create_session(sg.secure, sg.scheme, sg.hostname, sg.public_port, None):
                assert "Authorization" not in (client_class.call_args.kwargs["headers"] or {})

            auth_header = encode_basic_auth("alice", "s3cret", "ascii")
            async with sg._create_session(sg.secure, sg.scheme, sg.hostname, sg.port, {"Authorization": auth_header}):
                assert client_class.call_args.kwargs["headers"]["Authorization"] == auth_header

    @pytest.mark.asyncio
    async def test_user_client_get_document_revision_authenticates_as_given_user(
        self, sync_gateway: SyncGatewayFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"_id": "doc1", "_rev": "1-abc", "type": "test"}}]

        # A user client talks to the public port, so redirect its session to the test
        # server while leaving the credentials it builds alone.
        create_session = sg._create_session
        monkeypatch.setattr(
            SyncGatewayUserClient,
            "_create_session",
            lambda self, secure, scheme, url, port, headers=None: create_session(secure, scheme, url, sg.port, headers),
        )

        async with sg.get_user_client("alice", "s3cret") as user_client:
            doc = await user_client.get_document("db1", "doc1", revision="1-abc")

        assert doc is not None
        assert doc.revid == "1-abc"
        assert doc.body == {"type": "test"}
        assert received[0][_URL_KEY] == "/db1._default._default/doc1?rev=1-abc"
        # Authenticated as the passed-in user, not as the admin the sg session was built with.
        assert received[0].get("Authorization") == encode_basic_auth("alice", "s3cret", "ascii")


class TestSendRequest:
    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_success(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"ok": True}}]

        result = await sg._send_request("get", "/_status")

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_error_includes_json_response_body(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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
        # Also available on its own, so callers matching on it needn't parse the message.
        assert loads(exc_info.value.body) == {"error": "Service Unavailable", "reason": "db offline"}

    @pytest.mark.asyncio
    async def test_error_includes_non_json_response_body(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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

    @pytest.mark.asyncio
    async def test_error_includes_the_query_string(self, sync_gateway: SyncGatewayFixture) -> None:
        """The query string is what says which variant of an endpoint was called (request_plus,
        _doc_ids filtered, ...), so it has to reach the log and the error alongside the path."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 500, "json": {"error": "boom"}}]

        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._send_request("get", "/db/_changes", params={"request_plus": "true", "filter": "_doc_ids"})

        assert "get /db/_changes?request_plus=true&filter=_doc_ids returned 500" in str(exc_info.value)


class TestGetAllDatabasesVerbose:
    @pytest.mark.asyncio
    async def test_parses_valid_entries(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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
    async def test_validates_whole_list_in_one_pass(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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


class TestGetAllDocuments:
    @pytest.mark.asyncio
    async def test_asks_for_and_reports_both_revisions(self, sync_gateway: SyncGatewayFixture) -> None:
        """Sync Gateway 4.0 and later report a CV alongside the revid, so a row carries both and
        the caller picks the one it wants."""
        sg, specs, received = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": {
                    "total_rows": 1,
                    "rows": [{"key": "doc1", "id": "doc1", "value": {"rev": "1-abc", "cv": "18d3@src"}}],
                },
            }
        ]

        response = await sg.get_all_documents("db")

        assert "show_cv=true" in received[0][_URL_KEY]
        row = response.rows[0]
        assert row.revid == "1-abc"
        assert row.cv == "18d3@src"

    @pytest.mark.asyncio
    async def test_reports_no_cv_when_the_server_sends_none(self, sync_gateway: SyncGatewayFixture) -> None:
        """Edge Server shares this response class, and it answers with revids alone."""
        sg, specs, _ = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": {"total_rows": 1, "rows": [{"key": "doc1", "id": "doc1", "value": {"rev": "1-abc"}}]},
            }
        ]

        response = await sg.get_all_documents("db")

        assert response.rows[0].cv is None
        assert response.revmap == {"doc1": "1-abc"}


class TestWaitForDbUp:
    @pytest.mark.asyncio
    async def test_succeeds_when_database_is_online(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [{"bucket": "b1", "db_name": "db1", "state": "Online"}],
            }
        ]

        await sg._wait_for_db_online("db1", max_retries=1, retry_delay=0)

        # Wait for the node to serve the database at all, then for it to be online there.
        assert [entry[_URL_KEY] for entry in received] == [
            "/_all_dbs?verbose=true",
            "/_all_dbs?verbose=true",
        ]

    @pytest.mark.asyncio
    async def test_raises_when_polling_fails(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": [{"bucket": "b1", "db_name": "db1", "state": "Online"}]},
            {"status": 403, "json": {"error": "Forbidden", "reason": ""}},
        ]

        # Only a failed assertion is retried, so an HTTP error from the poll itself
        # surfaces rather than retrying to a timeout.
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._wait_for_db_online("db1", max_retries=2, retry_delay=0)

        assert exc_info.value.code == 403

    @pytest.mark.asyncio
    async def test_timeout_reports_last_seen_state(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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
    async def test_timeout_reports_database_error(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
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
    async def test_timeout_reports_database_never_seen(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": []}]

        with pytest.raises(TimeoutError) as exc_info:
            await sg._wait_for_db_online("db1", max_retries=2, retry_delay=0)

        assert "does not serve database db1 (not present in /_all_dbs?verbose=true)" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_user(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"ok": True}},  # delete_user
            {"status": 201, "json": {"ok": True}},  # add_user
        ]
        await sg.reset_user("db1", "test_user", "test_pass", ["channel1"])

    @pytest.mark.asyncio
    async def test_create_user_client_context_manager(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        # Specs for delete_user and add_user (via reset_user) during context enter
        specs[:] = [
            {"status": 200, "json": {"ok": True}},  # delete_user
            {"status": 201, "json": {"ok": True}},  # add_user
        ]

        async with sg.create_user_client("db1", "test_user", "test_pass", ["channel1"]) as client:
            assert client.hostname == sg.hostname
            assert client.secure == sg.secure
            assert not client._SyncGatewayBase__session.closed  # ty: ignore[unresolved-attribute]

        assert client._SyncGatewayBase__session.closed  # ty: ignore[unresolved-attribute]

    @pytest.mark.asyncio
    async def test_get_user_client_makes_no_admin_calls(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, _, received = sync_gateway

        async with sg.get_user_client("test_user", "test_pass") as client:
            assert not client._SyncGatewayBase__session.closed  # ty: ignore[unresolved-attribute]

        assert client._SyncGatewayBase__session.closed  # ty: ignore[unresolved-attribute]
        # Unlike create_user_client, this does not create the user.
        assert received == []


class TestDatabaseConfigSentinel:
    """A write stamps a sentinel into a setting Sync Gateway stores but does not act on,
    and the wait passes once a node reports that sentinel back."""

    @pytest.mark.asyncio
    async def test_put_database_stamps_the_sentinel_it_returns(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 201, "json": {}}]

        sentinel = await sg._put_database("db1", DatabaseConfig(bucket="b1"))

        assert loads(received[0][_BODY_KEY]) == {"bucket": "b1", "feed_type": sentinel}

    @pytest.mark.asyncio
    async def test_update_database_config_stamps_a_new_sentinel(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 201, "json": {}}]
        config = DatabaseConfig(bucket="b1")

        first = await sg._update_database_config("db1", config)
        second = await sg._update_database_config("db1", config)

        assert first != second
        assert loads(received[1][_BODY_KEY])["feed_type"] == second
        # The write stamps the sentinel into the config it was handed.
        assert config.feed_type == second

    @pytest.mark.asyncio
    async def test_wait_succeeds_when_the_node_reports_the_sentinel(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"bucket": "b1", "name": "db1", "feed_type": "abc123"}}]

        await sg._wait_for_database_config("db1", "abc123", max_retries=1, retry_delay=0)

        assert [entry[_URL_KEY] for entry in received] == ["/db1/_config?include_runtime=true"]

    @pytest.mark.asyncio
    async def test_wait_polls_until_the_node_loads_the_database(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [
            {"status": 403, "json": {"error": "Forbidden", "reason": ""}},
            {"status": 200, "json": {"bucket": "b1", "name": "db1", "feed_type": "abc123"}},
        ]

        # A node picks up a database another node created on its next config poll, and
        # rejects requests for it until then.
        await sg._wait_for_database_config("db1", "abc123", max_retries=2, retry_delay=0)

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_wait_times_out_while_the_node_runs_an_older_config(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"bucket": "b1", "name": "db1", "feed_type": "older"}}]

        with pytest.raises(TimeoutError) as exc_info:
            await sg._wait_for_database_config("db1", "abc123", max_retries=2, retry_delay=0)

        message = str(exc_info.value)
        assert "is not running config abc123 for db1" in message
        assert "it is running 'older'" in message

    @pytest.mark.asyncio
    async def test_wait_reports_a_failure_that_is_not_about_the_database(
        self, sync_gateway: SyncGatewayFixture
    ) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 500, "json": {"error": "Internal Server Error", "reason": "boom"}}]

        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._wait_for_database_config("db1", "abc123", max_retries=2, retry_delay=0)

        assert exc_info.value.code == 500


class TestDatabaseConfig:
    def test_init_with_nested_config(self) -> None:
        payload = DatabaseConfig(
            bucket="travel-sample",
            scopes={"_default": ScopeConfig(collections={"_default": {"sync": "function(doc){}"}})},
        )
        assert payload.bucket == "travel-sample"
        assert payload.scopes is not None
        assert list(payload.scopes.keys()) == ["_default"]
        assert payload.scopes["_default"].collections == {"_default": {"sync": "function(doc){}"}}
        assert payload.to_json() == {
            "bucket": "travel-sample",
            "scopes": {"_default": {"collections": {"_default": {"sync": "function(doc){}"}}}},
        }

    def test_init_with_flat_config(self) -> None:
        payload = DatabaseConfig(
            bucket="test-bucket",
            scopes={"s1": ScopeConfig(collections={"c1": {}})},
        )
        assert payload.bucket == "test-bucket"
        assert payload.scopes is not None
        assert list(payload.scopes.keys()) == ["s1"]
        assert payload.scopes["s1"].collections == {"c1": {}}

    def test_init_with_kwargs(self) -> None:
        payload = DatabaseConfig(bucket="kw-bucket", sync="function(doc){}")
        assert payload.bucket == "kw-bucket"
        assert payload.sync == "function(doc){}"
        assert payload.to_json() == {
            "bucket": "kw-bucket",
            "sync": "function(doc){}",
        }

    def test_invalid_input(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseConfig(scopes="not_a_dict")  # ty: ignore[invalid-argument-type]


MISSING_BUCKET_ENTRY_REASON = 'couldn\'t remove database "db2" from bucket "data-bucket-2": Not Found'


def _missing_bucket_entry_500() -> dict:
    """The 500 SGW returns when a database's registry entry is already gone (CBG-5731)."""
    return {"status": 500, "json": {"error": "Internal Server Error", "reason": MISSING_BUCKET_ENTRY_REASON}}


def _all_dbs(*db_names: str) -> dict:
    return {"status": 200, "json": [{"db_name": name, "bucket": "b", "state": "Online"} for name in db_names]}


class TestDeleteDatabase:
    """The delete waits for the node to stop serving the database, and still reports 500s
    that mean anything else."""

    @pytest.mark.asyncio
    async def test_waits_out_the_node_on_missing_bucket_entry(
        self, sync_gateway: SyncGatewayFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CBG-5731 500 means the node is still serving it, so the delete must wait."""
        sg, specs, received = sync_gateway
        wait_for_database_gone = sg._wait_for_database_gone
        monkeypatch.setattr(
            sg,
            "_wait_for_database_gone",
            lambda db_name: wait_for_database_gone(db_name, retry_delay=0),
        )
        specs[:] = [
            _missing_bucket_entry_500(),
            _all_dbs("db2"),  # still serving it
            _all_dbs("db2"),
            _all_dbs(),  # config poll caught up
        ]

        await sg._delete_database("db2")

        assert len(received) == 4  # The DELETE plus the polls it took.

    @pytest.mark.asyncio
    async def test_raises_if_the_node_never_stops_serving_the_database(self, sync_gateway: SyncGatewayFixture) -> None:
        """A node that never catches up is a failure. Exercised on the wait, which owns the
        budget and which the delete awaits."""
        sg, specs, _ = sync_gateway
        specs[:] = [_all_dbs("db2")]

        with pytest.raises(TimeoutError, match="still serving database db2"):
            await sg._wait_for_database_gone("db2", timeout=0.2, retry_delay=0)

    @pytest.mark.asyncio
    async def test_retries_then_raises_on_other_500(
        self, sync_gateway: SyncGatewayFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 500, "json": {"error": "Internal Server Error", "reason": "boom"}}]

        async def no_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)

        with pytest.raises(CblSyncGatewayBadResponseError):
            await sg._delete_database("db2")

        assert len(received) == 4  # Initial attempt plus three retries.


class TestGetLastSequence:
    """The sequence a wait bounds its feed read with comes from GET /{db}/."""

    @pytest.mark.asyncio
    async def test_reads_update_seq(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"db_name": "db", "update_seq": 76, "committed_update_seq": 76}}]

        assert await sg.get_last_sequence("db") == 76
        assert received[0][_URL_KEY] == "/db/"

    @pytest.mark.asyncio
    async def test_rejects_a_response_without_a_sequence(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"db_name": "db"}}]

        with pytest.raises(AssertionError, match="Unusable update_seq"):
            await sg.get_last_sequence("db")


class TestWaitForCachingFeed:
    """update_document(wait_for_caching_feed=True) has to read the unfiltered changes feed.

    Sync Gateway only honours `request_plus` there: `RequestPlusSeq` is consumed by
    `SimpleMultiChangesFeed`, while supplying `doc_ids` routes the request to
    `DocIDChangesFeed`, which reads each document straight out of the bucket and never waits
    for the channel cache.  Asking for both silently produced no wait at all.
    """

    @staticmethod
    def _record_get_changes(sg: SyncGateway, calls: list[dict], deleted: bool = False) -> None:
        """Record how get_changes was called, binding positional arguments to their names.

        `doc_ids` is the fifth positional parameter of `get_changes`, so a guard that only
        inspected **kwargs would pass even if it were being supplied.
        """
        signature = inspect.signature(SyncGateway.get_changes)

        async def fake_get_changes(*args: object, **kwargs: object) -> ChangesResponse:
            bound = signature.bind(sg, *args, **kwargs)
            calls.append({k: v for k, v in bound.arguments.items() if k != "self"})
            entry: dict = {"seq": 5, "id": "doc1", "changes": [{"rev": "2-abc"}]}
            if deleted:
                entry["deleted"] = True
            return ChangesResponse({"results": [entry], "last_seq": "5"})

        # An instance attribute, so only this SyncGateway is affected.
        sg.get_changes = fake_get_changes  # ty: ignore[invalid-assignment]

    @pytest.mark.asyncio
    async def test_waits_on_the_unfiltered_feed(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.update_document("db", "doc1", {"foo": "bar"}, "1-abc", wait_for_caching_feed=True)

        assert len(calls) == 1
        assert calls[0].get("request_plus") is True, "request_plus is what does the waiting"
        assert "doc_ids" not in calls[0], (
            "a _doc_ids feed is served from the bucket, not the channel cache, and silently "
            "ignores request_plus - so passing it here means no wait happens"
        )
        assert doc.seq == 5, "the sequence should come from the entry matching the revision written"

    @pytest.mark.asyncio
    async def test_create_waits_on_the_unfiltered_feed(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.create_document("db", "doc1", {"foo": "bar"}, wait_for_caching_feed=True)

        assert len(calls) == 1
        assert calls[0].get("request_plus") is True
        assert "doc_ids" not in calls[0]
        assert doc.seq == 5

    @pytest.mark.asyncio
    async def test_create_does_not_read_the_feed_by_default(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.create_document("db", "doc1", {"foo": "bar"})

        assert calls == []
        assert all(entry[_URL_KEY] != "/db/" for entry in received), "no wait means no sequence to read"
        with pytest.raises(CblTestError, match="No sequence recorded"):
            _ = doc.seq

    @pytest.mark.asyncio
    async def test_delete_waits_for_the_tombstone(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 200, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        calls: list[dict] = []
        self._record_get_changes(sg, calls, deleted=True)

        tombstone = await sg.delete_document("doc1", "1-abc", "db", wait_for_caching_feed=True)

        assert len(calls) == 1
        assert calls[0].get("request_plus") is True
        assert "doc_ids" not in calls[0]
        assert tombstone.tombstone is True
        assert tombstone.seq == 5

    @pytest.mark.asyncio
    async def test_delete_does_not_settle_for_a_live_revision(self, sync_gateway: SyncGatewayFixture) -> None:
        """A feed still showing the document alive must not satisfy a wait for its deletion."""
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 200, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        # deleted=False: the tombstone has not reached the cache yet.
        self._record_get_changes(sg, [], deleted=False)

        with pytest.raises(AssertionError, match="superseded"):
            await sg.delete_document("doc1", "1-abc", "db", wait_for_caching_feed=True)

    @pytest.mark.asyncio
    async def test_delete_does_not_read_the_feed_by_default(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        tombstone = await sg.delete_document("doc1", "1-abc", "db")

        assert calls == []
        assert tombstone.tombstone is True
        with pytest.raises(CblTestError, match="No sequence recorded"):
            _ = tombstone.seq

    @pytest.mark.asyncio
    async def test_the_pre_write_sequence_bounds_the_feed_read(self, sync_gateway: SyncGatewayFixture) -> None:
        """Writing in a loop, each wait reads only what arrived after the write it is waiting on."""
        sg, specs, received = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        await sg.create_document("db", "doc1", {"foo": "bar"}, wait_for_caching_feed=True)

        assert received[0][_URL_KEY] == "/db/", "the sequence has to be read before the write, not after"
        assert calls[0].get("since") == 41

    @pytest.mark.asyncio
    async def test_feed_body_is_kept_out_of_the_http_log(self, sync_gateway: SyncGatewayFixture) -> None:
        """The feed is read to find one document, so its body is noise in the log."""
        sg, specs, _ = sync_gateway
        specs[:] = [
            {"status": 200, "json": {"update_seq": 41}},
            {"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}},
        ]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        await sg.create_document("db", "doc1", {"foo": "bar"}, wait_for_caching_feed=True)

        assert calls[0].get("log_response") is False

    @pytest.mark.asyncio
    async def test_no_feed_read_when_not_requested(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        await sg.update_document("db", "doc1", {"foo": "bar"}, "1-abc")

        assert calls == [], "the default must not pay for a changes feed read"

    @pytest.mark.asyncio
    async def test_read_waits_on_the_unfiltered_feed(self, sync_gateway: SyncGatewayFixture) -> None:
        """A read imports a document Couchbase Server wrote, so it has a cache to wait for too."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"_id": "doc1", "_rev": "2-abc", "foo": "bar"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.get_document("db", "doc1", wait_for_caching_feed=True)

        assert len(calls) == 1
        assert calls[0].get("request_plus") is True
        assert "doc_ids" not in calls[0]
        assert doc.seq == 5

    @pytest.mark.asyncio
    async def test_bulk_update_waits_on_the_last_revision(self, sync_gateway: SyncGatewayFixture) -> None:
        """The last write's sequence covers the earlier ones, so only it is read back."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": [{"id": "doc0", "rev": "2-aaa"}, {"id": "doc1", "rev": "2-abc"}]}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        await sg.update_documents(
            "db",
            [
                DocumentUpdateEntry("doc0", None, {"foo": "bar"}),
                DocumentUpdateEntry("doc1", None, {"foo": "bar"}),
            ],
            wait_for_caching_feed=True,
        )

        assert len(calls) == 1, "one wait on the newest revision covers the whole batch"
        assert calls[0].get("request_plus") is True

    @pytest.mark.asyncio
    async def test_bulk_update_waits_for_a_tombstone(self, sync_gateway: SyncGatewayFixture) -> None:
        """A batch can end on a deletion, which the feed reports as deleted rather than live."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": [{"id": "doc1", "rev": "2-abc"}]}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls, deleted=True)

        await sg.update_documents(
            "db",
            [DocumentUpdateEntry("doc1", "1-abc", {"_deleted": True})],
            wait_for_caching_feed=True,
        )

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_bulk_update_fails_on_a_rejected_write(self, sync_gateway: SyncGatewayFixture) -> None:
        """_bulk_docs answers 201 even for writes it rejected, so the entries have to be checked."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": [{"id": "doc0", "error": "conflict", "status": 409}]}]
        self._record_get_changes(sg, [])

        with pytest.raises(CblSyncGatewayBadResponseError, match="conflict"):
            await sg.update_documents("db", [DocumentUpdateEntry("doc0", None, {"foo": "bar"})])


class TestWaitForDocuments:
    """wait_for_documents has to read the unfiltered changes feed, for the same reason
    wait_for_caching_feed does: `_doc_ids` routes the request to `DocIDChangesFeed`, which
    reads each document straight out of the bucket and so reports documents a replicator
    still cannot see.  Reading the whole feed on every poll is quadratic over a long wait,
    so each poll resumes from the previous one's `last_seq` and the entries matched so far
    are carried across polls.
    """

    @pytest.fixture
    def fast_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Collapse the helper's 2s/60s retry policy so a poll loop runs at test speed."""

        async def fast(function: object, wait: object, stop: object) -> object:
            return await async_retry_assert(
                function,  # ty: ignore[invalid-argument-type]
                tenacity.wait_fixed(0),
                tenacity.stop_after_attempt(4),
            )

        monkeypatch.setattr("cbltest.api.syncgateway.async_retry_assert", fast)

    @staticmethod
    def _page(last_seq: str, *entries: dict) -> dict:
        return {"status": 200, "json": {"results": list(entries), "last_seq": last_seq}}

    @staticmethod
    def _entry(seq: int, doc_id: str, deleted: bool = False, removed: list[str] | None = None) -> dict:
        entry: dict = {"seq": seq, "id": doc_id, "changes": [{"rev": f"{seq}-abc"}]}
        if deleted:
            entry["deleted"] = True
        if removed:
            entry["removed"] = removed
        return entry

    @pytest.mark.asyncio
    async def test_reads_the_unfiltered_feed(self, sync_gateway: SyncGatewayFixture, fast_retries: None) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [self._page("2", self._entry(1, "doc1"), self._entry(2, "doc2"))]

        found = await sg.wait_for_documents("db", ["doc1", "doc2"])

        assert sorted(found) == ["doc1", "doc2"]
        assert found["doc2"].seq == 2, "the matching entry is what comes back, not just the ID"
        assert len(received) == 1
        assert "doc_ids" not in received[0][_URL_KEY], (
            "a _doc_ids feed is served from the bucket, so it reports documents that are not "
            "yet visible to a replicator"
        )

    @pytest.mark.asyncio
    async def test_resumes_each_poll_from_the_previous_last_seq(
        self, sync_gateway: SyncGatewayFixture, fast_retries: None
    ) -> None:
        """The documents arrive across two polls, so the match from the first has to survive
        into the second - the second poll never sees doc1 again."""
        sg, specs, received = sync_gateway
        specs[:] = [self._page("1", self._entry(1, "doc1")), self._page("2", self._entry(2, "doc2"))]

        found = await sg.wait_for_documents("db", ["doc1", "doc2"])

        assert sorted(found) == ["doc1", "doc2"]
        assert len(received) == 2
        assert "since" not in received[0][_URL_KEY], "the first poll reads the feed from the start"
        assert "since=1" in received[1][_URL_KEY]

    @pytest.mark.asyncio
    async def test_waits_for_the_tombstone(self, sync_gateway: SyncGatewayFixture, fast_retries: None) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            self._page("1", self._entry(1, "doc1")),
            # A user's feed reports a tombstone as removed too, since a deleted document
            # grants no channels.  That must not stop the wait from settling.
            self._page("2", self._entry(2, "doc1", deleted=True, removed=["abc"])),
        ]

        found = await sg.wait_for_documents("db", ["doc1"], deleted=True)

        assert found["doc1"].deleted is True
        assert found["doc1"].removed == ["abc"]

    @pytest.mark.asyncio
    async def test_does_not_settle_for_a_live_document(
        self, sync_gateway: SyncGatewayFixture, fast_retries: None
    ) -> None:
        """A feed still showing the document alive must not satisfy a wait for its deletion."""
        sg, specs, _ = sync_gateway
        specs[:] = [self._page("1", self._entry(1, "doc1"))]

        with pytest.raises(TimeoutError, match="not tombstoned"):
            await sg.wait_for_documents("db", ["doc1"], deleted=True)

    @pytest.mark.asyncio
    async def test_does_not_settle_for_a_tombstone(self, sync_gateway: SyncGatewayFixture, fast_retries: None) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [self._page("1", self._entry(1, "doc1", deleted=True))]

        with pytest.raises(TimeoutError, match="not present"):
            await sg.wait_for_documents("db", ["doc1"])

    @pytest.mark.asyncio
    async def test_a_removal_notice_is_not_the_document_arriving(
        self, sync_gateway: SyncGatewayFixture, fast_retries: None
    ) -> None:
        """Sync Gateway reports a document the reader has lost access to as an ordinary entry
        carrying `removed`, so matching on the ID alone would call that a successful wait."""
        sg, specs, _ = sync_gateway
        specs[:] = [self._page("1", self._entry(1, "doc1", removed=["abc"]))]

        with pytest.raises(TimeoutError, match="not present"):
            await sg.wait_for_documents("db", ["doc1"])

    @pytest.mark.asyncio
    async def test_removed_channels_are_readable(self, sync_gateway: SyncGatewayFixture, fast_retries: None) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [self._page("1", self._entry(1, "doc1"), self._entry(2, "doc2", removed=["abc"]))]

        changes = await sg.get_changes("db")

        by_id = {entry.id: entry for entry in changes.results}
        assert by_id["doc1"].removed == [], "a normal entry carries no removal"
        assert by_id["doc2"].removed == ["abc"]
