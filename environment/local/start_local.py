#!/usr/bin/env python3
#
# This script builds/starts the local test server and Sync Gateway (against rosmar or
# Couchbase Server). The test server and Sync Gateway build/start stages can be skipped
# independently, e.g. to iterate on Sync Gateway without rebuilding/restarting the test
# server.
#
# Usage::
#
#   uv run environment/local/start_local.py --server rosmar
#   cd tests/dev_e2e
#   uv run pytest --config "$(cat ../../environment/local/topology_config)"
#
import concurrent.futures
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import click
import requests
from cbltest.configparser import CouchbaseServerInfo
from click.core import ParameterSource

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.common.versions import resolve_latest_version
from environment.aws.topology_setup import setup_topology
from environment.aws.topology_setup.test_server_platforms.exe_bridge import ExeBridge

TOPOLOGY_CONFIG_OUTPUT = SCRIPT_DIR / "topology_config"
SYNC_GATEWAY_BIN = SCRIPT_DIR / "sync_gateway"
SYNC_GATEWAY_CONFIG_DIR = SCRIPT_DIR / "sync_gateway_config"
SYNC_GATEWAY_CONFIG = {
    "rosmar": SYNC_GATEWAY_CONFIG_DIR / "basic_sync_gateway_rosmar.json",
    "cbs": SYNC_GATEWAY_CONFIG_DIR / "basic_sync_gateway_cbs.json",
}
TOPOLOGY_CONFIG_DIR = SCRIPT_DIR / "topology_configs"
TEST_CONFIG = {
    "rosmar": TOPOLOGY_CONFIG_DIR / "rosmar_config.json",
    "cbs": TOPOLOGY_CONFIG_DIR / "cbs_config.json",
}


