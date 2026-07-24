import json
from pathlib import Path
from typing import Any

import aiofiles


async def read_json_file(path: str | Path) -> Any:
    """Read and parse a JSON file without blocking the event loop."""
    async with aiofiles.open(path) as f:
        return json.loads(await f.read())


async def write_json_file(path: str | Path, data: Any) -> None:
    """Serialize and write a JSON file without blocking the event loop."""
    async with aiofiles.open(path, "w") as f:
        await f.write(json.dumps(data, indent=4))


async def read_binary_file(path: str | Path) -> bytes:
    """Read a file's raw bytes without blocking the event loop."""
    async with aiofiles.open(path, "rb") as f:
        return await f.read()
