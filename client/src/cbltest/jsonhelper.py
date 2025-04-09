import json
import sys
from typing import Any, List, Optional, Type, TypeVar, cast

if sys.version_info >= (3, 10):
    from typing import get_origin
else:
    from typing_extensions import get_origin

from .logging import cbl_info, cbl_warning

T = TypeVar("T")


def dumps_with_ellipsis(obj: Any, limit: int = 100) -> str:
    """
    Truncate a string to a specified length and add an ellipsis in the middle for the truncated characters.

    Args:
        text (str): The input string to truncate.
        limit (int): The maximum length of the resulting string, including the ellipsis. Default is 100.

    Returns:
        str: The truncated string with an ellipsis in the middle if it exceeds the limit.
    """
    text = json.dumps(obj)
    if len(text) <= limit:
        return text

    # Calculate the length of each half, accounting for the ellipsis (3 characters)
    half_length = (limit - 3) // 2
    return f"{text[:half_length]}...{text[-half_length:]}"


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


def _get_typed_nonnull(d: dict, key: str, type: Type[T], default: T) -> T:
    found_val = _get_typed(d, key, type)
    return found_val if found_val is not None else default


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


def json_equivalent(left: Any, right: Any, current_path: str = "") -> bool:
    if isinstance(left, dict):
        if not isinstance(right, dict):
            left_obj = dumps_with_ellipsis(left)
            right_obj = dumps_with_ellipsis(right)
            cbl_info(
                f"Lefthand '{left_obj}' was a dict and righthand '{right_obj}' was not"
            )
            return False

        left_dict = cast(dict, left)
        right_dict = cast(dict, right)
        for key in left_dict:
            if key not in right_dict:
                left_obj = dumps_with_ellipsis(left)
                right_obj = dumps_with_ellipsis(right)
                cbl_info(
                    f"Lefthand '{left_obj}' contained key '{key}' and righthand '{right_obj}' did not"
                )
                return False

            next_path = f"{current_path}.{key}"
            cbl_info(f"Entering key '{next_path}'")
            if not json_equivalent(left_dict[key], right_dict[key], next_path):
                return False

            cbl_info(f"Returning to key '{current_path}'")

        return True

    if isinstance(left, list):
        if not isinstance(right, list):
            left_obj = dumps_with_ellipsis(left)
            right_obj = dumps_with_ellipsis(right)
            cbl_info(
                f"Lefthand '{left_obj}' was a list and righthand '{right_obj}' was not"
            )
            return False

        left_list = cast(list, left)
        right_list = cast(list, right)
        if len(left_list) != len(right_list):
            left_obj = dumps_with_ellipsis(left)
            right_obj = dumps_with_ellipsis(right)
            cbl_info(
                f"Lefthand '{left_obj}' has different count ({len(left_list)}) than righthand '{right_obj}' {len(right_list)}"
            )
            return False

        for i in range(0, len(left_list)):
            next_path = f"{current_path}[{i}]"
            cbl_info(f"Entering index '{next_path}'")
            if not json_equivalent(left_list[i], right_list[i]):
                return False

            cbl_info(f"Returning to '{current_path}'")

        return True

    return left == right
