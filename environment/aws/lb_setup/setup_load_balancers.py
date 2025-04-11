#!/usr/bin/env python3

"""
This module sets up load balancers on an AWS EC2 instance. It includes functions for executing remote commands,
checking SSH key settings, and configuring Docker contexts.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    get_ec2_hostname(hostname: str) -> str:
        Convert an IP address to an EC2 hostname.

    check_aws_key_checking() -> None:
        Ensure that SSH key checking is configured correctly for AWS hosts.

    main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Set up the load balancers on an AWS EC2 instance.
"""

from pathlib import Path
from typing import List, Optional

import click
import paramiko

from environment.aws.common.docker import (
    check_aws_key_checking,
    get_ec2_hostname,
    start_container,
)
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

    _, stdout, stderr = ssh.exec_command(command, get_pty=True)
    for line in iter(stdout.readline, ""):
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)  # type: ignore

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def create_nginx_config(upstreams: List[str]) -> None:
    with open(SCRIPT_DIR / "nginx.conf", "w") as f:
        f.write("events { }\n")
        f.write("\n")
        f.write("http {\n")
        f.write("\tupstream admin {\n")
        f.write(f"\t\tserver {upstreams[0]}:4985 max_fails=1 fail_timeout=10s;\n")
        for upstream in upstreams[1:]:
            f.write(f"\t\tserver {upstream}:4985 backup;\n")

        f.write("\t}\n")
        f.write("\tupstream public {\n")
        f.write(f"\t\tserver {upstreams[0]}:4984 max_fails=1 fail_timeout=10s;\n")
        for upstream in upstreams[1:]:
            f.write(f"\t\tserver {upstream}:4984 backup;\n")

        f.write("\t}\n")

        for port, upstream in [(4984, "public"), (4985, "admin")]:
            f.write("\t server {\n")
            f.write(f"\t\tlisten {port};\n")
            f.write("\t\tclient_max_body_size 20m;\n")
            f.write("\t\tlocation / {\n")
            f.write("\t\t\tproxy_pass_header Accept;\n")
            f.write("\t\t\tproxy_pass_header Server;\n")
            f.write("\t\t\tproxy_http_version 1.1;\n")
            f.write("\t\t\tkeepalive_requests 1000;\n")
            f.write("\t\t\tkeepalive_timeout 360s;\n")
            f.write("\t\t\tproxy_read_timeout 360s;\n")
            f.write("\t\t\tproxy_set_header Upgrade $http_upgrade;\n")
            f.write('\t\t\tproxy_set_header Connection "Upgrade";\n')
            f.write(f"\t\t\tproxy_pass https://{upstream};\n")
            f.write("\t\t}\n")
            f.write("\t }\n")

        f.write("}\n")


def main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
    """
    Set up the load balancers on an AWS EC2 instance.

    Args:
        topology (TopologyConfig): The topology configuration that controls how many,
        if any, load balancers are needed.
        private_key (Optional[str]): The path to the private key for SSH access.
    """
    if len(topology.load_balancers) == 0:
        return

    header("Setting up load balancers")
    check_aws_key_checking()
    for lb in topology.load_balancers:
        create_nginx_config(lb.upstreams)
        ec2_hostname = get_ec2_hostname(lb.hostname)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey: Optional[paramiko.Ed25519Key] = (
            paramiko.Ed25519Key.from_private_key_file(private_key)
            if private_key
            else None
        )
        ssh.connect(ec2_hostname, username="ec2-user", pkey=pkey)

        global current_ssh
        current_ssh = lb.hostname
        sftp = ssh.open_sftp()
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
        )
        sftp_progress_bar(sftp, SCRIPT_DIR / "nginx.conf", "/home/ec2-user/nginx.conf")
        remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")
        sftp.close()
        ssh.close()

        docker_args = [
            "-p",
            "4984:4984",
            "-p",
            "4985:4985",
            "-v",
            "/home/ec2-user/nginx.conf:/etc/nginx/nginx.conf:ro",
        ]
        context_name = "lb" if topology.tag == "" else f"lb-{topology.tag}"
        start_container(
            "nginx", context_name, "nginx:1-alpine", ec2_hostname, docker_args
        )
