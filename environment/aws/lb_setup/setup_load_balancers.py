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
from environment.aws.common.ssh import connect_ssh
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


def remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
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


def _create_pool_router(admin: bool) -> dict:
    """The route a request with no ``X-Backend`` header takes: round robin over every node."""
    name = "admin" if admin else "public"
    return {
        "entryPoints": [name],
        "rule": "PathPrefix(`/`)",
        "priority": 1,
        "service": f"sgw-{name}-pool",
        "middlewares": ["limit-body", "retry-next-node"],
    }


def _create_pinned_router(index: int, admin: bool) -> dict:
    """
    The route ``X-Backend: sg-<index>`` takes: that one node, whatever state it is in.

    No retry, because the service behind this route holds only the node that was asked
    for, so a retry would re-run the request against the same node that just failed.
    """
    name = "admin" if admin else "public"
    return {
        "entryPoints": [name],
        "rule": f"Header(`X-Backend`, `sg-{index}`) && PathPrefix(`/`)",
        "priority": 10,
        "service": f"sgw-{name}-{index}",
        "middlewares": ["limit-body"],
    }


def _create_unknown_pin_router(admin: bool) -> dict:
    """
    The route an ``X-Backend`` value that names no upstream takes: a 500.

    Without it the pool router would catch the request and round robin it, so a stale or
    mistyped pin would silently become no pin at all.
    """
    name = "admin" if admin else "public"
    return {
        "entryPoints": [name],
        "rule": "HeaderRegexp(`X-Backend`, `.`) && PathPrefix(`/`)",
        "priority": 5,
        "service": f"sgw-{name}-pool",
        "middlewares": ["reject-unknown-pin"],
    }


def _create_service(admin: bool, servers: list[str]) -> dict:
    port = 4985 if admin else 4984
    return {
        "loadBalancer": {
            "passHostHeader": False,
            "serversTransport": "sg-upstream",
            "servers": [{"url": f"https://{server}:{port}"} for server in servers],
        }
    }


def create_traefik_config(upstreams: list[str]) -> None:
    config: Any = None
    with open(SCRIPT_DIR / "http_config.yml.in") as fin:
        config = yaml.load(fin, Loader=yaml.SafeLoader)
        routers: dict = {
            "public": _create_pool_router(False),
            "admin": _create_pool_router(True),
            "public-unknown-pin": _create_unknown_pin_router(False),
            "admin-unknown-pin": _create_unknown_pin_router(True),
        }
        services: dict = {
            "sgw-public-pool": _create_service(False, upstreams),
            "sgw-admin-pool": _create_service(True, upstreams),
        }
        for i, upstream in enumerate(upstreams):
            routers[f"public-{i}"] = _create_pinned_router(i, False)
            routers[f"admin-{i}"] = _create_pinned_router(i, True)
            services[f"sgw-public-{i}"] = _create_service(False, [upstream])
            services[f"sgw-admin-{i}"] = _create_service(True, [upstream])

        config["http"]["routers"] = routers
        config["http"]["services"] = services
        # A node that is down refuses the connection, which Traefik retries against the next
        # node in the pool, so trying as many times as there are nodes reaches a live one.
        config["http"]["middlewares"]["retry-next-node"]["retry"]["attempts"] = max(2, len(upstreams))

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
        ssh = connect_ssh(ec2_hostname, topology.ssh_key)

        global current_ssh
        current_ssh = lb.hostname
        sftp = ssh.open_sftp()
        sftp_progress_bar(sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh")
        sftp_progress_bar(sftp, SCRIPT_DIR / "traefik.yml", "/home/ec2-user/traefik.yml")
        sftp_progress_bar(sftp, SCRIPT_DIR / "http_config.yml", "/home/ec2-user/http_config.yml")
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

        start_container("traefik", "traefik:v3", ec2_hostname, topology.ssh_key, docker_args)
