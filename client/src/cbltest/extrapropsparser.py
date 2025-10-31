from json import load
from pathlib import Path
from typing import cast


def _parse_extra_props(file_path: str) -> dict[str, str]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Extra props file not found at {file_path}!")

    with open(p) as fin:
        json = load(fin)

    if not isinstance(json, dict):
        raise ValueError("Extra props is not a JSON dictionary object")

    return cast(dict[str, str], json)
