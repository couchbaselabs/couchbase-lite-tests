#!/usr/bin/env python3

"""
This module runs sgcollect_info on every Sync Gateway node in a previously created
E2E AWS EC2 testing backend and uploads the results to the Couchbase support portal.
It is intended to run from teardown scripts right before the environment is destroyed
so that SGW diagnostics survive the teardown.

Functions:
    main(topology_file: str | None, upload_host: str, customer: str, timeout: int,
         sgw_hosts: list[str] | None = None, ticket: str | None = None) -> bool:
        Main function to collect and upload logs from all Sync Gateway nodes.
"""

import re
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
POLL_INTERVAL_SECS = 15

# The SGW instances use a self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _sgcollect_url(scheme: str, hostname: str) -> str:
    return f"{scheme}://{hostname}:{SGW_ADMIN_PORT}/_sgcollect_info"


def start_collection(
    hostname: str, upload_host: str, customer: str, ticket: str | None
) -> str:
    """
    Start sgcollect_info on a Sync Gateway node.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.
        upload_host (str): The host to upload the collected logs to.
        customer (str): The customer name to file the upload under.
        ticket (str | None): Optional ticket number (1-7 digits) grouping the
            uploads of one run under <customer>/<ticket>/ on the upload host.

    Returns:
        str: The URL scheme ("https" or "http") that the admin API answered on.

    Raises:
        Exception: If the admin API is unreachable or rejects the request.
    """
    body: dict[str, str | bool] = {
        "output_dir": "/tmp",
        "upload": True,
        "upload_host": upload_host,
        "customer": customer,
    }
    if ticket:
        body["ticket"] = ticket
    last_error: Exception | None = None
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
        Exception: If the collection does not finish within the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(
            _sgcollect_url(scheme, hostname),
            auth=SGW_ADMIN_AUTH,
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        if cast(dict, resp.json()).get("status") != "running":
            return

        click.echo(f"[{hostname}] sgcollect_info still running...")
        time.sleep(POLL_INTERVAL_SECS)

    raise Exception(
        f"sgcollect_info on {hostname} did not finish within {timeout} seconds"
    )


@click.command()
@click.option(
    "--topology",
    help="The topology file that was used to start the environment",
    type=click.Path(exists=True),
)
@click.option(
    "--upload-host",
    default="uploads.couchbase.com",
    help="The host to upload the collected logs to",
)
@click.option(
    "--customer",
    default="sgw-qe",
    help="The customer name to file the upload under",
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
@click.option(
    "--ticket",
    default=None,
    help="Ticket number (1-7 digits, e.g. the Jenkins BUILD_NUMBER) grouping "
    "this run's uploads under <customer>/<ticket>/ on the upload host",
)
def cli_entry(
    topology: str | None,
    upload_host: str,
    customer: str,
    timeout: int,
    sgw_host: tuple[str, ...],
    ticket: str | None,
) -> None:
    if not main(topology, upload_host, customer, timeout, list(sgw_host), ticket):
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


def collect_node(
    hostname: str, upload_host: str, customer: str, timeout: int, ticket: str | None
) -> bool:
    """
    Run sgcollect_info on a single node from start to upload completion.

    Args:
        hostname (str): The public hostname of the Sync Gateway instance.
        upload_host (str): The host to upload the collected logs to.
        customer (str): The customer name to file the upload under.
        timeout (int): Seconds to wait for the collection to finish.
        ticket (str | None): Optional ticket number grouping this run's uploads.

    Returns:
        bool: True if the collection succeeded, False otherwise.
    """
    try:
        scheme = start_collection(hostname, upload_host, customer, ticket)
        wait_for_collection(scheme, hostname, timeout)
        destination = f"{upload_host}/{customer}" + (f"/{ticket}" if ticket else "")
        click.secho(f"[{hostname}] Logs uploaded to {destination}", fg="green")
        return True
    except Exception as e:
        click.secho(f"[{hostname}] sgcollect_info failed: {e}", fg="red")
        return False


def main(
    topology_file: str | None,
    upload_host: str,
    customer: str,
    timeout: int,
    sgw_hosts: list[str] | None = None,
    ticket: str | None = None,
) -> bool:
    """
    Collect and upload logs from every Sync Gateway node in the environment,
    in parallel. Does not return until all collections have finished, so a
    teardown that runs afterwards cannot destroy a node mid-collection.

    Args:
        topology_file (str | None): The topology file that was used to start the environment.
        upload_host (str): The host to upload the collected logs to.
        customer (str): The customer name to file the upload under.
        timeout (int): Seconds to wait for each node's collection to finish.
        sgw_hosts (list[str] | None): Explicit SGW hostnames, bypassing terraform state.
        ticket (str | None): Optional ticket number grouping this run's uploads.

    Returns:
        bool: True if every node was collected successfully, False otherwise.
    """
    if ticket and not re.fullmatch(r"\d{1,7}", ticket):
        # SGW rejects malformed tickets with a 400; dropping it keeps the
        # upload itself (the part that matters) alive.
        click.secho(f"Ignoring ticket '{ticket}': must be 1 to 7 digits.", fg="yellow")
        ticket = None

    hostnames = sgw_hosts or resolve_sgw_hostnames(topology_file)
    if hostnames is None:
        return False

    if len(hostnames) == 0:
        click.secho(
            "No Sync Gateway nodes in topology, nothing to collect.", fg="yellow"
        )
        return True

    header(f"Running sgcollect_info on {len(hostnames)} SGW node(s): {hostnames}")
    # Exiting the `with` block joins every worker (Go's WaitGroup.Wait()),
    # guaranteeing no collection is still running when teardown proceeds.
    with ThreadPoolExecutor(max_workers=len(hostnames)) as pool:
        results = list(
            pool.map(
                lambda hostname: collect_node(
                    hostname, upload_host, customer, timeout, ticket
                ),
                hostnames,
            )
        )

    return all(results)


if __name__ == "__main__":
    cli_entry()
