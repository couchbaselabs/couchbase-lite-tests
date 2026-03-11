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
from enum import Flag, auto
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    from environment.aws.common.io import configure_terminal_encoding

    configure_terminal_encoding()

from environment.aws.common.output import header
from environment.aws.start_backend import check_sts_status
from environment.aws.topology_setup.setup_topology import TopologyConfig


class BackendStopSteps(Flag):
    NONE = 0
    DESTROY_SGW = auto()
    DESTROY_CBS = auto()
    DESTROY_ES = auto()
    DESTROY_LB = auto()
    DESTROY_LS = auto()
    STOP_TS = auto()
    FULL_DESTROY = auto()
    ALL = FULL_DESTROY | STOP_TS


@click.command()
@click.option(
    "--topology",
    help="The topology file that was used to start the environment",
    type=click.Path(exists=True),
)
@click.option("--destroy-sgw", is_flag=True, help="Destroy only Sync Gateway instances")
@click.option(
    "--destroy-cbs", is_flag=True, help="Destroy only Couchbase Server instances"
)
@click.option("--destroy-es", is_flag=True, help="Destroy only Edge Server instances")
@click.option("--destroy-lb", is_flag=True, help="Destroy only Load Balancer instances")
@click.option("--destroy-ls", is_flag=True, help="Destroy only Logslurp instances")
@click.option("--no-ts-stop", is_flag=True, help="Do not stop test servers")
@click.option(
    "--no-full-destroy",
    is_flag=True,
    help="Do not destroy all terraform managed resources if no specific component is selected",
)
def cli_entry(
    topology: str | None,
    destroy_sgw: bool,
    destroy_cbs: bool,
    destroy_es: bool,
    destroy_lb: bool,
    destroy_ls: bool,
    no_ts_stop: bool,
    no_full_destroy: bool,
) -> None:
    steps = BackendStopSteps.NONE
    has_specific_destroy = False
    if destroy_sgw:
        steps |= BackendStopSteps.DESTROY_SGW
        has_specific_destroy = True
    if destroy_cbs:
        steps |= BackendStopSteps.DESTROY_CBS
        has_specific_destroy = True
    if destroy_es:
        steps |= BackendStopSteps.DESTROY_ES
        has_specific_destroy = True
    if destroy_lb:
        steps |= BackendStopSteps.DESTROY_LB
        has_specific_destroy = True
    if destroy_ls:
        steps |= BackendStopSteps.DESTROY_LS
        has_specific_destroy = True

    if not has_specific_destroy and not no_full_destroy:
        steps |= BackendStopSteps.FULL_DESTROY

    if not no_ts_stop:
        steps |= BackendStopSteps.STOP_TS

    main(topology, steps)


def main(topology: str | None, steps: BackendStopSteps) -> None:
    """
    Main function to tear down the AWS environment and stop the test servers.

    Args:
        topology_file (Optional[str]): The topology file that was used to start the environment.
        topology (Optional[TopologyConfig]): The topology file that was used to start the environment.
        steps (BackendStopSteps): The teardown steps to execute.
    """
    check_sts_status()
    topology_obj = TopologyConfig(topology) if topology else TopologyConfig()
    # In case of partial destroy, we need to know the counts of resources
    # to target them correctly.
    if not (steps & BackendStopSteps.FULL_DESTROY):
        topology_obj.read_from_terraform(str(SCRIPT_DIR))

    terraform_command = ["terraform", "destroy", "-auto-approve"]
    targets = []
    if steps & BackendStopSteps.DESTROY_SGW:
        targets.extend(
            [
                f"-target=aws_instance.sync_gateway[{i}]"
                for i in range(topology_obj.total_sgw_count)
            ]
        )
    if steps & BackendStopSteps.DESTROY_CBS:
        targets.extend(
            [
                f"-target=aws_instance.couchbaseserver[{i}]"
                for i in range(topology_obj.total_cbs_count)
            ]
        )
    if steps & BackendStopSteps.DESTROY_ES:
        targets.extend(
            [
                f"-target=aws_instance.edge_server[{i}]"
                for i in range(topology_obj.total_es_count)
            ]
        )
    if steps & BackendStopSteps.DESTROY_LB:
        targets.extend(
            [
                f"-target=aws_instance.load_balancer[{i}]"
                for i in range(topology_obj.total_lb_count)
            ]
        )
    if steps & BackendStopSteps.DESTROY_LS:
        if topology_obj.wants_logslurp:
            targets.append('-target=aws_instance.log_slurp["log_slurp"]')

    if targets:
        terraform_command.extend(targets)
    elif not (steps & BackendStopSteps.FULL_DESTROY):
        click.secho(
            "No AWS resources specified for destruction, skipping terraform destroy.",
            fg="yellow",
        )
        terraform_command = []

    result = None
    if terraform_command:
        header("Starting terraform destroy")
        result = subprocess.run(
            terraform_command, cwd=SCRIPT_DIR, capture_output=False, text=True
        )
        if result.returncode != 0:
            click.secho(
                f"WARNING: Command '{' '.join(terraform_command)}' failed with exit status {result.returncode}: {result.stderr}",
                fg="yellow",
            )
            click.echo()
        header("Done!")

    if steps & BackendStopSteps.STOP_TS:
        header("Stopping test servers")
        topology_obj.stop_test_servers()
        header("Done!")

    exit(result.returncode if result else 0)


if __name__ == "__main__":
    cli_entry()
