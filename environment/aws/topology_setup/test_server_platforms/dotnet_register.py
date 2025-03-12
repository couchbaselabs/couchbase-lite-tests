import glob
import platform
import subprocess
from abc import abstractmethod
from os import environ
from pathlib import Path
from typing import List, Optional

from common.output import header

from topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .ios_bridge import iOSBridge
from .macos_bridge import macOSBridge
from .platform_bridge import PlatformBridge

DOTNET_TEST_SERVER_DIR = TEST_SERVER_DIR / "dotnet"
SCRIPT_DIR = Path(__file__).resolve().parent

if platform.system() == "Windows":
    DOTNET_PATH = Path(environ["LOCALAPPDATA"]) / "Microsoft" / "dotnet" / "dotnet.exe"
else:
    DOTNET_PATH = Path.home() / ".dotnet" / "dotnet"


class WinUIBridge(PlatformBridge):
    def __init__(self, app_name: str, app_id: str, install_path: str):
        self.__app_name = app_name
        self.__app_id = app_id
        self.__install_path = install_path

    def validate(self, location):
        if location != "localhost":
            raise ValueError("WinUIBridge only supports local installation")

    def install(self, location: str) -> None:
        self.validate(location)
        header(f"Installing from {self.__install_path}")

        # https://github.com/PowerShell/PowerShell/issues/18530#issuecomment-1325691850
        environ_copy = environ.copy()
        environ_copy.pop("PSMODULEPATH")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Import-Module Microsoft.PowerShell.Security; {self.__install_path} -Force",
            ],
            check=True,
            capture_output=False,
            env=environ_copy,
        )

    def run(self, location: str) -> None:
        self.validate(location)
        header(f"Running {self.__app_name} ({self.__app_id})")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'Invoke-Expression "start shell:AppsFolder\\{self.__app_id}!App"',
            ],
            check=True,
            capture_output=False,
        )
        pass

    def stop(self, location: str) -> None:
        self.validate(location)
        header(f"Stopping {self.__app_name} ({self.__app_id})")
        result = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                f"Get-Process -ProcessName {self.__app_name} -ErrorAction Ignore | Select-Object -Expand Id",
            ],
            check=True,
            capture_output=True,
        )
        if result is None:
            print("No test server process found")
            return

        subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                f"Stop-Process {result.stdout.decode()}",
            ],
            check=True,
            capture_output=False,
        )

    def uninstall(self, location: str) -> None:
        self.validate(location)
        header(f"Uninstalling {self.__app_name} ({self.__app_id}")
        app_id_prefix = self.__app_id.split("_")[0]
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-AppxPackage {app_id_prefix}* | Remove-AppxPackage",
            ],
            check=True,
            capture_output=False,
        )

    def get_ip(self, location: str) -> str:
        return "localhost"


