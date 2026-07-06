#!/usr/bin/env python3

"""
This module runs sgcollect_info on every Sync Gateway node in a previously created
E2E AWS EC2 testing backend and downloads the resulting zips to a local directory.
It is intended to run from teardown scripts right before the environment is destroyed:
the zips land in the suite's tests directory, where move_artifacts places them in
the Jenkins artifacts directory to be archived under the job's normal retention.

Functions:
    main(topology_file: str | None, output_dir: str, timeout: int,
         sgw_hosts: list[str] | None = None) -> bool:
        Main function to collect and download logs from all Sync Gateway nodes.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import click
import requests
import urllib3

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    from environment.aws.common.io import configure_terminal_encoding

    configure_terminal_encoding()

from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

SGW_ADMIN_PORT = 4985
SGW_ADMIN_AUTH = ("admin", "password")
# Caddy on each SGW node serves this directory (see sgw_setup/Caddyfile),
# so zips written here are downloadable without SSH.
CADDY_PORT = 20000
SGW_LOG_DIR = "/home/ec2-user/log"
POLL_INTERVAL_SECS = 15

# The SGW instances use a self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _sgcollect_url(scheme: str, hostname: str) -> str:
    return f"{scheme}://{hostname}:{SGW_ADMIN_PORT}/_sgcollect_info"


def _caddy_url(hostname: str, filename: str = "") -> str:
    return f"http://{hostname}:{CADDY_PORT}/{filename}"


def start_collection(hostname: str) -> str:
    """
    Start sgcollect_info on a Sync Gateway node, writing the zip into the
    Caddy-served log directory.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.

    Returns:
        str: The URL scheme ("https" or "http") that the admin API answered on.

    Raises:
        Exception: If the admin API is unreachable or rejects the request.
    """
    body = {"output_dir": SGW_LOG_DIR, "upload": False}
    for scheme in ("https", "http"):
        try:
            resp = requests.post(
                _sgcollect_url(scheme, hostname),
                json=body,
                auth=SGW_ADMIN_AUTH,
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            return scheme
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            last_error = e

    raise Exception(f"Could not reach SGW admin API on {hostname}: {last_error}")


def wait_for_collection(scheme: str, hostname: str, timeout: int) -> None:
    """
    Poll the sgcollect_info status endpoint until the run finishes.

    Args:
        scheme (str): The URL scheme the admin API answered on.
        hostname (str): The public hostname of the Sync Gateway instance.
        timeout (int): Maximum number of seconds to wait.

    Raises:
        Exception: If the collection fails or does not finish within the timeout.
    """
    deadline = time.monotonic() + timeout
    with requests.Session() as session:
        while time.monotonic() < deadline:
            resp = session.get(
                _sgcollect_url(scheme, hostname),
                auth=SGW_ADMIN_AUTH,
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            status_resp = cast(dict, resp.json())
            status = status_resp.get("status")
            if status in {"stopped", "completed"}:
                return
            if status != "running":
                raise Exception(
                    f"sgcollect_info on {hostname} ended with status={status!r}: {status_resp.get('error')}"
                )

            click.echo(f"[{hostname}] sgcollect_info still running...")
            time.sleep(POLL_INTERVAL_SECS)
    raise Exception(
        f"sgcollect_info on {hostname} did not finish within {timeout} seconds"
    )


def list_sgcollect_zips(hostname: str) -> set[str]:
    """
    List sgcollect zips currently in the node's Caddy-served log directory.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.

    Returns:
        set[str]: Filenames matching sgcollectinfo-*.zip.
    """
    resp = requests.get(
        _caddy_url(hostname),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()

    try:
        listing = resp.json()
    except ValueError:
        # Fallback: Caddy may return HTML in some configurations.
        import re

        return set(re.findall(r"sgcollectinfo-[^\"\s<>]+\\.zip", resp.text))

    files = {
        entry.get("name")
        for entry in listing
        if isinstance(entry, dict) and not entry.get("is_dir", False)
    }
    return {
        name
        for name in files
        if isinstance(name, str)
        and name.startswith("sgcollectinfo-")
        and name.endswith(".zip")
    }


def download_zip(hostname: str, filename: str, output_dir: Path) -> Path:
    """
    Stream one sgcollect zip from the node's Caddy fileserver to output_dir.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.
        filename (str): The zip filename to download.
        output_dir (Path): Local directory to write the zip into.

    Returns:
        Path: The local path of the downloaded zip.
    """
    safe_host = hostname.replace(".", "_")
    local_filename = (
        f"sgcollectinfo-{safe_host}-{filename.removeprefix('sgcollectinfo-')}"
    )
    local_path = output_dir / local_filename
    tmp_path = local_path.with_suffix(local_path.suffix + ".part")
    try:
        with requests.get(
            _caddy_url(hostname, filename), stream=True, timeout=300
        ) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        tmp_path.replace(local_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return local_path


def collect_node(hostname: str, output_dir: Path, timeout: int) -> bool:
    """
    Run sgcollect_info on a single node and download the resulting zip.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.
        output_dir (Path): Local directory to write the zip into.
        timeout (int): Seconds to wait for the collection to finish.

    Returns:
        bool: True if the collection and download succeeded, False otherwise.
    """
    try:
        # Snapshot first so a zip left over from an earlier collection on this
        # node is never mistaken for this run's output.
        before = list_sgcollect_zips(hostname)
        scheme = start_collection(hostname)
        wait_for_collection(scheme, hostname, timeout)
        new_zips = list_sgcollect_zips(hostname) - before
        if not new_zips:
            raise Exception(f"no new sgcollect zip appeared in {SGW_LOG_DIR}")

        for filename in sorted(new_zips):
            local_path = download_zip(hostname, filename, output_dir)
            size_mb = local_path.stat().st_size / (1024 * 1024)
            click.secho(
                f"[{hostname}] Downloaded {local_path} ({size_mb:.1f} MB)", fg="green"
            )
        return True
    except Exception as e:
        click.secho(f"[{hostname}] sgcollect_info failed: {e}", fg="red")
        return False


@click.command()
@click.option(
    "--topology",
    help="The topology file that was used to start the environment",
    type=click.Path(exists=True),
)
@click.option(
    "--output-dir",
    default=".",
    help="Local directory to download the sgcollect zips into "
    "(teardown passes the suite's tests dir so move_artifacts picks them up)",
)
@click.option(
    "--timeout",
    default=1800,
    help="Seconds to wait for each node's collection to finish",
)
@click.option(
    "--sgw-host",
    multiple=True,
    help="Explicit SGW hostname(s) to collect from, bypassing terraform state "
    "(for ad-hoc runs against an environment provisioned elsewhere)",
)
def cli_entry(
    topology: str | None,
    output_dir: str,
    timeout: int,
    sgw_host: tuple[str, ...],
) -> None:
    if not main(topology, output_dir, timeout, list(sgw_host)):
        sys.exit(1)


def resolve_sgw_hostnames(topology_file: str | None) -> list[str] | None:
    """
    Read the public hostnames of all Sync Gateway nodes from terraform state.

    Args:
        topology_file (str | None): The topology file that was used to start the environment.

    Returns:
        list[str] | None: The hostnames, or None if the state could not be read.
    """
    topology = TopologyConfig(topology_file) if topology_file else TopologyConfig()
    try:
        topology.read_from_terraform(str(SCRIPT_DIR))
    except Exception as e:
        click.secho(
            f"Unable to read SGW hostnames from terraform state, skipping sgcollect: {e}",
            fg="yellow",
        )
        return None

    return [sgw.hostname for sgw in topology.sync_gateways]


def main(
    topology_file: str | None,
    output_dir: str,
    timeout: int,
    sgw_hosts: list[str] | None = None,
) -> bool:
    """
    Collect and download logs from every Sync Gateway node in the environment,
    in parallel. Does not return until all collections have finished, so a
    teardown that runs afterwards cannot destroy a node mid-collection.

    Args:
        topology_file (str | None): The topology file that was used to start the environment.
        output_dir (str): Local directory to download the sgcollect zips into.
        timeout (int): Seconds to wait for each node's collection to finish.
        sgw_hosts (list[str] | None): Explicit SGW hostnames, bypassing terraform state.

    Returns:
        bool: True if every node was collected successfully, False otherwise.
    """
    hostnames = sgw_hosts or resolve_sgw_hostnames(topology_file)
    if hostnames is None:
        return False

    if len(hostnames) == 0:
        click.secho(
            "No Sync Gateway nodes in topology, nothing to collect.", fg="yellow"
        )
        return True

    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    header(f"Running sgcollect_info on {len(hostnames)} SGW node(s): {hostnames}")
    # Exiting the `with` block joins every worker (Go's WaitGroup.Wait()),
    # guaranteeing no collection is still running when teardown proceeds.
    with ThreadPoolExecutor(max_workers=len(hostnames)) as pool:
        futures = [
            pool.submit(collect_node, hostname, output_path, timeout)
            for hostname in hostnames
        ]
        results = [f.result() for f in futures]
    return all(results)


if __name__ == "__main__":
    cli_entry()
