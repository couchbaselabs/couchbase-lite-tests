"""
This module provides classes for managing Java test servers on various platforms, including Windows, macOS, Linux, and Android.
It includes functions for building, compressing, and creating bridges for the test servers.

Classes:
    JAKTestServer: A base class for Java test servers.
    JAKTestServer_Android: A class for managing Java test servers on Android.
    JAKTestServer_Windows: A class for managing Java test servers on Windows.
    JAKTestServer_macOS: A class for managing Java test servers on macOS.
    JAKTestServer_Linux: A class for managing Java test servers on macOS.

Functions:
    build(self) -> None:
        Build the Java test server.
    compress_package(self) -> str:
        Compress the Java test server package.
    create_bridge(self) -> PlatformBridge:
        Create a bridge for the Java test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    uncompress_package(self, path: Path) -> None:
        Uncompress the Java test server package.
"""

from pathlib import Path

from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .platform_bridge import PlatformBridge

JAK_TEST_SERVER_DIR = TEST_SERVER_DIR / "jak"
SCRIPT_DIR = Path(__file__).resolve().parent


class JAKTestServer(TestServer):
    """
    A base class for JAK test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    def build(self) -> None:
        """
        Build the JAK test server.
        """
        raise NotImplementedError("Please implement JAK build logic")

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the Java test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        raise NotImplementedError(
            "Probably going to need something like GradleBridge here"
        )


@TestServer.register("jak_android")
class JAKTestServer_Android(JAKTestServer):
    """
    A class for managing JAK test servers on Android.

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
        return "jak_android"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """

        # testserver_android.apk must match what is output in compress_package
        version_parts = self.version.split("-")
        return f"couchbase-lite-android/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the Java test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = ""
        if path == "":
            raise NotImplementedError(
                "Please choose the directory to find either downloaded or built test server"
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
        Compress the Java test server package.

        Returns:
            str: The path to the compressed package.
        """

        # NOTE: It is ok to just rename to make sure that you have testserver_android.apk,
        # as .NET does
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Java test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )


@TestServer.register("jak_windows")
class DotnetTestServer_Windows(JAKTestServer):
    """
    A class for managing Java test servers on Windows.

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
        return "jak_windows"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_windows.zip"

    def compress_package(self) -> str:
        """
        Compress the Java test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Java test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )


@TestServer.register("jak_macos")
class JAKTestServer_macOS(JAKTestServer):
    """
    A class for managing Java test servers on macOS.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_macos.zip"

    def compress_package(self) -> str:
        """
        Compress the Java test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Java test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )


@TestServer.register("jak_linux")
class JAKTestServer_Linux(JAKTestServer):
    """
    A class for managing Java test servers on Linux.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_linux.tar.gz"

    def compress_package(self) -> str:
        """
        Compress the Java test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Java test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )
