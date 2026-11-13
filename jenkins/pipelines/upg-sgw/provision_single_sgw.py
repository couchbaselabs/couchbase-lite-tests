#!/usr/bin/env python3
"""Provision a single Sync Gateway node by index from the topology."""

import sys
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))

from environment.aws.common.output import header
from environment.aws.sgw_setup.setup_sgw import (
    SgwDownloadInfo,
    download_sgw_package,
    setup_config,
    setup_server,
)
from environment.aws.start_backend import check_sts_status
from environment.aws.topology_setup.setup_topology import TopologyConfig


@click.command()
@click.argument("sgw_index", type=int)
@click.option(
    "--topology",
    help="The topology file",
    type=click.Path(exists=True),
    required=True,
)
def cli_entry(sgw_index: int, topology: str) -> None:
    check_sts_status()
    topo = TopologyConfig(topology)
    topo.read_from_terraform(str(Path(topology).resolve().parent.parent))

    if sgw_index < 0 or sgw_index >= len(topo.sync_gateways):
        click.secho(
            f"SGW index {sgw_index} out of range (topology has {len(topo.sync_gateways)} nodes)",
            fg="red",
        )
        sys.exit(1)

    sgw = topo.sync_gateways[sgw_index]
    header(f"Provisioning SGW node {sgw_index} ({sgw.version}) at {sgw.hostname}")

    sgw_info = SgwDownloadInfo(sgw.version)
    download_sgw_package(sgw_info)
    setup_config(sgw.cluster_hostname)
    setup_server(sgw.hostname, topo.ssh_key, sgw_info)

    header(f"SGW node {sgw_index} provisioned successfully")


if __name__ == "__main__":
    cli_entry()
