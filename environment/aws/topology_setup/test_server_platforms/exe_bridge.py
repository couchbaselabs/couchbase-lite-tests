"""
This module provides the ExeBridge class for managing executable applications on local or remote machines.
It includes functions for validating, installing, running, stopping, and uninstalling applications, as well as retrieving the IP address of a machine.

Classes:
    ExeBridge: A class to manage executable applications on local or remote machines.

Functions:
    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.
"""

import json
import subprocess
from pathlib import Path
from typing import List, Optional

import click
import paramiko
import psutil

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


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
        click.echo(line, nl=False)

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


class ExeBridge(PlatformBridge):
    """
    A class to manage executable applications on local or remote machines.
    """

    def __init__(self, exe_path: str, extra_args: Optional[List[str]] = None):
        """
        Initialize the ExeBridge with the executable path and optional extra arguments.

        Args:
            exe_path (str): The path to the executable file.
            extra_args (Optional[List[str]]): A list of extra arguments to pass to the executable.
        """
        self.__exe_path = exe_path
        self.__extra_args = extra_args or []
        self.__exe_name = Path(self.__exe_path).name

    def validate(self, location: str) -> None:
        """
        Validate that the executable is accessible.

        Args:
            location (str): The location of the executable (e.g., "localhost").
        """
        click.echo("No validation needed for executables")

    def install(self, location: str) -> None:
        """
        Install the executable on the specified location.

        Args:
            location (str): The location of the executable (e.g., "localhost").
        """
        if location == "localhost":
            click.echo("No action needed for installing executables locally")
            return

    def run(self, location: str) -> None:
        """
        Run the executable on the specified location.

        Args:
            location (str): The location of the executable (e.g., "localhost").
        """
        header(f"Running {self.__exe_path}")
        if len(self.__extra_args) > 0:
            click.echo(f"Extra args: {json.dumps(self.__extra_args)}")
            click.echo()

        args = [self.__exe_path]
        args.extend(self.__extra_args)
        log_file = Path(self.__exe_path).parent / "server.log"
        log_fd = open(log_file, "w")
        process = subprocess.Popen(
            args, start_new_session=True, stdout=log_fd, stderr=log_fd
        )
        click.echo(f"Started {self.__exe_name} with PID {process.pid}")

    def stop(self, location: str) -> None:
        """
        Stop the executable on the specified location.

        Args:
            location (str): The location of the executable (e.g., "localhost").
        """
        header(f"Stopping test server '{self.__exe_name}'")
        for proc in psutil.process_iter():
            if proc.name() == self.__exe_name:
                proc.terminate()
                click.secho(f"Stopped PID {proc.pid}", fg="green")
                return

        click.secho(f"Unable to find process to stop ({self.__exe_name})", fg="yellow")

    def uninstall(self, location: str) -> None:
        """
        Uninstall the executable from the specified location.

        Args:
            location (str): The location of the executable (e.g., "localhost").
        """
        click.echo("No action needed for uninstalling executable")

    def get_ip(self, location: str) -> str:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the executable (e.g., "localhost").

        Returns:
            str: The IP address of the location.
        """
        return location