@click.command()
@click.option(
    "--server",
    type=click.Choice(["rosmar", "cbs"]),
    help="The Sync Gateway backing store to use. Required unless --stop-sync-gateway is set.",
)
@click.option(
    "--connstr",
    envvar="SG_TEST_COUCHBASE_SERVER_URL",
    default=None,
    help="Couchbase Server connection string to use (e.g. couchbase://127.0.0.1). "
    "Only valid with --server cbs. Defaults to $SG_TEST_COUCHBASE_SERVER_URL.",
)
@click.option(
    "--start-cbs",
    is_flag=True,
    help="Start a local single-node Couchbase Server cluster via cbdinocluster (using the "
    "Sync Gateway checkout's integration-test/start_cbs.py) instead of pointing at an "
    "existing one with --connstr. Only valid with --server cbs; requires Docker and Go. "
    "Reuses a previously started cluster (tracked in environment/local/) if one is still "
    "running.",
)
@click.option(
    "--build-testserver",
    help="Build the test server from source rather than downloading it. Takes a version string (e.g., 4.0.3).",
)
@click.option("--repo-path", help="Path to an existing sync_gateway repo to build from.")
@click.option(
    "--git-tag",
    help="Sync Gateway git tag/branch to build from (clones to sync_gateway_clone if needed).",
)
@click.option(
    "--admin-user",
    default="Administrator",
    show_default=True,
    help="Couchbase Server admin username. Only used with --connstr; ignored with --start-cbs, "
    "which always uses the default Administrator/password.",
)
@click.option(
    "--admin-password",
    default="password",
    show_default=True,
    help="Couchbase Server admin password. Only used with --connstr; ignored with --start-cbs, "
    "which always uses the default Administrator/password.",
)
@click.option(
    "--skip-testserver",
    is_flag=True,
    help="Skip downloading/building and installing/running the test server.",
)
@click.option(
    "--skip-sync-gateway-build",
    is_flag=True,
    help="Skip building Sync Gateway (reuses the existing environment/local/sync_gateway binary).",
)
@click.option(
    "--skip-sync-gateway-start",
    is_flag=True,
    help="Skip (re)starting Sync Gateway.",
)
@click.option(
    "--stop-sync-gateway",
    is_flag=True,
    help="Stop the running Sync Gateway process and exit, skipping all other stages.",
)
def main(
    server: str,
    connstr: str | None,
    start_cbs: bool,
    build_testserver: str | None,
    repo_path: str | None,
    git_tag: str | None,
    admin_user: str,
    admin_password: str,
    skip_testserver: bool,
    skip_sync_gateway_build: bool,
    skip_sync_gateway_start: bool,
    stop_sync_gateway: bool,
) -> None:
    if stop_sync_gateway:
        ExeBridge(
            exe_path=str(SYNC_GATEWAY_BIN),
            extra_args=[],
            log_filename="sync_gateway.log",
        ).stop("localhost")
        return

    if not server:
        raise click.UsageError("--server is required unless --stop-sync-gateway is set.")

    if connstr and server != "cbs":
        # --connstr defaults from $SG_TEST_COUCHBASE_SERVER_URL, so it may be set in the
        # environment without the user actually asking for it on this invocation. Only
        # treat it as a usage error if they passed --connstr explicitly.
        if click.get_current_context().get_parameter_source("connstr") == (ParameterSource.COMMANDLINE):
            raise click.UsageError("--connstr is only valid with --server cbs.")
        connstr = None

    if start_cbs:
        if server != "cbs":
            raise click.UsageError("--start-cbs is only valid with --server cbs.")
        if connstr and click.get_current_context().get_parameter_source("connstr") == (ParameterSource.COMMANDLINE):
            raise click.UsageError("--start-cbs cannot be combined with --connstr; use one or the other.")
        # Ignore any env-var-sourced --connstr default; --start-cbs supplies its own.
        connstr = None
        # --start-cbs always uses these credentials; --admin-user/--admin-password are ignored.
        admin_user, admin_password = "Administrator", "password"

    if connstr:
        _validate_single_node_connstr(connstr)

    if (not skip_sync_gateway_build or start_cbs) and bool(repo_path) == bool(git_tag):
        raise click.UsageError(
            "Exactly one of --repo-path or --git-tag must be provided, unless "
            "--skip-sync-gateway-build is set (still required with --start-cbs, to locate "
            "integration-test/start_cbs.py in the checkout)."
        )

    repo_dir = None
    if not skip_sync_gateway_build or start_cbs:
        repo_dir = resolve_sync_gateway_repo_dir(repo_path, git_tag)

    cbs_future = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        if not skip_testserver:
            futures.append(executor.submit(run_test_server, build_testserver))
        if not skip_sync_gateway_build:
            assert repo_dir is not None
            futures.append(executor.submit(build_sync_gateway, repo_dir))
        if start_cbs:
            assert repo_dir is not None
            cbs_future = executor.submit(start_cbs_cluster, repo_dir)
            futures.append(cbs_future)
        for future in futures:
            future.result()

    if cbs_future:
        connstr = cbs_future.result()

    if not skip_sync_gateway_start:
        start_sync_gateway(server, connstr, admin_user, admin_password)

    topology_config_path = resolve_topology_config(server, connstr, admin_user, admin_password)
    TOPOLOGY_CONFIG_OUTPUT.write_text(str(topology_config_path))
    click.echo(f"Topology config for pytest ({topology_config_path}) written to {TOPOLOGY_CONFIG_OUTPUT}")


def _connstr_hosts(connstr: str) -> list[str]:
    """Split a couchbase:// connection string's netloc into its comma-separated node entries."""
    return urlsplit(connstr).netloc.split(",")


def _validate_single_node_connstr(connstr: str) -> None:
    """Raise if connstr specifies more than one node — this tool only supports a single CBS node."""
    hosts = _connstr_hosts(connstr)
    if len(hosts) > 1:
        raise click.UsageError(f"--connstr must specify exactly one Couchbase Server node; got {len(hosts)}: {connstr}")


def run_test_server(build_testserver: str | None) -> None:
    """Download/build and run the local CBL test server based on --build-testserver."""
    if build_testserver:
        cbl_version = f"{build_testserver}-0"
        download = False
    else:
        cbl_version = get_latest_released_cbl_c_version()
        download = True

    config = {
        "test_servers": [
            {
                "location": "localhost",
                "download": download,
                "platform": get_cbl_platform(),
                "cbl_version": cbl_version,
            }
        ],
    }
    topology_config = setup_topology.TopologyConfig(config_input=config)
    topology_config.run_test_servers()


