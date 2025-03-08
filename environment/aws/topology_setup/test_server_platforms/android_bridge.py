from pathlib import Path
from typing import List
from .platform_bridge import PlatformBridge
from common.output import header
import subprocess

class AndroidBridge(PlatformBridge):
    __potential_adb_locations: List[str] = [
        "/opt/homebrew/share/android-commandlinetools/platform-tools/",
        "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools"
    ]
    
    def __init__(self, app_path: str, app_id: str, activity: str = "MainActivity"):
        self.__app_path = app_path
        self.__app_id = app_id
        self.__activity = activity
        for adb_location in self.__potential_adb_locations:
            print(adb_location)
            if (Path(adb_location) / "adb").exists():
                self.__adb_location = Path(adb_location) / "adb"
                break

            if (Path(adb_location) / "adb.exe").exists():
                self.__adb_location = Path(adb_location) / "adb.exe"
                break

        if self.__adb_location is None:
            raise RuntimeError("adb not found")

    def install(self, location: str) -> None:
        header(f"Installing {self.__app_path} to {location}")
        subprocess.run([str(self.__adb_location), "-s", location, "install", self.__app_path], check=True, capture_output=False)

    def run(self, location: str) -> None:
        header(f"Running {self.__app_id} on {location}")
        subprocess.run([str(self.__adb_location), "-s", location, "shell", "am", "start", f"{self.__app_id}/{self.__app_id}.{self.__activity}"], check=True, capture_output=False)

    def stop(self, location: str) -> None:
        header(f"Stopping {self.__app_id} on {location}")
        subprocess.run([str(self.__adb_location), "-s", location, "shell", "am", "force-stop", self.__app_id], check=True, capture_output=False)

    def uninstall(self, location: str) -> None:
        header(f"Uninstalling {self.__app_id} from {location}")
        subprocess.run([str(self.__adb_location), "-s", location, "uninstall", self.__app_id], check=True, capture_output=False)