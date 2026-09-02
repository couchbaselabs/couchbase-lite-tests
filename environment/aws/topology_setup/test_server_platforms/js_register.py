import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
import psutil

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import (
    DOWNLOADED_TEST_SERVER_DIR,
    TEST_SERVER_DIR,
    TestServer,
)
from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

JS_TEST_SERVER_DIR = TEST_SERVER_DIR / "javascript"
ZIP_FOLDER_NAME = "compressed"
ZIP_DIR = JS_TEST_SERVER_DIR / ZIP_FOLDER_NAME
SCRIPT_DIR = Path(__file__).resolve().parent
PID_FILENAME = "server.pid"
LOG_FILENAME = "server.log"


class JavascriptBridge(PlatformBridge):
    def __init__(self, working_dir: str) -> None:
        """
        Initialize the JavascriptBridge with the working directory containing the site files
        """
        self.__working_dir = Path(working_dir)
        self.__pid_file = self.__working_dir / PID_FILENAME

    def validate(self, location: str) -> None:
        """
        Validate that the Javascript is accessible.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        click.echo("No validation needed for Javascript")

    def install(self, location: str) -> None:
        """
        Install the Javascript on the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        if location == "localhost":
            click.echo("No action needed for installing Javascript locally")
            return

    def run(self, location: str) -> None:
        """
        Run the Javascript on the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        header("Running bun run dev")

        log_file = self.__working_dir / LOG_FILENAME
        with open(log_file, "w") as log_fd:
            process = subprocess.Popen(
                ["bun", "run", "dev"],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=log_fd,
                cwd=self.__working_dir,
            )
        self.__pid_file.write_text(str(process.pid))
        click.echo(f"Started bun with PID {process.pid}")

    def stop(self, location: str) -> None:
        """
        Stop the Javascript on the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        header("Stopping test server")
        stopped = False
        for proc in self.__dev_server_processes():
            # Terminating the launcher leaves the node process running vite behind,
            # so take the children down first.
            for child in proc.children(recursive=True):
                self.__terminate(child)
            self.__terminate(proc)
            stopped = True

        self.__pid_file.unlink(missing_ok=True)
        if not stopped:
            click.secho("No running JS test server found to stop", fg="yellow")

    def __dev_server_processes(self) -> Iterator[psutil.Process]:
        """
        Yield the launcher process recorded in the pid file, or, if that is gone, any
        vite process running out of this bridge's working directory.
        """
        if self.__pid_file.exists():
            try:
                yield psutil.Process(int(self.__pid_file.read_text().strip()))
                return
            except (ValueError, psutil.NoSuchProcess):
                click.secho(f"Stale pid in {self.__pid_file}, searching for vite instead", fg="yellow")

        for proc in psutil.process_iter(["cmdline"]):
            cmdline = proc.info["cmdline"] or []
            if not any("vite" in arg for arg in cmdline):
                continue
            try:
                if Path(proc.cwd()) == self.__working_dir:
                    yield proc
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

    @staticmethod
    def __terminate(proc: psutil.Process) -> None:
        try:
            proc.terminate()
            click.secho(f"Stopped PID {proc.pid}", fg="green")
        except psutil.NoSuchProcess:
            pass

    def uninstall(self, location: str) -> None:
        """
        Uninstall the Javascript from the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        click.echo("No action needed for uninstalling Javascript")

    def _get_ip(self, location: str) -> str | None:
        """
        Retrieve the IP address of the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").

        Returns:
            str: The IP address of the location.
        """
        return location


@TestServer.register("js")
class JavascriptTestServer(TestServer):
    """
    A class for running JS servers

    Attributes:
        version (str): The version of the test server.
    """

    def __init__(self, version: str) -> None:
        super().__init__(version)

    @property
    def product(self) -> str:
        return "couchbase-lite-js"

    @property
    def platform(self) -> str:
        return "js"

    @property
    def latestbuilds_path(self) -> str:
        return self.artifact_path("testserver.zip")

    def build(self) -> None:
        header(f"Installing CBL JS and dependencies for version {self.version}")
        click.echo("Installing CBL")
        working_dir = DOWNLOADED_TEST_SERVER_DIR / "js" / self.version if self._downloaded else JS_TEST_SERVER_DIR

        install_args = ["bun", "install", f"@couchbase/lite-js@{self.version}"]
        if not self.is_release:
            # Prerelease builds only exist on the internal proget npm feed; release
            # versions are published to the default (public) npm registry.
            install_args += ["--registry", "https://proget.sc.couchbase.com/npm/cbl-npm/"]

        subprocess.run(
            install_args,
            check=True,
            cwd=working_dir,
        )
        click.echo("Installing dependencies")
        subprocess.run(["bun", "install"], check=True, cwd=working_dir)

    def compress_package(self) -> str:
        header(f"Compressing JS test server for {self.platform}")
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = ZIP_DIR / "testserver.zip"
        zip_directory(
            JS_TEST_SERVER_DIR,
            zip_path,
            excludes=[f"{ZIP_FOLDER_NAME}/**", ".gitignore", "bun.lock*", PID_FILENAME, LOG_FILENAME],
        )
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        unzip_directory(path, path.parent)
        path.unlink()

    def create_bridge(self, **kwargs: Any) -> PlatformBridge:
        working_dir = DOWNLOADED_TEST_SERVER_DIR / "js" / self.version if self._downloaded else JS_TEST_SERVER_DIR

        if self._downloaded:
            # Downloaded server needs to be setup like the built one
            self.build()

        return JavascriptBridge(str(working_dir))
