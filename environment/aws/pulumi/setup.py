import os
from time import sleep
from typing import Optional

import click
from pulumi.automation import ConfigValue, create_or_select_stack, select_stack

from environment.aws.common.output import header
from environment.aws.pulumi import constants, input_keys
from environment.aws.topology_setup.setup_topology import TopologyConfig


def pulumi_up(public_key_name: Optional[str], topology: TopologyConfig):
    header("Starting pulumi update")
    if not topology.has_aws_resources():
        click.secho("No AWS resources requested, skipping pulumi", fg="yellow")
        return

    if public_key_name is None:
        raise Exception(
            "--public-key-name was not provided, but it is required for AWS resources."
        )

    os.makedirs((constants.WORK_DIR / ".pulumi"), exist_ok=True)

    sgw_count = topology.total_sgw_count
    cbs_count = topology.total_cbs_count
    lb_count = topology.total_lb_count
    wants_logslurp = str(topology.wants_logslurp).lower()

    # This is confusing, but it runs the program found in __main__.py
    pulumi_stack = create_or_select_stack(
        constants.STACK_NAME, work_dir=str(constants.WORK_DIR)
    )
    pulumi_stack.set_config(input_keys.PUBLIC_KEYNAME, ConfigValue(public_key_name))
    pulumi_stack.set_config(input_keys.SGW_COUNT, ConfigValue(str(sgw_count)))
    pulumi_stack.set_config(input_keys.CBS_COUNT, ConfigValue(str(cbs_count)))
    pulumi_stack.set_config(input_keys.LB_COUNT, ConfigValue(str(lb_count)))
    pulumi_stack.set_config(input_keys.WANTS_LOGSLURP, ConfigValue(wants_logslurp))
    result = pulumi_stack.up(on_output=click.echo)
    if not result.summary:
        raise Exception("Pulumi update failed")

    topology.read_from_pulumi()

    header("Done, sleeping for 5s")
    # The machines won't be ready immediately, so we need to wait a bit
    # before SSH access succeeds
    sleep(5)


def pumuli_down(topology: TopologyConfig) -> int:
    header("Starting pulumi destroy")
    result_code = 0
    try:
        stack = select_stack(constants.STACK_NAME, work_dir=str(constants.WORK_DIR))
        stack.destroy(on_output=click.echo)
    except Exception as e:
        result_code = 1
        click.secho(
            f"WARNING: Pulumi destroy failed with error: {e}",
            fg="yellow",
        )
        click.echo()

    header("Done!")
    return result_code
