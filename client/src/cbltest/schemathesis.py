"""
Runs the schemathesis CLI, which checks a REST API against its OpenAPI spec.
"""

import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path


async def run_schemathesis(
    spec: Path,
    config_file: Path,
    url: str,
    operations: list[str],
    auth: str | None = None,
    env: Mapping[str, str] | None = None,
    mode: str | None = None,
    timeout: float = 1800,
) -> tuple[int, str]:
    """
    Run schemathesis against the given operations of a spec, and return its exit code and output.

    :param spec: Local path to the OpenAPI spec
    :param config_file: The schemathesis.toml that holds the seed, the pinned parameters and the known mismatches
    :param url: Base URL of the server under test
    :param operations: The operations in scope, each as "METHOD /path"
    :param auth: Basic auth credentials as "user:password", or None to send none
    :param env: Extra environment variables, for example those the config file reads
    :param mode: "positive" for valid requests only, or "negative" for invalid ones only.  A phase that
        sets its own mode in the config file ignores this.
    :param timeout: Seconds to wait for the run before it is killed and fails
    """
    args = ["--config-file", str(config_file), "run", str(spec), "--url", url, "--no-color"]
    if auth is not None:
        args += ["--auth", auth]
    if mode is not None:
        args += ["--mode", mode]
    args += [arg for op in operations for arg in ("--include-name", op)]
    # The CLI installed beside this interpreter, so that a venv need not be on PATH.
    proc = await asyncio.create_subprocess_exec(
        str(Path(sys.executable).parent / "schemathesis"),
        *args,
        env={**os.environ, **(env or {})},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        output, _ = await proc.communicate()
        return -1, f"schemathesis did not finish in {timeout} seconds\n{output.decode()}"
    assert proc.returncode is not None
    return proc.returncode, output.decode()
