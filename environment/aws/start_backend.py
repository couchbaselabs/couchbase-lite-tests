#!/usr/bin/env python3

"""
This module prepares an AWS EC2 environment for running end-to-end (E2E) tests. It includes functions for applying Terraform configurations,
writing TDK configurations, and managing the lifecycle of Couchbase Server, Sync Gateway, and Logslurp instances.

Functions:
    terraform_apply(public_key_name: str, topology: TopologyConfig) -> None:
        Apply the Terraform configuration to set up the AWS environment.

    write_config(in_config_file: str, topology: TopologyConfig, output: IO[str]) -> None:
        Write the TDK configuration based on the provided topology.

    main(topology: TopologyConfig, public_key_name: str, sgw_url: str, tdk_config_in: str, cbs_version: str = "7.6.4", tdk_config_out: Optional[str] = None) -> None:
        Main function to set up the AWS environment and run the test servers.
"""

import json
import subprocess
import sys
from enum import Flag, auto
from io import TextIOWrapper
from pathlib import Path
from time import sleep
from typing import IO, Any, cast

import click

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.output import header
from environment.aws.es_setup.setup_edge_servers import main as es_main
from environment.aws.lb_setup.setup_load_balancers import main as lb_main
from environment.aws.logslurp_setup.setup_logslurp import main as logslurp_main
from environment.aws.server_setup.setup_server import main as server_main
from environment.aws.sgw_setup.setup_sgw import main as sgw_main
from environment.aws.topology_setup.setup_topology import TopologyConfig
from environment.aws.topology_setup.setup_topology import main as topology_main


class TopologyParamType(click.ParamType):
    name = "path"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> TopologyConfig:
        if isinstance(value, TopologyConfig):
            return value

        if value is None:
            return TopologyConfig()

        if isinstance(value, str):
            return TopologyConfig(cast(str, value))

        self.fail("Unable to convert non string value to TopologyConfig", param, ctx)


def topology_has_aws_resources(topology: TopologyConfig) -> bool:
    """
    Check if the topology has any AWS resources.

    Args:
        topology (TopologyConfig): The topology configuration.

    Returns:
        bool: True if there are AWS resources, False otherwise.
    """
    return (
        topology.total_sgw_count > 0
        or topology.total_es_count > 0
        or topology.total_cbs_count > 0
        or topology.total_lb_count > 0
        or topology.wants_logslurp
    )


