#!/usr/bin/env python3

import json
import subprocess
import sys
from argparse import ArgumentParser
from time import sleep
from typing import IO, Dict, cast

from common.output import header
from logslurp_setup.setup_logslurp import main as logslurp_main
from server_setup.setup_server import main as server_main
from sgw_setup.setup_sgw import main as sgw_main
from topology_setup.setup_topology import TopologyConfig
from topology_setup.setup_topology import main as topology_main


def terraform_apply(public_key_name: str, topology: TopologyConfig):
    header("Starting terraform apply")
    sgw_count = topology.total_sgw_count
    cbs_count = topology.total_cbs_count
    wants_logslurp = str(topology.wants_logslurp).lower()

    if sgw_count == 0 and cbs_count == 0 and not topology.wants_logslurp:
        print("No AWS resources requested, skipping terraform")
        return
    
    result = subprocess.run(["terraform", "init"], capture_output=False, text=True)
    if result.returncode != 0:
        raise Exception(
            f"Command 'terraform init' failed with exit status {result.returncode}: {result.stderr}"
        )

    command = [
        "terraform",
        "apply",
        f"-var=key_name={public_key_name}",
        f"-var=server_count={cbs_count}",
        f"-var=sgw_count={sgw_count}",
        f"-var=logslurp={wants_logslurp}",
        "-auto-approve",
    ]
    result = subprocess.run(command, capture_output=False, text=True)

    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )
    
    topology.read_from_terraform()

    header("Done, sleeping for 5s")
    # The machines won't be ready immediately, so we need to wait a bit
    # before SSH access succeeds
    sleep(5)


def write_config(in_config_file: str, topology: TopologyConfig, output: IO[str]):
    header(f"Writing TDK configuration based on {in_config_file}...")
    with open(in_config_file, "r") as fin:
        config_json = cast(Dict, json.load(fin))
        config_json.pop("couchbase-servers", None)
        config_json.pop("sync-gateways", None)
        config_json.pop("test-servers", None)
        config_json.pop("logslurp", None)

        if len(topology.clusters) > 0:
            cbs_instances = []
            for cluster in topology.clusters:
                for public_hostname in cluster.public_hostnames:
                    cbs_instances.append({"hostname": public_hostname})

            config_json["couchbase-servers"] = cbs_instances

        if len(topology.sync_gateways) > 0:
            sgw_instances = []
            for sgw in topology.sync_gateways:
                sgw_instances.append({"hostname": sgw.hostname, "tls": True})

            config_json["sync-gateways"] = sgw_instances

        if topology.wants_logslurp:
            config_json["logslurp"] = f"{topology.logslurp}:8180"

        if len(topology.test_servers) > 0:
            test_servers = []
            for ts in topology.test_servers:
                port = 5555 if ts.platform.startswith("dotnet") else 8080
                test_servers.append(f"http://{ts.ip_address}:{port}")

            config_json["test-servers"] = test_servers

        json.dump(config_json, output, indent=2)


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
    topology.resolve_test_servers()
    topology.dump()
    server_main(args.cbs_version, topology, args.private_key)
    sgw_main(args.sgw_url, topology, args.private_key)
    logslurp_main(topology, args.private_key)
    topology_main(topology)
    if args.tdk_config_out is not None:
        with open(args.tdk_config_out, "w") as fout:
            write_config(args.tdk_config_in, topology, fout)
    else:
        write_config(args.tdk_config_in, topology, sys.stdout)
