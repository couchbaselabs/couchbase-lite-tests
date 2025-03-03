import sys
from typing import Any, List, Optional, Type, TypeVar, cast

if sys.version_info >= (3, 10):
    from typing import get_origin
else:
    from typing_extensions import get_origin

from .logging import cbl_warning

T = TypeVar("T")


def _get_string_list(d: dict, key: str) -> Optional[List[str]]:
    if key not in d:
        return None

    ret_val = d[key]
    if not isinstance(ret_val, list):
        raise ValueError(f"Expecting an array for key {key} but found {type(ret_val)}!")

    for x in ret_val:
        if not isinstance(x, str):
            raise ValueError(
                f"Expecting an array of strings for {key} but found {x} inside!"
            )

    return cast(List[str], ret_val)


def _assert_contains_string_list(d: dict, key: str) -> List[str]:
    ret_val = _get_string_list(d, key)
    if ret_val is None:
        raise ValueError(f"Missing required key {key} in dictionary!")

    return ret_val


def _assert_string_entry(d: dict, key: str) -> str:
    if key not in d:
        raise ValueError(f"Missing required key {key} in dictionary!")

    ret_val = d[key]
    if not isinstance(ret_val, str):
        raise ValueError(f"Expecting string for key {key} but found {ret_val}")

    return ret_val


def _get_int_or_default(d: dict, key: str, default: int) -> int:
    if key not in d:
        cbl_warning(f"{key} not present in dictionary, using default {default}!")
        return default

    ret_val = d[key]
    if not isinstance(ret_val, int):
        raise ValueError(f"Expecting an int for key {key} but found {ret_val} instead")

    return cast(int, ret_val)


def _get_str_or_default(d: dict, key: str, default: str) -> str:
    if key not in d:
        cbl_warning(f"{key} not present in dictionary, using default {default}!")
        return default

    ret_val = d[key]
    if not isinstance(ret_val, str):
        raise ValueError(
            f"Expecting a string for key {key} but found {ret_val} instead"
        )

    return cast(str, ret_val)


def _get_bool_or_default(d: dict, key: str, default: bool) -> bool:
    if key not in d:
        cbl_warning(f"{key} not present in dictionary, using default {default}!")
        return default

    ret_val = d[key]
    if not isinstance(ret_val, bool):
        raise ValueError(
            f"Expecting a string for key {key} but found {ret_val} instead"
        )

    return cast(bool, ret_val)


def _get_typed(d: dict, key: str, type: Type[T]) -> Optional[T]:
    if key not in d:
        return None

    origin = get_origin(type)
    if origin is None:
        origin = type

    ret_val = d[key]
    if ret_val is None:
        return ret_val

    if not isinstance(ret_val, cast(Type, origin)):
        raise ValueError(
            f"Expecting {str(type)} for key {key} but found {ret_val} instead"
        )

    return cast(T, ret_val)


def _get_typed_required(d: dict, key: str, type: Type[T]) -> T:
    if key not in d:
        raise ValueError(f"Missing required key {key} in dictionary!")

    origin = get_origin(type)
    if origin is None:
        origin = type

    ret_val = d[key]
    if not isinstance(ret_val, cast(Type, origin)):
        raise ValueError(
            f"Expecting {str(type)} for key {key} but found {ret_val} instead"
        )

    return cast(T, ret_val)


def json_equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, dict):
        if not isinstance(right, dict):
            return False

        left_dict = cast(dict, left)
        right_dict = cast(dict, right)
        for key in left_dict:
            if key not in right_dict:
                return False

            if not json_equivalent(left_dict[key], right_dict[key]):
                return False

        return True

    if isinstance(left, list):
        if not isinstance(right, list):
            return False

        left_list = cast(list, left)
        right_list = cast(list, right)
        if len(left_list) != len(right_list):
            return False

        for i in range(0, len(left_list)):
            if not json_equivalent(left_list[i], right_list[i]):
                return False

        return True

    return left == right