def terraform_apply(topology: TopologyConfig) -> None:
    """
    Apply the Terraform configuration to set up the AWS environment.

    Args:
        public_key_name (str): The name of the public key stored in AWS.
        topology (TopologyConfig): The topology configuration.

    Raises:
        Exception: If any Terraform command fails.
    """

    header("Starting terraform apply")
    if not topology_has_aws_resources(topology):
        click.secho("No AWS resources requested, skipping terraform", fg="yellow")
        return

    result = subprocess.run(
        ["terraform", "init"], capture_output=False, text=True, cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        raise Exception(
            f"Command 'terraform init' failed with exit status {result.returncode}: {result.stderr}"
        )

    sgw_count = topology.total_sgw_count
    es_count = topology.total_es_count
    cbs_count = topology.total_cbs_count
    lb_count = topology.total_lb_count
    wants_logslurp = str(topology.wants_logslurp).lower()

    command = [
        "terraform",
        "apply",
        f"-var=server_count={cbs_count}",
        f"-var=sgw_count={sgw_count}",
        f"-var=es_count={es_count}",
        f"-var=lb_count={lb_count}",
        f"-var=logslurp={wants_logslurp}",
        "-auto-approve",
    ]
    result = subprocess.run(command, capture_output=False, text=True, cwd=SCRIPT_DIR)

    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    topology.read_from_terraform(str(SCRIPT_DIR))

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
    with open(in_config_file) as fin:
        config_json = cast(dict, json.load(fin))
        config_json.pop("couchbase-servers", None)
        config_json.pop("sync-gateways", None)
        config_json.pop("edge-servers", None)
        config_json.pop("test-servers", None)
        config_json.pop("load-balancers", None)
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

        if len(topology.edge_servers) > 0:
            es_instances = []
            for es in topology.edge_servers:
                es_instances.append({"hostname": es.hostname, "tls": True})

            config_json["edge-servers"] = es_instances

        if topology.logslurp is not None:
            config_json["logslurp"] = f"{topology.logslurp}:8180"

        if len(topology.test_servers) > 0:
            test_servers = []
            for ts in topology.test_servers:
                port = (
                    5555
                    if ts.platform.startswith("dotnet")
                    else 5173
                    if ts.platform == "js"
                    else 8080
                )
                ts_definition = {
                    "url": f"http://{ts.ip_address}:{port}",
                    # TODO: Convert all test servers to URLs to this is not needed
                    "dataset_version": "3.2",
                }

                if ts.platform == "js":
                    ts_definition["transport"] = "ws"

                test_servers.append(ts_definition)

            config_json["test-servers"] = test_servers

        if len(topology.load_balancers) > 0:
            load_balancers = []
            for lb in topology.load_balancers:
                load_balancers.append(lb.hostname)

            config_json["load-balancers"] = load_balancers

        json.dump(config_json, output, indent=2)


class BackendSteps(Flag):
    NONE = 0
    TERRAFORM_APPLY = auto()
    CBS_PROVISION = auto()
    SGW_PROVISION = auto()
    ES_PROVISION = auto()
    LB_PROVISION = auto()
    LS_PROVISION = auto()
    TS_RUN = auto()
    ALL = (
        TERRAFORM_APPLY
        | CBS_PROVISION
        | SGW_PROVISION
        | ES_PROVISION
        | LB_PROVISION
        | LS_PROVISION
        | TS_RUN
    )


def main(
    topology: TopologyConfig,
    tdk_config_in: str,
    tdk_config_out: str | None = None,
    steps: BackendSteps = BackendSteps.ALL,
) -> None:
    """
    Main function to set up the AWS environment and run the test servers.

    Args:
        topology (TopologyConfig): The topology configuration.
        public_key_name (str): The name of the public key stored in AWS.
        tdk_config_in (str): The path to the input TDK configuration file.
        private_key (Optional[str], optional): The private key to use for the SSH connection. Defaults to None.
        tdk_config_out (Optional[str], optional): The path to write the resulting TDK configuration file. Defaults to None.
        steps (BackendSteps, optional): The steps to execute. Defaults to BackendSteps.ALL.
    """
    if steps & BackendSteps.TERRAFORM_APPLY:
        terraform_apply(topology)
    else:
        result = subprocess.run(
            ["terraform", "init"], capture_output=False, text=True, cwd=SCRIPT_DIR
        )
        if result.returncode != 0:
            raise Exception(
                f"Command 'terraform init' failed with exit status {result.returncode}: {result.stderr}"
            )

        click.echo()
        click.secho("Skipping terraform apply...", fg="yellow")
        click.echo()
        if topology_has_aws_resources(topology):
            topology.read_from_terraform(str(SCRIPT_DIR))

    topology.resolve_test_servers()
    topology.dump()

    if steps & BackendSteps.CBS_PROVISION:
        server_main(topology)
    else:
        click.secho("Skipping Couchbase Server provisioning...", fg="yellow")

    if steps & BackendSteps.SGW_PROVISION:
        sgw_main(topology)
    else:
        click.secho("Skipping Sync Gateway provisioning...", fg="yellow")

    if steps & BackendSteps.ES_PROVISION:
        es_main(topology)
    else:
        click.secho("Skipping Edge Server provisioning...", fg="yellow")

    if steps & BackendSteps.LB_PROVISION:
        lb_main(topology)
    else:
        click.secho("Skipping load balancer provisioning...", fg="yellow")

    if steps & BackendSteps.LS_PROVISION:
        logslurp_main(topology)
    else:
        click.secho("Skipping Logslurp provisioning...", fg="yellow")

    if steps & BackendSteps.TS_RUN:
        topology_main(topology)
    else:
        click.secho("Skipping test server install and run...", fg="yellow")

    if tdk_config_out is not None:
        with open(tdk_config_out, "w") as fout:
            write_config(tdk_config_in, topology, fout)
    else:
        write_config(tdk_config_in, topology, sys.stdout)


@click.command()
@click.option(
    "--topology",
    help="The path to the topology configuration file",
    default=TopologyConfig(),
    type=TopologyParamType(),
)
@click.option(
    "--tdk-config-out",
    help="The path to the write the resulting TDK configuration file (stdout if empty)",
    type=click.Path(writable=True),
)
@click.option(
    "--no-terraform-apply",
    type=bool,
    is_flag=True,
    help="Skip terraform apply step",
    envvar="TDK_NO_TERRAFORM_APPLY",
)
@click.option(
    "--no-cbs-provision",
    type=bool,
    is_flag=True,
    help="Skip Couchbase Server provisioning step",
    envvar="TDK_NO_CBS_PROVISION",
)
@click.option(
    "--no-sgw-provision",
    type=bool,
    is_flag=True,
    help="Skip Sync Gateway provisioning step",
    envvar="TDK_NO_SGW_PROVISION",
)
@click.option(
    "--no-es-provision",
    type=bool,
    is_flag=True,
    help="Skip Edge Server provisioning step",
    envvar="TDK_NO_ES_PROVISION",
)
@click.option(
    "--no-lb-provision",
    type=bool,
    is_flag=True,
    help="Skip load balancer provisioning step",
    envvar="TDK_NO_LB_PROVISION",
)
@click.option(
    "--no-ls-provision",
    type=bool,
    is_flag=True,
    help="Skip Logslurp provisioning step",
    envvar="TDK_NO_LS_PROVISION",
)
@click.option(
    "--no-ts-run",
    type=bool,
    is_flag=True,
    help="Skip test server install and run step",
    envvar="TDK_NO_TS_RUN",
)
@click.option(
    "--tdk-config-in",
    required=True,
    help="The path to the input TDK configuration file",
    type=click.Path(exists=True),
)
def cli_entry(
    topology: TopologyConfig,
    tdk_config_in: str,
    tdk_config_out: str | None,
    no_terraform_apply: bool,
    no_cbs_provision: bool,
    no_sgw_provision: bool,
    no_es_provision: bool,
    no_lb_provision: bool,
    no_ls_provision: bool,
    no_ts_run: bool,
) -> None:
    steps = BackendSteps.ALL
    if no_terraform_apply:
        steps &= ~BackendSteps.TERRAFORM_APPLY
    if no_cbs_provision:
        steps &= ~BackendSteps.CBS_PROVISION
    if no_sgw_provision:
        steps &= ~BackendSteps.SGW_PROVISION
    if no_es_provision:
        steps &= ~BackendSteps.ES_PROVISION
    if no_lb_provision:
        steps &= ~BackendSteps.LB_PROVISION
    if no_ls_provision:
        steps &= ~BackendSteps.LS_PROVISION
    if no_ts_run:
        steps &= ~BackendSteps.TS_RUN

    main(
        topology,
        tdk_config_in,
        tdk_config_out,
        steps,
    )


def script_entry(
    topology: TopologyConfig,
    tdk_config_in: str,
    tdk_config_out: str | None = None,
    steps: BackendSteps | None = None,
) -> None:
    if steps is not None:
        main(
            topology,
            tdk_config_in,
            tdk_config_out,
            steps,
        )
    else:
        args = [
            "--topology",
            topology,
            "--tdk-config-in",
            tdk_config_in,
            "--tdk-config-out",
            tdk_config_out,
        ]
        cli_entry(args)


if __name__ == "__main__":
    cli_entry()
