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

import os
import platform
import subprocess
import zipfile
from abc import abstractmethod
from pathlib import Path

import psutil
import requests

from environment.aws.common.io import download_progress_bar, unzip_directory
from environment.aws.topology_setup.test_server import TEST_SERVER_DIR, TestServer

from .android_bridge import AndroidBridge
from .platform_bridge import PlatformBridge

JAK_TEST_SERVER_DIR = TEST_SERVER_DIR / "jak"
SCRIPT_DIR = Path(__file__).resolve().parent


class JavaBridge(PlatformBridge):
    def _download_support_libs(self, cbl_version: str, variant: str) -> None:
        if platform.system() != "Linux":
            return

        version_parts = cbl_version.split("-")
        supportlib_dir = JAK_TEST_SERVER_DIR / variant / "supportlib"
        supportlib_dir.mkdir(0o755, exist_ok=True)

        if (supportlib_dir / "libstdc++.so.6").exists():
            print(f"Support libraries already exist in {supportlib_dir}")
            return

        download_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/couchbase-lite-java-linux-supportlibs-{cbl_version}.zip"
        try:
            print(f"Downloading support libraries from {download_url}")
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            download_progress_bar(
                response, JAK_TEST_SERVER_DIR / variant / "support.zip"
            )
            unzip_directory(
                JAK_TEST_SERVER_DIR / variant / "support.zip", supportlib_dir
            )
            (JAK_TEST_SERVER_DIR / variant / "support.zip").unlink()

            print(f"Support libraries downloaded and extracted to {supportlib_dir}")
        except requests.RequestException as e:
            print(f"Failed to download support libraries: {e}")
            raise
        except zipfile.BadZipFile as e:
            print(f"Failed to extract support libraries: {e}")
            raise

    def _ensure_support_libs_in_path(self, variant: str) -> None:
        if platform.system() != "Linux":
            return

        supportlib_dir = (JAK_TEST_SERVER_DIR / variant / "supportlib").resolve()
        ld_lib_path = os.environ.get("LD_LIBRARY_PATH", "")
        if ld_lib_path == "":
            os.environ["LD_LIBRARY_PATH"] = str(supportlib_dir)
        elif str(supportlib_dir) not in ld_lib_path:
            os.environ["LD_LIBRARY_PATH"] = f"{supportlib_dir}:{ld_lib_path}"


