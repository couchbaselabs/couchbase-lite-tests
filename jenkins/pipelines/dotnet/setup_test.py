#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# For others looking to analyze what this file does, it basically performs two steps.
# The first step is creating an appropriate topology JSON file.  You can see
# the templates for .NET in the topologies directory.  It rewrites the $schema and
# include property so that the relative paths are correct for the destination
# directory, adds a tag for the platform, and sets the CBL version to use in the
# test server.  Currently all of the tests that we are running use a single test
# server, a single sync gateway, and a single Couchbase Server, and this will
# be reflected in the topology file.
#
# The second step is to create a Topology instance from the resulting JSON file
# and then pass that information, along with other basically hard coded info,
# to the start_backend function which will handle the actual setup.

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    sys.stdout.reconfigure(encoding="utf-8")

from environment.aws.start_backend import main as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig


@click.command()
@click.argument("platform")
@click.argument("cbl_version")
@click.argument("dataset_version")
@click.argument("sgw_version")
@click.option(
    "--private_key",
    help="The private key to use for the SSH connection (if not default)",
)
def cli_entry(
    platform: str,
    cbl_version: str,
    dataset_version: str,
    sgw_version: str,
    private_key: Optional[str],
) -> None:
    """
    Sets up a .NET testing environment with the specified .NET platform, CBL version, dataset version, and Sync Gateway version.
    """
    topology_file = str(
        SCRIPT_DIR.parents[2]
        / "environment"
        / "aws"
        / "topology_setup"
        / "topology.json"
    )
    with open(
        str(SCRIPT_DIR / "topologies" / f"topology_single_{platform}.json"), "r"
    ) as fin:
        topology = json.load(fin)
        topology["$schema"] = "topology_schema.json"
        topology["include"] = "default_topology.json"
        topology["defaults"] = {
            "cbs": {
                "version": "7.6.4",
            },
            "sgw": {
                "version": sgw_version,
            },
        }
        topology["tag"] = platform
        topology["test_servers"][0]["cbl_version"] = cbl_version
        topology["test_servers"][0]["dataset_version"] = dataset_version
        with open(topology_file, "w") as fout:
            json.dump(topology, fout, indent=4)

    topology = TopologyConfig(topology_file)
    start_backend(
        topology,
        "jborden",
        str(SCRIPT_DIR / "config_aws.json"),
        private_key=private_key,
        tdk_config_out=str(SCRIPT_DIR.parents[2] / "tests" / "dev_e2e" / "config.json"),
    )


if __name__ == "__main__":
    cli_entry()
