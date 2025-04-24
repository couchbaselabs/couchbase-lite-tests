#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module tears down a previously created E2E AWS EC2 testing backend. It includes functions for destroying the Terraform-managed infrastructure
and stopping the test servers.

Functions:
    main(topology_file: Optional[str]) -> None:
        Main function to tear down the AWS environment and stop the test servers.
"""

import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Optional, cast

import click

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.output import header
from environment.aws.pulumi.setup import pumuli_down
from environment.aws.topology_setup.setup_topology import TopologyConfig


@click.command()
@click.option(
    "--topology",
    help="The topology file that was used to start the environment",
    type=click.Path(exists=True),
)
def main(topology: Optional[str]) -> None:
    """
    Main function to tear down the AWS environment and stop the test servers.

    Args:
        topology_file (Optional[str]): The topology file that was used to start the environment.
    """
    topology_obj = TopologyConfig(topology) if topology else TopologyConfig()
    result_code = pumuli_down(topology_obj)

    header("Stopping test servers")
    topology_obj.stop_test_servers()
    header("Done!")

    exit(result_code)


if __name__ == "__main__":
    main()