class JarBridge(JavaBridge):
    def __init__(self, cbl_version: str):
        self.__cbl_version = cbl_version
        if not (JAK_TEST_SERVER_DIR / "version.txt").exists():
            raise ValueError("Server version.txt not found")

        with open(JAK_TEST_SERVER_DIR / "version.txt") as f:
            self.__server_version = f.read().strip()

        self.__jar_path = str(
            JAK_TEST_SERVER_DIR
            / "desktop"
            / "app"
            / "build"
            / "libs"
            / f"CBLTestServer-Java-Desktop-{self.__server_version}_{self.__cbl_version}.jar"
        )

    def install(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        self._download_support_libs(self.__cbl_version, "desktop")

    def uninstall(self, location: str) -> None:
        pass

    def get_ip(self, location):
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        return location

    def validate(self, location):
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

    def run(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        self._ensure_support_libs_in_path("desktop")
        args = ["java", "-jar", self.__jar_path, "server"]
        if platform.system() != "Windows":
            args.insert(0, "nohup")

        info_dir = JAK_TEST_SERVER_DIR / "desktop"
        log_file = open(info_dir / "server.log", "w")
        process = subprocess.Popen(
            args,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        print(f"Started {self.__jar_path} with PID {process.pid}")
        with open(info_dir / "server.pid", "w") as pid_file:
            pid_file.write(str(process.pid))

    def stop(self, location):
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        with open(JAK_TEST_SERVER_DIR / "desktop" / "server.pid") as pid_file:
            pid = int(pid_file.read())
            psutil.Process(pid).kill()


class JettyBridge(JavaBridge):
    def __init__(self, cbl_version: str, dataset_version: str):
        super().__init__()

        self.__cbl_version = cbl_version
        self.__dataset_version = dataset_version
        self.__gradle_path = JAK_TEST_SERVER_DIR / "webservice" / "gradlew"
        if platform.system() == "Windows":
            self.__gradle_path = self.__gradle_path.with_suffix(".bat")

    def install(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        self._download_support_libs(self.__cbl_version, "webservice")

    def uninstall(self, location: str) -> None:
        pass

    def get_ip(self, location):
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        return location

    def validate(self, location):
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

    def run(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        self._ensure_support_libs_in_path("webservice")
        self._stop(location, False)
        args = [
            str(self.__gradle_path),
            "jettyStart",
            f"-PcblVersion={self.__cbl_version}",
            f"-PdatasetVersion={self.__dataset_version}",
        ]
        if platform.system() != "Windows":
            args.insert(0, "nohup")

        info_dir = JAK_TEST_SERVER_DIR / "webservice"
        log_file = open(info_dir / "server.log", "w")
        process = subprocess.Popen(
            args,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=self.__gradle_path.parent,
        )
        print(f"Started web service with PID {process.pid}")

    def stop(self, location: str) -> None:
        self._stop(location, True)

    def _stop(self, location: str, check_result: bool) -> None:
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        args = [
            str(self.__gradle_path),
            "appStop",
            f"-PcblVersion={self.__cbl_version}",
            f"-PdatasetVersion={self.__dataset_version}",
        ]
        subprocess.run(
            args, cwd=self.__gradle_path.parent, check=check_result, capture_output=True
        )


class JAKTestServer(TestServer):
    """
    A base class for JAK test servers.

    Attributes:
        version (str): The version of the test server.
    """

    @property
    @abstractmethod
    def test_server_path(self) -> str:
        pass

    def __init__(self, version: str, gradle_target: str = "jar"):
        super().__init__(version)
        self.__gradle_target = gradle_target

    def build(self) -> None:
        """
        Build the JAK test server.
        """
        if self.dataset_version is None:
            raise RuntimeError("dataset_version must be set before building")

        gradle_path = JAK_TEST_SERVER_DIR / self.test_server_path / "gradlew"
        if platform.system() == "Windows":
            gradle_path = gradle_path.with_suffix(".bat")

        args = [
            str(gradle_path.resolve()),
            self.__gradle_target,
            f"-PcblVersion={self.version}",
            f"-PdatasetVersion={self.dataset_version}",
        ]
        if platform.system() == "Windows":
            args.append("--no-daemon")

        subprocess.run(args, cwd=gradle_path.parent, check=True)


@TestServer.register("jak_android")
class JAKTestServer_Android(JAKTestServer):
    """
    A class for managing JAK test servers on Android.

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str):
        super().__init__(version, "assembleRelease")

    @property
    def test_server_path(self) -> str:
        return "android"

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
        path = (
            JAK_TEST_SERVER_DIR
            / self.test_server_path
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "release"
            / "app-release.apk"
        )
        app_id = "com.couchbase.lite.android.mobiletest"

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


class JAKTestServer_Desktop(JAKTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def test_server_path(self) -> str:
        return "desktop"

    def create_bridge(self):
        return JarBridge(self.version)


class JAKTestServer_WebService(JAKTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def test_server_path(self) -> str:
        return "webservice"

    def create_bridge(self):
        if self.dataset_version is None:
            raise RuntimeError("dataset_version must be set before creating bridge")

        return JettyBridge(self.version, self.dataset_version)


@TestServer.register("jak_windows_desktop")
class JAKTestServer_WindowsDesktop(JAKTestServer_Desktop):
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
        return "jak_windows_desktop"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_windows_desktop.zip"

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


@TestServer.register("jak_windows_webservice")
class JAKTestServer_WindowsWebService(JAKTestServer_WebService):
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
        return "jak_windows_webservice"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_windows_webservice.zip"

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


@TestServer.register("jak_macos_webservice")
class JAKTestServer_macOSWebService(JAKTestServer_WebService):
    """
    A class for managing Java test servers on macOS.

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
        return "jak_macos_webservice"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_macos_webservice.zip"

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


@TestServer.register("jak_macos_desktop")
class JAKTestServer_macOSDesktop(JAKTestServer_Desktop):
    """
    A class for managing Java test servers on macOS.

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
        return "jak_macos_desktop"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_macos_desktop.zip"

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


@TestServer.register("jak_linux_desktop")
class JAKTestServer_LinuxDesktop(JAKTestServer_Desktop):
    """
    A class for managing Java test servers on Linux.

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
        return "jak_linux_desktop"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_linux_desktop.tar.gz"

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


@TestServer.register("jak_linux_webservice")
class JAKTestServer_LinuxWebService(JAKTestServer_WebService):
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
        return "jak_linux_webservice"

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/testserver_linux_webservice.tar.gz"

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
