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
import psutil
import requests
from cbltest.configparser import CouchbaseServerInfo
from click.core import ParameterSource

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.common.output import header
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
SYNC_GATEWAY_EXE_NAME = SYNC_GATEWAY_BIN.name
# Stem shared by every per-instance file, so a whole run's worth can be swept as a set.
SG_INSTANCE_STEM = "sync_gateway_instance"
# Matches the per-instance logs of any run, plus the single sync_gateway.log written before instances
# were numbered -- that name is never written now, so left behind it would only ever mislead.
SG_LOG_GLOB = "sync_gateway*.log"
# Sync Gateway's own default ports, which instance 1 keeps so a single-instance run is unchanged.
SG_BASE_PUBLIC_PORT = 4984
SG_BASE_ADMIN_PORT = 4985
SG_BASE_METRICS_PORT = 4986
# Instance N's ports are the defaults plus (N - 1) * stride, leaving room between instances.
SG_PORT_STRIDE = 10
# How long a terminated Sync Gateway gets to release its ports before it is killed outright.
SG_STOP_TIMEOUT_SECONDS = 10
# Highest instance number probed when working out what an earlier run left running.
SG_MAX_DISCOVERED_INSTANCES = 10


# Instances are numbered from 1 everywhere -- ports, filenames and console output alike -- so the
# number printed at startup is the number naming that instance's files. Every name below is derived
# from sync_gateway_instance_name() rather than spelled out, which is what keeps them in step.
def sync_gateway_ports(number: int) -> tuple[int, int, int]:
    """Return the (public, admin, metrics) ports for the given 1-based Sync Gateway instance."""
    offset = (number - 1) * SG_PORT_STRIDE
    return SG_BASE_PUBLIC_PORT + offset, SG_BASE_ADMIN_PORT + offset, SG_BASE_METRICS_PORT + offset


def sync_gateway_instance_name(number: int) -> str:
    """Stem naming every file of the given 1-based instance, e.g. `sync_gateway_instance2`."""
    return f"{SG_INSTANCE_STEM}{number}"


def sync_gateway_config_prefix(number: int) -> str:
    """Generated-config filename prefix for the given 1-based instance."""
    return f"{sync_gateway_instance_name(number)}_"


def sync_gateway_log_name(number: int) -> str:
    """Filename the given 1-based instance's console output is captured to."""
    return f"{sync_gateway_instance_name(number)}.log"


def sync_gateway_api_config(number: int) -> dict[str, str]:
    """The Sync Gateway `api` config block pinning the given 1-based instance to its own ports."""
    public, admin, metrics = sync_gateway_ports(number)
    return {
        "public_interface": f":{public}",
        "admin_interface": f"127.0.0.1:{admin}",
        "metrics_interface": f"127.0.0.1:{metrics}",
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
    "--sync-gateways",
    type=int,
    default=1,
    show_default=True,
    help="Number of Sync Gateway instances to start against the same backing store. Instances are "
    f"numbered from 1; instance N binds to Sync Gateway's default ports shifted by (N-1)*{SG_PORT_STRIDE} "
    "(so instance 2 uses 4994/4995/4996) and writes sync_gateway_instanceN.log, and the topology "
    "config lists them all. Values above 1 require --server cbs, since rosmar's in-memory bucket is "
    "per-process and instances would not share data.",
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
    sync_gateways: int,
    skip_testserver: bool,
    skip_sync_gateway_build: bool,
    skip_sync_gateway_start: bool,
    stop_sync_gateway: bool,
) -> None:
    if stop_sync_gateway:
        stop_all_sync_gateways()
        return

    if not server:
        raise click.UsageError("--server is required unless --stop-sync-gateway is set.")

    if sync_gateways < 1:
        raise click.UsageError(f"--sync-gateways must be at least 1; got {sync_gateways}.")

    if sync_gateways > 1 and server != "cbs":
        raise click.UsageError(
            "--sync-gateways > 1 requires --server cbs. Each rosmar instance keeps its bucket in its "
            "own process memory, so the instances would not share any data."
        )

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
        start_sync_gateways(server, connstr, admin_user, admin_password, sync_gateways)
    else:
        sync_gateways = resolve_skipped_sync_gateway_count(sync_gateways)

    topology_config_path = resolve_topology_config(server, connstr, admin_user, admin_password, sync_gateways)
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


def _remove_generated(dir: pathlib.Path, pattern: str) -> None:
    """Delete previously generated files in dir matching pattern, ignoring any that are already gone."""
    for stale in dir.glob(pattern):
        stale.unlink(missing_ok=True)


