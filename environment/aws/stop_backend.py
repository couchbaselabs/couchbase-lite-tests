#!/usr/bin/env python3

"""
This module tears down a previously created E2E AWS EC2 testing backend. It includes functions for destroying the Terraform-managed infrastructure
and stopping the test servers.

Functions:
    main(topology_file: Optional[str]) -> None:
        Main function to tear down the AWS environment and stop the test servers.
"""

import subprocess
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import cast

import click

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig


@click.command()
@click.option(
    "--topology",
    help="The topology file that was used to start the environment",
    type=click.Path(exists=True),
)
def main(topology: str | None) -> None:
    """
    Main function to tear down the AWS environment and stop the test servers.

    Args:
        topology_file (Optional[str]): The topology file that was used to start the environment.
    """
    topology_obj = TopologyConfig(topology) if topology else TopologyConfig()

    header("Starting terraform destroy")
    command = [
        "terraform",
        "destroy",
        "-var=key_name=x",
        "-auto-approve",
    ]

    result = subprocess.run(command, cwd=SCRIPT_DIR, capture_output=False, text=True)

    if result.returncode != 0:
        click.secho(
            f"WARNING: Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}",
            fg="yellow",
        )
        click.echo()

    header("Done!")

    header("Stopping test servers")
    topology_obj.stop_test_servers()
    header("Done!")

    exit(result.returncode)


if __name__ == "__main__":
    main()