def _run(cmd: list[str], step: str, cwd: str | None = None) -> None:
    """Run cmd, raising a ClickException naming step and the command on failure."""
    try:
        subprocess.check_call(cmd, cwd=cwd)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"{step} failed (exit code {e.returncode}): {' '.join(cmd)}") from e


def resolve_sync_gateway_repo_dir(repo_path: str | None, git_tag: str | None) -> str:
    """
    Resolve the Sync Gateway repo directory to build from / locate integration-test scripts in.

    Exactly one of repo_path or git_tag must be provided. If git_tag is given, clones (if
    needed) into sync_gateway_clone and checks out the tag.
    """
    if bool(repo_path) == bool(git_tag):
        raise ValueError("Exactly one of repo_path or git_tag must be provided.")

    if repo_path:
        repo_dir = os.path.abspath(repo_path)
        if not os.path.isdir(repo_dir):
            raise FileNotFoundError(f"Repository path {repo_dir} does not exist.")
        return repo_dir

    assert git_tag is not None
    # We use a local clone
    repo_dir = str(SCRIPT_DIR / "sync_gateway_clone")
    repo_url = "https://github.com/couchbase/sync_gateway.git"

    if not os.path.exists(repo_dir):
        click.echo(f"Cloning {repo_url} into {repo_dir}...")
        _run(["git", "clone", repo_url, repo_dir], step="git clone")

    click.echo(f"Fetching updates and checking out {git_tag}...")
    _run(["git", "fetch", "--all", "--tags"], step="git fetch", cwd=repo_dir)
    _run(["git", "reset", "--hard"], step="git reset", cwd=repo_dir)
    _run(["git", "checkout", git_tag], step=f"git checkout {git_tag}", cwd=repo_dir)
    return repo_dir


def build_sync_gateway(repo_dir: str) -> str:
    """Build sync_gateway from source in repo_dir, returning the path to the built binary."""
    click.echo(f"Building sync_gateway in {repo_dir}...")
    build_cmd = [
        "go",
        "build",
        "-tags",
        "cb_sg_enterprise",
        "-o",
        str(SYNC_GATEWAY_BIN),
        ".",
    ]
    _run(build_cmd, step="go build", cwd=repo_dir)
    click.secho(f"Successfully built sync_gateway to {SYNC_GATEWAY_BIN}", fg="green")
    return str(SYNC_GATEWAY_BIN)


def start_cbs_cluster(repo_dir: str) -> str:
    """
    Start (or reuse) a local single-node Couchbase Server cluster via the Sync Gateway
    checkout's integration-test/start_cbs.py (which drives cbdinocluster), returning its
    connection string.

    Requires Docker and Go on PATH; cbdinocluster itself is fetched automatically via `go run`.
    """
    script = os.path.join(repo_dir, "integration-test", "start_cbs.py")
    if not os.path.exists(script):
        raise click.ClickException(
            f"{script} not found. --start-cbs requires a Sync Gateway checkout that includes "
            "integration-test/start_cbs.py — use a newer --git-tag/--repo-path, or start "
            "Couchbase Server yourself and pass --connstr instead."
        )

    click.echo("Starting local Couchbase Server via cbdinocluster...")
    env_var = "SG_TEST_COUCHBASE_SERVER_URL"
    with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as env_file:
        env_file_path = pathlib.Path(env_file.name)
    try:
        _run(
            [sys.executable, script, "--env-file", str(env_file_path)],
            step="start_cbs.py",
            cwd=str(SCRIPT_DIR),
        )

        for line in env_file_path.read_text().splitlines():
            prefix = f"export {env_var}="
            if line.startswith(prefix):
                connstr = shlex.split(line[len(prefix) :])[0]
                click.secho(f"Couchbase Server available at {connstr}", fg="green")
                return connstr
    finally:
        env_file_path.unlink(missing_ok=True)

    raise click.ClickException(f"Could not find {env_var} in start_cbs.py's output")


