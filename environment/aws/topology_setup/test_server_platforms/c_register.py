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
    create_bridge(self, **kwargs) -> PlatformBridge:
        Create a bridge for the C test server to be able to install, run, etc.
    latestbuilds_path(self) -> str:
        Get the path for the package on the latestbuilds server.
    platform(self) -> str:
        Get the platform name.
    uncompress_package(self, path: Path) -> None:
        Uncompress the C test server package.
"""

import os
import platform
import shutil
import subprocess
from abc import abstractmethod
from io import BytesIO
from pathlib import Path
from typing import cast

import click

from environment.aws.common.io import (
    tar_directory,
    untar_directory,
    unzip_directory,
    zip_directory,
)
from environment.aws.common.output import header
from environment.aws.topology_setup.cbl_library_downloader import CBLLibraryDownloader
from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .exe_bridge import ExeBridge
from .ios_bridge import iOSBridge
from .platform_bridge import PlatformBridge

C_TEST_SERVER_DIR = TEST_SERVER_DIR / "c"
DOWNLOAD_DIR = C_TEST_SERVER_DIR / "download"
BUILD_DIR = C_TEST_SERVER_DIR / "build"
IOS_BUILD_DIR = C_TEST_SERVER_DIR / "build_device"
SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = C_TEST_SERVER_DIR / "lib"
IOS_FRAMEWORKS_DIR = C_TEST_SERVER_DIR / "platforms" / "ios" / "Frameworks"
IOS_VENDOR_DIR = C_TEST_SERVER_DIR / "platforms" / "ios" / "vendor"


class CTestServer(TestServer):
    """
    A base class for C test servers.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    @abstractmethod
    def cbl_filename(self, version: str) -> str:
        pass


class CTestServer_Desktop(CTestServer):
    def _download_cbl(self) -> None:
        """
        Download the CBL library for the build
        """
        header(f"Downloading CBL library {self.version}")
        build = 0
        version_parts = self.version.split("-")
        if len(version_parts) > 1:
            build = int(version_parts[1])

        filename = self.cbl_filename(self.version)
        ext = ".tar.gz" if filename.endswith(".tar.gz") else ".zip"
        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)

        if self._check_downloaded(LIB_DIR):
            header(f"CBL library {self.version} already downloaded")
            return

        download_file = DOWNLOAD_DIR / f"framework.{ext}"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-c",
            self.cbl_filename(self.version),
            version_parts[0],
            build,
        )
        downloader.download(download_file)
        if ext == ".zip":
            unzip_directory(download_file, LIB_DIR)
        else:
            untar_directory(download_file, LIB_DIR)
        self._mark_downloaded(LIB_DIR)

    def build(self) -> None:
        """
        Build the C test server.
        """
        shutil.rmtree(LIB_DIR, ignore_errors=True)
        self._download_cbl()
        header("Building C test server")
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        BUILD_DIR.mkdir(0o755, exist_ok=True)
        cbl_version = self.version.split("-")[0]
        subprocess.run(
            [
                "cmake",
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCBL_VERSION={cbl_version}",
                "..",
            ],
            cwd=BUILD_DIR,
            check=True,
        )

        header("Installing C test server")
        args = [
            "cmake",
            "--build",
            ".",
            "--target",
            "install",
            "--parallel",
            str(os.cpu_count()),
        ]
        if platform.system() == "Windows":
            args.extend(["--config", "Release"])

        subprocess.run(
            args,
            cwd=BUILD_DIR,
            check=True,
        )

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent)
        path.unlink()


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

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-c-enterprise-{version}-ios.zip"

    def _download_cbl(self):
        header(f"Downloading CBL library {self.version}")
        build = 0
        version_parts = self.version.split("-")
        if len(version_parts) > 1:
            build = int(version_parts[1])

        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)
        if self._check_downloaded(IOS_FRAMEWORKS_DIR):
            header(f"CBL library {self.version} already downloaded")
            return

        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-c",
            self.cbl_filename(self.version),
            version_parts[0],
            build,
        )
        downloader.download(download_file)
        shutil.rmtree(
            IOS_FRAMEWORKS_DIR / "CouchbaseLite.xcframework", ignore_errors=True
        )
        unzip_directory(download_file, IOS_FRAMEWORKS_DIR)

        shutil.rmtree(IOS_VENDOR_DIR / "cmake", ignore_errors=True)
        (IOS_VENDOR_DIR / "cmake").mkdir(0o755)
        subprocess.run(
            ["cmake", "-DCMAKE_BUILD_TYPE=Release", "../../../../vendor"],
            cwd=IOS_VENDOR_DIR / "cmake",
            check=True,
        )
        self._mark_downloaded(IOS_FRAMEWORKS_DIR)

    def build(self):
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
            str(IOS_BUILD_DIR),
            "-allowProvisioningUpdates",
        ]

        with subprocess.Popen(
            xcodebuild_cmd,
            env=env,
            cwd=C_TEST_SERVER_DIR / "platforms" / "ios",
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

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else IOS_BUILD_DIR / "Build" / "Products" / "Release-iphoneos"
        )

        return iOSBridge(
            str(prefix / "TestServer.app"),
            "com.couchbase.CBLTestServer",
        )

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing C test server for {self.platform}")
        publish_dir = (
            IOS_BUILD_DIR / "Build" / "Products" / "Release-iphoneos" / "TestServer.app"
        )
        zip_path = publish_dir.parents[5] / "testserver_ios.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        unzip_directory(path, path.parent / "testserver.app")
        path.unlink()


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

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-c-enterprise-{version}-android.zip"

    def _download_cbl(self):
        android_lib_dir = (
            C_TEST_SERVER_DIR
            / "platforms"
            / "android"
            / "app"
            / "src"
            / "main"
            / "cpp"
            / "lib"
        )
        header(f"Downloading CBL library {self.version}")
        build = 0
        version_parts = self.version.split("-")
        if len(version_parts) > 1:
            build = int(version_parts[1])

        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)
        if self._check_downloaded(android_lib_dir):
            header(f"CBL library {self.version} already downloaded")
            return

        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-c",
            self.cbl_filename(self.version),
            version_parts[0],
            build,
        )
        downloader.download(download_file)
        shutil.rmtree(android_lib_dir, ignore_errors=True)
        android_lib_dir.mkdir(0o755)
        unzip_directory(download_file, android_lib_dir)
        self._mark_downloaded(android_lib_dir)

    def build(self) -> None:
        """
        Build the C test server.
        """
        self._download_cbl()
        gradle_path = C_TEST_SERVER_DIR / "platforms" / "android" / "gradlew"
        if platform.system() == "Windows":
            gradle_path = gradle_path.with_suffix(".bat")

        args = [
            str(gradle_path.resolve()),
            "assembleRelease",
            "-PabiFilters=arm64-v8a",
            f"-PcblVersion={self.version.split('-')[0]}",
        ]
        if platform.system() == "Windows":
            args.append("--no-daemon")

        subprocess.run(args, cwd=gradle_path.parent, check=True)

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

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
            else C_TEST_SERVER_DIR
            / "platforms"
            / "android"
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "release"
            / "app-release.apk"
        )
        app_id = "com.couchbase.lite.testserver"

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
        header(f"Compressing C test server for {self.platform}")
        apk_path = (
            C_TEST_SERVER_DIR
            / "platforms"
            / "android"
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "release"
            / "app-release.apk"
        )
        zip_path = apk_path.parents[5] / "testserver_android.apk"
        shutil.copy(apk_path, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        click.secho(
            "No uncompressing needed for Android test server package", fg="yellow"
        )


@TestServer.register("c_windows")
class CTestServer_Windows(CTestServer_Desktop):
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

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-c-enterprise-{version}-windows-x86_64.zip"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else BUILD_DIR / "out" / "bin"
        )
        return ExeBridge(str(prefix / "testserver.exe"))

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        header("Compressing C test server for Windows")
        publish_dir = C_TEST_SERVER_DIR / "build" / "out" / "bin"
        zip_path = publish_dir.parents[5] / "testserver_windows.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)


