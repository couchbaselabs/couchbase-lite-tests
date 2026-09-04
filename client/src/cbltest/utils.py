import inspect
import json
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn, cast

import requests
import tenacity
import tenacity._utils
import tenacity.asyncio

# Hide tenacity's retry-loop frames so failures show the actual assertion, not
# Retrying/AsyncRetrying plumbing.
tenacity.__dict__["__tracebackhide__"] = True
tenacity.asyncio.__dict__["__tracebackhide__"] = True
tenacity._utils.__dict__["__tracebackhide__"] = True


def _on_retry_assert_exhausted(retry_state: tenacity.RetryCallState) -> NoReturn:
    __tracebackhide__ = True
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    elapsed = retry_state.seconds_since_start
    raise TimeoutError(f"{exc} (gave up after {retry_state.attempt_number} attempts, {elapsed:.1f}s)") from exc


def _retry_assert_policy(wait: tenacity.wait.wait_base, stop: tenacity.stop.stop_base) -> dict[str, Any]:
    return {
        "wait": wait,
        "stop": stop,
        "retry": tenacity.retry_if_exception_type(AssertionError),
        "retry_error_callback": _on_retry_assert_exhausted,
    }


async def async_retry_assert[T](
    function: Callable[[], Awaitable[T]],
    wait: tenacity.wait.wait_base,
    stop: tenacity.stop.stop_base,
) -> T:
    """Retries function while it raises AssertionError; on exhaustion, re-raises
    as TimeoutError with elapsed time.

    :raises TypeError: if function is not async.  tenacity calls a plain callable
        without awaiting it, so a lambda returning a coroutine never runs any of its
        assertions, which would look like success on the first attempt.  Use
        :func:`retry_assert` instead.
    """
    __tracebackhide__ = True

    if not tenacity._utils.is_coroutine_callable(function):
        name = getattr(function, "__name__", repr(function))
        raise TypeError(f"{name} is not async, use retry_assert instead of async_retry_assert")

    retrying = tenacity.AsyncRetrying(**_retry_assert_policy(wait, stop))
    return await retrying(function)


def retry_assert[T](
    function: Callable[[], T],
    wait: tenacity.wait.wait_base,
    stop: tenacity.stop.stop_base,
) -> T:
    """Retries function while it raises AssertionError; on exhaustion, re-raises
    as TimeoutError with elapsed time.

    :raises TypeError: if function is async.  An async callable returns its
        coroutine without running any assertions, which would look like success on
        the first attempt and silently skip the retry loop.  Use
        :func:`async_retry_assert` instead.
    """
    __tracebackhide__ = True

    def checked_function() -> T:
        __tracebackhide__ = True
        result = function()
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if close is not None:
                close()
            name = getattr(function, "__name__", repr(function))
            raise TypeError(f"{name} is async, use async_retry_assert instead of retry_assert")
        return result

    retrying = tenacity.Retrying(**_retry_assert_policy(wait, stop))
    return retrying(checked_function)


# Port the shell2http sidecar listens on, on every Sync Gateway and Edge Server host.
SHELL2HTTP_PORT = 20001


def is_sidecar_reachable(hostname: str, port: int, timeout: float = 1.0) -> bool:
    """
    Whether anything responds on ``hostname:port``.  Any status counts -- this asks whether
    a sidecar is there at all, not whether a particular resource exists.

    :param hostname: Host to probe
    :param port: Port the sidecar is expected on
    :param timeout: Seconds to wait before deciding nothing is listening
    :return: True if the port answered
    """
    try:
        requests.get(f"http://{hostname}:{port}/", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def describe_transfer(received: int, expected: int | None) -> str:
    """
    Describes how much of a response body arrived, for error messages on a transfer that
    did not finish.

    :param received: Bytes actually read so far
    :param expected: Bytes the response promised via Content-Length, or None if it did not say
    :return: Something like "12.3 MiB of 40.0 MiB (31%)", or "12.3 MiB of unknown total"
    """

    def size(n: int) -> str:
        value = float(n)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{n} B"
            value /= 1024
        raise AssertionError("unreachable")

    if expected is None:
        return f"{size(received)} of unknown total"
    if expected == 0:
        return f"{size(received)} of 0 B"
    return f"{size(received)} of {size(expected)} ({received * 100 // expected}%)"


def assert_not_null[T](input: T | None, msg: str) -> T:
    assert input is not None, msg
    return cast(T, input)


def verify_lfs_checkout() -> None:
    """
    This function is used to verify that the LFS files are being properly checked out.
    """
    if os.name == "nt" or sys.platform.startswith("linux"):
        # This check, for whatever reason, is entirely unreliable on Windows and linux.
        # The command itself returns what I expect, but the checkout field is always false
        # when invoking from python, even when the files are properly checked out
        return

    try:
        process_output = subprocess.run(
            ["git", "lfs", "ls-files", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to run {e.cmd!r} (return code {e.returncode}). stdout: {e.stdout!r} stderr: {e.stderr!r}"
        ) from e
    try:
        lfs = json.loads(process_output.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse git lfs output: {e}.") from e
    if not lfs["files"]:
        return
    for f in lfs["files"]:
        if f["checkout"] is False:
            raise RuntimeError(
                "git lfs is not configured. Please run 'git lfs install' and then 'git lfs pull'.\n"
                f"Full output of git lfs ls-files --json:\n{json.dumps(lfs, indent=2)}"
            )
