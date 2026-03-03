from typing import TypeVar, cast

T = TypeVar("T")


def assert_not_null(input: T | None, msg: str) -> T:
    assert input is not None, msg
    return cast(T, input)
