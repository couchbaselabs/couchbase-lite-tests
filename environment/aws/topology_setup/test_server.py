"""
This module provides the abstract base class TestServer for managing Couchbase Lite test servers on various platforms.
It includes functions for initializing, registering, creating, building, downloading, compressing, and uncompressing test servers.

Classes:
    TestServer: An abstract base class for managing Couchbase Lite test servers on various platforms.

Functions:
    initialize(cls) -> None:
        Initialize the test server registry by importing platform-specific modules.

    register(cls, name: str) -> Callable[[Type[TestServer]], Type[TestServer]]:
        Register a test server subclass with a given name.

    create(cls, name: str, version: str) -> TestServer:
        Create an instance of a registered test server subclass.

    version(self) -> str:
        Get the version of the test server.

    platform(self) -> str:
        Get the platform of the test server.

    latestbuilds_path(self) -> str:
        Get the path for the latest builds of the test server.

    build(self) -> None:
        Build the test server.

    download(self) -> None:
        Download the test server package from the latestbuilds server.

    compress_package(self) -> str:
        Compress the test server package.

    uncompress_package(self, path: Path) -> None:
        Uncompress the test server package.

    create_bridge(self) -> PlatformBridge:
        Create a platform bridge for the test server.
"""

from __future__ import annotations

import importlib
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import click
import requests

from environment.aws.common.io import download_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SERVER_DIR = (SCRIPT_DIR / ".." / ".." / ".." / "servers").resolve()
DOWNLOADED_TEST_SERVER_DIR = TEST_SERVER_DIR / "downloaded"


