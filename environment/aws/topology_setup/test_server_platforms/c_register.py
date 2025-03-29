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

from abc import abstractmethod
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from typing import cast

from environment.aws.common.io import unzip_directory
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
IOS_VENDOR_DIR = C_TEST_SERVER_DIR / "platforms" / "ios" / "Vendor"

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

    def _copy_with_symlink_preservation(self, src: Path, dest: Path) -> None:
        if src.is_symlink():
            # Get the target of the symlink
            target = os.readlink(src)
            # Create the symlink at the destination
            os.symlink(target, dest)
        else:
            # Copy the file normally
            shutil.copy2(src, dest)

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

        DOWNLOAD_DIR.mkdir(0o755, exist_ok=True)
        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-c",
            self.cbl_filename(self.version),
            version_parts[0],
            build,
        )
        downloader.download(download_file)
        unzip_directory(download_file, LIB_DIR)
        (LIB_DIR / f"libcblite-{version_parts[0]}").rename(LIB_DIR / "libcblite")

     def build(self) -> None:
        """
        Build the C test server.
        """
        shutil.rmtree(LIB_DIR, ignore_errors=True)
        self._download_cbl()
        header("Building C test server")
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        BUILD_DIR.mkdir(0o755, exist_ok=True)
        subprocess.run(["cmake", "-DCMAKE_BUILD_TYPE=Release", ".."], cwd=BUILD_DIR, check=True)

        header("Installing C test server")
        subprocess.run(["cmake", "--build", ".", "--target", "install", "-j"], cwd=BUILD_DIR, check=True)
        

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
        download_file = DOWNLOAD_DIR / "framework.zip"
        downloader = CBLLibraryDownloader(
            "couchbase-lite-c",
            self.cbl_filename(self.version),
            version_parts[0],
            build,
        )
        #downloader.download(download_file)
        #shutil.rmtree(IOS_FRAMEWORKS_DIR / "CouchbaseLite.xcframework", ignore_errors=True)
        #unzip_directory(download_file, IOS_FRAMEWORKS_DIR)

        #shutil.rmtree(IOS_VENDOR_DIR / "cmake", ignore_errors=True)
        #(IOS_VENDOR_DIR / "cmake").mkdir(0o755)
        subprocess.run(["cmake", "-DCMAKE_BUILD_TYPE=Release", "../../../../vendor"], cwd=IOS_VENDOR_DIR / "cmake", check=True)

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

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        path = (
            IOS_BUILD_DIR
            / "Build"
            / "Products"
            / "Release-iphoneos"
            / "TestServer.app"
        )

        return iOSBridge(
            str(path),
            False,
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

    def build(self) -> None:
        """
        Build the C test server.
        """
        super().build()
        libcblite_lib_dir = LIB_DIR / "libcblite" / "lib"
        output_bin_dir = BUILD_DIR / "out" / "bin"
        for dylib_file in libcblite_lib_dir.glob("libcblite*.dylib"):
            self._copy_with_symlink_preservation(dylib_file, output_bin_dir / dylib_file.name)

    def create_bridge(self) -> PlatformBridge:
        """
        Create a bridge for the C test server to be able to install, run, etc.

        Returns:
            PlatformBridge: The platform bridge.
        """
        return ExeBridge(
            BUILD_DIR / "out" / "bin" / "testserver",
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
