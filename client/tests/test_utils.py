import pytest
import tenacity
from cbltest.utils import retry_assert


class TestRetryAssert:
    @pytest.mark.asyncio
    async def test_returns_result_once_assertion_passes(self):
        calls = {"n": 0}

        async def poll() -> str:
            calls["n"] += 1
            assert calls["n"] >= 3, f"not ready yet (attempt {calls['n']})"
            return "ok"

        result = await retry_assert(
            poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5)
        )

        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_raises_timeout_with_assertion_message(self):
        async def poll() -> None:
            raise AssertionError("still not ready")

        with pytest.raises(TimeoutError) as exc_info:
            await retry_assert(
                poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(3)
            )

        assert str(exc_info.value).startswith("still not ready")

    @pytest.mark.asyncio
    async def test_timeout_error_chains_the_assertion_error(self):
        async def poll() -> None:
            raise AssertionError("still not ready")

        with pytest.raises(TimeoutError) as exc_info:
            await retry_assert(
                poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(1)
            )

        assert isinstance(exc_info.value.__cause__, AssertionError)
        assert str(exc_info.value.__cause__) == "still not ready"

    @pytest.mark.asyncio
    async def test_reports_the_last_attempts_message_not_the_first(self):
        calls = {"n": 0}

        async def poll() -> None:
            calls["n"] += 1
            raise AssertionError(f"attempt {calls['n']}")

        with pytest.raises(TimeoutError) as exc_info:
            await retry_assert(
                poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(4)
            )

        assert calls["n"] == 4
        assert str(exc_info.value).startswith("attempt 4")

    @pytest.mark.asyncio
    async def test_does_not_retry_non_assertion_errors(self):
        calls = {"n": 0}

        async def poll() -> None:
            calls["n"] += 1
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await retry_assert(
                poll, tenacity.wait_fixed(0), tenacity.stop_after_attempt(5)
            )

        assert calls["n"] == 1