def _write_patched_json(
    template_path: pathlib.Path,
    dir: pathlib.Path,
    prefix: str,
    patch_fn: Callable[[dict[str, Any]], None],
    *,
    clean_stale: bool = True,
) -> str:
    """
    Read a JSON template, apply patch_fn(config) in place, and write the result to a new temp file in dir.

    Earlier files under the same prefix are removed first so the random temp names cannot pile up
    across runs. A caller writing a *set* of files whose prefixes differ per member passes
    clean_stale=False and sweeps the whole set itself -- a per-write sweep only ever matches that
    member's own prefix, which would leave the surplus members of a larger previous run behind.
    """
    config = json.loads(template_path.read_text())
    patch_fn(config)
    if clean_stale:
        _remove_generated(dir, f"{prefix}*.json")
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


def _is_our_sync_gateway(proc: psutil.Process) -> bool:
    """
    Whether proc is the sync_gateway binary this script builds, rather than some other copy of it.

    A process whose executable cannot be read is treated as ours: it is more likely an instance
    running under another user than an unrelated Sync Gateway, and terminating it will fail loudly
    below rather than silently, which is the better outcome when it is holding our ports.
    """
    try:
        return pathlib.Path(proc.exe()) == SYNC_GATEWAY_BIN
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return True


def _wait_for_exit(procs: list[psutil.Process]) -> None:
    """
    Wait for terminated processes to actually exit, killing any that overstay.

    Sync Gateway holds its listening ports until it has finished shutting down, and the next instance
    binds those same ports within milliseconds -- without this wait it loses the race and dies with
    "address already in use", while the script reports a successful start.
    """
    if not procs:
        return

    _, alive = psutil.wait_procs(procs, timeout=SG_STOP_TIMEOUT_SECONDS)
    for proc in alive:
        click.secho(f"PID {proc.pid} did not exit within {SG_STOP_TIMEOUT_SECONDS}s; killing it", fg="yellow")
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            continue

    if alive:
        psutil.wait_procs(alive, timeout=SG_STOP_TIMEOUT_SECONDS)


def stop_all_sync_gateways() -> None:
    """
    Terminate every sync_gateway process started from this checkout, and wait for its ports to free.

    ExeBridge.stop() stops only the first process matching the executable name, which is not enough
    once more than one instance is running. Processes are matched on their executable path rather
    than that name alone: a name match would also kill a system-installed Sync Gateway, or one run
    from a second checkout of this repo, neither of which is ours to stop.
    """
    header(f"Stopping all '{SYNC_GATEWAY_EXE_NAME}' processes from {SYNC_GATEWAY_BIN}")
    terminated: list[psutil.Process] = []
    refused: list[psutil.Process] = []
    for proc in psutil.process_iter():
        try:
            if proc.name() != SYNC_GATEWAY_EXE_NAME:
                continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # The process list is a snapshot; anything that exits from under us is not our concern.
            continue

        if not _is_our_sync_gateway(proc):
            continue

        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            refused.append(proc)
            continue

        click.secho(f"Stopped PID {proc.pid}", fg="green")
        terminated.append(proc)

    for proc in refused:
        click.secho(
            f"Not allowed to stop PID {proc.pid} -- it may still be holding Sync Gateway's ports",
            fg="red",
        )

    if not terminated and not refused:
        click.secho(f"Unable to find process to stop ({SYNC_GATEWAY_EXE_NAME})", fg="yellow")

    _wait_for_exit(terminated)


def discover_running_sync_gateways() -> int:
    """
    Count the Sync Gateway instances already listening, by probing consecutive admin ports.

    Any response at all means something is bound there; only a refused connection ends the count.
    """
    for number in range(1, SG_MAX_DISCOVERED_INSTANCES + 1):
        _, admin_port, _ = sync_gateway_ports(number)
        try:
            requests.get(f"http://localhost:{admin_port}/", timeout=2)
        except requests.RequestException:
            return number - 1

    return SG_MAX_DISCOVERED_INSTANCES


def resolve_skipped_sync_gateway_count(requested: int) -> int:
    """
    Decide how many instances to describe when --skip-sync-gateway-start started none of them.

    The count drives the topology, so taking --sync-gateways at face value here would advertise nodes
    that may not exist -- or, at its default of 1, quietly drop the extra nodes an earlier run left
    running. Probe for the truth instead, and only accept an explicit --sync-gateways that agrees.
    """
    running = discover_running_sync_gateways()
    explicit = click.get_current_context().get_parameter_source("sync_gateways") == ParameterSource.COMMANDLINE
    if explicit and running != requested:
        raise click.UsageError(
            f"--sync-gateways {requested} does not match the {running} Sync Gateway instance(s) currently "
            "listening, and --skip-sync-gateway-start means this run will not change that. Drop "
            f"--sync-gateways to describe what is running, or drop --skip-sync-gateway-start to start {requested}."
        )

    if running == 0:
        click.secho(
            "No Sync Gateway instances are listening, so the topology config will describe none. "
            "Drop --skip-sync-gateway-start to start some.",
            fg="yellow",
        )
    else:
        click.echo(f"Describing the {running} already-running Sync Gateway instance(s) in the topology config")

    return running


