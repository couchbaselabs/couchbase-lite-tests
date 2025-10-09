import os
import subprocess
from pathlib import Path

import click

from environment.aws.common.output import header


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


def start_container(
    name: str,
    context_name: str,
    image_name: str,
    host: str,
    docker_args: list[str] | None = None,
    container_args: list[str] | None = None,
) -> None:
    context_result = subprocess.run(
        ["docker", "context", "ls", "--format", "{{.Name}}"],
        check=True,
        capture_output=True,
        text=True,
    )

    if context_name in context_result.stdout:
        header(f"Updating docker context '{context_name}'")
        subprocess.run(
            [
                "docker",
                "context",
                "update",
                context_name,
                "--docker",
                f"host=ssh://ec2-user@{host}",
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
                f"host=ssh://ec2-user@{host}",
            ]
        )

    header(f"Starting {name} on {host}")
    env = os.environ.copy()
    env["DOCKER_CONTEXT"] = context_name

    container_check = subprocess.run(  
        ["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Status}}"],  
        check=True,  
        capture_output=True,  
        text=True,  
        env=env,  
    ) 

    if container_check.stdout.strip() != "":
        if container_check.stdout.startswith("Up"):
            click.echo(f"{name} already running, returning...")
            return

        click.echo(f"Restarting existing {name} container...")
        subprocess.run(["docker", "start", name], check=False, env=env)
        return

    click.echo(f"Starting new {name} container...")
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
    ]

    if docker_args:
        args.extend(docker_args)

    args.append(image_name)

    if container_args:
        args.extend(container_args)

    subprocess.run(
        args,
        check=True,
        env=env,
    )
