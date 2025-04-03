#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module prepares an AWS EC2 environment for running end-to-end (E2E) tests. It includes functions for applying Terraform configurations,
writing TDK configurations, and managing the lifecycle of Couchbase Server, Sync Gateway, and Logslurp instances.

Functions:
    terraform_apply(public_key_name: str, topology: TopologyConfig) -> None:
        Apply the Terraform configuration to set up the AWS environment.

    write_config(in_config_file: str, topology: TopologyConfig, output: IO[str]) -> None:
        Write the TDK configuration based on the provided topology.

    main(topology: TopologyConfig, public_key_name: str, sgw_url: str, tdk_config_in: str, cbs_version: str = "7.6.4", private_key: Optional[str] = None, tdk_config_out: Optional[str] = None) -> None:
        Main function to set up the AWS environment and run the test servers.
"""

import json
import os
import subprocess
import sys
from argparse import Action, ArgumentParser
from enum import Flag, auto
from io import TextIOWrapper
from pathlib import Path
from time import sleep
from typing import IO, Dict, Optional, cast

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.output import header
from environment.aws.logslurp_setup.setup_logslurp import main as logslurp_main
from environment.aws.server_setup.setup_server import main as server_main
from environment.aws.sgw_setup.setup_sgw import main as sgw_main
from environment.aws.topology_setup.setup_topology import TopologyConfig
from environment.aws.topology_setup.setup_topology import main as topology_main


def terraform_apply(public_key_name: Optional[str], topology: TopologyConfig) -> None:
    """
    Apply the Terraform configuration to set up the AWS environment.

    Args:
        public_key_name (str): The name of the public key stored in AWS.
        topology (TopologyConfig): The topology configuration.

    Raises:
        Exception: If any Terraform command fails.
    """
    os.chdir(SCRIPT_DIR)
    header("Starting terraform apply")
    sgw_count = topology.total_sgw_count
    cbs_count = topology.total_cbs_count
    wants_logslurp = str(topology.wants_logslurp).lower()

    if sgw_count == 0 and cbs_count == 0 and not topology.wants_logslurp:
        print("No AWS resources requested, skipping terraform")
        return

    if public_key_name is None:
        raise Exception(
            "--public-key-name was not provided, but it is required for AWS resources."
        )

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


def write_config(
    in_config_file: str, topology: TopologyConfig, output: IO[str]
) -> None:
    """
    Write the TDK configuration based on the provided topology.

    Args:
        in_config_file (str): The path to the input TDK configuration file.
        topology (TopologyConfig): The topology configuration.
        output (IO[str]): The output stream to write the configuration to.
    """
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

        if topology.logslurp is not None:
            config_json["logslurp"] = f"{topology.logslurp}:8180"

        if len(topology.test_servers) > 0:
            test_servers = []
            for ts in topology.test_servers:
                port = 5555 if ts.platform.startswith("dotnet") else 8080
                test_servers.append(f"http://{ts.ip_address}:{port}")

            config_json["test-servers"] = test_servers

        json.dump(config_json, output, indent=2)


class BackendSteps(Flag):
    TERRAFORM_APPLY = auto()
    CBS_PROVISION = auto()
    SGW_PROVISION = auto()
    LS_PROVISION = auto()
    TS_RUN = auto()
    ALL = TERRAFORM_APPLY | CBS_PROVISION | SGW_PROVISION | LS_PROVISION | TS_RUN


class RemoveFlagAction(Action):
    """
    Custom argparse action to remove a specific flag from steps.
    """

    def __init__(self, option_strings, dest, nargs=0, **kwargs):
        self.flag_to_remove = kwargs.pop("flag_to_remove", None)
        super().__init__(option_strings, dest, nargs=nargs, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if not hasattr(namespace, "steps"):
            namespace.steps = BackendSteps.ALL
        if self.flag_to_remove:
            namespace.steps &= ~self.flag_to_remove


def main(
    topology: TopologyConfig,
    tdk_config_in: str,
    public_key_name: Optional[str] = None,
    sgw_url: Optional[str] = None,
    cbs_version: str = "7.6.4",
    private_key: Optional[str] = None,
    tdk_config_out: Optional[str] = None,
    steps: BackendSteps = BackendSteps.ALL,
) -> None:
    """
    Main function to set up the AWS environment and run the test servers.

    Args:
        topology (TopologyConfig): The topology configuration.
        public_key_name (str): The name of the public key stored in AWS.
        sgw_url (str): The URL of Sync Gateway to install.
        tdk_config_in (str): The path to the input TDK configuration file.
        cbs_version (str, optional): The version of Couchbase Server to install. Defaults to "7.6.4".
        private_key (Optional[str], optional): The private key to use for the SSH connection. Defaults to None.
        tdk_config_out (Optional[str], optional): The path to write the resulting TDK configuration file. Defaults to None.
        steps (BackendSteps, optional): The steps to execute. Defaults to BackendSteps.ALL.
    """
    if steps & BackendSteps.TERRAFORM_APPLY:
        terraform_apply(public_key_name, topology)
    else:
        result = subprocess.run(["terraform", "init"], capture_output=False, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command 'terraform init' failed with exit status {result.returncode}: {result.stderr}"
            )
        print()
        print("Skipping terraform apply...")
        print()
        topology.read_from_terraform()

    topology.resolve_test_servers()
    topology.dump()

    if steps & BackendSteps.CBS_PROVISION:
        server_main(cbs_version, topology, private_key)
    else:
        print("Skipping Couchbase Server provisioning...")

    if steps & BackendSteps.SGW_PROVISION:
        if len(topology.sync_gateways) > 0:
            if sgw_url is None:
                raise Exception(
                    "--sgw-url was not provided, but it is required for provisioning SGW."
                )

            sgw_main(sgw_url, topology, private_key)
    else:
        print("Skipping Sync Gateway provisioning...")

    if steps & BackendSteps.LS_PROVISION:
        logslurp_main(topology, private_key)
    else:
        print("Skipping Logslurp provisioning...")

    if steps & BackendSteps.TS_RUN:
        topology_main(topology)
    else:
        print("Skipping test server install and run...")

    if tdk_config_out is not None:
        with open(tdk_config_out, "w") as fout:
            write_config(tdk_config_in, topology, fout)
    else:
        write_config(tdk_config_in, topology, sys.stdout)


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

    parser.add_argument(
        "--no-terraform-apply",
        action=RemoveFlagAction,
        flag_to_remove=BackendSteps.TERRAFORM_APPLY,
        help="Skip terraform apply step",
    )
    parser.add_argument(
        "--no-cbs-provision",
        action=RemoveFlagAction,
        flag_to_remove=BackendSteps.CBS_PROVISION,
        help="Skip Couchbase Server provisioning step",
    )
    parser.add_argument(
        "--no-sgw-provision",
        action=RemoveFlagAction,
        flag_to_remove=BackendSteps.SGW_PROVISION,
        help="Skip Sync Gateway provisioning step",
    )
    parser.add_argument(
        "--no-ls-provision",
        action=RemoveFlagAction,
        flag_to_remove=BackendSteps.LS_PROVISION,
        help="Skip Logslurp provisioning step",
    )
    parser.add_argument(
        "--no-ts-run",
        action=RemoveFlagAction,
        flag_to_remove=BackendSteps.TS_RUN,
        help="Skip test server install and run step",
    )

    conditional_required = parser.add_argument_group("conditionally required arguments")
    conditional_required.add_argument(
        "--sgw-url", help="The URL of Sync Gateway to install (required if using SGW)"
    )
    conditional_required.add_argument(
        "--public-key-name",
        help="The public key stored in AWS that pairs with the private key (required if using any AWS elements)",
    )

    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--tdk-config-in",
        help="The path to the input TDK configuration file",
        required=True,
    )
    args = parser.parse_args()

    topology: TopologyConfig = (
        TopologyConfig(args.topology) if args.topology is not None else TopologyConfig()
    )

    main(
        topology,
        args.tdk_config_in,
        args.public_key_name,
        args.sgw_url,
        args.cbs_version,
        args.private_key,
        args.tdk_config_out,
        args.steps if args.steps is not None else BackendSteps.ALL,
    )
