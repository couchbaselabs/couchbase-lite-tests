#!/usr/bin/env python3
#
# Runs the smoke tests against a test server on this host. The smoke tests need no Sync
# Gateway, so only the test server is started.
#
# Usage::
#
#   uv run client/smoke_tests/run_local.py --platform c --build-testserver 4.1.2 --logslurp
#   uv run --group dotnet-build client/smoke_tests/run_local.py --platform dotnet --build-testserver 4.1.2
#   uv run client/smoke_tests/run_local.py --platform jak_desktop --build-testserver 4.1.2-3
#   uv run client/smoke_tests/run_local.py --platform js --build-testserver 1.0.3
#   uv run client/smoke_tests/run_local.py --platform c --cbl-version 3.2.1 -- --junitxml=results.xml
#   uv run client/smoke_tests/run_local.py --skip-testserver -- -k test_get_root
#
# Per platform:
#   c            CMake and Xcode command line tools.
#   dotnet       Needs `uv run --group dotnet-build`; dotnetenv installs the pinned SDK, and the
#                Mac Catalyst build needs the Xcode version that the SDK pins.
#   jak_desktop  Java 17 or later; JAVA_HOME is set from Homebrew's openjdk when java is missing.
#                Maven has no plain 4.1.2, so name an exact build such as 4.1.2-3.
#   js           Bun and Playwright's Chromium. Versions are lite-js versions, such as 1.0.3.
#   --logslurp   Docker.
#
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import click

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent.parent
if __name__ == "__main__":
    sys.path.append(str(REPO_ROOT))

from environment.aws.topology_setup.test_server import TestServer, listen_port
from environment.local.start_local import LOCAL_PLATFORMS, get_cbl_platform, run_test_server

CONFIG_IN = SCRIPT_DIR / "config_in.json"
CONFIG_OUT = SCRIPT_DIR / "config.json"
LOGSLURP_DIR = REPO_ROOT / "environment" / "LogSlurp"
LOGSLURP_CONTAINER = "cbl-tests-logslurp"
LOGSLURP_PORT = 8180

# Tracked files that the test server builds rewrite, such as version pins and lock files
BUILD_REWRITTEN_FILES = [
    REPO_ROOT / "servers" / "dotnet" / "testserver.logic" / "testserver.logic.csproj",
    REPO_ROOT / "servers" / "javascript" / "package.json",
]


def _port_answers(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except OSError:
        return False


def start_logslurp() -> str:
    """Build and start the LogSlurp container, or reuse the one already running, and return its address."""
    running = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"name=^{LOGSLURP_CONTAINER}$"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if not running:
        subprocess.run(
            ["docker", "build", "-t", LOGSLURP_CONTAINER, "-f", str(LOGSLURP_DIR / "LogSlurp" / "Dockerfile"), "."],
            cwd=LOGSLURP_DIR,
            check=True,
        )
        subprocess.run(["docker", "rm", "-f", LOGSLURP_CONTAINER], capture_output=True)
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                LOGSLURP_CONTAINER,
                "-p",
                f"{LOGSLURP_PORT}:{LOGSLURP_PORT}",
                LOGSLURP_CONTAINER,
            ],
            check=True,
        )

    deadline = time.monotonic() + 30
    while not _port_answers(LOGSLURP_PORT):
        if time.monotonic() > deadline:
            raise click.ClickException(f"LogSlurp did not start listening on port {LOGSLURP_PORT}")
        time.sleep(0.5)
    return f"localhost:{LOGSLURP_PORT}"