@TestServer.register("c_macos")
class CTestServer_macOS(CTestServer_Desktop):
    """
    A class for managing C test servers on macOS.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version)

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-c-enterprise-{version}-macos.zip"

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

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else BUILD_DIR / "out" / "bin"
        )
        return ExeBridge(str(prefix / "testserver"))

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        header("Compressing C test server for macOS")
        publish_dir = C_TEST_SERVER_DIR / "build" / "out" / "bin"
        zip_path = publish_dir.parents[5] / "testserver_macos.zip"
        zip_directory(publish_dir, zip_path)
        return str(zip_path)


class CTestServer_Linux(CTestServer_Desktop):
    """
    A class for managing C test servers on Linux.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str, arch: str):
        super().__init__(version)
        self.__arch = arch

    @property
    def platform(self) -> str:
        """
        Get the platform name.

        Returns:
            str: The platform name.
        """
        return f"c_linux_{self.__arch}"

    def cbl_filename(self, version: str) -> str:
        return f"couchbase-lite-c-enterprise-{version}-linux-{self.__arch}.tar.gz"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-c/{version_parts[0]}/{version_parts[1]}/testserver_linux-{self.__arch}.tar.gz"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        prefix = (
            TEST_SERVER_DIR / "downloaded" / self.platform / self.version
            if self._downloaded
            else BUILD_DIR / "out" / "bin"
        )
        return ExeBridge(str(prefix / "testserver"))

    def compress_package(self) -> str:
        """
        Compress the C test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing C test server for {self.platform}")
        publish_dir = C_TEST_SERVER_DIR / "build" / "out" / "bin"

        tar_path = publish_dir.parents[5] / f"testserver_{self.platform}.tar.gz"
        tar_directory(publish_dir, tar_path)
        return str(tar_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        untar_directory(path, path.parent)
        path.unlink()


@TestServer.register("c_linux_x86_64")
class CTestServer_Linux_x86_64(CTestServer_Linux):
    """
    A class for managing C test servers on Linux x86_64.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version, "x86_64")
