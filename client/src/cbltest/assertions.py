def _assert_not_null(arg: any, name: str) -> any:
    if arg is None:
        raise TypeError(f"{name} cannot be null!")
    
    return arg