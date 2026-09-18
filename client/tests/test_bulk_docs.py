"""Tests for the shared _bulk_docs response parser and the two clients built on it.

Sync Gateway and Edge Server expose the same CouchDB-style _bulk_docs endpoint: both
answer 201 with one result per document, `{"id", "rev"}` for a success and
`{"id", "error", "reason", "status"}` for a failure. A failed document therefore shows
up only in the response body, never in the HTTP status.

The sample entries below are the shapes Sync Gateway 4.2 returns for a rev mismatch
(conflict) and for a sync function rejection (forbidden).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from cbltest.api.bulk_docs import _MAX_REPORTED_BULK_ERRORS, analyze_bulk_docs_response
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblRemoteBadResponseError,
    CblSyncGatewayBadResponseError,
)
from cbltest.api.syncgateway import DocumentUpdateEntry, SyncGateway
from conftest import fake_edge_server, fake_sync_gateways

SUCCESS = {"id": "doc1", "rev": "2-abc"}
CONFLICT = {"id": "doc2", "error": "conflict", "reason": "document update conflict", "status": 409}
FORBIDDEN = {"id": "doc3", "error": "forbidden", "reason": "sgw rejected the document", "status": 403}

ERROR_TYPES = [CblSyncGatewayBadResponseError, CblEdgeServerBadResponseError]


def conflicts(count: int) -> list[dict]:
    return [
        {"id": f"doc{i}", "error": "conflict", "reason": "document update conflict", "status": 409}
        for i in range(count)
    ]


class TestAnalyzeBulkDocsResponse:
    def test_returns_the_results_when_every_document_succeeded(self) -> None:
        results = [SUCCESS, {"id": "doc2", "rev": "3-def"}]

        assert analyze_bulk_docs_response(results, CblSyncGatewayBadResponseError) == results

    def test_accepts_an_empty_result_list(self) -> None:
        """An empty list is the normal answer to an empty batch, and to new_edits=false."""
        assert analyze_bulk_docs_response([], CblSyncGatewayBadResponseError) == []

    def test_reports_every_failed_document(self) -> None:
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            analyze_bulk_docs_response([SUCCESS, CONFLICT, FORBIDDEN], CblSyncGatewayBadResponseError)

        message = str(exc_info.value)
        assert "2 of 3 documents" in message
        assert "'doc2' (conflict)" in message
        assert "'doc3' (forbidden)" in message

    def test_keeps_the_full_failure_list_in_the_body(self) -> None:
        """The message is capped, so the body is where a caller reads every failure,
        with the reason each one came with."""
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            analyze_bulk_docs_response(conflicts(_MAX_REPORTED_BULK_ERRORS + 2), CblSyncGatewayBadResponseError)

        message = str(exc_info.value)
        assert f"{_MAX_REPORTED_BULK_ERRORS + 2} of {_MAX_REPORTED_BULK_ERRORS + 2} documents" in message
        assert f"doc{_MAX_REPORTED_BULK_ERRORS - 1}" in message
        assert f"doc{_MAX_REPORTED_BULK_ERRORS}" not in message
        assert "and 2 more" in message

        body = json.loads(exc_info.value.body)
        assert len(body) == _MAX_REPORTED_BULK_ERRORS + 2
        assert body[0]["reason"] == "document update conflict"

    def test_code_comes_from_the_first_failure(self) -> None:
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            analyze_bulk_docs_response([SUCCESS, FORBIDDEN, CONFLICT], CblSyncGatewayBadResponseError)

        assert exc_info.value.code == 403

    def test_a_failure_without_a_status_reports_500(self) -> None:
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            analyze_bulk_docs_response([{"id": "doc1", "error": "conflict"}], CblSyncGatewayBadResponseError)

        assert exc_info.value.code == 500

    def test_a_failure_without_an_id_is_still_reported(self) -> None:
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            analyze_bulk_docs_response([{"error": "bad_request", "status": 400}], CblSyncGatewayBadResponseError)

        assert "bad_request" in str(exc_info.value)
        assert exc_info.value.code == 400

    @pytest.mark.parametrize("error_type", ERROR_TYPES)
    def test_raises_the_error_type_it_was_given(self, error_type: type[CblRemoteBadResponseError]) -> None:
        """The type is what names the server that failed, so both clients report their own."""
        with pytest.raises(error_type):
            analyze_bulk_docs_response([CONFLICT], error_type)

    def test_rejects_a_response_that_is_not_a_list(self) -> None:
        """A JSON object here means the request never reached the per-document stage."""
        with pytest.raises(AssertionError, match="not a list"):
            analyze_bulk_docs_response({"error": "not_found"}, CblSyncGatewayBadResponseError)

    def test_rejects_a_response_body_that_is_not_json(self) -> None:
        with pytest.raises(AssertionError, match="not a list"):
            analyze_bulk_docs_response("502 Bad Gateway", CblSyncGatewayBadResponseError)

    def test_rejects_an_entry_that_is_not_an_object(self) -> None:
        with pytest.raises(AssertionError, match="not an object"):
            analyze_bulk_docs_response([SUCCESS, "doc2"], CblSyncGatewayBadResponseError)


def stub_bulk_docs(
    monkeypatch: pytest.MonkeyPatch,
    sgw: SyncGateway,
    bulk_response: Any,
) -> list[dict]:
    """Answer _bulk_docs with the given body. Returns the list the sent batches land in."""
    sent: list[dict] = []

    async def fake_send_request(method: str, path: str, payload: Any = None, params: Any = None) -> Any:
        if path.endswith("_bulk_docs"):
            sent.append(payload.to_json())
            return bulk_response
        raise CblSyncGatewayBadResponseError(404, f"{method} {path} returned 404", body="{}")

    monkeypatch.setattr(sgw, "_send_request", fake_send_request)
    return sent


class TestSyncGatewayBulkWrites:
    """update_documents answers 201 whatever happens to the individual documents, so it
    has to read its failures out of the response."""

    @pytest.mark.asyncio
    async def test_raises_when_a_document_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with fake_sync_gateways(1) as (sgw,):
            stub_bulk_docs(monkeypatch, sgw, [SUCCESS, CONFLICT])
            updates = [
                DocumentUpdateEntry("doc1", "1-abc", {"answer": 42}),
                DocumentUpdateEntry("doc2", "1-def", {"answer": 43}),
            ]

            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await sgw.update_documents("db1", updates)

            assert exc_info.value.code == 409
            assert "'doc2' (conflict)" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_returns_when_every_document_succeeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with fake_sync_gateways(1) as (sgw,):
            stub_bulk_docs(monkeypatch, sgw, [SUCCESS])

            await sgw.update_documents("db1", [DocumentUpdateEntry("doc1", "1-abc", {"answer": 42})])

    @pytest.mark.asyncio
    async def test_sends_a_cv_under_cv_and_a_revid_under_rev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sync Gateway reads a CV from _cv and a RevTree ID from _rev, and answers 400 for
        either one in the other's field."""
        with fake_sync_gateways(1) as (sgw,):
            sent = stub_bulk_docs(monkeypatch, sgw, [SUCCESS, SUCCESS, SUCCESS])
            updates = [
                DocumentUpdateEntry("doc1", "1-abc", {"answer": 42}),
                DocumentUpdateEntry("doc2", "18d3331395040000@hb4cU6v8xvp8/rZO5cZ2Mg", {"answer": 43}),
                DocumentUpdateEntry("doc3", None, {"answer": 44}),
            ]

            await sgw.update_documents("db1", updates)

            assert sent[0]["docs"] == [
                {"_id": "doc1", "_rev": "1-abc", "answer": 42},
                {"_id": "doc2", "_cv": "18d3331395040000@hb4cU6v8xvp8/rZO5cZ2Mg", "answer": 43},
                {"_id": "doc3", "answer": 44},
            ]


