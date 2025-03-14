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
    __registry: Dict[str, Type[TestServer]] = {}

    def __init__(self, version: str):
        self.__version = version
        self._downloaded = False

    @classmethod
    def initialize(cls) -> None:
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
        def decorator(subclass: Type[TestServer]) -> Type[TestServer]:
            cls.__registry[name] = subclass
            return subclass

        return decorator

    @classmethod
    def create(cls, name: str, version: str) -> TestServer:
        cls.initialize()

        if name not in cls.__registry:
            raise ValueError(f"Unknown test server type: {name}")

        return cls.__registry[name](version)

    @property
    def version(self) -> str:
        return self.__version

    @property
    @abstractmethod
    def platform(self) -> str:
        pass

    @property
    @abstractmethod
    def latestbuilds_path(self) -> str:
        pass

    @abstractmethod
    def build(self) -> None:
        pass

    def download(self) -> None:
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
        pass

    @abstractmethod
    def uncompress_package(self, path: Path) -> None:
        pass

    @abstractmethod
    def create_bridge(self) -> PlatformBridge:
        pass


assert __name__ != "__main__", "This module is not meant to be run directly"
