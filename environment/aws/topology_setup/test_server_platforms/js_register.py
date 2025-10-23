import platform
import subprocess
from pathlib import Path

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


class JavascriptBridge(PlatformBridge):
    def __init__(self, working_dir: str):
        """
        Initialize the JavascriptBridge with the working directory containing the site files
        """
        self.__working_dir = working_dir

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

        log_file = JS_TEST_SERVER_DIR / "server.log"
        log_fd = open(log_file, "w")
        process = subprocess.Popen(
            ["bun", "run", "dev"],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            cwd=self.__working_dir,
        )
        click.echo(f"Started bun with PID {process.pid}")

    def stop(self, location: str) -> None:
        """
        Stop the Javascript on the specified location.

        Args:
            location (str): The location of the Javascript (e.g., "localhost").
        """
        proc_name = "bun.exe" if platform.system() == "Windows" else "bun"
        header("Stopping test server")
        for proc in psutil.process_iter():
            if proc.name() == proc_name:
                proc.terminate()
                click.secho(f"Stopped PID {proc.pid}", fg="green")
                return

        click.secho(f"Unable to find process to stop ({proc_name})", fg="yellow")

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

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def product(self) -> str:
        return "couchbase-lite-js"

    @property
    def platform(self) -> str:
        return "js"

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver.zip"

    def build(self) -> None:
        header(f"Installing CBL JS and dependencies for version {self.version}")
        click.echo("Installing CBL")
        subprocess.run(
            [
                "bun",
                "install",
                f"@couchbase/lite-js@{self.version}",
                "--registry",
                "https://proget.sc.couchbase.com/npm/cbl-npm/",
            ],
            check=True,
            cwd=JS_TEST_SERVER_DIR,
        )
        click.echo("Installing dependencies")
        subprocess.run(["bun", "install"], check=True, cwd=JS_TEST_SERVER_DIR)
        pass

    def compress_package(self):
        header(f"Compressing JS test server for {self.platform}")
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = ZIP_DIR / "testserver.zip"
        zip_directory(
            JS_TEST_SERVER_DIR,
            zip_path,
            excludes=[f"{ZIP_FOLDER_NAME}/**", ".gitignore", "bun.lock*"],
        )
        return str(zip_path)

    def uncompress_package(self, path):
        unzip_directory(path, path.parent)
        path.unlink()

    def create_bridge(self, **kwargs):
        working_dir = (
            DOWNLOADED_TEST_SERVER_DIR / "js" / self.version
            if self._downloaded
            else JS_TEST_SERVER_DIR
        )

        return JavascriptBridge(str(working_dir))
