#!/usr/bin/env python3

import os
import subprocess
from pathlib import Path
from typing import Optional

import paramiko
from termcolor import colored

from environment.aws.common.io import sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


def remote_exec(
    ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True
):
    header(desc)

    _, stdout, stderr = ssh.exec_command(command, get_pty=True)
    for line in iter(stdout.readline, ""):
        print(colored(f"[{current_ssh}] {line}", "light_grey"), end="")

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    print()


def get_ec2_hostname(hostname: str) -> str:
    if hostname.startswith("ec2-"):
        return hostname

    components = hostname.split(".")
    if len(components) != 4:
        raise ValueError(f"Invalid hostname {hostname}")

    return f"ec2-{hostname.replace('.', '-')}.compute-1.amazonaws.com"


def check_aws_key_checking() -> None:
    ssh_config_path = Path.home() / ".ssh" / "config"
    if not ssh_config_path.exists():
        raise FileNotFoundError(f"SSH config file not found at {ssh_config_path}")

    with ssh_config_path.open() as f:
        lines = f.readlines()

    host_found = False
    for line in lines:
        if line.strip() == "Host *.amazonaws.com":
            host_found = True
            continue

        if host_found:
            if line.strip().startswith("Host"):
                raise Exception(
                    "No StrictHostKeyChecking line found for Host *.amazonaws.com, please modify your ssh config to set it to accept-new"
                )

            if "StrictHostKeyChecking" in line:
                if "accept-new" not in line:
                    raise Exception(
                        "StrictHostKeyChecking is not set to accept-new for Host *.amazonaws.com, please modify your ssh config to set it to accept-new"
                    )

                return

    if host_found:
        raise Exception(
            "No StrictHostKeyChecking line found for Host *.amazonaws.com, please modify your ssh config to set it to accept-new"
        )
    else:
        raise Exception(
            "Host *.amazonaws.com not found in SSH config, please add it with StrictHostKeyChecking accept-new"
        )


def main(topology: TopologyConfig, private_key: Optional[str] = None):
    if not topology.wants_logslurp:
        return

    header("Setting up logslurp")
    check_aws_key_checking()
    ec2_hostname = get_ec2_hostname(topology.logslurp)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey: Optional[paramiko.Ed25519Key] = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )
    ssh.connect(ec2_hostname, username="ec2-user", pkey=pkey)

    global current_ssh
    current_ssh = topology.logslurp
    sftp = ssh.open_sftp()
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")
    sftp.close()
    ssh.close()

    context_result = subprocess.run(
        ["docker", "context", "ls", "--format", "{{.Name}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "aws" in context_result.stdout:
        header("Updating docker context")
        subprocess.run(
            [
                "docker",
                "context",
                "update",
                "aws",
                "--docker",
                f"host=ssh://ec2-user@{ec2_hostname}",
            ]
        )
    else:
        header("Creating docker context")
        subprocess.run(
            [
                "docker",
                "context",
                "create",
                "aws",
                "--docker",
                f"host=ssh://ec2-user@{ec2_hostname}",
            ]
        )

    header(f"Building and starting logslurp on {topology.logslurp}")
    env = os.environ.copy()
    env["DOCKER_CONTEXT"] = "aws"
    subprocess.run(
        ["docker", "stop", "logslurp"],
        check=False,
        env=env,
        cwd=SCRIPT_DIR / ".." / "..",
    )
    subprocess.run(
        ["docker", "rm", "logslurp"],
        check=False,
        env=env,
        cwd=SCRIPT_DIR / ".." / "..",
    )
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-p",
            "8180:8180",
            "--name",
            "logslurp",
            "public.ecr.aws/q8y4w9v7/couchbase/logslurp",
        ],
        check=True,
        env=env,
        cwd=SCRIPT_DIR / ".." / "..",
    )
