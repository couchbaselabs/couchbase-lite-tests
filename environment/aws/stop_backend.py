#!/usr/bin/env python3

from argparse import ArgumentParser
from common.output import header
import subprocess


if __name__ == "__main__":
    parser = ArgumentParser(description="Run a script over an SSH connection.")
    parser.add_argument("--public-key-name", help="The public key stored in AWS that pairs with the private key", required=True)
    args = parser.parse_args()

    header("Starting terraform destroy")
    command = ["terraform", "destroy", f"-var=key_name={args.public_key_name}", "-auto-approve"]
    print(command)
    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}")

    header("Done!")