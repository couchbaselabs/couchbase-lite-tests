import platform
import re
import subprocess
from os import environ
from pathlib import Path

from common.output import header

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


class iOSBridge(PlatformBridge):
    def __init__(self, app_path: str, use_devicectl: bool = True):
        self.__app_path = app_path
        self.__use_devicectl = use_devicectl
        self.__pid: str = ""

    def validate(self, location: str) -> None:
        if self.__use_devicectl:
            self.__validate_devicectl(location)
        else:
            self.__validate_xharness(location)

    def install(self, location: str) -> None:
        header(f"Installing {self.__app_path} to {location}")
        if self.__use_devicectl:
            self.__install_devicectl(location)
        else:
            self.__install_xharness(location)

    def run(self, location: str) -> None:
        header(f"Running {self.__app_path} on {location}")
        if self.__use_devicectl:
            self.__run_devicectl(location)
        else:
            self.__run_xharness(location)

    def stop(self, location: str) -> None:
        pid = self.__pid if self.__pid != "" else "<error>"
        header(f"Stopping testserver PID {pid} on {location}")
        if self.__use_devicectl:
            self.__stop_devicectl(location)
        else:
            self.__stop_xharness(location)

    def uninstall(self, location: str) -> None:
        print("iOS app uninstall deliberately not implemented")

    def __validate_xharness(self, location: str) -> None:
        result = subprocess.run(
            [
                str(XHARNESS_PATH),
                "apple",
                "device",
                "ios-device",
                f"--device={location}",
            ],
            check=False,
            capture_output=True,
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
            self.__pid = match.group(1)
            print(f"Extracted PID: {self.__pid}")
        else:
            raise RuntimeError("Failed to extract PID from XHarness output")

    def __stop_devicectl(self, location: str) -> None:
        pass

    def __stop_xharness(self, location: str) -> None:
        self.__verify_xharness()
        if self.__pid == "":
            raise RuntimeError("PID not set, cannot stop test server")

        subprocess.run(
            [
                str(XHARNESS_PATH),
                "apple",
                "mlaunch",
                "--",
                "--devname",
                location,
                "--killdev",
                self.__pid,
            ],
            check=True,
            capture_output=False,
        )

    def __verify_xharness(self) -> None:
        if not XHARNESS_PATH.is_file():
            raise RuntimeError(f"XHarness not found at {XHARNESS_PATH}, aborting...")
