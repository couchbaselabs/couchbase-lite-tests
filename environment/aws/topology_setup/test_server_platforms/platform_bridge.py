"""
This module provides the abstract base class PlatformBridge for managing applications on various platforms.
It defines the interface for validating, installing, running, stopping, and uninstalling applications, as well as retrieving the IP address of a device.

Classes:
    PlatformBridge: An abstract base class for managing applications on various platforms.

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

from abc import ABC, abstractmethod

import click


class PlatformBridge(ABC):
    """
    An abstract base class for managing applications on various platforms.

    Methods:
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

    @abstractmethod
    def validate(self, location: str) -> None:
        """
        Validate that the application can be managed on the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
        """
        pass

    @abstractmethod
    def install(self, location: str) -> None:
        """
        Install the application on the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
        """
        pass

    @abstractmethod
    def run(self, location: str) -> None:
        """
        Run the application on the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
        """
        pass

    @abstractmethod
    def stop(self, location: str) -> None:
        """
        Stop the application on the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
        """
        pass

    @abstractmethod
    def uninstall(self, location: str) -> None:
        """
        Uninstall the application from the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
        """
        pass

    def get_ip(self, location: str, *, fallback: str | None = None) -> str:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).
            fallback (str | None): An optional fallback IP address if the retrieval fails.

        Returns:
            str: The IP address of the location, or the fallback if specified.
        """
        attempt = self._get_ip(location)
        if attempt is not None:
            return attempt

        if fallback is not None:
            click.secho(
                f"Failed to retrieve IP address for {location}, using fallback: {fallback}.",
                fg="yellow",
            )
            return fallback

        raise RuntimeError(
            f"Failed to retrieve IP address for {location} and no fallback provided."
        )

    @abstractmethod
    def _get_ip(self, location: str) -> str | None:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).

        Returns:
            str: The IP address of the location.
        """
        pass
