"""
This module sets up the LogSlurp service on an AWS EC2 instance. It includes functions for executing remote commands,
checking SSH key settings, and configuring Docker contexts.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    get_ec2_hostname(hostname: str) -> str:
        Convert an IP address to an EC2 hostname.

    main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Set up the LogSlurp service on an AWS EC2 instance.
"""

from pathlib import Path

import click
import paramiko

from environment.aws.common.docker import (
    start_container,
)
from environment.aws.common.io import LIGHT_GRAY, get_ec2_hostname, sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


def remote_exec(
    ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True
) -> None:
    """
    Execute a remote command via SSH with a description and optional error handling.

    Args:
        ssh (paramiko.SSHClient): The SSH client.
        command (str): The command to execute.
        desc (str): A description of the command.
        fail_on_error (bool): Whether to raise an exception if the command fails.

    Raises:
        Exception: If the command fails and fail_on_error is True.
    """
    header(desc)

    _, stdout, stderr = ssh.exec_command(command, get_pty=True)
    for line in iter(stdout.readline, ""):
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)  # type: ignore

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def main(topology: TopologyConfig) -> None:
    """
    Set up the LogSlurp service on an AWS EC2 instance.

    Args:
        topology (TopologyConfig): The topology configuration that controls whether
        or not logslurp is needed.
        private_key (Optional[str]): The path to the private key for SSH access.
    """
    if topology.logslurp is None:
        return

    header("Setting up logslurp")
    ec2_hostname = get_ec2_hostname(topology.logslurp)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ec2_hostname, username="ec2-user", pkey=topology.ssh_key)

    global current_ssh
    current_ssh = topology.logslurp
    sftp = ssh.open_sftp()
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")
    sftp.close()
    ssh.close()

    docker_args = ["-p", "8180:8180"]
    start_container(
        "logslurp",
        "public.ecr.aws/q8y4w9v7/couchbase/logslurp",
        ec2_hostname,
        topology.ssh_key,
        docker_args,
    )
