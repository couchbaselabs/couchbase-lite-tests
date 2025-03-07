from abc import ABC, abstractmethod

class PlatformBridge(ABC):
    @abstractmethod
    def install(self, location: str) -> None:
        pass

    @abstractmethod
    def run(self, location: str) -> None:
        pass

    @abstractmethod
    def stop(self, location: str) -> None:
        pass

    @abstractmethod
    def uninstall(self, location: str) -> None:
        pass