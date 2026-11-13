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
        Install the application on the specified device, uninstalling a conflicting existing copy if needed.

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
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

import click

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


class AndroidBridge(PlatformBridge):
    """
    A class to manage Android applications on devices using ADB.
    """

    __potential_adb_locations: ClassVar[list[str]] = [
        "/opt/homebrew/share/android-commandlinetools/platform-tools/",
        "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools",
    ]

    # Dangerous (runtime) permissions the MultipeerReplicator may need. These are
    # granted right after install so the test server doesn't need to block waiting
    # for a system permission dialog during a test run. Each entry is
    # (permission, min_api, max_api); None means unbounded on that side.
    __runtime_permissions: ClassVar[list[tuple[str, int | None, int | None]]] = [
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

    # adb install failures that a clean uninstall of the package already on the
    # device resolves (e.g. an APK signed with a different key, or a build whose
    # version code is older than the installed one).
    __conflict_failures: ClassVar[tuple[str, ...]] = (
        "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
        "INSTALL_FAILED_VERSION_DOWNGRADE",
        "INSTALL_FAILED_ALREADY_EXISTS",
        "signatures do not match",
    )

    def __init__(
        self,
        app_path: str,
        app_id: str,
        activity: str = "MainActivity",
        *,
        needs_permissions: bool = True,
        launch_extras: Mapping[str, str] | None = None,
        restart_on_run: bool = False,
    ) -> None:
        """
        Initialize the AndroidBridge with the application path, application ID, and activity name.

        Args:
            app_path (str): The path to the application APK file.
            app_id (str): The application ID.
            activity (str): The activity name to launch.
            needs_permissions (bool): Whether to grant the runtime permissions after install.
            launch_extras (Mapping[str, str] | None): String extras passed to the activity on launch.
            restart_on_run (bool): Force-stop any running instance before launching.

        Raises:
            RuntimeError: If the ADB executable is not found.
        """
        self.__app_path = app_path
        self.__app_id = app_id
        self.__activity = activity
        self.__adb_location = None
        self.__needs_permissions = needs_permissions
        self.__launch_extras = dict(launch_extras or {})
        self.__restart_on_run = restart_on_run

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

        If the APK conflicts with the copy already on the device (a different
        signing key, or a lower version code) the existing package is
        uninstalled and the install retried once.

        Args:
            location (str): The device location (e.g., device serial number).

        Raises:
            RuntimeError: If the application cannot be installed.
        """
        header(f"Installing {self.__app_path} to {location}")
        output = self.__try_install(location)
        if output is not None and self.__conflicts_with_existing(output):
            click.secho(
                f"Install conflicts with the {self.__app_id} already on {location}, uninstalling and retrying...",
                fg="yellow",
            )
            subprocess.run(
                [str(self.__adb_location), "-s", location, "uninstall", self.__app_id],
                check=False,
                capture_output=False,
            )
            output = self.__try_install(location)

        if output is not None:
            raise RuntimeError(f"Failed to install {self.__app_path} to {location}: {output}")

        if self.__needs_permissions:
            self.__grant_runtime_permissions(location)

    def __try_install(self, location: str) -> str | None:
        """
        Run a single adb install, echoing whatever adb reports.

        Args:
            location (str): The device location (e.g., device serial number).

        Returns:
            str | None: None if the install succeeded, otherwise adb's output.
        """
        result = subprocess.run(
            [str(self.__adb_location), "-s", location, "install", self.__app_path],
            check=False,
            capture_output=True,
            text=True,
        )
        output = f"{result.stdout}\n{result.stderr}".strip()
        if output:
            click.echo(output)

        # Some adb versions report a failed install with an exit status of 0,
        # so the output has to be inspected as well.
        if result.returncode == 0 and "Failure [" not in output:
            return None

        return output or f"adb install exited with status {result.returncode}"

    def __conflicts_with_existing(self, output: str) -> bool:
        """
        Determine whether a failed install can be fixed by uninstalling the
        package that is already on the device.

        Args:
            output (str): The output of the failed adb install.
        """
        return any(failure in output for failure in self.__conflict_failures)

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

    def __wake_device(self, location: str) -> None:
        """
        Wake the screen and dismiss the keyguard so the test server is
        launched into the foreground.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        for command in (["input", "keyevent", "KEYCODE_WAKEUP"], ["wm", "dismiss-keyguard"]):
            subprocess.run(
                [str(self.__adb_location), "-s", location, "shell", *command],
                check=False,
                capture_output=True,
            )

    def run(self, location: str) -> None:
        """
        Run the application on the specified device.

        Args:
            location (str): The device location (e.g., device serial number).
        """
        header(f"Running {self.__app_id} on {location}")
        self.__wake_device(location)
        adb = [str(self.__adb_location), "-s", location]
        start_args = ["-S"] if self.__restart_on_run else []
        for key, value in self.__launch_extras.items():
            start_args += ["--es", key, value]

        subprocess.run(
            [*adb, "shell", "am", "start", *start_args, f"{self.__app_id}/.{self.__activity}"],
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
