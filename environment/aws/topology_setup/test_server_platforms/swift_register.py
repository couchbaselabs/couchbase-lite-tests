"""
This module provides classes for managing Swift test servers on iOS and macOS
It includes functions for building, compressing, and creating bridges for the test servers.

Classes:
    SwiftTestServer: A base class for Swift test servers.
    SwiftTestServer_iOS: A class for managing Swift test servers on iOS
    SwiftTestServer_macOS: A class for managing Swift test servers on macOS.

Functions:
    build(self) -> None:
        Build the Swift test server.
    compress_package(self) -> str:
        Compress the Swift test server package.
    create_bridge(self) -> PlatformBridge:
        Create a bridge for the Swift test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    uncompress_package(self, path: Path) -> None:
        Uncompress the Swift test server package.
"""

from pathlib import Path

from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .ios_bridge import iOSBridge
from .macos_bridge import macOSBridge
from .platform_bridge import PlatformBridge

SWIFT_TEST_SERVER_DIR = TEST_SERVER_DIR / "ios"
SCRIPT_DIR = Path(__file__).resolve().parent


class SwiftTestServer(TestServer):
    """
    A base class for Swift test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    def build(self) -> None:
        """
        Build the Swift test server.
        """
        raise NotImplementedError("Please implement JSwiftAK build logic")


@TestServer.register("swift_ios")
class SwiftTestServer_iOS(SwiftTestServer):
    """
    A class for managing Swift test servers on iOS.

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
        return "swift_ios"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """

        # testserver_android.apk must match what is output in compress_package
        version_parts = self.version.split("-")
        return f"couchbase-lite-ios/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the Swift test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = ""
        if path == "":
            raise NotImplementedError(
                "Please choose the path to find either downloaded or built test server"
            )

        return iOSBridge(
            str(path),
            True,
        )

    def compress_package(self) -> str:
        """
        Compress the Swift test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Swift test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )


@TestServer.register("swift_macos")
class SwiftTestServer_macOS(SwiftTestServer):
    """
    A class for managing Swift test servers on Linux.

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
        return f"couchbase-lite-ios/{version_parts[0]}/{version_parts[1]}/testserver_macos.zip"

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the Swift test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = ""
        if path == "":
            raise NotImplementedError(
                "Please choose the path to find either downloaded or built test server"
            )

        return macOSBridge(
            str(path),
        )

    def compress_package(self) -> str:
        """
        Compress the Swift test server package.

        Returns:
            str: The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the compress logic for a built server"
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Swift test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        raise NotImplementedError(
            "Please implement the uncompress logic for a compressed server"
        )
