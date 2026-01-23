"""
This module provides classes for managing .NET test servers on various platforms, including Windows, macOS, iOS, and Android.
It includes functions for building, compressing, and creating bridges for the test servers.

Classes:
    DotnetTestServer: A base class for .NET test servers.
    DotnetTestServerCli: A base class for .NET CLI test servers.
    DotnetTestServer_iOS: A class for managing .NET test servers on iOS.
    DotnetTestServer_Android: A class for managing .NET test servers on Android.
    DotnetTestServer_Windows: A class for managing .NET test servers on Windows.
    DotnetTestServer_macOS: A class for managing .NET test servers on macOS.

Functions:
    build(self) -> None:
        Build the .NET test server.
    compress_package(self) -> str:
        Compress the .NET test server package.
    create_bridge(self, **kwargs) -> PlatformBridge:
        Create a bridge for the .NET test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    publish(self) -> bool:
        Determine if the test server should be published.  Some platforms don't have the necessary artifacts otherwise.
    rid(self) -> str:
        Get the runtime identifier.
    uncompress_package(self, path: Path) -> None:
        Uncompress the .NET test server package.
"""

import platform
import shutil
import subprocess
from abc import abstractmethod
from os import environ
from pathlib import Path

import click

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
    """
    A base class for .NET test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    @abstractmethod
    def dotnet_framework(self) -> str:
        """
        Get the .NET framework version.

        Returns:
            str: The .NET framework version.
        """
        pass

    @property
    def extra_args(self) -> str | None:
        """
        Get the extra arguments for the build command.

        Returns:
            Optional[str]: The extra arguments for the build command.
        """
        return None

    @property
    def product(self) -> str:
        return "couchbase-lite-net"

    @property
    @abstractmethod
    def publish(self) -> bool:
        """
        Determine if the test server should be published.  Some platforms don't have the necessary artifacts otherwise.

        Returns:
            bool: True if the test server should be published, False otherwise.
        """
        pass

    def build(self) -> None:
        """
        Build the .NET test server.
        """
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

        verb = "publish" if self.publish else "build"
        csproj_path = DOTNET_TEST_SERVER_DIR / "testserver" / "testserver.csproj"
        header(f"Building .NET test server for {self.platform}")
        args: list[str] = [
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
    """
    A base class for .NET CLI test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    @abstractmethod
    def rid(self) -> str:
        """
        Get the runtime identifier.

        Returns:
            str: The runtime identifier.
        """
        pass

    @property
    def product(self) -> str:
        return "couchbase-lite-net"

    def build(self) -> None:
        """
        Build the .NET CLI test server.
        """
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
        args: list[str] = [
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
    """
    A class for managing .NET test servers on iOS.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        """
        Get the platform name.

        Returns:
            str: The platform name.
        """
        return "dotnet_ios"

    @property
    def dotnet_framework(self) -> str:
        """
        Get the .NET framework version.

        Returns:
            str: The .NET framework version.
        """
        return "net9.0-ios"

    @property
    def rid(self) -> str:
        """
        Get the runtime identifier.

        Returns:
            str: The runtime identifier.
        """
        return "win-x64"

    @property
    def publish(self) -> bool:
        """
        Determine if the test server should be published.  Some platforms don't have the necessary artifacts otherwise.

        Returns:
            bool: True if the test server should be published, False otherwise.
        """
        return False

    @property
    def extra_args(self) -> str | None:
        """
        Get the extra arguments for the build command.

        Returns:
            Optional[str]: The extra arguments for the build command.
        """
        return "-p:RuntimeIdentifier=ios-arm64"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return (
            f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"
        )

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the .NET test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net9.0-ios"
            / "ios-arm64"
        )
        return iOSBridge(
            str(prefix / "testserver.app"),
            "com.couchbase.dotnet.testserver",
        )

    def compress_package(self) -> str:
        """
        Compress the .NET test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing .NET test server for {self.platform}")
        publish_dir = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net9.0-ios"
            / "ios-arm64"
            / "testserver.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_ios.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the .NET test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent / "testserver.app")
        path.unlink()


@TestServer.register("dotnet_android")
class DotnetTestServer_Android(DotnetTestServer):
    """
    A class for managing .NET test servers on Android.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        """
        Get the platform name.

        Returns:
            str: The platform name.
        """
        return "dotnet_android"

    @property
    def dotnet_framework(self) -> str:
        """
        Get the .NET framework version.

        Returns:
            str: The .NET framework version.
        """
        return "net9.0-android"

    @property
    def publish(self) -> bool:
        """
        Determine if the test server should be published.  Some platforms don't have the necessary artifacts otherwise.

        Returns:
            bool: True if the test server should be published, False otherwise.
        """
        return True

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the .NET test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = (
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
            / "net9.0-android"
            / "com.couchbase.dotnet.testserver-Signed.apk"
        )
        return AndroidBridge(
            str(path),
            "com.couchbase.dotnet.testserver",
        )

    def compress_package(self) -> str:
        """
        Compress the .NET test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing .NET test server for {self.platform}")
        apk_path = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net9.0-android"
            / "com.couchbase.dotnet.testserver-Signed.apk"
        )
        zip_path = apk_path.parents[5] / "testserver_android.apk"
        shutil.copy(apk_path, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the .NET test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        click.secho(
            "No uncompressing needed for Android test server package", fg="yellow"
        )


@TestServer.register("dotnet_windows")
class DotnetTestServer_Windows(DotnetTestServerCli):
    """
    A class for managing .NET test servers on Windows.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        """
        Get the platform name.

        Returns:
            str: The platform name.
        """
        return "dotnet_windows"

    @property
    def rid(self) -> str:
        """
        Get the runtime identifier.

        Returns:
            str: The runtime identifier.
        """
        return "win-x64"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_windows.zip"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the .NET test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
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
        """
        Compress the .NET test server package.

        Returns:
            str: The path to the compressed package.
        """
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

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the .NET test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent)
        path.unlink()


@TestServer.register("dotnet_macos")
class DotnetTestServer_macOS(DotnetTestServer):
    """
    A class for managing .NET test servers on macOS.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        """
        Get the platform name.

        Returns:
            str: The platform name.
        """
        return "dotnet_macos"

    @property
    def dotnet_framework(self) -> str:
        """
        Get the .NET framework version.

        Returns:
            str: The .NET framework version.
        """
        return "net9.0-maccatalyst"

    @property
    def publish(self) -> bool:
        """
        Determine if the test server should be published.  Some platforms don't have the necessary artifacts otherwise.

        Returns:
            bool: True if the test server should be published, False otherwise.
        """
        return False

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return (
            f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_macos.zip"
        )

    @property
    def _mac_arch(self) -> str:
        """Get the Mac architecture (arm64 for Apple Silicon, x64 for Intel)."""
        return "arm64" if platform.machine() == "arm64" else "x64"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the .NET test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net9.0-maccatalyst"
            / f"maccatalyst-{self._mac_arch}"
        )
        return macOSBridge(str(prefix / "testserver.app"))

    def compress_package(self) -> str:
        """
        Compress the .NET test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing .NET test server for {self.platform}")
        publish_dir = (
            DOTNET_TEST_SERVER_DIR
            / "testserver"
            / "bin"
            / "Release"
            / "net9.0-maccatalyst"
            / f"maccatalyst-{self._mac_arch}"
            / "testserver.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_macos.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the .NET test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent / "testserver.app")
        path.unlink()
