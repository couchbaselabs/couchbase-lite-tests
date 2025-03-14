import platform
import shutil
import subprocess
from abc import abstractmethod
from os import environ
from pathlib import Path
from typing import List, Optional

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .exe_bridge import ExeBridge
from .ios_bridge import iOSBridge
from .macos_bridge import macOSBridge
from .platform_bridge import PlatformBridge

DOTNET_TEST_SERVER_DIR = TEST_SERVER_DIR / "dotnet"
SCRIPT_DIR = Path(__file__).resolve().parent

if platform.system() == "Windows":
    DOTNET_PATH = Path(environ["LOCALAPPDATA"]) / "Microsoft" / "dotnet" / "dotnet.exe"
else:
    DOTNET_PATH = Path.home() / ".dotnet" / "dotnet"


class DotnetTestServer(TestServer):
    def __init__(self, version: str):
        super().__init__(version)

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

    def build(self):
        version_parts = self.version.split("-")
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
    def __init__(self, version: str):
        super().__init__(version)

    @property
    @abstractmethod
    def rid(self) -> str:
        pass

    def build(self):
        version_parts = self.version.split("-")
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

        csproj_path = (
            DOTNET_TEST_SERVER_DIR / "testserver.cli" / "testserver.cli.csproj"
        )
        header(f"Building .NET test server for {self.platform}")
        args: List[str] = [
            str(DOTNET_PATH),
            "publish",
            str(csproj_path),
            "-r",
            self.rid,
            "-c",
            "Release",
            "--self-contained",
            "true",
        ]

        subprocess.run(args, check=True, capture_output=False)


@TestServer.register("dotnet_ios")
class DotnetTestServer_iOS(DotnetTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "dotnet_ios"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-ios"

    @property
    def publish(self) -> bool:
        return False

    @property
    def extra_args(self) -> Optional[str]:
        return "-p:RuntimeIdentifier=ios-arm64"

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"couchbase-lite-net/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"

    def create_bridge(self) -> PlatformBridge:
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-ios"
            / "ios-arm64"
        )
        return iOSBridge(
            str(prefix / "testserver.app"),
            False,
        )

    def compress_package(self):
        header(f"Compressing .NET test server for {self.platform}")
        publish_dir = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-ios"
            / "ios-arm64"
            / "testserver.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_ios.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path):
        unzip_directory(path, path.parent / "testserver.app")
        path.unlink()


@TestServer.register("dotnet_android")
class DotnetTestServer_Android(DotnetTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "dotnet_android"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-android"

    @property
    def publish(self) -> bool:
        return True

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"couchbase-lite-net/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self) -> PlatformBridge:
        dir = (
            TEST_SERVER_DIR
            / "downloaded"
            / self.platform
            / self.version
            / "testserver_android.apk"
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-android"
            / "com.couchbase.dotnet.testserver-Signed.apk"
        )
        return AndroidBridge(
            str(dir),
            "com.couchbase.dotnet.testserver",
        )

    def compress_package(self):
        header(f"Compressing .NET test server for {self.platform}")
        apk_path = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-android"
            / "com.couchbase.dotnet.testserver-Signed.apk"
        )
        zip_path = apk_path.parents[5] / "testserver_android.apk"
        shutil.copy(apk_path, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        # No action needed
        pass


@TestServer.register("dotnet_windows")
class DotnetTestServer_Windows(DotnetTestServerCli):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "dotnet_windows"

    @property
    def rid(self) -> str:
        return "win-x64"

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"couchbase-lite-net/{version_parts[0]}/{version_parts[1]}/testserver_windows.zip"

    def create_bridge(self) -> PlatformBridge:
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver.cli"
            / "bin"
            / "Release"
            / "net8.0"
            / "win-x64"
            / "publish"
        )
        return ExeBridge(
            str(prefix / "testserver.cli.exe"),
            ["--silent", "5555"],
        )

    def compress_package(self) -> str:
        header(f"Compressing .NET test server for {self.platform}")
        publish_dir = (
            DOTNET_TEST_SERVER_DIR
            / "testserver.cli"
            / "bin"
            / "Release"
            / "net8.0"
            / "win-x64"
            / "publish"
        )
        zip_path = publish_dir.parents[5] / "testserver_windows.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path):
        unzip_directory(path, path.parent)
        path.unlink()


@TestServer.register("dotnet_macos")
class DotnetTestServer_macOS(DotnetTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "dotnet_macos"

    @property
    def dotnet_framework(self) -> str:
        return "net8.0-maccatalyst"

    @property
    def publish(self) -> bool:
        return False

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"couchbase-lite-net/{version_parts[0]}/{version_parts[1]}/testserver_macos.zip"

    def create_bridge(self) -> PlatformBridge:
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-maccatalyst"
            / "maccatalyst-x64"
        )
        return macOSBridge(str(prefix / "testserver.app"))

    def compress_package(self) -> str:
        header(f"Compressing .NET test server for {self.platform}")
        publish_dir = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net8.0-maccatalyst"
            / "maccatalyst-x64"
            / "testserver.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_macos.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        unzip_directory(path, path.parent / "testserver.app")
        path.unlink()
