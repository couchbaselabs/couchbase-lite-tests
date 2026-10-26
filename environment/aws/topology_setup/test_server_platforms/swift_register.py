"""
This module provides classes for managing Swift test servers on iOS and macOS
It includes functions for building, compressing, and creating bridges for the test servers.

Classes:
    SwiftTestServer: A base class for Swift test servers.
    SwiftTestServer_iOS: A class for managing Swift test servers on iOS
    SwiftTestServer_iOSSimulator: A class for managing Swift test servers on an iOS simulator
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
    uncompress_package(self, path: Path) -> None:
        Uncompress the Swift test server package.
"""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.cbl_library_downloader import CBLLibraryDownloader
from environment.aws.topology_setup.test_server import (
    DOWNLOADED_TEST_SERVER_DIR,
    TEST_SERVER_DIR,
    TestServer,
)

from .ios_bridge import iOSBridge
from .ios_simulator_bridge import iOSSimulatorBridge
from .platform_bridge import PlatformBridge

SWIFT_TEST_SERVER_DIR = TEST_SERVER_DIR / "ios"
BUILD_DEVICE_DIR = SWIFT_TEST_SERVER_DIR / "build_device"
BUILD_SIMULATOR_DIR = SWIFT_TEST_SERVER_DIR / "build_simulator"
DOWNLOAD_DIR = SWIFT_TEST_SERVER_DIR / "downloaded"
FRAMEWORKS_DIR = SWIFT_TEST_SERVER_DIR / "Frameworks"
IOS_APP_ID = "com.couchbase.ios.testserver"

SCRIPT_DIR = Path(__file__).resolve().parent


class SwiftTestServer(TestServer):
    """
    A base class for Swift test servers.

    Attributes:
        version (str): The version of the test server.
    """

    product = "couchbase-lite-ios"

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-swift_xc_enterprise_{version}.zip"

    def _download_cbl(self) -> None:
        """
        Download the CBL library to the Frameworks directory
        """
        header(f"Downloading CBL library {self.version}")
        version_parts = self.version.split("-")
        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)
        if self._check_downloaded(FRAMEWORKS_DIR):
            header(f"CBL library {self.version} already downloaded")
            return

        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            self.product,
            f"{self.cbl_filename(self.version)}",
            version_parts[0],
            int(version_parts[1]) if len(version_parts) > 1 else 0,
        )
        downloader.download(download_file)
        shutil.rmtree(FRAMEWORKS_DIR / "CouchbaseLiteSwift.xcframework", ignore_errors=True)
        unzip_directory(download_file, FRAMEWORKS_DIR)
        download_file.unlink()
        self._mark_downloaded(FRAMEWORKS_DIR)


@TestServer.register
class SwiftTestServer_iOS(SwiftTestServer):
    """
    A class for managing Swift test servers on iOS.

    Attributes:
        version (str): The version of the test server.
    """

    platform = "swift_ios"
    _sdk = "iphoneos"
    _build_dir = BUILD_DEVICE_DIR
    _package_name = "testserver_ios.zip"
    _bridge_type: Callable[[str, str], PlatformBridge] = iOSBridge

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        return self.artifact_path(self._package_name)

    @property
    def _app_path(self) -> Path:
        return self._build_dir / "Build" / "Products" / f"Release-{self._sdk}" / "TestServer-iOS.app"

    def build(self) -> None:
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
            self._sdk,
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(self._build_dir),
            "-allowProvisioningUpdates",
        ]

        if shutil.which("xcpretty") is None:
            if subprocess.run(xcodebuild_cmd, env=env, cwd=SWIFT_TEST_SERVER_DIR).returncode != 0:
                raise RuntimeError("Build failed")
            return

        with subprocess.Popen(
            xcodebuild_cmd,
            env=env,
            cwd=SWIFT_TEST_SERVER_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as xcodebuild_proc:
            assert xcodebuild_proc.stdout is not None

            with subprocess.Popen(
                ["xcpretty"],
                stdin=xcodebuild_proc.stdout,
                env=env,
            ) as xcpretty_proc:
                xcodebuild_proc.stdout.close()

                xcpretty_rc = xcpretty_proc.wait()
                xcodebuild_rc = xcodebuild_proc.wait()

        if xcodebuild_rc != 0 or xcpretty_rc != 0:
            raise RuntimeError("Build failed")

    def create_bridge(self, **kwargs: Any) -> PlatformBridge:
        """
        Create a bridge for the Swift test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = (
            DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version / "TestServer-iOS.app"
            if self._downloaded
            else self._app_path
        )
        return self._bridge_type(str(path), IOS_APP_ID)

    def compress_package(self) -> str:
        """
        Compress the Swift test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing Swift test server for {self._sdk}")
        publish_dir = self._app_path
        zip_path = publish_dir.parents[5] / self._package_name
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


@TestServer.register
class SwiftTestServer_iOSSimulator(SwiftTestServer_iOS):
    """
    A class for managing Swift test servers on an iOS simulator of this Mac.

    Attributes:
        version (str): The version of the test server.
    """

    platform = "swift_ios_simulator"
    published = False
    _sdk = "iphonesimulator"
    _build_dir = BUILD_SIMULATOR_DIR
    _package_name = "testserver_ios_simulator.zip"
    _bridge_type = iOSSimulatorBridge
