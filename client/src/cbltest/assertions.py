def _assert_not_null(arg: any, name: str):
    if arg is None:
        raise TypeError(f"{name} cannot be null!")