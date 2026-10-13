import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from cbltest.api.error import CblRemoteBadResponseError, CblTestServerBadResponseError
from cbltest.request_types import TestServerRequest as _Request
from cbltest.requests_transport import _RequestHttpTransport, _RequestWebSocketTransport
from cbltest.responses import TestServerResponse as _Response
from cbltest.responses import register_response

NOT_FOUND_BODY = {
    "domain": "TESTSERVER",
    "code": 404,
    "message": "Document '_default._default.doc1' not found",
}


# Importing cbltest.v1 here would change the request registration order the session fixture relies on.
class _FakeGetDocumentRequest(_Request):
    def __init__(self) -> None:
        super().__init__(1, uuid4(), "getDocument")


@register_response(_FakeGetDocumentRequest, 1)
class _FakeGetDocumentResponse(_Response):
    def __init__(self, status_code: int, uuid: str, body: dict) -> None:
        super().__init__(status_code, uuid, body, "getDocument")


def _http_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.ok = status < 400
    resp.headers = {
        "CBLTest-API-Version": "1",
        "CBLTest-Server-ID": "server-uuid",
        "Content-Type": "application/json",
    }
    resp.content_length = 1
    resp.json = AsyncMock(return_value=body)
    return resp


class TestCblTestServerBadResponseError:
    def test_message_includes_error_body(self) -> None:
        response = _Response(404, "server-uuid", NOT_FOUND_BODY, "getDocument")
        err = CblTestServerBadResponseError(404, response, "POST /getDocument returned 404")

        assert str(err) == (
            "POST /getDocument returned 404: (TESTSERVER / 404) Document '_default._default.doc1' not found"
        )
        assert err.code == 404
        assert isinstance(err, CblRemoteBadResponseError)
        assert json.loads(err.body) == NOT_FOUND_BODY

    def test_message_without_error_body(self) -> None:
        response = _Response(404, "server-uuid", {}, "getDocument")
        err = CblTestServerBadResponseError(404, response, "POST /getDocument returned 404")

        assert str(err) == "POST /getDocument returned 404"

    def test_null_body_has_no_error(self) -> None:
        # The C server answers /newSession with a JSON null body
        response = _Response(200, "server-uuid", None, "newSession")  # ty: ignore[invalid-argument-type]

        assert response.error is None


class TestRequestHttpTransport:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 404])
    async def test_bad_response_names_request_and_error(self, status: int) -> None:
        session = MagicMock()
        session.request = AsyncMock(return_value=_http_response(status, {**NOT_FOUND_BODY, "code": status}))
        transport = _RequestHttpTransport("http://localhost:8080", session)
        with pytest.raises(CblTestServerBadResponseError) as exc_info:
            await transport.send(_FakeGetDocumentRequest(), 1)

        assert exc_info.value.code == status
        assert str(exc_info.value) == (
            f"POST /getDocument returned {status}: (TESTSERVER / {status}) Document '_default._default.doc1' not found"
        )


class TestRequestWebSocketTransport:
    @pytest.mark.asyncio
    async def test_bad_response_reads_ts_error(self) -> None:
        reply: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        reply.set_result({"ts_apiVersion": 1, "ts_serverID": "server-uuid", "ts_error": NOT_FOUND_BODY})
        ws_router = MagicMock()
        ws_router.register.return_value = reply
        ws_router.get_websocket_for_write.return_value.send_str = AsyncMock()
        transport = _RequestWebSocketTransport("ws://localhost:8080", ws_router)

        with pytest.raises(CblTestServerBadResponseError) as exc_info:
            await transport.send(_FakeGetDocumentRequest(), 1)

        assert exc_info.value.code == 404
        assert str(exc_info.value) == (
            "POST /getDocument returned 404: (TESTSERVER / 404) Document '_default._default.doc1' not found"
        )
