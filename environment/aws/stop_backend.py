#!/usr/bin/env python3

import subprocess
from argparse import ArgumentParser

from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Tear down a previously created E2E AWS EC2 testing backend"
    )
    parser.add_argument(
        "--topology", help="The topology file that was used to start the environemnt"
    )
    args = parser.parse_args()
    topology = (
        TopologyConfig(args.topology) if args.topology is not None else TopologyConfig()
    )

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
