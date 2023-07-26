from typing import Any

def _assert_not_null(arg: Any, name: str) -> Any:
    if arg is None:
        raise TypeError(f"{name} cannot be null!")
    
    return arg