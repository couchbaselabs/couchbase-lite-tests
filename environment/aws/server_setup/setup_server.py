#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module sets up Couchbase Server on AWS EC2 instances. It includes functions for executing remote commands,
setting up individual nodes, and configuring the server topology.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    setup_node(hostname: str, pkey: Optional[paramiko.Ed25519Key], version: str, cluster: Optional[str] = None) -> None:
        Set up a Couchbase Server node on an EC2 instance.

    setup_topology(pkey: Optional[paramiko.Ed25519Key], version: str, topology: TopologyConfig) -> None:
        Use the indicated topology to set up the desired number of Couchbase Server nodes

    main(version: str, topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Main function to set up the Couchbase Server topology.
"""

from pathlib import Path
from typing import Optional

import click
import paramiko

from environment.aws.common.io import LIGHT_GRAY, sftp_progress_bar
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
    pkey: Optional[paramiko.Ed25519Key],
    version: str,
    cluster: Optional[str] = None,
) -> None:
    """
    Set up a Couchbase Server node on an EC2 instance.

    Args:
        hostname (str): The hostname or IP address of the EC2 instance.
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        version (str): The version of Couchbase Server to install.
        cluster (Optional[str]): The cluster to join, if any.
    """
    couchbase_filename = f"couchbase-server-enterprise-{version}-linux.x86_64.rpm"
    couchbase_url = (
        f"http://packages.couchbase.com/releases/{version}/{couchbase_filename}"
    )

    header(f"Setting up server {hostname} with version {version}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(hostname, username="ec2-user", pkey=pkey)

    sftp = ssh.open_sftp()
    sftp_progress_bar(sftp, SCRIPT_DIR / "configure-node.sh", "/tmp/configure-node.sh")
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "disable-thp.service", "/tmp/disable-thp.service"
    )
    sftp.close()

    global current_ssh
    current_ssh = hostname

    remote_exec(ssh, "sudo bash /tmp/configure-system.sh", "Setting up machine")
    remote_exec(
        ssh,
        f"wget -nc -O /tmp/{couchbase_filename} {couchbase_url} 2>&1",
        f"Downloading Couchbase Server {version}",
        fail_on_error=False,
    )
    remote_exec(
        ssh,
        "sudo rpm -e couchbase-server",
        "Uninstalling Couchbase Server",
        fail_on_error=False,
    )
    remote_exec(
        ssh,
        f"sudo rpm -i /tmp/{couchbase_filename}",
        f"Installing Couchbase Server {version}",
    )
    remote_exec(
        ssh, "sudo systemctl start couchbase-server", "Starting Couchbase Server"
    )

    # Some magic here that might be overlooked.  If we pass in a cluster
    # address to the configure node script, it will join an existing cluster
    # rather than using itself to create a new one
    config_command = "bash /tmp/configure-node.sh"
    if cluster is not None:
        config_command += f" {cluster}"
    remote_exec(ssh, config_command, "Setting up node")

    ssh.close()


def setup_topology(
    pkey: Optional[paramiko.Ed25519Key], topology: TopologyConfig
) -> None:
    """
    Set up the Couchbase Server topology on EC2 instances.

    Args:
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        version (str): The version of Couchbase Server to install.
        topology (TopologyConfig): The topology configuration.
    """
    if len(topology.clusters) == 0:
        return

    for cluster_config in topology.clusters:
        setup_node(cluster_config.public_hostnames[0], pkey, cluster_config.version)
        for server in cluster_config.public_hostnames[1:]:
            setup_node(
                server, pkey, cluster_config.version, cluster_config.public_hostnames[0]
            )


def main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
    """
    Main function to set up the Couchbase Server topology.

    Args:
        version (str): The version of Couchbase Server to install.
        topology (TopologyConfig): The topology configuration.
        private_key (Optional[str]): The path to the private key for SSH access.
    """
    pkey = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )

    setup_topology(pkey, topology)
