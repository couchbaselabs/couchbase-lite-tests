import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from .api.error import CblTimeoutError

T = TypeVar("T")


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
                print(
                    f"Trying {function_name} failed (reason='{e}'), retry in {seconds_between} seconds ..."
                )
                time.sleep(seconds_between)
            else:
                print(f"Trying {function_name} failed (reason='{e}')")

    raise CblTimeoutError(f"Failed to call {function_name} after {num_times} attempts!")


def assert_not_null(input: T | None, msg: str) -> T:
    assert input is not None, msg
    return cast(T, input)
