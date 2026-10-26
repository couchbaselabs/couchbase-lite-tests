"""
This module provides the iOSSimulatorBridge class for managing iOS applications on a simulator
of this Mac using `xcrun simctl`.

Classes:
    iOSSimulatorBridge: A class to manage iOS applications on a simulator.
"""

import json
import subprocess

import click

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


def booted_simulator() -> str:
    """
    The UDID of the one booted simulator.

    Raises:
        RuntimeError: If no simulator or more than one is booted, since "booted" then names no single one.
    """
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted", "--json"], check=True, capture_output=True, text=True
    )
    booted = [device["udid"] for devices in json.loads(result.stdout)["devices"].values() for device in devices]
    if len(booted) != 1:
        raise RuntimeError(
            f"{len(booted)} simulators are booted. Boot exactly one with `xcrun simctl boot <UDID>`, "
            "or name one by UDID."
        )
    return booted[0]


class iOSSimulatorBridge(PlatformBridge):
    """
    A class to manage iOS applications on a simulator. The location is a simulator UDID, or
    "booted" when exactly one simulator is running. A simulator shares the network of this Mac,
    so the app is reachable on localhost.
    """

    def __init__(self, app_path: str, app_id: str) -> None:
        self.__app_path = app_path
        self.__app_id = app_id

    def validate(self, location: str) -> None:
        if location == "booted":
            booted_simulator()
            return

        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", location],
            check=False,
            capture_output=True,
            text=True,
        )
        # simctl filters the list by the search term, so an unknown or unbooted one lists no device.
        if result.returncode != 0 or "(Booted)" not in result.stdout:
            raise RuntimeError(f"No booted simulator matches '{location}'. Boot one with `xcrun simctl boot <UDID>`.")

    def install(self, location: str) -> None:
        header(f"Installing {self.__app_path} to simulator {location}")
        subprocess.run(["xcrun", "simctl", "install", location, self.__app_path], check=True)

    def run(self, location: str) -> None:
        header(f"Running {self.__app_id} on simulator {location}")
        subprocess.run(
            ["xcrun", "simctl", "launch", "--terminate-running-process", location, self.__app_id], check=True
        )

    def stop(self, location: str) -> None:
        header(f"Stopping {self.__app_id} on simulator {location}")
        result = subprocess.run(
            ["xcrun", "simctl", "terminate", location, self.__app_id],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.secho(f"{self.__app_id} is not running on simulator {location}", fg="yellow")

    def uninstall(self, location: str) -> None:
        header(f"Uninstalling {self.__app_id} from simulator {location}")
        subprocess.run(["xcrun", "simctl", "uninstall", location, self.__app_id], check=True)

    def _get_ip(self, location: str) -> str | None:
        return "localhost"
