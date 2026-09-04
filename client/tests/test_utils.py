from json import loads

import pytest
import tenacity
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblSyncGatewayBadResponseError,
)
from cbltest.utils import async_retry_assert, retry_assert


class TestAsyncRetryAssert:
    @pytest.mark.asyncio
    async def test_returns_result_once_assertion_passes(self) -> None:
        calls = {"n": 0}

        async def poll() -> str:
            calls["n"] += 1
            assert calls["n"] >= 3, f"not ready yet (attempt {calls['n']})"
            return "ok"

        result = await async_retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5))

        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_raises_timeout_with_assertion_message(self) -> None:
        async def poll() -> None:
            raise AssertionError("still not ready")

        with pytest.raises(TimeoutError) as exc_info:
            await async_retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(3))

        assert str(exc_info.value).startswith("still not ready")

    @pytest.mark.asyncio
    async def test_timeout_error_chains_the_assertion_error(self) -> None:
        async def poll() -> None:
            raise AssertionError("still not ready")

        with pytest.raises(TimeoutError) as exc_info:
            await async_retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(1))

        assert isinstance(exc_info.value.__cause__, AssertionError)
        assert str(exc_info.value.__cause__) == "still not ready"

    @pytest.mark.asyncio
    async def test_reports_the_last_attempts_message_not_the_first(self) -> None:
        calls = {"n": 0}

        async def poll() -> None:
            calls["n"] += 1
            raise AssertionError(f"attempt {calls['n']}")

        with pytest.raises(TimeoutError) as exc_info:
            await async_retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(4))

        assert calls["n"] == 4
        assert str(exc_info.value).startswith("attempt 4")

    @pytest.mark.asyncio
    async def test_does_not_retry_non_assertion_errors(self) -> None:
        calls = {"n": 0}

        async def poll() -> None:
            calls["n"] += 1
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await async_retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5))

        assert calls["n"] == 1


class TestRetryAssert:
    def test_returns_result_once_assertion_passes(self) -> None:
        calls = {"n": 0}

        def poll() -> str:
            calls["n"] += 1
            assert calls["n"] >= 3, f"not ready yet (attempt {calls['n']})"
            return "ok"

        result = retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5))

        assert result == "ok"
        assert calls["n"] == 3

    def test_rejects_async_functions(self) -> None:
        calls = {"n": 0}

        async def poll() -> None:
            calls["n"] += 1
            raise AssertionError("still not ready")

        with pytest.raises(TypeError) as exc_info:
            retry_assert(poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5))

        assert "async_retry_assert" in str(exc_info.value)
        assert calls["n"] == 0


class TestBadResponseErrors:
    """Edge Server and Sync Gateway errors should expose the same detail."""

    def test_edge_server_error_exposes_code_and_body(self) -> None:
        body = '{"status": 404, "error": "Not Found"}'
        err = CblEdgeServerBadResponseError(404, "get /db/nope returned 404", body=body)

        assert err.code == 404
        assert err.body == body
        assert loads(err.body)["error"] == "Not Found"
        assert str(err) == "get /db/nope returned 404"

    def test_edge_server_error_requires_a_body(self) -> None:
        """body is keyword-only and mandatory, so no raise site can quietly omit it."""
        with pytest.raises(TypeError):
            CblEdgeServerBadResponseError(404, "no body given")  # ty: ignore[missing-argument]

    def test_edge_server_error_matches_sync_gateway_error(self) -> None:
        es = CblEdgeServerBadResponseError(500, "es", body="es body")
        sg = CblSyncGatewayBadResponseError(500, "sg", body="sg body")

        assert (es.code, es.body) == (500, "es body")
        assert (sg.code, sg.body) == (500, "sg body")
