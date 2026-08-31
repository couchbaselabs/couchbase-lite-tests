import atexit
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles

_DERIVED_DIR: Path | None = None


def _derived_dir() -> Path:
    """The process-wide temp directory that holds derived JSON files."""
    global _DERIVED_DIR
    if _DERIVED_DIR is None:
        _DERIVED_DIR = Path(tempfile.mkdtemp(prefix="cbltest-config-"))
        atexit.register(shutil.rmtree, _DERIVED_DIR, True)

    return _DERIVED_DIR


async def read_json_file(path: str | Path) -> Any:
    """Read and parse a JSON file without blocking the event loop."""
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return json.loads(await f.read())


async def write_json_file(path: str | Path, data: Any) -> None:
    """Serialize and write a JSON file without blocking the event loop."""
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, indent=4))


async def read_binary_file(path: str | Path) -> bytes:
    """Read a file's raw bytes without blocking the event loop."""
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def write_derived_json_file(template_path: str | Path, data: Any) -> str:
    """
    Write `data` to a fresh temp file named after `template_path`, leaving the
    template itself untouched, and return the new file's path.

    Use this rather than :func:`write_json_file` whenever the JSON being
    modified is a checked-in template. Writing back into the repo dirties the
    working tree, leaks environment hostnames into git, makes tests
    order-dependent on whatever a previous run left behind, and races when two
    suites run concurrently.

    Calling this on an already-derived path (as the multi-node tests do, when
    they render one template once per Edge Server) yields a fresh sibling
    rather than compounding the suffix.

    The temp directory is created once per process and removed at exit.
    """
    stem = re.sub(r"-[0-9a-f]{8}$", "", Path(template_path).stem)
    out = _derived_dir() / f"{stem}-{uuid4().hex[:8]}.json"
    await write_json_file(out, data)
    return str(out)
