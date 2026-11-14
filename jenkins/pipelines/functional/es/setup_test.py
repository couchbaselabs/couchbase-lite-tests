#!/usr/bin/env python3

import json
import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Any

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

from environment.aws.common.versions import resolve_latest_version
from environment.aws.download_tool import ToolName, download_tool
from environment.aws.start_backend import script_entry as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig


def generate_topology(
    *,
    es_version: str,
    topology_in: Path,
    topology_out: Path,
    sgw_version: str,
    cbs_version: str,
    cbl_version: str,
) -> None:
    """Generate the topology JSON from the template, pinning every product's version."""

    with topology_in.open() as f:
        topology: dict[str, Any] = json.load(f)

    # Normalize schema
    topology["$schema"] = "topology_schema.json"
    for es in topology["edge_servers"]:
        es["version"] = es_version
    for sgw in topology["sync_gateways"]:
        sgw["version"] = sgw_version
    for cb in topology["clusters"]:
        cb["version"] = cbs_version
    for ts in topology["test_servers"]:
        ts["cbl_version"] = cbl_version

    topology_out.parent.mkdir(parents=True, exist_ok=True)
    with topology_out.open("w") as f:
        json.dump(topology, f, indent=2)

    click.secho("Generated topology:", fg="cyan")
    click.echo(json.dumps(topology, indent=2))


@click.command()
@click.argument("es_version")
@click.option("--sgw-version", default=None, help="Sync Gateway version (omit for latest release)")
@click.option("--cbl-version", required=True, help="CBL-JS version-build for the JS test server, e.g. 1.1.0-25")
@click.option("--config-file", default="config.json", help="Backend config file")
def main(
    es_version: str,
    sgw_version: str | None,
    cbl_version: str,
    config_file: str,
) -> None:
    topology_file = SCRIPT_DIR / "topology.json"
    topology_out = SCRIPT_DIR.parents[3] / "environment" / "aws" / "topology_setup" / "topology.json"

    config_in = SCRIPT_DIR / config_file
    config_out = SCRIPT_DIR.parents[3] / "tests" / "functional" / "config.json"

    if not sgw_version or len(sgw_version.split(".")) < 3:
        sgw_version = resolve_latest_version("sync-gateway", sgw_version or None)
    cbs_version = resolve_latest_version("couchbase-server")

    click.secho("🚀 Backend setup", fg="blue", bold=True)
    click.echo(f"Edge Server Version : {es_version}")
    click.echo(f"Topology File       : {topology_file}")
    click.echo(f"SGW Version         : {sgw_version}")
    click.echo(f"CBS Version         : {cbs_version}")
    click.echo(f"CBL Version         : {cbl_version}")
    click.echo()
    generate_topology(
        es_version=es_version,
        topology_in=topology_file,
        topology_out=topology_out,
        sgw_version=sgw_version,
        cbs_version=cbs_version,
        cbl_version=cbl_version,
    )

    download_tool(ToolName.BucketPool)

    topology_obj = TopologyConfig(str(topology_out))
    print(f"topology_obj: {topology_obj}")
    start_backend(
        topology_obj,
        str(config_in),
        str(config_out),
    )

    click.secho("🎉 Backend started successfully", fg="green", bold=True)


if __name__ == "__main__":
    main()
