
from __future__ import annotations
from abc import ABC, abstractmethod
import importlib
from pathlib import Path
from typing import Dict, Type, Callable
from topology_setup.test_server_platforms.platform_bridge import PlatformBridge

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SERVER_DIR = (SCRIPT_DIR / ".." / ".." / ".." / "servers").resolve()

class TestServer(ABC):
    __registry : Dict[str, Type] = {}

    @classmethod
    def initialize(cls) -> None:
        platforms_path = SCRIPT_DIR / "test_server_platforms"
        for platform in platforms_path.iterdir():
            if platform.is_file() and platform.stem.endswith("_register") and platform.suffix == ".py":
                importlib.import_module(f"topology_setup.test_server_platforms.{platform.stem}")

    @classmethod
    def register(cls, name: str) -> Callable[[Type], Type]:
        def decorator(subclass: Type) -> Type:
            cls.__registry[name] = subclass
            return subclass
        
        return decorator
    
    @classmethod
    def create(cls, name: str, *args, **kwargs) -> TestServer:
        if name not in cls.__registry:
            raise ValueError(f"Unknown test server type: {name}")
        
        return cls.__registry[name](*args, **kwargs)
    
    @property
    @abstractmethod
    def platform(self) -> str:
        pass

    @abstractmethod
    def build(self, cbl_version: str) -> None:
        pass

    @abstractmethod
    def create_bridge(self) -> PlatformBridge:
        pass

TestServer.initialize()