class TestEdgeServerBulkDocOp:
    @pytest.mark.asyncio
    async def test_returns_the_results_when_every_document_succeeded(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Callers build their next rev map out of the returned results."""
        with fake_edge_server(tmp_path) as edge_server:
            monkeypatch.setattr(edge_server, "_send_request", _returning([SUCCESS]))

            results = await edge_server.bulk_doc_op([BulkDocOperation(body={"answer": 42}, _id="doc1")], "db")

            assert results == [SUCCESS]

    @pytest.mark.asyncio
    async def test_raises_when_a_document_failed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        with fake_edge_server(tmp_path) as edge_server:
            monkeypatch.setattr(edge_server, "_send_request", _returning([SUCCESS, CONFLICT, FORBIDDEN]))

            with pytest.raises(CblEdgeServerBadResponseError) as exc_info:
                await edge_server.bulk_doc_op([BulkDocOperation(body={"answer": 42}, _id="doc1")], "db")

            message = str(exc_info.value)
            assert "2 of 3 documents" in message
            assert "'doc2' (conflict)" in message
            assert "'doc3' (forbidden)" in message

    @pytest.mark.asyncio
    async def test_raises_on_a_non_list_response(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Every successful _bulk_docs answers with one result per document."""
        with fake_edge_server(tmp_path) as edge_server:
            monkeypatch.setattr(edge_server, "_send_request", _returning({"ok": True}))

            with pytest.raises(CblEdgeServerBadResponseError, match="Unexpected response type"):
                await edge_server.bulk_doc_op([BulkDocOperation(body={"answer": 42}, _id="doc1")], "db")


def _returning(response: Any) -> Any:
    """A stand-in for _send_request that answers with the given body."""

    async def fake_send_request(method: str, path: str, payload: Any = None) -> Any:
        return response

    return fake_send_request
