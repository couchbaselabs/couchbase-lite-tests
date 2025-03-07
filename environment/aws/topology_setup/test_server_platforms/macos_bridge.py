from .platform_bridge import PlatformBridge

class macOSBridge(PlatformBridge):
    def install(self, path: str) -> None:
        pass

    def run(self, id: str) -> None:
        pass

    def stop(self, id: str) -> None:
        pass

    def uninstall(self, id: str) -> None:
        pass