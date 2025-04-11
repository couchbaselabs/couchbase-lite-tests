"""
This module provides the macOSBridge class for managing macOS applications on local machines.
It includes functions for validating, installing, running, stopping, and uninstalling applications, as well as retrieving the IP address of the machine.

Classes:
    macOSBridge: A class to manage macOS applications on local machines.

Functions:
    validate(self, location: str) -> None:
        Validate that the application can be managed on the specified location.

    install(self, location: str) -> None:
        Install the application on the specified location.

    run(self, location: str) -> None:
        Run the application on the specified location.

    stop(self, location: str) -> None:
        Stop the application on the specified location.

    uninstall(self, location: str) -> None:
        Uninstall the application from the specified location.

    get_ip(self, location: str) -> str:
        Retrieve the IP address of the specified location.
"""

import subprocess

import click

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


class macOSBridge(PlatformBridge):
    """
    A class to manage macOS applications on local machines.

    Attributes:
        __app_path (str): The path to the application bundle.
    """

    def __init__(self, app_path: str):
        """
        Initialize the macOSBridge with the application path.

        Args:
            app_path (str): The path to the application bundle.
        """
        self.__app_path = app_path

    def validate(self, location: str) -> None:
        """
        Validate that the application can be managed on the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").

        Raises:
            RuntimeError: If the location is not supported.
        """
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")

    def install(self, location: str) -> None:
        """
        Install the application on the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").
        """
        self.validate(location)
        click.echo("No action needed for installing macOS app")

    def run(self, location: str) -> None:
        """
        Run the application on the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").
        """
        self.validate(location)
        header(f"Running {self.__app_path}")
        subprocess.run(["open", self.__app_path], check=True, capture_output=False)

    def stop(self, location: str) -> None:
        """
        Stop the application on the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").
        """
        self.validate(location)
        header("Stopping macOS test server")
        click.echo("running 'killall testserver'")
        subprocess.run(["killall", "testserver"], check=False, capture_output=False)

    def uninstall(self, location: str) -> None:
        """
        Uninstall the application from the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").
        """
        self.validate(location)
        click.echo("No action needed for uninstalling macOS app")

    def get_ip(self, location: str) -> str:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the application (e.g., "localhost").

        Returns:
            str: The IP address of the location.
        """
        return location