class TestServer(ABC):
    """
    An abstract base class for managing Couchbase Lite test servers on various platforms.

    Methods:
        initialize(cls) -> None:
            Initialize the test server registry by importing platform-specific modules.

        register(cls, name: str) -> Callable[[Type[TestServer]], Type[TestServer]]:
            Register a test server subclass with a given name.

        create(cls, name: str, version: str) -> TestServer:
            Create an instance of a registered test server subclass.

        version(self) -> str:
            Get the version of the test server.

        platform(self) -> str:
            Get the platform of the test server.

        latestbuilds_path(self) -> str:
            Get the path for the latest builds of the test server.

        build(self) -> None:
            Build the test server.

        download(self) -> None:
            Download the test server package from the latestbuilds server.

        compress_package(self) -> str:
            Compress the test server package.

        uncompress_package(self, path: Path) -> None:
            Uncompress the test server package.

        create_bridge(self) -> PlatformBridge:
            Create a platform bridge for the test server.
    """

    __registry: dict[str, type[TestServer]] = {}

    def __init__(self, version: str, dataset_version: str) -> None:
        self.__version = version
        self.__dataset_version = dataset_version
        self._downloaded = False

    @classmethod
    def initialize(cls) -> None:
        """
        Initialize the test server registry by importing platform-specific modules.
        """
        if len(cls.__registry) > 0:
            return

        platforms_path = SCRIPT_DIR / "test_server_platforms"
        for platform in platforms_path.iterdir():
            if (
                platform.is_file()
                and platform.stem.endswith("_register")
                and platform.suffix == ".py"
            ):
                importlib.import_module(
                    f"environment.aws.topology_setup.test_server_platforms.{platform.stem}"
                )

    @classmethod
    def register(cls, name: str) -> Callable[[type[TestServer]], type[TestServer]]:
        """
        Register a test server subclass with a given name.

        Args:
            name (str): The name to register the test server subclass with.

        Returns:
            Callable[[Type[TestServer]], Type[TestServer]]: A decorator function to register the subclass.
        """

        def decorator(subclass: type[TestServer]) -> type[TestServer]:
            cls.__registry[name] = subclass
            return subclass

        return decorator

    @classmethod
    def create(cls, name: str, version: str, dataset_version: str) -> TestServer:
        """
        Create an instance of a registered test server subclass.

        Args:
            name (str): The name of the registered test server subclass.
            version (str): The version of the test server.
            dataset_version (str): The dataset version to use when building.

        Returns:
            TestServer: An instance of the registered test server subclass.

        Raises:
            ValueError: If the test server type is unknown.
        """
        cls.initialize()

        if name not in cls.__registry:
            raise ValueError(f"Unknown test server type: {name}")

        return cls.__registry[name](version, dataset_version)

    @property
    def version(self) -> str:
        """
        Get the version of the test server.

        Returns:
            str: The version of the test server.
        """
        return self.__version

    @property
    def dataset_version(self) -> str:
        """
        Get the dataset version of the test server.

        Returns:
            str: The dataset version of the test server.
        """
        return self.__dataset_version

    @property
    @abstractmethod
    def platform(self) -> str:
        """
        Get the platform of the test server.

        Returns:
            str: The platform of the test server.
        """
        pass

    @property
    @abstractmethod
    def latestbuilds_path(self) -> str:
        """
        Get the path for the latest builds of the test server.

        Returns:
            str: The path for the latest builds of the test server.
        """
        pass

    @abstractmethod
    def build(self) -> None:
        """
        Build the test server.
        """
        pass

    def download(self) -> None:
        """
        Download the test server package from the latestbuilds server.

        Raises:
            FileNotFoundError: If the test server package is not found on the latestbuilds server.
        """
        download_dir = DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version
        download_dir.mkdir(parents=True, exist_ok=True)
        if (download_dir / ".downloaded").exists():
            click.secho("Already downloaded", fg="green")
            click.echo()
            return

        url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{self.latestbuilds_path}"
        header(f"Downloading {url}")
        response = requests.head(url)
        if response.status_code == 404:
            raise FileNotFoundError(f"Test server not found at {url}")
        response.raise_for_status()

        response = requests.get(url, stream=True)
        file_path = download_dir / Path(url).name
        download_progress_bar(response, file_path)
        self.uncompress_package(file_path)
        Path(download_dir / ".downloaded").touch()
        self._downloaded = True

    @abstractmethod
    def compress_package(self) -> str:
        """
        Compress the test server package.

        Returns:
            str: The path to the compressed package.
        """
        pass

    @abstractmethod
    def uncompress_package(self, path: Path) -> None:
        """
        Uncompress the test server package.

        Args:
            path (Path): The path to the compressed package.
        """
        pass

    @abstractmethod
    def create_bridge(self) -> PlatformBridge:
        """
        Create a platform bridge for the test server.

        .. warning::
            If self._downloaded is true your implementation must
            use the path DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version
            to find the downloaded test server. Otherwise, it should
            use whatever path is appropriate for the output of the build system.

        Returns:
            PlatformBridge: The platform bridge for the test server.
        """
        pass


def copy_dataset(dest_dir: Path, version: str):
    header(f"Copying dataset resources v{version}")
    db_dir = TEST_SERVER_DIR.parent / "dataset" / "server" / "dbs" / version
    blob_dir = TEST_SERVER_DIR.parent / "dataset" / "server" / "blobs"

    dest_db_dir = dest_dir / "dbs"
    shutil.rmtree(dest_db_dir, ignore_errors=True)
    dest_db_dir.mkdir(0o755)
    for db in db_dir.glob("*.zip"):
        click.echo(f"Copying {db} -> {dest_db_dir / db.name}")
        shutil.copy2(db, dest_db_dir)

    dest_blob_dir = dest_dir / "blobs"
    shutil.rmtree(dest_blob_dir, ignore_errors=True)
    dest_blob_dir.mkdir(0o755)
    for blob in blob_dir.iterdir():
        click.echo(f"Copying {blob} -> {dest_blob_dir / blob.name}")
        shutil.copy2(blob, dest_blob_dir)


assert __name__ != "__main__", "This module is not meant to be run directly"
