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
    create_bridge(self, **kwargs) -> PlatformBridge:
        Create a bridge for the Swift test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    uncompress_package(self, path: Path) -> None:
        Uncompress the Swift test server package.
"""

import os
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from typing import cast

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.cbl_library_downloader import CBLLibraryDownloader
from environment.aws.topology_setup.test_server import (
    DOWNLOADED_TEST_SERVER_DIR,
    TEST_SERVER_DIR,
    TestServer,
    copy_dataset,
)

from .ios_bridge import iOSBridge
from .platform_bridge import PlatformBridge

SWIFT_TEST_SERVER_DIR = TEST_SERVER_DIR / "ios"
BUILD_DEVICE_DIR = SWIFT_TEST_SERVER_DIR / "build_device"
DOWNLOAD_DIR = SWIFT_TEST_SERVER_DIR / "downloaded"
FRAMEWORKS_DIR = SWIFT_TEST_SERVER_DIR / "Frameworks"

SCRIPT_DIR = Path(__file__).resolve().parent


class SwiftTestServer(TestServer):
    """
    A base class for Swift test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-swift_xc_enterprise_{version}.zip"

    def _download_cbl(self) -> None:
        """
        Download the CBL library to the Frameworks directory
        """
        header(f"Downloading CBL library {self.version}")
        version_parts = self.version.split("-")
        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)
        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-ios",
            f"{self.cbl_filename(self.version)}",
            version_parts[0],
            int(version_parts[1]) if len(version_parts) > 1 else 0,
        )
        downloader.download(download_file)
        shutil.rmtree(
            FRAMEWORKS_DIR / "CouchbaseLiteSwift.xcframework", ignore_errors=True
        )
        unzip_directory(download_file, FRAMEWORKS_DIR)
        download_file.unlink()

    def _copy_dataset(self) -> None:
        dest_dir = SWIFT_TEST_SERVER_DIR / "Assets"
        copy_dataset(dest_dir)


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
        version_parts = self.version.split("-")
        return f"couchbase-lite-ios/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"

    def build(self) -> None:
        self._copy_dataset()
        self._download_cbl()
        header("Building")
        env = os.environ.copy()
        env["LANG"] = "en_US.UTF-8"
        env["LC_ALL"] = "en_US.UTF-8"

        xcodebuild_cmd = [
            "xcodebuild",
            "-scheme",
            "TestServer",
            "-sdk",
            "iphoneos",
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(BUILD_DEVICE_DIR),
            "-allowProvisioningUpdates",
        ]

        with subprocess.Popen(
            xcodebuild_cmd,
            env=env,
            cwd=SWIFT_TEST_SERVER_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as xcodebuild_proc:
            with subprocess.Popen(
                ["xcpretty"], stdin=xcodebuild_proc.stdout, env=env
            ) as xcpretty_proc:
                # Close the stdout of the first process to allow it to receive a SIGPIPE if the second process exits
                cast(BytesIO, xcodebuild_proc.stdout).close()

                xcpretty_proc.wait()
                if xcpretty_proc.returncode != 0:
                    raise RuntimeError("Build failed")

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the Swift test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        location = (
            DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version
            if self._downloaded
            else BUILD_DEVICE_DIR / "Build" / "Products" / "Release-iphoneos"
        )
        path = location / "TestServer-iOS.app"
        return iOSBridge(
            str(path),
            "com.couchbase.ios.testserver",
        )

    def compress_package(self) -> str:
        """
        Compress the Swift test server package.

        Returns:
            str: The path to the compressed package.
        """
        header("Compressing Swift test server for iOS")
        publish_dir = (
            BUILD_DEVICE_DIR
            / "Build"
            / "Products"
            / "Release-iphoneos"
            / "TestServer-iOS.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_ios.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the Swift test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent / "TestServer-iOS.app")
        path.unlink()
