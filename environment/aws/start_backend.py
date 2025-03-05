#!/usr/bin/env python3

import json
import subprocess
import sys
from argparse import ArgumentParser
from time import sleep
from typing import IO, List, cast

from common.output import header
from server_setup.setup_server import main as server_main
from sgw_setup.setup_sgw import main as sgw_main
from logslurp_setup.setup_logslurp import main as logslurp_main
from topology_setup.setup_topology import TopologyConfig


def terraform_apply(public_key_name: str, topology: TopologyConfig):
    header("Starting terraform apply")
    result = subprocess.run(["terraform", "init"], capture_output=False, text=True)
    if result.returncode != 0:
        raise Exception(
            f"Command 'terraform init' failed with exit status {result.returncode}: {result.stderr}"
        )

    sgw_count = topology.total_sgw_count if topology is not None else 1
    cbs_count = topology.total_cbs_count if topology is not None else 1

    command = [
        "terraform",
        "apply",
        f"-var=key_name={public_key_name}",
        f"-var=server_count={cbs_count}",
        f"-var=sgw_count={sgw_count}",
        "-auto-approve",
    ]
    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    header("Done, sleeping for 5s")


def write_config(in_config_file: str, output: IO[str]):
    header(f"Writing TDK configuration based on {in_config_file}...")
    cbs_command = ["terraform", "output", "-json", "couchbase_instance_public_ips"]
    result = subprocess.run(cbs_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    cbs_ips = cast(List[str], json.loads(result.stdout))
    sgw_command = ["terraform", "output", "-json", "sync_gateway_instance_public_ips"]
    result = subprocess.run(sgw_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(sgw_command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    sgw_ips = cast(List[str], json.loads(result.stdout))
    with open(in_config_file, "r") as fin:
        input = fin.read()
        i = 1
        for ip in cbs_ips:
            next_arg = f"{{{{cbs-ip{i}}}}}"
            print(f"{next_arg} -> {ip}")
            input = input.replace(next_arg, ip)
            i += 1

        i = 1
        for ip in sgw_ips:
            next_arg = f"{{{{sgw-ip{i}}}}}"
            print(f"{next_arg} -> {ip}")
            input = input.replace(next_arg, ip)
            i += 1
        
        logslurp_ip = get_logslurp_ip()
        print(f"ls-ip -> {logslurp_ip}")
        input = input.replace("{{ls-ip}}", logslurp_ip)

        output.write(input)

def get_logslurp_ip():
    logslurp_command = ["terraform", "output", "-json", "logslurp_instance_public_ip"]
    result = subprocess.run(logslurp_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(logslurp_command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    return cast(str, json.loads(result.stdout))

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Prepare an AWS EC2 environment for running E2E tests"
    )
    parser.add_argument(
        "--cbs-version",
        default="7.6.4",
        help="The version of Couchbase Server to install.",
    )
    parser.add_argument(
        "--private-key",
        help="The private key to use for the SSH connection (if not default)",
    )
    parser.add_argument(
        "--tdk-config-out",
        help="The path to the write the resulting TDK configuration file (stdout if empty)",
    )
    parser.add_argument(
        "--topology",
        help="The path to the topology configuration file",
    )
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--public-key-name",
        help="The public key stored in AWS that pairs with the private key",
        required=True,
    )
    required.add_argument(
        "--tdk-config-in",
        help="The path to the input TDK configuration file",
        required=True,
    )
    required.add_argument(
        "--sgw-url", help="The URL of Sync Gateway to install.", required=True
    )
    args = parser.parse_args()

    topology: TopologyConfig = (
        TopologyConfig(args.topology) if args.topology is not None else TopologyConfig()
    )

    terraform_apply(args.public_key_name, topology)

    # The machines won't be ready immediately, so we need to wait a bit
    # before SSH access succeeds
    sleep(5)

    topology.read_from_terraform()
    topology.dump()
    server_main(args.cbs_version, topology, args.private_key)
    sgw_main(args.sgw_url, topology, args.private_key)
    logslurp_main(get_logslurp_ip(), args.private_key)
    if args.tdk_config_out is not None:
        with open(args.tdk_config_out, "w") as fout:
            write_config(args.tdk_config_in, fout)
    else:
        write_config(args.tdk_config_in, sys.stdout)