def _pin_api_ports(number: int) -> Callable[[dict[str, Any]], None]:
    """Return a patch pinning a config's `api` block to the instance's ports, keeping any other api keys."""

    def patch(config: dict[str, Any]) -> None:
        config["api"] = {**config.get("api", {}), **sync_gateway_api_config(number)}

    return patch


def sync_gateway_instance_configs(base_config_path: str, count: int) -> list[str]:
    """
    Write one copy of base_config_path per instance, each pinned to that instance's ports.

    Every previously generated instance config is swept first: the filenames carry the instance
    number, so a run asking for fewer instances than the last would otherwise leave the surplus
    ones on disk.

    Instance 1 lands on Sync Gateway's own default ports, so a single-instance run still reaches
    Sync Gateway where everything expects to find it.
    """
    _remove_generated(SYNC_GATEWAY_CONFIG_DIR, f"{SG_INSTANCE_STEM}*.json")

    return [
        _write_patched_json(
            pathlib.Path(base_config_path),
            SYNC_GATEWAY_CONFIG_DIR,
            sync_gateway_config_prefix(number),
            _pin_api_ports(number),
            clean_stale=False,
        )
        for number in range(1, count + 1)
    ]


def start_sync_gateways(server: str, connstr: str | None, admin_user: str, admin_password: str, count: int = 1) -> None:
    """Stop any running sync_gateway processes and start `count` new ones for the given server type."""
    base_config_path = resolve_sync_gateway_config(server, connstr, admin_user, admin_password)
    config_paths = sync_gateway_instance_configs(base_config_path, count)

    stop_all_sync_gateways()

    # Wipe every Sync Gateway log before launching. ExeBridge truncates the log of each instance it
    # starts anyway, so this only really matters for the logs this run has no instance for -- left
    # alone, they sit there looking current and send you reading a stale instance.
    header("Removing previous Sync Gateway logs")
    _remove_generated(SCRIPT_DIR, SG_LOG_GLOB)

    for number, config_path in enumerate(config_paths, start=1):
        public_port, admin_port, _ = sync_gateway_ports(number)
        click.echo(
            f"Sync Gateway instance {number}/{count}: public {public_port}, admin {admin_port}, "
            f"log {sync_gateway_log_name(number)}"
        )
        ExeBridge(
            exe_path=str(SYNC_GATEWAY_BIN),
            extra_args=[config_path],
            log_filename=sync_gateway_log_name(number),
        ).run("localhost")


def resolve_topology_config(
    server: str, connstr: str | None, admin_user: str, admin_password: str, count: int = 1
) -> pathlib.Path:
    """
    Resolve the cbltest topology config to use.

    Patches in a CBS connstr override if given, and expands `sync-gateways` to one entry per running
    instance so tests marked `min_sync_gateways(N)` can see them all.

    Any topology config generated by an earlier run is swept first, for every server rather than just
    this one: the filename carries the server name, so switching servers -- or dropping back to the
    unpatched checked-in template below -- would otherwise leave the previous run's config sitting in
    the directory looking current.
    """
    for name in TEST_CONFIG:
        _remove_generated(TOPOLOGY_CONFIG_DIR, f"{name}_config_*.json")

    config_path = TEST_CONFIG[server]
    override_cbs = server == "cbs" and bool(connstr)
    if not override_cbs and count == 1:
        return config_path

    def patch(c: dict[str, Any]) -> None:
        if override_cbs:
            cbs = c["couchbase-servers"][0]
            cbs["hostname"] = connstr
            cbs["admin_user"] = admin_user
            cbs["admin_password"] = admin_password

        template = c["sync-gateways"][0]
        c["sync-gateways"] = []
        for number in range(1, count + 1):
            public_port, admin_port, _ = sync_gateway_ports(number)
            c["sync-gateways"].append({**template, "port": public_port, "admin_port": admin_port})

    return pathlib.Path(
        _write_patched_json(config_path, TOPOLOGY_CONFIG_DIR, f"{server}_config_", patch, clean_stale=False)
    )


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
    r = requests.get("http://proget.build.couchbase.com:8080/api/latest_release?product=couchbase-lite-c")
    r.raise_for_status()
    return r.json()["version"]


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.secho(f"Error: command failed with exit code {e.returncode}", fg="red")
        sys.exit(e.returncode)
