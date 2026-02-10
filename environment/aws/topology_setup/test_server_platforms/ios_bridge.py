"""
This module provides the iOSBridge class for managing iOS applications on devices using ADB (Android Debug Bridge).
It includes functions for validating devices, installing, running, stopping, and uninstalling applications, and retrieving the IP address of a device.

Classes:
    iOSBridge: A class to manage iOS applications on devices using ADB.

Functions:
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
import re
import shutil
import subprocess
from os import environ
from pathlib import Path

import click
import netifaces

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge

if platform.system() == "Windows":
    XHARNESS_PATH = (
        Path(environ["LOCALAPPDATA"])
        / "Microsoft"
        / "dotnet"
        / "tools"
        / "xharness.exe"
    )
else:
    XHARNESS_PATH = Path.home() / ".dotnet" / "tools" / "xharness"

SCRIPT_PATH = Path(__file__).resolve().parent
_xharness_devices: set[str] = set()


def _ios_pid_file_path(location: str) -> Path:
    """
    Returns the path to the PID file for iOS applications.
    """
    return SCRIPT_PATH / f"ios_pid_{location}.txt"


class iOSBridge(PlatformBridge):
    """
    A class to manage iOS applications on devices using either xharness or devicectl.
    """

    def __init__(self, app_path: str, app_id: str):
        """
        Initialize the iOSBridge with the application path and whether to use devicectl.

        Args:
            app_path (str): The path to the application.
            app_id (bool): The bundle ID of the application.
        """
        self.__app_path = app_path
        self.__has_xharness: bool = XHARNESS_PATH.is_file()
        self.__app_id = app_id

    def validate(self, location: str) -> None:
        """
        Validate that the device is connected and accessible

        Args:
            location (str): The device location (e.g., device UUID).

        Raises:
            RuntimeError: If the device is not found.
        """
        if location in _xharness_devices:
            # Already previously validated
            return

        if self.__validate_devicectl(location):
            return

        if not self.__has_xharness:
            raise RuntimeError(
                f"devicectl cannot find device '{location}' and xharness not found, aborting..."
            )

        if not self.__validate_libimobiledevice(location):
            raise RuntimeError(f"device '{location}' not found!")

        click.echo()
        click.secho(
            "Device not found with devicectl, falling back to xharness...", fg="yellow"
        )
        click.echo()
        _xharness_devices.add(location)

    def install(self, location: str) -> None:
        """
        Install the application on the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        header(f"Installing {self.__app_path} to {location}")
        if location not in _xharness_devices:
            self.__install_devicectl(location)
        else:
            self.__install_xharness(location)

    def run(self, location: str) -> None:
        """
        Run the application on the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        header(f"Running {self.__app_path} on {location}")
        if location not in _xharness_devices:
            self.__run_devicectl(location)
        else:
            self.__run_xharness(location)

    def stop(self, location: str) -> None:
        """
        Stop the application on the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        header(f"Stopping testserver on {location}")
        if location not in _xharness_devices:
            self.__stop_devicectl(location)
        else:
            self.__stop_xharness(location)

    def uninstall(self, location: str) -> None:
        """
        Uninstall the application from the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        click.echo("iOS app uninstall deliberately not implemented")

    def __validate_libimobiledevice(self, location: str) -> bool:
        self.__verify_libimobiledevice()
        result = subprocess.run(
            ["ideviceinfo", "-u", location], check=False, capture_output=True
        )

        return result.returncode == 0

    def __validate_devicectl(self, location: str) -> bool:
        result = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "info",
                "details",
                "--device",
                location,
            ],
            check=False,
            capture_output=True,
        )

        return result.returncode == 0

    def __install_devicectl(self, location: str) -> None:
        subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "install",
                "app",
                "--device",
                location,
                self.__app_path,
            ],
            check=True,
            capture_output=False,
        )

    def __install_xharness(self, location: str) -> None:
        subprocess.run(
            [
                str(XHARNESS_PATH),
                "apple",
                "mlaunch",
                "--",
                "--devname",
                location,
                "--installdev",
                self.__app_path,
            ],
            check=True,
            capture_output=False,
        )

    def __run_devicectl(self, location: str) -> None:
        result = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "process",
                "launch",
                "--device",
                location,
                self.__app_id,
            ],
            check=True,
            capture_output=True,
        )

        click.echo(result.stdout)

    def __run_xharness(self, location: str) -> None:
        pid_file = _ios_pid_file_path(location)
        pid_file.unlink() if pid_file.exists() else None
        result = subprocess.run(
            [
                str(XHARNESS_PATH),
                "apple",
                "mlaunch",
                "--",
                "--devname",
                location,
                "--launchdev",
                self.__app_path,
            ],
            check=True,
            capture_output=True,
        )
        click.echo(result.stdout)

        # Extract PID from result.stdout
        match = re.search(r"pid ([0-9]+)", result.stdout.decode("utf-8"))
        if match:
            pid = match.group(1)
            click.secho(f"Extracted PID: {pid}", fg="green")
        else:
            raise RuntimeError("Failed to extract PID from XHarness output")

        with open(pid_file, "w") as file:
            file.write(pid)

    def __stop_devicectl(self, location: str) -> None:
        click.echo("Finding PID of test server...")
        try:
            result = subprocess.run(
                [
                    "xcrun",
                    "devicectl",
                    "device",
                    "info",
                    "apps",
                    "--device",
                    location,
                    "--bundle-id",
                    self.__app_id,
                    "--hide-headers",
                    "--hide-default-columns",
                    "--columns",
                    "path",
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            click.secho(
                f"App not found or devicectl failed. Skipping termination. Error:\n{e.stderr.decode('utf-8')}",
                fg="yellow",
            )
            return

        stdout = result.stdout.decode("utf-8").splitlines()
        if not stdout:
            click.secho(
                "App not found in device list. Skipping termination.", fg="yellow"
            )
            return

        app_path = stdout[-1].strip()
        click.echo(f"\tApp Path: {app_path}")

        try:
            result = subprocess.run(
                [
                    "xcrun",
                    "devicectl",
                    "device",
                    "info",
                    "processes",
                    "--device",
                    location,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(
                f"Failed to get processes. Skipping termination. Error:\n{e.stderr.decode('utf-8')}"
            )
            return

        stdout = result.stdout.decode("utf-8").splitlines()
        app_path_line = next((line for line in stdout if app_path in line), None)

        if not app_path_line:
            click.echo("Could not find PID line for app. Skipping termination.")
            return

        pid = app_path_line.split(" ")[0]
        click.echo(f"\tPID {pid}")
        try:
            subprocess.run(
                [
                    "xcrun",
                    "devicectl",
                    "device",
                    "process",
                    "terminate",
                    "--device",
                    location,
                    "--pid",
                    pid,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(
                f"Failed to terminate process. Continuing. Error:\n{e.stderr.decode('utf-8')}"
            )

    def __stop_xharness(self, location: str) -> None:
        pid_file = _ios_pid_file_path(location)
        if not pid_file.exists():
            raise RuntimeError("PID file not found, cannot stop test server")

        with open(pid_file) as file:
            pid = file.read().strip()

        click.echo(f"\t...PID {pid}")

        subprocess.run(
            [
                str(XHARNESS_PATH),
                "apple",
                "mlaunch",
                "--",
                "--devname",
                location,
                "--killdev",
                pid,
            ],
            check=True,
            capture_output=False,
        )

    def __verify_libimobiledevice(self) -> None:
        if shutil.which("ideviceinfo") is None:
            raise RuntimeError("ideviceinfo not found, aborting...")

    def __broadcast_ping_request(self) -> None:
        for interface in netifaces.interfaces():
            if interface == "lo":
                continue

            addr = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addr:
                if "broadcast" not in addr[netifaces.AF_INET][0]:
                    continue

                ip = addr[netifaces.AF_INET][0]["broadcast"]
                if ip.startswith("169.254"):
                    continue

                click.echo(f"Broadcasting ping request on {interface} ({ip})")
                result = subprocess.run(
                    ["ping", ip, "-c", "3"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode != 0:
                    click.secho(
                        f"Failed to ping {ip} on {interface}: {result.stderr}",
                        fg="yellow",
                    )

    def _get_ip(self, location: str) -> str | None:
        """
        Retrieve the IP address of the specified device.

        Args:
            location (str): The device location (e.g., device UUID).

        Returns:
            str | None: The IP address of the device, or None if it cannot be determined.
        """
        # Apple provides no sane way to do this so the following dance is performed:
        #    1. Retrieve MAC address of device (this requires the default "Private Wifi Address" to be turned off on device)
        #    2. Broadcast a ping to the broadcast address of all network interfaces that have one, to ensure that the device
        #       responds and has an ARP table entry
        #    3. Retrieve the ARP table and find the IP address that corresponds to the MAC address
        self.__verify_libimobiledevice()
        result = subprocess.run(
            ["ideviceinfo", "-u", location, "-k", "WiFiAddress"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.secho(
                f"Failed to retrieve WiFi address for device {location}: {result.stderr.strip()}",
                fg="yellow",
            )
            return None

        mac_address = result.stdout.strip()
        stripped_mac_parts = [
            part.lstrip("0") or "0" for part in mac_address.split(":")
        ]
        mac_address = ":".join(stripped_mac_parts)

        self.__broadcast_ping_request()

        result = subprocess.run(
            ["arp", "-an"], check=True, capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if mac_address in line:
                var = line.split(" ")[1].strip("()")
                click.echo(f"Found MAC address {var} ")
                return var
        click.echo(f"Could not find MAC address {mac_address}")
        return None
