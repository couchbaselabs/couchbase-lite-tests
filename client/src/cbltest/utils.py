import time
from typing import Any, Callable, Dict, TypeVar, Type, Union, Optional, cast

from .api.error import CblTimeoutError

T = TypeVar('T')


def _try_n_times(num_times: int,
                 seconds_between: Union[int, float],
                 wait_before_first_try: bool,
                 func: Callable,
                 ret_type: Type[T],
                 *args: Any,
                 **kwargs: Dict[str, Any]) -> T:
    for i in range(num_times):
        try:
            if i == 0 and wait_before_first_try:
                time.sleep(seconds_between)
            ret: T = func(*args, **kwargs)
            return ret
        except Exception as e:
            if i < num_times - 1:
                print(f"Trying {func.__name__} failed (reason='{e}'), retry in {seconds_between} seconds ...")
                time.sleep(seconds_between)
            else:
                print(f"Trying {func.__name__} failed (reason='{e}')")

    raise CblTimeoutError(f"Failed to call {func.__name__} after {num_times} attempts!")

def assert_not_null(input: Optional[T], msg: str) -> T:
    assert input is not None, msg
    return cast(T, input)