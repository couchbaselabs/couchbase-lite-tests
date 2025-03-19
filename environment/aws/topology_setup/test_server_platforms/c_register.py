"""
This module provides classes for managing C test servers on various platforms, including Windows, macOS, iOS, and Android.
It includes functions for building, compressing, and creating bridges for the test servers.

Classes:
    CTestServer: A base class for C test servers.
    CTestServer_iOS: A class for managing C test servers on iOS.
    CTestServer_Android: A class for managing C test servers on Android.
    CTestServer_Windows: A class for managing C test servers on Windows.
    CTestServer_macOS: A class for managing C test servers on macOS.
    CTestServer_Linux: A class for managing C test servers on Linux.

Functions:
    build(self) -> None:
        Build the C test server.
    compress_package(self) -> str:
        Compress the C test server package.
    create_bridge(self) -> PlatformBridge:
        Create a bridge for the C test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    uncompress_package(self, path: Path) -> None:
        Uncompress the C test server package.
"""

from pathlib import Path

from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .exe_bridge import ExeBridge
from .ios_bridge import iOSBridge
from .platform_bridge import PlatformBridge

C_TEST_SERVER_DIR = TEST_SERVER_DIR / "c"
SCRIPT_DIR = Path(__file__).resolve().parent


class CTestServer(TestServer):
    """
    A base class for C test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    def build(self) -> None:
        """
        Build the C test server.
        """
        raise NotImplementedError("Please implement C build logic")


@TestServer.register("c_ios")
class CTestServer_iOS(CTestServer):
    """
    A class for managing C test servers on iOS.

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
        return "c_ios"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return (
            f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"
        )

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = Path("")
        if prefix == "":
            raise NotImplementedError(
                "Please choose a directory to either downloaded or built test server"
            )

        return iOSBridge(
            str(prefix / "testserver.app"),
            True,
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError("Please implement C compress_package logic")

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError("Please implement C uncompress_package logic")


@TestServer.register("c_android")
class CTestServer_Android(CTestServer):
    """
    A class for managing C test servers on Android.

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
        return "c_android"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = ""
        if path == "":
            raise NotImplementedError(
                "Please choose the path to find either downloaded or built test server"
            )

        app_id = ""
        if app_id == "":
            raise NotImplementedError("Please set the app id")

        return AndroidBridge(
            str(path),
            app_id,
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError("Please implement C compress_package logic")

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError("Please implement C uncompress_package logic")


@TestServer.register("c_windows")
class CTestServer_Windows(CTestServer):
    """
    A class for managing C test servers on Windows.

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
        return "c_windows"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_windows.zip"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = ""
        if prefix == "":
            raise NotImplementedError(
                "Please choose a directory to either downloaded or built test server"
            )

        exe_name = ""
        if exe_name == "":
            raise NotImplementedError("Please set the exe name")

        return ExeBridge(
            str(Path(prefix) / exe_name),
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError("Please implement C compress_package logic")

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError("Please implement C uncompress_package logic")


@TestServer.register("c_macos")
class CTestServer_macOS(CTestServer):
    """
    A class for managing C test servers on macOS.

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
        return "c_macos"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_macos.zip"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = Path("")
        if prefix == "":
            raise NotImplementedError(
                "Please choose a directory to either downloaded or built test server"
            )

        exe_name = ""
        if exe_name == "":
            raise NotImplementedError("Please set the exe name")

        return ExeBridge(
            str(Path(prefix) / exe_name),
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError("Please implement C compress_package logic")

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError("Please implement C uncompress_package logic")


@TestServer.register("c_linux")
class CTestServer_Linux(CTestServer):
    """
    A class for managing C test servers on Linux.

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
        return "c_linux"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserverlinux.tar.gz"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = ""
        if prefix == "":
            raise NotImplementedError(
                "Please choose a directory to either downloaded or built test server"
            )

        exe_name = ""
        if exe_name == "":
            raise NotImplementedError("Please set the exe name")

        return ExeBridge(
            str(Path(prefix) / exe_name),
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError("Please implement C compress_package logic")

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError("Please implement C uncompress_package logic")
