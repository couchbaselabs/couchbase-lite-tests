from typing import List, cast

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
        raise ValueError(f"Missing required key {key} in config file!")
    
    return ret_val