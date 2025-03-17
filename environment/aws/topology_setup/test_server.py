#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, Type

import requests

from environment.aws.common.io import download_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SERVER_DIR = (SCRIPT_DIR / ".." / ".." / ".." / "servers").resolve()


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

    __registry: Dict[str, Type[TestServer]] = {}

    def __init__(self, version: str):
        self.__version = version
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
    def register(cls, name: str) -> Callable[[Type[TestServer]], Type[TestServer]]:
        """
        Register a test server subclass with a given name.

        Args:
            name (str): The name to register the test server subclass with.

        Returns:
            Callable[[Type[TestServer]], Type[TestServer]]: A decorator function to register the subclass.
        """

        def decorator(subclass: Type[TestServer]) -> Type[TestServer]:
            cls.__registry[name] = subclass
            return subclass

        return decorator

    @classmethod
    def create(cls, name: str, version: str) -> TestServer:
        """
        Create an instance of a registered test server subclass.

        Args:
            name (str): The name of the registered test server subclass.
            version (str): The version of the test server.

        Returns:
            TestServer: An instance of the registered test server subclass.

        Raises:
            ValueError: If the test server type is unknown.
        """
        cls.initialize()

        if name not in cls.__registry:
            raise ValueError(f"Unknown test server type: {name}")

        return cls.__registry[name](version)

    @property
    def version(self) -> str:
        """
        Get the version of the test server.

        Returns:
            str: The version of the test server.
        """
        return self.__version

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
        download_dir = TEST_SERVER_DIR / "downloaded" / self.platform / self.version
        download_dir.mkdir(parents=True, exist_ok=True)
        if (download_dir / ".downloaded").exists():
            print("Already downloaded")
            print()
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
        print(file_path)
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

        Returns:
            PlatformBridge: The platform bridge for the test server.
        """
        pass


assert __name__ != "__main__", "This module is not meant to be run directly"
