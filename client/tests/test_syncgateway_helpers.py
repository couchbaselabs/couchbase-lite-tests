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

import pytest
import pytest_asyncio
from aiohttp import encode_basic_auth, web
from aiohttp.test_utils import TestServer
from cbltest.api.error import CblSyncGatewayBadResponseError, CblTestError
from cbltest.api.syncgateway import (
    ChangesResponse,
    DatabaseConfig,
    DatabaseState,
    ScopeConfig,
    SyncGateway,
)
from cbltest.httplog import _HttpLogWriter
from pydantic import ValidationError

# (SyncGateway, response specs the test server serves, headers the server saw)
SyncGatewayFixture = tuple[SyncGateway, list[dict], list[dict[str, str]]]


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
    every request the server saw, so tests can assert on what went out on the wire."""
    monkeypatch.setattr(_HttpLogWriter, "_HttpLogWriter__record_path", tmp_path / "http_log")
    monkeypatch.setattr(
        "cbltest.api.syncgateway.requests.get",
        lambda *args, **kwargs: _FakeConfigResponse(),
    )

    specs: list[dict] = []
    received: list[dict[str, str]] = []

    async def handle(request: web.Request) -> web.Response:
        received.append(dict(request.headers))
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
    async def test_anonymous_session_sends_no_auth_header(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"ok": True}}]

        async with sg._create_session(sg.secure, sg.scheme, sg.hostname, sg.port, None) as session:
            await sg._send_request("get", "/_status", session=session)

        assert "Authorization" not in received[0]

    @pytest.mark.asyncio
    async def test_get_document_revision_public_authenticates_as_given_user(
        self, sync_gateway: SyncGatewayFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sg, specs, received = sync_gateway
        specs[:] = [{"status": 200, "json": {"_id": "doc1", "_rev": "1-abc"}}]

        # get_document_revision_public hardcodes the public port, so redirect its
        # session to the test server while leaving the credentials it builds alone.
        create_session = sg._create_session
        monkeypatch.setattr(
            sg,
            "_create_session",
            lambda secure, scheme, url, port, auth_header: create_session(secure, scheme, url, sg.port, auth_header),
        )

        doc = await sg.get_document_revision_public("db1", "doc1", "1-abc", username="alice", password="s3cret")

        assert doc == {"_id": "doc1", "_rev": "1-abc"}
        # Authenticated as the passed-in user, not as the admin the session was built with.
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


class TestWaitForDbUp:
    @pytest.mark.asyncio
    async def test_succeeds_when_database_is_online(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [
            {
                "status": 200,
                "json": [{"bucket": "b1", "db_name": "db1", "state": "Online"}],
            }
        ]

        await sg._wait_for_db_online("db1", max_retries=1, retry_delay=0)

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

        assert "database not present in /_all_dbs?verbose=true" in str(exc_info.value)

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


class TestDeleteDatabase:
    """delete_database swallows the CBG-5731 500 SGW returns once the database's bucket
    entry is gone, without swallowing 500s that a retry could still clear."""

    @pytest.mark.asyncio
    async def test_ignores_known_missing_bucket_failure(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, received = sync_gateway
        reason = 'couldn\'t remove database "db2" from bucket "data-bucket-2": Not Found'
        specs[:] = [{"status": 500, "json": {"error": "Internal Server Error", "reason": reason}}]

        await sg.delete_database("db2")

        # No retries: this response never changes.
        assert len(received) == 1

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
            await sg.delete_database("db2")

        assert len(received) == 4  # Initial attempt plus three retries.


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
        sg.get_changes = fake_get_changes  # type: ignore[method-assign]

    @pytest.mark.asyncio
    async def test_waits_on_the_unfiltered_feed(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
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
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.create_document("db", "doc1", {"foo": "bar"}, wait_for_caching_feed=True)

        assert len(calls) == 1
        assert calls[0].get("request_plus") is True
        assert "doc_ids" not in calls[0]
        assert doc.seq == 5

    @pytest.mark.asyncio
    async def test_create_does_not_read_the_feed_by_default(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        doc = await sg.create_document("db", "doc1", {"foo": "bar"})

        assert calls == []
        with pytest.raises(CblTestError, match="No sequence recorded"):
            _ = doc.seq

    @pytest.mark.asyncio
    async def test_delete_waits_for_the_tombstone(self, sync_gateway: SyncGatewayFixture) -> None:
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 200, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
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
        specs[:] = [{"status": 200, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
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
    async def test_since_bounds_the_feed_read(self, sync_gateway: SyncGatewayFixture) -> None:
        """Writing in a loop, the previous write's sequence keeps each wait off the whole feed."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
        calls: list[dict] = []
        self._record_get_changes(sg, calls)

        await sg.create_document("db", "doc1", {"foo": "bar"}, wait_for_caching_feed=True, since=41)

        assert calls[0].get("since") == 41

    @pytest.mark.asyncio
    async def test_feed_body_is_kept_out_of_the_http_log(self, sync_gateway: SyncGatewayFixture) -> None:
        """The feed is read to find one document, so its body is noise in the log."""
        sg, specs, _ = sync_gateway
        specs[:] = [{"status": 201, "json": {"id": "doc1", "ok": True, "rev": "2-abc"}}]
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
