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

    @abstractmethod
    def get_ip(self, location: str) -> str:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the application (e.g., device serial number).

        Returns:
            str: The IP address of the location.
        """
        pass