class DotnetTestServer(TestServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    @abstractmethod
    def dotnet_framework(self) -> str:
        pass

    @property
    def extra_args(self) -> Optional[str]:
        return None

    @property
    @abstractmethod
    def publish(self) -> bool:
        pass

    def build(self, cbl_version: str):
        version_parts = cbl_version.split("-")
        build = version_parts[1]
        cbl_version = f"{version_parts[0]}-b{build.zfill(4)}"
        csproj_path = (
            DOTNET_TEST_SERVER_DIR / "testserver.logic" / "testserver.logic.csproj"
        )
        header(f"Modifying Couchbase Lite version to {cbl_version}")
        print(DOTNET_PATH)
        print(csproj_path)
        subprocess.run(
            [
                DOTNET_PATH,
                "add",
                csproj_path,
                "package",
                "Couchbase.Lite.Enterprise",
                "--version",
                cbl_version,
            ],
            check=True,
            capture_output=False,
        )

        verb = "publish" if self.publish else "build"
        csproj_path = DOTNET_TEST_SERVER_DIR / "testserver" / "testserver.csproj"
        header(f"Building .NET test server for {self.platform}")
        args: List[str] = [
            str(DOTNET_PATH),
            verb,
            str(csproj_path),
            "-f",
            self.dotnet_framework,
            "-c",
            "Release",
            "-v",
            "n",
        ]
        if self.extra_args:
            args.append(self.extra_args)

        subprocess.run(args, check=True, capture_output=False)

class DotnetTestServerCli(TestServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    @abstractmethod
    def rid(self) -> str:
        pass

    def build(self, cbl_version: str):
        version_parts = cbl_version.split("-")
        build = version_parts[1]
        cbl_version = f"{version_parts[0]}-b{build.zfill(4)}"
        csproj_path = (
            DOTNET_TEST_SERVER_DIR / "testserver.logic" / "testserver.logic.csproj"
        )
        header(f"Modifying Couchbase Lite version to {cbl_version}")
        subprocess.run(
            [
                DOTNET_PATH,
                "add",
                csproj_path,
                "package",
                "Couchbase.Lite.Enterprise",
                "--version",
                cbl_version,
            ],
            check=True,
            capture_output=False,
        )

        csproj_path = DOTNET_TEST_SERVER_DIR / "testserver.cli" / "testserver.cli.csproj"
        header(f"Building .NET test server for {self.platform}")
        args: List[str] = [
            str(DOTNET_PATH),
            "publish",
            str(csproj_path),
            "-r",
            self.rid,
            "-c",
            "Release"
        ]

        subprocess.run(args, check=True, capture_output=False)


@TestServer.register("dotnet_ios")
class DotnetTestServer_iOS(DotnetTestServer):
    @property
    def platform(self) -> str:
        return ".NET iOS"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-ios"

    @property
    def publish(self) -> bool:
        return False

    @property
    def extra_args(self) -> Optional[str]:
        return "-p:RuntimeIdentifier=ios-arm64"

    def create_bridge(self) -> PlatformBridge:
        return iOSBridge(
            str(
                DOTNET_TEST_SERVER_DIR
                / "testserver"
                / "bin"
                / "Release"
                / "net8.0-ios"
                / "ios-arm64"
                / "testserver.app"
            ),
            False,
        )


@TestServer.register("dotnet_android")
class DotnetTestServer_Android(DotnetTestServer):
    @property
    def platform(self) -> str:
        return ".NET Android"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-android"

    @property
    def publish(self) -> bool:
        return True

    def create_bridge(self) -> PlatformBridge:
        return AndroidBridge(
            str(
                DOTNET_TEST_SERVER_DIR
                / "testserver"
                / "bin"
                / "Release"
                / "net8.0-android"
                / "com.couchbase.dotnet.testserver-Signed.apk"
            ),
            "com.couchbase.dotnet.testserver",
        )


@TestServer.register("dotnet_windows")
class DotnetTestServer_Windows(DotnetTestServer):
    @property
    def platform(self) -> str:
        return ".NET Windows"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-windows10.0.19041.0"

    @property
    def publish(self) -> bool:
        return True

    def create_bridge(self) -> PlatformBridge:
        base_path = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-windows10.0.19041.0"
            / "win10-x64"
            / "AppPackages"
        )
        install_scripts = glob.glob(
            str(base_path / "**" / "Install.ps1"), recursive=True
        )
        if not install_scripts:
            raise FileNotFoundError(
                "Install.ps1 not found, was the test server properly built?"
            )

        install_path = install_scripts[0]
        return WinUIBridge(
            "testserver",
            "bf1b9964-631c-4489-91fa-a04e7f3f3765_nw4t8ysxwwgx8",
            install_path,
        )


@TestServer.register("dotnet_macos")
class DotnetTestServer_macOS(DotnetTestServer):
    @property
    def platform(self) -> str:
        return ".NET macOS"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-maccatalyst"

    @property
    def publish(self) -> bool:
        return False

    def create_bridge(self) -> PlatformBridge:
        return macOSBridge(
            str(
                DOTNET_TEST_SERVER_DIR
                / "testserver"
                / "bin"
                / "Release"
                / "net8.0-maccatalyst"
                / "maccatalyst-x64"
                / "testserver.app"
            )
        )
