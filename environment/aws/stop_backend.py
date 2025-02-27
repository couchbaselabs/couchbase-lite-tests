#!/usr/bin/env python3

import subprocess
from argparse import ArgumentParser

from common.output import header

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Tear down a previously created E2E AWS EC2 testing backend"
    )
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--public-key-name",
        help="The public key stored in AWS that pairs with the private key",
        required=True,
    )
    args = parser.parse_args()

    header("Starting terraform destroy")
    command = [
        "terraform",
        "destroy",
        f"-var=key_name={args.public_key_name}",
        "-auto-approve",
    ]
    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    header("Done!")
