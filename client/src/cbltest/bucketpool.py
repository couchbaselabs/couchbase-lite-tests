"""
Run ``bucketpool``, the helper that empties a Couchbase Server bucket in place.

Emptying a bucket means removing tombstones that still carry xattrs, and only a DCP feed
reports those.  The Python Couchbase SDK cannot open a DCP feed, so the work is done by
https://github.com/couchbaselabs/bucketpool, downloaded into ``tests/.tools`` by
``environment/aws/download_tool.py``.
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

from cbltest.api.error import CblTestError
from cbltest.logging import cbl_trace

_TOOL_NAME = "bucketpool"
_PASSWORD_ENV_VAR = "BUCKETPOOL_PASSWORD"

#: Seconds a purge is given before it is treated as hung.  A bucket holding hundreds of
#: thousands of documents takes minutes, so this is generous on purpose.
DEFAULT_TIMEOUT = 900.0


def tool_path() -> Path:
    """
    Finds the ``bucketpool`` binary, either downloaded into this checkout or on the PATH.

    :raises CblTestError: if neither one holds the binary
    """
    binary = f"{_TOOL_NAME}.exe" if sys.platform == "win32" else _TOOL_NAME
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tests" / ".tools" / _TOOL_NAME / binary
        if candidate.is_file():
            return candidate

    on_path = shutil.which(_TOOL_NAME)
    if on_path is not None:
        return Path(on_path)

    raise CblTestError(
        f"{_TOOL_NAME} was not found, so buckets cannot be purged.  Download it with "
        f"'uv run environment/aws/download_tool.py {_TOOL_NAME}'."
    )


async def purge_bucket(
    *,
    connection_string: str,
    management_url: str,
    username: str,
    password: str,
    bucket: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """
    Removes every document, and every xattr, from all collections of a bucket.  The bucket,
    its scopes, its collections and its indexes are left in place.

    :param connection_string: The ``couchbase://`` URL of the cluster
    :param management_url: The ``http://`` management URL of one node, e.g. ``http://host:8091``
    :param username: The administrator username
    :param password: The administrator password
    :param bucket: The name of the bucket to empty
    :param timeout: Seconds the feed and the purge together are allowed to take
    :return: The one line summary the helper prints
    """
    summary = await _run(
        [
            str(tool_path()),
            "purge",
            "--connection-string",
            connection_string,
            "--management-url",
            management_url,
            "--username",
            username,
            "--bucket",
            bucket,
            "--timeout",
            f"{timeout}s",
        ],
        # The password goes through the environment so that it stays out of the process list.
        env_additions={_PASSWORD_ENV_VAR: password},
    )
    cbl_trace(f"🧹 purged bucket '{bucket}': {summary.strip()}")
    return summary


async def _run(args: list[str], *, env_additions: dict[str, str] | None = None) -> str:
    """
    Runs a command and returns its standard output.

    :raises CblTestError: if the command exits non-zero.  Only the program name is repeated
        back, since the arguments can name a cluster.
    """
    env = None
    if env_additions is not None:
        env = {**os.environ, **env_additions}

    process = await asyncio.create_subprocess_exec(
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        name = Path(args[0]).name
        raise CblTestError(f"{name} exited with {process.returncode}: {stderr.decode().strip()}")

    return stdout.decode()
