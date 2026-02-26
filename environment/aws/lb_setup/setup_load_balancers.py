"""
This module sets up load balancers on an AWS EC2 instance. It includes functions for executing remote commands,
checking SSH key settings, and configuring Docker contexts.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    main(topology: TopologyConfig) -> None:
        Set up the load balancers on an AWS EC2 instance.
"""

from pathlib import Path
from typing import Any

import click
import paramiko
import yaml

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
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def _create_router(index: int, admin: bool) -> dict:
    name = "admin" if admin else "public"
    rule = (
        "PathPrefix(`/`)"
        if index == 0
        else f"Header(`X-Backend`, `sg-{index}`) && PathPrefix(`/`)"
    )
    return {
        "entryPoints": [name],
        "rule": rule,
        "priority": 10 * (index + 1),
        "service": f"sgw-{name}-{index}",
        "middlewares": ["limit-body", "retry-once"],
    }


def _create_service(index: int, admin: bool, server: str) -> dict:
    return {
        "loadBalancer": {
            "passHostHeader": False,
            "serversTransport": "sg-upstream",
            "servers": [{"url": f"https://{server}:{4985 if admin else 4984}"}],
        }
    }


def create_traefik_config(upstreams: list[str]) -> None:
    config: Any = None
    with open(SCRIPT_DIR / "http_config.yml.in") as fin:
        config = yaml.load(fin, Loader=yaml.SafeLoader)
        routers: dict = {}
        services: dict = {}
        for i, upstream in enumerate(upstreams):
            routers[f"public-{i}"] = _create_router(i, False)
            routers[f"admin-{i}"] = _create_router(i, True)
            services[f"sgw-public-{i}"] = _create_service(i, False, upstream)
            services[f"sgw-admin-{i}"] = _create_service(i, True, upstream)

        config["http"]["routers"] = routers
        config["http"]["services"] = services

    with open(SCRIPT_DIR / "http_config.yml", "w") as fout:
        yaml.dump(config, fout)


def main(topology: TopologyConfig) -> None:
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
    for lb in topology.load_balancers:
        create_traefik_config(lb.upstreams)
        ec2_hostname = get_ec2_hostname(lb.hostname)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ec2_hostname, username="ec2-user", pkey=topology.ssh_key)

        global current_ssh
        current_ssh = lb.hostname
        sftp = ssh.open_sftp()
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "traefik.yml", "/home/ec2-user/traefik.yml"
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "http_config.yml", "/home/ec2-user/http_config.yml"
        )
        remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")
        sftp.close()
        ssh.close()

        docker_args = [
            "-p",
            "4984:4984",
            "-p",
            "4985:4985",
            "-v",
            "/home/ec2-user/traefik.yml:/etc/traefik/traefik.yml:ro",
            "-v",
            "/home/ec2-user/http_config.yml:/etc/traefik/http_config.yml:ro",
        ]

        start_container(
            "traefik", "traefik:v3", ec2_hostname, topology.ssh_key, docker_args
        )
