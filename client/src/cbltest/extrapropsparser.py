from pathlib import Path
from json import load
from typing import Dict, cast

def _parse_extra_props(file_path: str) -> Dict[str, str]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Extra props file not found at {file_path}!")
    
    with open(p) as fin:
        json = load(fin)

    if not isinstance(json, dict):
        raise ValueError("Extra props is not a JSON dictionary object")
    
    return cast(Dict[str, str], json)
