import json
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn, TypeVar, cast

import tenacity
import tenacity._utils
import tenacity.asyncio

from .api.error import CblTimeoutError

T = TypeVar("T")

# Hide tenacity's retry-loop frames so failures show the actual assertion, not
# AsyncRetrying plumbing.
tenacity.asyncio.__dict__["__tracebackhide__"] = True
tenacity._utils.__dict__["__tracebackhide__"] = True


async def retry_assert(
    function: Callable[[], Awaitable[T]],
    wait: tenacity.wait.wait_base,
    stop: tenacity.stop.stop_base,
) -> T:
    """Retries function while it raises AssertionError; on exhaustion, re-raises
    as TimeoutError with elapsed time."""
    __tracebackhide__ = True

    def _on_exhausted(retry_state: tenacity.RetryCallState) -> NoReturn:
        __tracebackhide__ = True
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        elapsed = retry_state.seconds_since_start
        raise TimeoutError(f"{exc} (gave up after {retry_state.attempt_number} attempts, {elapsed:.1f}s)") from exc

    retrying = tenacity.AsyncRetrying(
        wait=wait,
        stop=stop,
        retry=tenacity.retry_if_exception_type(AssertionError),
        retry_error_callback=_on_exhausted,
    )
    return await retrying(function)


def _try_n_times(
    num_times: int,
    seconds_between: int | float,
    wait_before_first_try: bool,
    func: Callable[..., T],
    *args: Any,
    **kwargs: dict[str, Any],
) -> T:
    function_name = getattr(func, "__name__", "<unknown function>")
    for i in range(num_times):
        try:
            if i == 0 and wait_before_first_try:
                time.sleep(seconds_between)
            ret = func(*args, **kwargs)
            return ret
        except Exception as e:
            if i < num_times - 1:
                print(f"Trying {function_name} failed (reason='{e}'), retry in {seconds_between} seconds ...")
                time.sleep(seconds_between)
            else:
                print(f"Trying {function_name} failed (reason='{e}')")

    raise CblTimeoutError(f"Failed to call {function_name} after {num_times} attempts!")


def assert_not_null(input: T | None, msg: str) -> T:
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
