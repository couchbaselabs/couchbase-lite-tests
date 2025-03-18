#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module tears down a previously created E2E AWS EC2 testing backend. It includes functions for destroying the Terraform-managed infrastructure
and stopping the test servers.

Functions:
    main(topology_file: Optional[str]) -> None:
        Main function to tear down the AWS environment and stop the test servers.
"""

from pathlib import Path
import subprocess
from argparse import ArgumentParser
import sys
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    sys.stdout.reconfigure(encoding='utf-8')

from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig


def main(topology_file: Optional[str]) -> None:
    """
    Main function to tear down the AWS environment and stop the test servers.

    Args:
        topology_file (Optional[str]): The topology file that was used to start the environment.
    """
    topology = TopologyConfig(topology_file) if topology_file else TopologyConfig()

    header("Starting terraform destroy")
    command = [
        "terraform",
        "destroy",
        "-var=key_name=x",
        "-auto-approve",
    ]

    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        print(
            f"WARNING: Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )
        print()

    header("Done!")

    header("Stopping test servers")
    topology.stop_test_servers()
    header("Done!")

    exit(result.returncode)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Tear down a previously created E2E AWS EC2 testing backend"
    )
    parser.add_argument(
        "--topology", help="The topology file that was used to start the environment"
    )
    args = parser.parse_args()

    main(args.topology)
