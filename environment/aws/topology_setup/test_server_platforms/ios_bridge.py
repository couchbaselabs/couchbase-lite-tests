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
PID_FILE = SCRIPT_PATH / "ios_pid.txt"


class iOSBridge(PlatformBridge):
    """
    A class to manage iOS applications on devices using either xharness or devicectl.
    """

    def __init__(self, app_path: str, use_devicectl: bool = True):
        """
        Initialize the iOSBridge with the application path and whether to use devicectl.

        Args:
            app_path (str): The path to the application.
            use_devicectl (bool): Whether to use devicectl for managing the application.
        """
        self.__app_path = app_path
        self.__use_devicectl = use_devicectl

    def validate(self, location: str) -> None:
        """
        Validate that the device is connected and accessible

        Args:
            location (str): The device location (e.g., device UUID).

        Raises:
            RuntimeError: If the device is not found.
        """
        if self.__use_devicectl:
            self.__validate_devicectl(location)
        else:
            self.__validate_libimobiledevice(location)

    def install(self, location: str) -> None:
        """
        Install the application on the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        header(f"Installing {self.__app_path} to {location}")
        if self.__use_devicectl:
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
        if self.__use_devicectl:
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
        if self.__use_devicectl:
            self.__stop_devicectl(location)
        else:
            self.__stop_xharness(location)

    def uninstall(self, location: str) -> None:
        """
        Uninstall the application from the specified device.

        Args:
            location (str): The device location (e.g., device UUID).
        """
        print("iOS app uninstall deliberately not implemented")

    def __validate_libimobiledevice(self, location: str) -> None:
        self.__verify_libimobiledevice()
        result = subprocess.run(
            ["ideviceinfo", "-u", location], check=False, capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Device {location} not found!")

    def __validate_devicectl(self, location: str) -> None:
        pass

    def __install_devicectl(self, location: str) -> None:
        pass

    def __install_xharness(self, location: str) -> None:
        self.__verify_xharness()
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
        pass

    def __run_xharness(self, location: str) -> None:
        PID_FILE.unlink() if PID_FILE.exists() else None
        self.__verify_xharness()
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
        print(result.stdout)

        # Extract PID from result.stdout
        match = re.search(r"pid ([0-9]+)", result.stdout.decode("utf-8"))
        if match:
            pid = match.group(1)
            print(f"Extracted PID: {pid}")
        else:
            raise RuntimeError("Failed to extract PID from XHarness output")

        with open(PID_FILE, "w") as file:
            file.write(pid)

    def __stop_devicectl(self, location: str) -> None:
        pass

    def __stop_xharness(self, location: str) -> None:
        if not PID_FILE.exists():
            raise RuntimeError("PID file not found, cannot stop test server")

        with open(PID_FILE) as file:
            pid = file.read().strip()

        print(f"\t...PID {pid}")
        self.__verify_xharness()

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

    def __verify_xharness(self) -> None:
        if not XHARNESS_PATH.is_file():
            raise RuntimeError(f"XHarness not found at {XHARNESS_PATH}, aborting...")

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
                print(f"Broadcasting ping request on {interface} ({ip})")
                subprocess.run(
                    ["ping", ip, "-c", "3"], check=True, capture_output=True, text=True
                )

    def get_ip(self, location: str) -> str:
        """
        Retrieve the IP address of the specified device.

        Args:
            location (str): The device location (e.g., device UUID).

        Returns:
            str: The IP address of the device.

        Raises:
            RuntimeError: If the IP address cannot be determined.
        """
        if "IOS_TEST_SERVER_IP" in environ:
            return environ["IOS_TEST_SERVER_IP"]

        # Apple provides no sane way to do this so the following dance is performed:
        #    1. Retrieve MAC address of device (this requires the default "Private Wifi Address" to be turned off on device)
        #    2. Broadcast a ping to the broadcast address of all network interfaces that have one, to ensure that the device
        #       responds and has an ARP table entry
        #    3. Retrieve the ARP table and find the IP address that corresponds to the MAC address
        self.__verify_libimobiledevice()
        result = subprocess.run(
            ["ideviceinfo", "-u", location, "-k", "WiFiAddress"],
            check=True,
            capture_output=True,
            text=True,
        )
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
                return line.split(" ")[1].strip("()")

        raise RuntimeError(f"Could not determine IP address of '{location}'")