def _dirty_files(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """The paths among these that have uncommitted changes."""
    return [p for p in paths if subprocess.run(["git", "diff", "--quiet", "--", str(p)], cwd=REPO_ROOT).returncode != 0]


def _restore_files(paths: list[pathlib.Path]) -> None:
    if paths:
        subprocess.run(["git", "checkout", "--", *map(str, paths)], cwd=REPO_ROOT, check=True)


def _ensure_java() -> None:
    """Point JAVA_HOME at a Homebrew JDK when no java runs, since macOS has only a stub."""
    if subprocess.run(["java", "-version"], capture_output=True).returncode == 0:
        return

    for formula in ("openjdk@17", "openjdk@21", "openjdk"):
        java_home = pathlib.Path("/opt/homebrew/opt") / formula
        if (java_home / "bin" / "java").exists():
            os.environ["JAVA_HOME"] = str(java_home)
            os.environ["PATH"] = f"{java_home / 'bin'}{os.pathsep}{os.environ['PATH']}"
            return
    raise click.ClickException("No Java runtime found. Install one, for example `brew install openjdk@17`.")


def _exact_version(platform_key: str, version: str | None) -> str | None:
    """Resolve a full version (3.4.2) as the prebuild job does: the release, or else its latest good build."""
    if version is None or "-" in version or version.count(".") != 2:
        return version

    resolved = TestServer.create(platform_key, version).version
    # start_local.py reads a version with no build number as a prefix, and build 0 as a release
    return resolved if "-" in resolved else f"{resolved}-0"


def _start_test_server(platform: str, build_testserver: str | None, cbl_version: str | None) -> None:
    platform_key = get_cbl_platform(platform)
    cbl_version = _exact_version(platform_key, cbl_version)
    if platform == "dotnet" and build_testserver and importlib.util.find_spec("dotnetenv") is None:
        raise click.UsageError("Building the .NET server needs `uv run --group dotnet-build`.")
    if platform == "jak_desktop":
        _ensure_java()

    # The JAK server writes CouchbaseLiteTemp/ and server.url into its working directory
    server_cwd = pathlib.Path(tempfile.gettempdir()) / "cbl-tests-testserver"
    server_cwd.mkdir(exist_ok=True)
    cwd = os.getcwd()
    os.chdir(server_cwd)
    try:
        run_test_server(platform_key, LOCAL_PLATFORMS[platform], build_testserver, cbl_version)
    finally:
        os.chdir(cwd)


@click.command(context_settings={"ignore_unknown_options": True})
@click.option("--platform", type=click.Choice(list(LOCAL_PLATFORMS)), default="c", show_default=True)
@click.option(
    "--cbl-version",
    help="Couchbase Lite version of the prebuilt test server to download: a release prefix (3.4), "
    "a version (3.4.2), which is the release or else its latest good build, or an exact build "
    "(3.4.2-2). Defaults to the latest release.",
)
@click.option(
    "--build-testserver",
    help="Build the test server from source for this release version (4.0.3) or build (4.0.3-12).",
)
@click.option("--skip-testserver", is_flag=True, help="Use the test server already running on the platform's port.")
@click.option("--logslurp", is_flag=True, help=f"Run LogSlurp in Docker on port {LOGSLURP_PORT} and log to it.")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def main(
    platform: str,
    cbl_version: str | None,
    build_testserver: str | None,
    skip_testserver: bool,
    logslurp: bool,
    pytest_args: tuple[str, ...],
) -> None:
    if build_testserver and cbl_version:
        raise click.UsageError("--build-testserver and --cbl-version cannot be combined.")

    config = json.loads(CONFIG_IN.read_text())
    restore = BUILD_REWRITTEN_FILES if not skip_testserver and build_testserver else []
    if dirty := _dirty_files(restore):
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in dirty)
        raise click.ClickException(f"The build rewrites files with uncommitted changes. Commit or stash them: {names}")
    if not skip_testserver:
        try:
            _start_test_server(platform, build_testserver, cbl_version)
        finally:
            _restore_files(restore)

    platform_key = get_cbl_platform(platform)
    test_server = {"url": f"http://localhost:{listen_port(platform_key)}"}
    if platform_key == "js":
        test_server["transport"] = "ws"
    config["test-servers"] = [test_server]

    if logslurp:
        if shutil.which("docker") is None:
            raise click.ClickException("--logslurp needs Docker.")
        config["logslurp"] = start_logslurp()
    CONFIG_OUT.write_text(json.dumps(config, indent=4) + "\n")

    cmd = [sys.executable, "-m", "pytest", "-v", "--config", str(CONFIG_OUT), *pytest_args]
    sys.exit(subprocess.call(cmd, cwd=SCRIPT_DIR))


if __name__ == "__main__":
    main()
