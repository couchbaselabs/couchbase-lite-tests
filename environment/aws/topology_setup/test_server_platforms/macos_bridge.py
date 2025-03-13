import subprocess
from typing import Optional

from environment.aws.common.output import header

from .platform_bridge import PlatformBridge


class macOSBridge(PlatformBridge):
    def __init__(self, app_path: str):
        self.__app_path = app_path

    def validate(self, location: str) -> None:
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")

    def install(self, location: str) -> None:
        self.validate(location)
        print("No action needed for installing macOS app")

    def run(self, location: str) -> None:
        self.validate(location)
        header(f"Running {self.__app_path}")
        subprocess.run(["open", self.__app_path], check=True, capture_output=False)

    def stop(self, location: str) -> None:
        self.validate(location)
        header("Stopping test server")
        subprocess.run(["killall", "testserver"], check=True, capture_output=False)

    def uninstall(self, location: str) -> None:
        self.validate(location)
        print("No action needed for uninstalling macOS app")

    def get_ip(self, location):
        return location
