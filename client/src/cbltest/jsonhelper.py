from typing import List, cast

from .logging import cbl_warning

def _get_string_list(d: dict, key: str) -> List[str]:
    if key not in d:
        return None
        
    ret_val = d[key]
    if not isinstance(ret_val, list):
        raise ValueError(f"Expecting an array for key {key} but found {type(ret_val)}!")
    
    for x in ret_val:
        if not isinstance(x, str):
            raise ValueError(f"Expecting an array of strings for {key} but found {x} inside!")
    
    return cast(List[str], ret_val)

def _assert_contains_string_list(d: dict, key: str) -> List[str]:
    ret_val = _get_string_list(d, key)
    if ret_val is None:
        raise ValueError(f"Missing required key {key} in dictionary!")
    
    return ret_val

def _assert_string_entry(d: dict, key: str) -> str:
    if key not in d:
        raise ValueError(f"Missing requied key {key} in dictionary!")
    
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
        raise ValueError(f"Expecting a string for key {key} but found {ret_val} instead")
    
    return cast(str, ret_val)