def parse_hostname(connstr: str) -> str:
    """Extract the bare hostname/IP of the first node from a couchbase:// connection string."""
    return _connstr_hosts(connstr)[0].split(":")[0]


def get_cbs_version(hostname: str, admin_user: str, admin_password: str) -> str:
    """Query the given Couchbase Server instance for its release version."""
    r = requests.get(
        f"http://{hostname}:8091/pools",
        auth=(admin_user, admin_password),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["implementationVersion"].split("-")[0]


def _write_patched_json(
    template_path: pathlib.Path,
    dir: pathlib.Path,
    prefix: str,
    patch_fn: Callable[[dict[str, Any]], None],
) -> str:
    """Read a JSON template, apply patch_fn(config) in place, and write the result to a new temp file in dir."""
    config = json.loads(template_path.read_text())
    patch_fn(config)
    for stale in dir.glob(f"{prefix}*.json"):
        stale.unlink()
    with tempfile.NamedTemporaryFile(mode="w", dir=dir, suffix=".json", delete=False, prefix=prefix) as f:
        json.dump(config, f)
        return f.name


def resolve_sync_gateway_config(server: str, connstr: str | None, admin_user: str, admin_password: str) -> str:
    """
    Resolve the sync_gateway config path to use for the given server type.

    For --server cbs, this also downloads the matching BackupManager tool and,
    if connstr is given, overrides the config's bootstrap server with it.
    """
    config_path = str(SYNC_GATEWAY_CONFIG[server])
    if server != "cbs":
        return config_path

    if connstr:
        hostname = parse_hostname(connstr)
        cbs_user, cbs_password = admin_user, admin_password
    else:
        cbs_info = CouchbaseServerInfo(json.loads(TEST_CONFIG["cbs"].read_text())["couchbase-servers"][0])
        hostname = cbs_info.hostname
        cbs_user, cbs_password = cbs_info.admin_user, cbs_info.admin_password

    cbs_version = get_cbs_version(hostname, cbs_user, cbs_password)
    download_tool.download_tool(download_tool.ToolName.BackupManager, cbs_version)

    if connstr:
        config_path = _write_patched_json(
            SYNC_GATEWAY_CONFIG["cbs"],
            SYNC_GATEWAY_CONFIG_DIR,
            "basic_sync_gateway_cbs_",
            lambda c: c["bootstrap"].update({"server": connstr, "username": admin_user, "password": admin_password}),
        )

    return config_path


def start_sync_gateway(server: str, connstr: str | None, admin_user: str, admin_password: str) -> None:
    """Stop any running sync_gateway process and start a new one for the given server type."""
    config_path = resolve_sync_gateway_config(server, connstr, admin_user, admin_password)
    bridge = ExeBridge(
        exe_path=str(SYNC_GATEWAY_BIN),
        extra_args=[config_path],
        log_filename="sync_gateway.log",
    )
    bridge.stop("localhost")
    bridge.run("localhost")


def resolve_topology_config(server: str, connstr: str | None, admin_user: str, admin_password: str) -> pathlib.Path:
    """Resolve the cbltest topology config to use, patching in a CBS connstr override if given."""
    config_path = TEST_CONFIG[server]
    if server != "cbs" or not connstr:
        return config_path

    def patch(c: dict[str, Any]) -> None:
        cbs = c["couchbase-servers"][0]
        cbs["hostname"] = connstr
        cbs["admin_user"] = admin_user
        cbs["admin_password"] = admin_password

    return pathlib.Path(_write_patched_json(config_path, TOPOLOGY_CONFIG_DIR, "cbs_config_", patch))


def get_cbl_platform() -> str:
    """
    Return the name of the CBL platform to use.
    """
    if sys.platform == "win32":
        return "c_windows"
    elif sys.platform == "darwin":
        return "c_macos"
    elif sys.platform.startswith("linux"):
        return "c_linux_x86_64"
    raise Exception(f"Unsupported platform: {sys.platform}")


def get_latest_released_cbl_c_version() -> str:
    return resolve_latest_version("couchbase-lite-c")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.secho(f"Error: command failed with exit code {e.returncode}", fg="red")
        sys.exit(e.returncode)
