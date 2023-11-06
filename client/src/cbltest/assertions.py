from typing import List, Any

def _assert_not_null(arg: Any, name: str) -> Any:
    if arg is None:
        raise TypeError(f"{name} must not be null!")
    
    return arg

def _assert_not_empty(arg: List[Any], name: str) -> Any:
    if len(arg) <= 0:
        raise TypeError(f"{name} must not be empty!")

    return arg