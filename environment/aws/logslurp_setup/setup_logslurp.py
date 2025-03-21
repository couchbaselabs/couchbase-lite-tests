#!/usr/bin/env python3

"""
This module sets up the LogSlurp service on an AWS EC2 instance. It includes functions for executing remote commands,
checking SSH key settings, and configuring Docker contexts.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    get_ec2_hostname(hostname: str) -> str:
        Convert an IP address to an EC2 hostname.

    check_aws_key_checking() -> None:
        Ensure that SSH key checking is configured correctly for AWS hosts.

    main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Set up the LogSlurp service on an AWS EC2 instance.
"""

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
        print(colored(f"[{current_ssh}] {line}", "light_grey"), end="")

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    print()


def get_ec2_hostname(hostname: str) -> str:
    """
    Convert an IP address to an EC2 hostname.

    Args:
        hostname (str): The IP address.

    Returns:
        str: The EC2 hostname.

    Raises:
        ValueError: If the hostname is not an IP address.
    """
    if hostname.startswith("ec2-"):
        return hostname

    components = hostname.split(".")
    if len(components) != 4:
        raise ValueError(f"Invalid hostname {hostname}")

    return f"ec2-{hostname.replace('.', '-')}.compute-1.amazonaws.com"


def check_aws_key_checking() -> None:
    """
    Ensure that SSH key checking is configured correctly for AWS hosts.
    There should be a section titled Host *.amazonaws.com in the SSH config file
    with StrictHostKeyChecking set to accept-new.

    Raises:
        FileNotFoundError: If the SSH config file is not found.
        Exception: If the SSH config is not set correctly for AWS hosts.
    """
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


def main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
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

    context_name = "aws" if topology.tag == "" else f"aws-{topology.tag}"
    if context_name in context_result.stdout:
        header(f"Updating docker context '{context_name}'")
        subprocess.run(
            [
                "docker",
                "context",
                "update",
                context_name,
                "--docker",
                f"host=ssh://ec2-user@{ec2_hostname}",
            ]
        )
    else:
        header(f"Creating docker context '{context_name}'")
        subprocess.run(
            [
                "docker",
                "context",
                "create",
                context_name,
                "--docker",
                f"host=ssh://ec2-user@{ec2_hostname}",
            ]
        )

    header(f"Starting logslurp on {topology.logslurp}")
    env = os.environ.copy()
    env["DOCKER_CONTEXT"] = context_name

    container_check = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=logslurp", "--format", "{{.Status}}"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    if container_check.stdout.strip() != "":
        if container_check.stdout.startswith("Up"):
            print("logslurp already running, returning...")
            return

        print("Restarting existing logslurp container...")
        subprocess.run(["docker", "start", "logslurp"], check=False, env=env)
        return

    print("Starting new logslurp container...")
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
    )


"""
This module provides utility functions for file operations, including downloading files with a progress bar,
uploading files via SFTP with a progress bar, and zipping/unzipping directories.

Functions:
    download_progress_bar(response: Response, output_path: Path) -> None:
        Download a file with a progress bar.

    sftp_progress_bar(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
        Upload a file via SFTP with a progress bar.

    zip_directory(input: Path, output: Path) -> None:
        Zip the contents of a directory.

    unzip_directory(input: Path, output: Path) -> None:
        Unzip the contents of a zip file to a directory.
"""

import zipfile
from pathlib import Path

import paramiko
from requests import Response
from tqdm import tqdm


def download_progress_bar(response: Response, output_path: Path) -> None:
    """
    Download a file with a progress bar.

    Args:
        response (Response): The HTTP response object.
        output_path (Path): The path where the downloaded file will be saved.

    Raises:
        RuntimeError: If the response does not contain a content-length header.
    """
    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024

    with (
        open(output_path, "wb") as f,
        tqdm(total=total_size, unit="iB", unit_scale=True) as progress_bar,
    ):
        for data in response.iter_content(block_size):
            progress_bar.update(len(data))
            f.write(data)


def zip_directory(input: Path, output: Path) -> None:
    """
    Zip the contents of a directory.

    Args:
        input (Path): The path to the directory to be zipped.
        output (Path): The path where the zip file will be saved.

    Raises:
        RuntimeError: If the input directory does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    print("Zipping...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(input):
            for file in tqdm(files, desc="Zipping"):
                file_path = Path(root) / file
                zipf.write(file_path, file_path.relative_to(input))

    print("Done")


def unzip_directory(input: Path, output: Path) -> None:
    """
    Unzip the contents of a zip file to a directory.

    Args:
        input (Path): The path to the zip file to be unzipped.
        output (Path): The path where the contents will be extracted.

    Raises:
        RuntimeError: If the input zip file does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    with zipfile.ZipFile(input, "r") as zipf:
        for member in tqdm(zipf.infolist(), desc="Unzipping"):
            zipf.extract(member, output)
            extracted_path = output / member.filename

            # Preserve file permissions
            perm = member.external_attr >> 16
            if perm:
                extracted_path.chmod(perm)

    print("Done")
