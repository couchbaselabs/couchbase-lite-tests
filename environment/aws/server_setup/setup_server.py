"""
This module sets up Couchbase Server on AWS EC2 instances. It includes functions for executing remote commands,
setting up individual nodes, and configuring the server topology.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    setup_node(hostname: str, pkey: paramiko.Ed25519Key, version: str, cluster: Optional[str] = None) -> None:
        Set up a Couchbase Server node on an EC2 instance.

    main(version: str, topology: TopologyConfig) -> None:
        Main function to set up the Couchbase Server topology.
"""

from pathlib import Path

import click
import paramiko

from environment.aws.common.docker import start_container
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

    _, stdout, stderr = ssh.exec_command(command)
    for line in iter(stdout.readline, ""):
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)  # type: ignore

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def setup_node(
    hostname: str,
    pkey: paramiko.Ed25519Key,
    version: str,
    cluster: str | None = None,
) -> None:
    """
    Set up a Couchbase Server node on an EC2 instance.

    Args:
        hostname (str): The hostname or IP address of the EC2 instance.
        pkey (paramiko.Ed25519Key): The private key for SSH access.
        version (str): The version of Couchbase Server to install.
        cluster (Optional[str]): The cluster to join, if any.
    """
    header(f"Setting up server {hostname} with version {version}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username="ec2-user", pkey=pkey)

    sftp = ssh.open_sftp()
    sftp_progress_bar(sftp, SCRIPT_DIR / "configure-node.sh", "/tmp/configure-node.sh")
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    sftp.close()

    global current_ssh
    current_ssh = hostname

    remote_exec(
        ssh,
        "chmod +x /tmp/configure-node.sh && bash /tmp/configure-system.sh",
        "Setting up machine",
    )
    ssh.close()

    ec2_hostname = get_ec2_hostname(hostname)
    docker_args = [
        "--network",
        "host",
        "-v",
        "/tmp/configure-node.sh:/etc/service/couchbase-config/run",
    ]

    if cluster is not None:
        docker_args.extend(
            [
                "-e",
                f"E2E_PARENT_CLUSTER={cluster}",
            ]
        )
    start_container(
        "cbs-e2e",
        f"couchbase/server:enterprise-{version}",
        ec2_hostname,
        pkey,
        docker_args,
        replace_existing=True,
    )


def main(topology: TopologyConfig) -> None:
    """
    Set up the Couchbase Server topology on EC2 instances.

    Args:
        topology (TopologyConfig): The topology configuration.
    """

    if len(topology.clusters) == 0:
        return
    for cluster_config in topology.clusters:
        setup_node(
            cluster_config.public_hostnames[0],
            topology.ssh_key,
            cluster_config.version,
        )
        for server in cluster_config.public_hostnames[1:]:
            setup_node(
                server,
                topology.ssh_key,
                cluster_config.version,
                cluster_config.internal_hostnames[0],
            )
