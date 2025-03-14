from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, Type

from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SERVER_DIR = (SCRIPT_DIR / ".." / ".." / ".." / "servers").resolve()


class TestServer(ABC):
    __registry: Dict[str, Type[TestServer]] = {}

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
    def create(cls, name: str) -> TestServer:
        cls.initialize()

        if name not in cls.__registry:
            raise ValueError(f"Unknown test server type: {name}")

        return cls.__registry[name]()

    @property
    @abstractmethod
    def platform(self) -> str:
        pass

    @property
    @abstractmethod
    def latestbuilds_path(self, version: str) -> str:
        pass

    @abstractmethod
    def build(self, cbl_version: str) -> None:
        pass

    @abstractmethod
    def compress_package(self) -> str:
        pass

    @abstractmethod
    def create_bridge(self) -> PlatformBridge:
        pass


assert __name__ != "__main__", "This module is not meant to be run directly"
