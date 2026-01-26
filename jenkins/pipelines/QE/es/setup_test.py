#!/usr/bin/env python3

import json
from pathlib import Path
from typing import Any

import click

from environment.aws.start_backend import script_entry as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent


def generate_topology(
    *,
    es_version: str,
    topology_in: Path,
    topology_out: Path,
    sgw_version: str | None = None,
    cbs_version: str | None = None,
    tag: str = "es",
) -> None:
    """
    Generate a topology JSON without injecting implicit CBS/SGW defaults.
    """

    with topology_in.open() as f:
        topology: dict[str, Any] = json.load(f)

    # Normalize schema
    topology["$schema"] = "topology_schema.json"
    for es in topology["edge_servers"]:
        es["version"] = es_version
    sgws = topology.get("sync_gateways")
    if sgws:
        for sgw in sgws:
            sgw["version"] = sgw_version
    cbs = topology.get("clusters")
    if cbs:
        for cb in cbs:
            cb["version"] = cbs_version

    topology_out.parent.mkdir(parents=True, exist_ok=True)
    with topology_out.open("w") as f:
        json.dump(topology, f, indent=2)

    click.secho("Generated topology:", fg="cyan")
    click.echo(json.dumps(topology, indent=2))


@click.command()
@click.argument("es_version")
@click.argument(
    "topology_file",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--sgw-version", default="4.0.0", help="Provision Sync Gateway")
@click.option("--cbs-version", default="7.6.8", help="Provision Couchbase Server")
@click.option("--config-file", default="config.json", help="Backend config file")
def main(
    es_version: str,
    topology_file: Path,
    sgw_version: str | None,
    cbs_version: str | None,
    config_file: str,
) -> None:
    topology_out = (
        SCRIPT_DIR.parents[3]
        / "environment"
        / "aws"
        / "topology_setup"
        / "topology.json"
    )

    config_in = SCRIPT_DIR / config_file
    config_out = SCRIPT_DIR.parents[3] / "tests" / "QE" / "config.json"

    if sgw_version is None or len(sgw_version) == 0:
        sgw_version = "4.0.0"
    if cbs_version is None or len(cbs_version) == 0:
        cbs_version = "7.6.8"

    click.secho("🚀 Backend setup", fg="blue", bold=True)
    click.echo(f"Edge Server Version : {es_version}")
    click.echo(f"Topology File       : {topology_file}")
    click.echo(f"SGW Version         : {sgw_version}")
    click.echo(f"CBS Version         : {cbs_version}")
    click.echo()
    generate_topology(
        es_version=es_version,
        topology_in=topology_file,
        topology_out=topology_out,
        sgw_version=sgw_version,
        cbs_version=cbs_version,
    )

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
