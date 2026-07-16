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

    # Dangerous (runtime) permissions the MultipeerReplicator may need. These are
    # granted right after install so the test server doesn't need to block waiting
    # for a system permission dialog during a test run. Each entry is
    # (permission, min_api, max_api); None means unbounded on that side.
    __runtime_permissions: list[tuple[str, int | None, int | None]] = [
        (
            "android.permission.ACCESS_FINE_LOCATION",
            None,
            30,
        ),  # BLE scanning on API <= 30
        ("android.permission.BLUETOOTH_SCAN", 31, None),  # API 31+
        ("android.permission.BLUETOOTH_CONNECT", 31, None),  # API 31+
        ("android.permission.BLUETOOTH_ADVERTISE", 31, None),  # API 31+
        ("android.permission.NEARBY_WIFI_DEVICES", 31, None),  # API 31+
    ]

    def __init__(
        self,
        app_path: str,
        app_id: str,
        activity: str = "MainActivity",
        *,
        needs_permissions: bool = True,
    ) -> None:
        """
        Initialize the AndroidBridge with the application path, application ID, and activity name.

        Args:
            app_path (str): The path to the application APK file.
            app_id (str): The application ID.
            activity (str): The activity name to launch.

        Raises:
            RuntimeError: If the ADB executable is not found.
        """
        self.__app_path = app_path
        self.__app_id = app_id
        self.__activity = activity
        self.__adb_location = None
        self.__needs_permissions = needs_permissions

        find_command = "where" if platform.system() == "Windows" else "which"
        find_adb_result = subprocess.run([find_command, "adb"], check=False, capture_output=True, text=True)
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
        if self.__needs_permissions:
            self.__grant_runtime_permissions(location)

    def __get_api_level(self, location: str) -> int:
        """
        Retrieve the Android API level of the specified device.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        result = subprocess.run(
            [
                str(self.__adb_location),
                "-s",
                location,
                "shell",
                "getprop",
                "ro.build.version.sdk",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip())

    def __grant_runtime_permissions(self, location: str) -> None:
        """
        Grant of the runtime permissions for MultipeerReplicator when using
        Bluetooth, so the test server never blocks on a system permission
        dialog.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Granting runtime permissions to {self.__app_id} on {location}")
        api_level = self.__get_api_level(location)
        permissions = [
            permission
            for permission, min_api, max_api in self.__runtime_permissions
            if (min_api is None or api_level >= min_api) and (max_api is None or api_level <= max_api)
        ]
        for permission in permissions:
            result = subprocess.run(
                [
                    str(self.__adb_location),
                    "-s",
                    location,
                    "shell",
                    "pm",
                    "grant",
                    self.__app_id,
                    permission,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                click.echo(f"  granted {permission}")
            else:
                message = (result.stderr or result.stdout).strip()
                click.echo(f"  skipped {permission} ({message})")

    def run(self, location: str) -> None:
        """
        Run the application on the specified device.

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
        Retrieve the IP address of the specified device.

        Args:
            location (str): The device location (e.g., device serial number).

        Returns:
            str: The IP address of the device.

        Raises:
            RuntimeError: If the IP address cannot be determined.
        """
        result = subprocess.run(
            [
                str(self.__adb_location),
                "-s",
                location,
                "shell",
                "ip",
                "-f",
                "inet",
                "addr",
                "show",
                "wlan0",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            click.echo(line)
            if "inet" in line:
                return line.lstrip().split(" ")[1].split("/")[0]

        return None
