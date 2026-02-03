"""
This module provides the AndroidBridge class for managing Android applications on devices using ADB (Android Debug Bridge).
It includes functions for validating devices, installing, running, stopping, and uninstalling applications, and retrieving the IP address of a device.

Classes:
    AndroidBridge: A class to manage Android applications on devices using ADB.

Functions:
    __init__(self, app_path: str, app_id: str, activity: str = "MainActivity") -> None:
        Initialize the AndroidBridge with the application path, application ID, and activity name.

    validate(self, location: str) -> None:
        Validate that the device is connected and accessible via ADB.

    install(self, location: str) -> None:
        Install the application on the specified device.

    run(self, location: str) -> None:
        Run the application on the specified device.

    stop(self, location: str) -> None:
        Stop the application on the specified device.

    uninstall(self, location: str) -> None:
        Uninstall the application from the specified device.

    get_ip(self, location: str) -> str:
        Retrieve the IP address of the specified device.
"""

import platform
import subprocess
from pathlib import Path

import click

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


class AndroidBridge(PlatformBridge):
    """
    A class to manage Android applications on devices using ADB.
    """

    __potential_adb_locations: list[str] = [
        "/opt/homebrew/share/android-commandlinetools/platform-tools/",
        "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools",
    ]

    def __init__(
        self,
        app_path: str,
        app_id: str,
        activity: str = "MainActivity",
        port: int = 8080,
    ):
        """
        Initialize the AndroidBridge with the application path, application ID, and activity name.

        Args:
            app_path (str): The path to the application APK file.
            app_id (str): The application ID.
            activity (str): The activity name to launch.
            port (int): The port the test server listens on; used for adb reverse so the host
                can connect via localhost. Default 8080 (C/Java); use 5555 for .NET.

        Raises:
            RuntimeError: If the ADB executable is not found.
        """
        self.__app_path = app_path
        self.__app_id = app_id
        self.__activity = activity
        self.__port = port
        self.__adb_location = None

        find_command = "where" if platform.system() == "Windows" else "which"
        find_adb_result = subprocess.run(
            [find_command, "adb"], check=False, capture_output=True, text=True
        )
        if find_adb_result.returncode == 0:
            self.__adb_location = Path(find_adb_result.stdout.strip())
            return

        for adb_location in self.__potential_adb_locations:
            if (Path(adb_location) / "adb").exists():
                self.__adb_location = Path(adb_location) / "adb"
                break

            if (Path(adb_location) / "adb.exe").exists():
                self.__adb_location = Path(adb_location) / "adb.exe"
                break

        if self.__adb_location is None:
            raise RuntimeError("adb not found")

    def validate(self, location: str) -> None:
        """
        Validate that the device is connected and accessible via ADB.

        Args:
            location (str): The device location (e.g., device serial number).

        Raises:
            RuntimeError: If the device is not found.
        """
        result = subprocess.run(
            [str(self.__adb_location), "-s", location, "get-state"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Device {location} not found!")

    def install(self, location: str) -> None:
        """
        Install the application on the specified device.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Installing {self.__app_path} to {location}")
        subprocess.run(
            [str(self.__adb_location), "-s", location, "install", self.__app_path],
            check=True,
            capture_output=False,
        )

    def run(self, location: str) -> None:
        """
        Run the application on the specified device.

        Starts the app, then sets up adb reverse so the host can reach the test server
        at localhost:<port> (forwarded to the device's port).

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Running {self.__app_id} on {location}")
        subprocess.run(
            [
                str(self.__adb_location),
                "-s",
                location,
                "shell",
                "am",
                "start",
                f"{self.__app_id}/.{self.__activity}",
            ],
            check=True,
            capture_output=False,
        )
        header(f"Forwarding host localhost:{self.__port} to device port {self.__port}")
        subprocess.run(
            [
                str(self.__adb_location),
                "-s",
                location,
                "reverse",
                f"tcp:{self.__port}",
                f"tcp:{self.__port}",
            ],
            check=True,
            capture_output=False,
        )

    def stop(self, location: str) -> None:
        """
        Stop the application on the specified device.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Stopping {self.__app_id} on {location}")
        subprocess.run(
            [
                str(self.__adb_location),
                "-s",
                location,
                "shell",
                "am",
                "force-stop",
                self.__app_id,
            ],
            check=True,
            capture_output=False,
        )

    def uninstall(self, location: str) -> None:
        """
        Uninstall the application from the specified device.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Uninstalling {self.__app_id} from {location}")
        subprocess.run(
            [str(self.__adb_location), "-s", location, "uninstall", self.__app_id],
            check=True,
            capture_output=False,
        )

    def _get_ip(self, location: str) -> str | None:
        """
        Return the address the host should use to reach the test server.

        Uses 127.0.0.1 because run() sets up adb reverse: host localhost:<port> is
        forwarded to the device's port, so the host must connect to 127.0.0.1.

        Args:
            location (str): The device location (e.g., device serial number).

        Returns:
            str: "127.0.0.1" so the host connects via the adb reverse tunnel.
        """
        return "127.0.0.1"
