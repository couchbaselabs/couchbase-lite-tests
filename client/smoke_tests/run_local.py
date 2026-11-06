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
#   uv run client/smoke_tests/run_local.py --platform reactnative
#   uv run client/smoke_tests/run_local.py --skip-testserver -- -k test_get_root
#
# Per platform:
#   c            CMake and Xcode command line tools.
#   dotnet       Needs `uv run --group dotnet-build`; dotnetenv installs the pinned SDK, and the
#                Mac Catalyst build needs the Xcode version that the SDK pins.
#   jak_desktop  Java 17 or later; JAVA_HOME is set from Homebrew's openjdk when java is missing.
#                Maven has no plain 4.1.2, so name an exact build such as 4.1.2-3.
#   js           Bun and Playwright's Chromium. Versions are lite-js versions, such as 1.0.3.
#   ios_simulator  Needs the start_local.py support from PR #678, and exactly one booted simulator.
#   reactnative  Builds servers/reactnative for exactly one booted iOS simulator, with npm, CocoaPods
#                and Xcode. The version comes from its package.json, so --build-testserver is unused.
#   --logslurp   Docker.
#
import importlib.util
import inspect
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
import psutil

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

RN_DIR = REPO_ROOT / "servers" / "reactnative"
RN_APP = RN_DIR / "ios" / "build" / "Build" / "Products" / "Release-iphonesimulator" / "CblTestServer.app"
RN_BUNDLE_ID = "com.cbltestserver"

# Tracked files that the test server builds rewrite, such as version pins and lock files
BUILD_REWRITTEN_FILES = [
    REPO_ROOT / "servers" / "dotnet" / "testserver.logic" / "testserver.logic.csproj",
    REPO_ROOT / "servers" / "javascript" / "package.json",
    RN_DIR / "package-lock.json",
    RN_DIR / "ios" / "Podfile.lock",
]

PLATFORMS = [*LOCAL_PLATFORMS, "reactnative"]


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


def booted_simulator() -> str:
    """The UDID of the one booted iOS simulator."""
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted", "--json"], check=True, capture_output=True, text=True
    )
    booted = [device["udid"] for devices in json.loads(result.stdout)["devices"].values() for device in devices]
    if len(booted) != 1:
        raise click.ClickException(f"{len(booted)} simulators are booted. Boot exactly one with `xcrun simctl boot`.")
    return booted[0]


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
        # Until PR #678 merges, start_local.py has no simulator support and takes the product name
        if "ios_device" in inspect.signature(run_test_server).parameters:
            device = booted_simulator() if platform == "ios_simulator" else None
            run_test_server(platform_key, build_testserver, ios_device=device)  # ty: ignore
        else:
            run_test_server(platform_key, LOCAL_PLATFORMS[platform], build_testserver, cbl_version)
    finally:
        os.chdir(cwd)


def _build_reactnative(device: str) -> None:
    """Build the React Native app for the simulator, with a fresh JS bundle, and install it."""

    def run(*args: str, cwd: pathlib.Path = RN_DIR) -> None:
        subprocess.run(args, cwd=cwd, check=True)

    run("npm", "install", "--no-audit", "--no-fund")
    run("pod", "install", cwd=RN_DIR / "ios")
    # The Xcode build copies ios/main.jsbundle as it is, so the bundle must be rebuilt first
    run(
        "npx",
        "react-native",
        "bundle",
        "--platform",
        "ios",
        "--dev",
        "false",
        "--entry-file",
        "index.js",
        "--bundle-output",
        "ios/main.jsbundle",
        "--assets-dest",
        "ios",
    )
    run(
        "xcodebuild",
        "-workspace",
        "ios/CblTestServer.xcworkspace",
        "-scheme",
        "CblTestServer",
        "-sdk",
        "iphonesimulator",
        "-configuration",
        "Release",
        "-derivedDataPath",
        "ios/build",
    )
    subprocess.run(["xcrun", "simctl", "terminate", device, RN_BUNDLE_ID], capture_output=True)
    run("xcrun", "simctl", "install", device, str(RN_APP))


def _listening_port(pid: int) -> int | None:
    try:
        conns = psutil.Process(pid).net_connections(kind="tcp")
    except psutil.Error:
        return None
    return next((c.laddr.port for c in conns if c.status == psutil.CONN_LISTEN), None)


def _run_reactnative_pytest(device: str, cmd: list[str]) -> int:
    """
    Run pytest and launch the app once its WebSocket router listens.

    The app connects out to the router, whose port is picked by the OS, and the router gives up
    after 30 seconds without a connection.
    """
    subprocess.run(["xcrun", "simctl", "terminate", device, RN_BUNDLE_ID], capture_output=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as props:
        json.dump({"auto_start_tdk_page": False}, props)

    proc = subprocess.Popen([*cmd, "--test-props", props.name], cwd=SCRIPT_DIR)
    try:
        deadline = time.monotonic() + 60
        port = None
        while port is None and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.5)
            port = _listening_port(proc.pid)
        if port is not None:
            subprocess.run(
                [
                    "xcrun",
                    "simctl",
                    "launch",
                    device,
                    RN_BUNDLE_ID,
                    "-deviceID",
                    "ws0",
                    "-wsURL",
                    f"ws://localhost:{port}",
                ],
                check=True,
                capture_output=True,
            )
        return proc.wait()
    finally:
        os.unlink(props.name)


@click.command(context_settings={"ignore_unknown_options": True})
@click.option("--platform", type=click.Choice(PLATFORMS), default="c", show_default=True)
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
    device = None
    builds = not skip_testserver and (platform == "reactnative" or build_testserver is not None)
    restore = BUILD_REWRITTEN_FILES if builds else []
    if dirty := _dirty_files(restore):
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in dirty)
        raise click.ClickException(f"The build rewrites files with uncommitted changes. Commit or stash them: {names}")
    try:
        if platform == "reactnative":
            device = booted_simulator()
            if not skip_testserver:
                _build_reactnative(device)
            config["test-servers"] = [{"url": "ws://localhost:8765", "transport": "ws"}]
        else:
            if not skip_testserver:
                _start_test_server(platform, build_testserver, cbl_version)
            platform_key = get_cbl_platform(platform)
            test_server = {"url": f"http://localhost:{listen_port(platform_key)}"}
            if platform_key == "js":
                test_server["transport"] = "ws"
            config["test-servers"] = [test_server]
    finally:
        _restore_files(restore)

    if logslurp:
        if shutil.which("docker") is None:
            raise click.ClickException("--logslurp needs Docker.")
        config["logslurp"] = start_logslurp()
    CONFIG_OUT.write_text(json.dumps(config, indent=4) + "\n")

    cmd = [sys.executable, "-m", "pytest", "-v", "--config", str(CONFIG_OUT), *pytest_args]
    if device is not None:
        sys.exit(_run_reactnative_pytest(device, cmd))
    sys.exit(subprocess.call(cmd, cwd=SCRIPT_DIR))


if __name__ == "__main__":
    main()
