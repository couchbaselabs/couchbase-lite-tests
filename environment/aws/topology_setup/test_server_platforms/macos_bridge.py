from .platform_bridge import PlatformBridge
from common.output import header
import subprocess

class macOSBridge(PlatformBridge):
    def __init__(self, app_path: str):
        self.__app_path = app_path

    def install(self, location: str) -> None:
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")
        
        print("No action needed for installing macOS app")

    def run(self, location: str) -> None:
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")
        
        header(f"Running {self.__app_path}")
        subprocess.run(["open", self.__app_path], check=True, capture_output=False)

    def stop(self, location: str) -> None:
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")
        
        header("Stopping test server")
        subprocess.run(["killall", "testserver"], check=True, capture_output=False)


    def uninstall(self, location: str) -> None:
        if location != "localhost":
            raise RuntimeError("macOSBridge only supports local deployment")

        print("No action needed for uninstalling macOS app")