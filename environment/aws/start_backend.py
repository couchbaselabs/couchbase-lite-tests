#!/usr/bin/env python3

from typing import List, cast
from sgw_setup.setup_sgw import main as sgw_main
from server_setup.setup_server import main as server_main
from common.output import header
from argparse import ArgumentParser
import subprocess
import json

def terraform_apply(public_key_name: str):
    header("Starting terraform apply")
    command = ["terraform", "apply", f"-var=key_name={public_key_name}", "-auto-approve"]
    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}")

    header("Done!")

def write_config(config_file: str):
    header(f"Writing TDK configuration based on {config_file}...")
    cbs_command = ["terraform", "output", "-json", "couchbase_instance_public_ips"]
    result = subprocess.run(cbs_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}")

    cbs_ips = cast(List[str], json.loads(result.stdout))
    sgw_command = ["terraform", "output", "-json", "sync_gateway_instance_public_ips"]
    result = subprocess.run(sgw_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(sgw_command)}' failed with exit status {result.returncode}: {result.stderr}")
    
    sgw_ips = cast(List[str], json.loads(result.stdout))
    with open(config_file, "r") as fin:
        with open("config.json", "w") as fout:
            input = fin.read()
            i = 1
            for ip in cbs_ips:
                next_arg = f"{{{{cbs-ip{i}}}}}"
                print(f"{next_arg} -> {ip}")
                input = input.replace(next_arg, ip)

            i = 1
            for ip in sgw_ips:
                next_arg = f"{{{{sgw-ip{i}}}}}"
                print(f"{next_arg} -> {ip}")
                input = input.replace(next_arg, ip)
            
            fout.write(input)

if __name__ == "__main__":
    parser = ArgumentParser(description="Run a script over an SSH connection.")
    parser.add_argument("--cbs-version", default="7.6.4", help="The version of Couchbase Server to install.")
    parser.add_argument("--sgw-version", default="4.0.0", help="The version of Sync Gateway to install.")
    parser.add_argument("--sgw-build", default=-1, type=int, help="The build number of Sync Gateway to install (latest good by default)")
    parser.add_argument("--private-key", help="The private key to use for the SSH connection (if not default)")
    parser.add_argument("--public-key-name", help="The public key stored in AWS that pairs with the private key", required=True)
    parser.add_argument("--tdk-config", help="The path to the TDK configuration file", required=True)
    args = parser.parse_args()

    terraform_apply(args.public_key_name)

    cbs_command = ["terraform", "output", "-json", "couchbase_instance_public_ips"]
    result = subprocess.run(cbs_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}")

    cbs_ips = cast(List[str], json.loads(result.stdout))
    sgw_command = ["terraform", "output", "-json", "sync_gateway_instance_public_ips"]
    result = subprocess.run(sgw_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(sgw_command)}' failed with exit status {result.returncode}: {result.stderr}")
    
    sgw_ips = cast(List[str], json.loads(result.stdout))

    server_main(cbs_ips, args.cbs_version, args.private_key)
    sgw_main(sgw_ips, args.sgw_version, args.sgw_build, args.private_key)
    write_config(args.tdk_config)