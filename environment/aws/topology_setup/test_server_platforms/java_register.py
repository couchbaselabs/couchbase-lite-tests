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
    create_bridge(self, **kwargs) -> PlatformBridge:
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
import shutil
import subprocess
import zipfile
from abc import abstractmethod
from pathlib import Path

import click
import psutil
import requests

from environment.aws.common.io import download_progress_bar, unzip_directory
from environment.aws.common.output import header
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
            click.secho(
                f"Support libraries already exist in {supportlib_dir}", fg="yellow"
            )
            return

        download_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-java/{version_parts[0]}/{version_parts[1]}/couchbase-lite-java-linux-supportlibs-{cbl_version}.zip"
        try:
            click.echo(f"Downloading support libraries from {download_url}")
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            download_progress_bar(
                response, JAK_TEST_SERVER_DIR / variant / "support.zip"
            )
            unzip_directory(
                JAK_TEST_SERVER_DIR / variant / "support.zip", supportlib_dir
            )
            (JAK_TEST_SERVER_DIR / variant / "support.zip").unlink()

            click.echo(
                f"Support libraries downloaded and extracted to {supportlib_dir}"
            )
        except requests.RequestException as e:
            click.secho(f"Failed to download support libraries: {e}", fg="red")
            raise
        except zipfile.BadZipFile as e:
            click.secho(f"Failed to extract support libraries: {e}", fg="red")
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
    def __init__(self, path: str, cbl_version: str):
        self.__cbl_version = cbl_version
        if not (JAK_TEST_SERVER_DIR / "version.txt").exists():
            raise ValueError("Server version.txt not found")

        self.__jar_path = path

    def install(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        self._download_support_libs(self.__cbl_version, "desktop")

    def uninstall(self, location: str) -> None:
        pass

    def _get_ip(self, location) -> str | None:
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

        info_dir = Path(self.__jar_path).parent
        log_file = open(info_dir / "server.log", "w")
        process = subprocess.Popen(
            args,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        click.echo(f"Started {self.__jar_path} with PID {process.pid}")
        with open(info_dir / "server.pid", "w") as pid_file:
            pid_file.write(str(process.pid))

    def stop(self, location):
        if location != "localhost":
            raise ValueError("JarBridge only supports running on localhost")

        info_dir = Path(self.__jar_path).parent
        with open(info_dir / "server.pid") as pid_file:
            pid = int(pid_file.read())
            psutil.Process(pid).kill()


class JettyBridge(JavaBridge):
    def __init__(self, cbl_version: str):
        super().__init__()

        self.__cbl_version = cbl_version
        self.__gradle_path = JAK_TEST_SERVER_DIR / "webservice" / "gradlew"
        if platform.system() == "Windows":
            self.__gradle_path = self.__gradle_path.with_suffix(".bat")

    def install(self, location: str) -> None:
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        self._download_support_libs(self.__cbl_version, "webservice")

    def uninstall(self, location: str) -> None:
        pass

    def _get_ip(self, location) -> str | None:
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
            "-PdatasetVersion=3.2",
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
        click.echo(f"Started web service with PID {process.pid}")

    def stop(self, location: str) -> None:
        self._stop(location, True)

    def _stop(self, location: str, check_result: bool) -> None:
        if location != "localhost":
            raise ValueError("JettyBridge only supports running on localhost")

        args = [
            str(self.__gradle_path),
            "appStop",
            f"-PcblVersion={self.__cbl_version}",
            "-PdatasetVersion=3.2",
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
        gradle_path = JAK_TEST_SERVER_DIR / self.test_server_path / "gradlew"
        if platform.system() == "Windows":
            gradle_path = gradle_path.with_suffix(".bat")

        args = [
            str(gradle_path.resolve()),
            self.__gradle_target,
            f"-PcblVersion={self.version}",
            "-PdatasetVersion=3.2",
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
    def product(self) -> str:
        return "couchbase-lite-android"

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
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def create_bridge(self, **kwargs) -> PlatformBridge:
        """
        Create a bridge for the Android test server to be able to install, run, etc.

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
            else JAK_TEST_SERVER_DIR
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
        Compress the Android test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing C test server for {self.platform}")
        apk_path = (
            JAK_TEST_SERVER_DIR
            / self.test_server_path
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
        Uncompress the Android test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        click.secho(
            "No uncompressing needed for Android test server package", fg="yellow"
        )


class JAKTestServer_NonAndroid(JAKTestServer):
    def __init__(self, version: str, jar_name: str):
        super().__init__(version)
        self.__jar_name = jar_name
        with open(JAK_TEST_SERVER_DIR / "version.txt") as f:
            self._server_version = f.read().strip()

    @property
    def platform(self) -> str:
        return f"jak_{self.__jar_name.lower()}"

    @property
    def product(self) -> str:
        return "couchbase-lite-java"

    @property
    def test_server_path(self) -> str:
        return self.__jar_name.lower()

    @property
    def latestbuilds_path(self) -> str:
        """
        Get the path for the package on the latestbuilds server.

        Returns:
            str: The path for the latest builds.
        """
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/CBLTestServer-Java-{self.__jar_name}.jar"

    def compress_package(self):
        """
        Compress the Java test server package.

        Returns:
            str: The path to the compressed package.
        """
        header(f"Compressing test server for {self.platform}")

        jar_path = (
            JAK_TEST_SERVER_DIR
            / self.test_server_path
            / "app"
            / "build"
            / "libs"
            / f"CBLTestServer-Java-{self.__jar_name}-{self._server_version}_{self.version}.jar"
        )

        # The server version is not going to be known when downloading from latestbuilds,
        # and the CBL version will be built into the path on latestbuilds, so remove both
        copy_path = jar_path.parents[5] / f"CBLTestServer-Java-{self.__jar_name}.jar"
        shutil.copy(jar_path, copy_path)
        return str(copy_path)

    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the C test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        click.secho(
            f"No uncompressing needed for {self.__jar_name} server package", fg="yellow"
        )


@TestServer.register("jak_desktop")
class JAKTestServer_Desktop(JAKTestServer_NonAndroid):
    def __init__(self, version: str):
        super().__init__(version, "Desktop")

    def create_bridge(self, **kwargs):
        jar_path = (
            str(
                TEST_SERVER_DIR
                / "downloaded"
                / self.platform
                / self.version
                / "CBLTestServer-Java-Desktop.jar"
            )
            if self._downloaded
            else str(
                JAK_TEST_SERVER_DIR
                / "desktop"
                / "app"
                / "build"
                / "libs"
                / f"CBLTestServer-Java-Desktop-{self._server_version}_{self.version}.jar"
            )
        )
        return JarBridge(jar_path, self.version)


@TestServer.register("jak_webservice")
class JAKTestServer_WebService(JAKTestServer_NonAndroid):
    def __init__(self, version: str):
        super().__init__(version, "WebService")

    def create_bridge(self, **kwargs):
        if not self._downloaded and not kwargs.get("downloaded", False):
            return JettyBridge(self.version)

        return JarBridge(
            str(
                TEST_SERVER_DIR
                / "downloaded"
                / self.platform
                / self.version
                / "CBLTestServer-Java-WebService.jar"
            ),
            self.version,
        )
