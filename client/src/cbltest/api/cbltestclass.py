from enum import Enum
from types import FunctionType
from typing import assert_never

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from cbltest.api.syncgateway import SyncGateway
from cbltest.api.testserver import TestServer
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_info, cbl_warning
from cbltest.responses import ServerVariant


class CouchbaseLiteFeature(Enum):
    """CBL features that not every test server supports. Each value names the feature in skip messages."""

    # LiteCore-based platforms from 4.0.0. CBL JS and CBL React Native do not support them yet.
    VERSION_VECTORS = "version vectors"
    # CBL iOS and CBL Android from 3.3.0.
    MULTIPEER = "multipeer replication"
    # LiteCore-based platforms.
    LEGACY_P2P = "legacy peer-to-peer replication"
    # CBL JS does not support it.
    DELTA_SYNC = "delta sync"
    # The CBL JS WebSocket library cannot send them.
    CUSTOM_REPLICATOR_HEADERS = "custom replicator headers"
    # CBL React Native has no API for one.
    CUSTOM_CONFLICT_RESOLVER = "custom conflict resolver"


class CBLTestClass:
    def setup_method(self, method: FunctionType) -> None:
        CBLPyTestGlobal.running_test_name = method.__name__
        cbl_info(f"Starting test: {method.__name__}")
        self.__step: int = 1
        self.__skipped: bool = False
        self.last_test_step: tuple[int, list[str]] | None = None

    def teardown_method(self, method: FunctionType) -> None:
        if self.__step == 1 and not self.__skipped:
            cbl_warning(f"No test steps marked in {method.__name__}, did you forget to use self.mark_test_step()?")

    def mark_test_step(self, description: str) -> None:
        """
        Lets the TDK know that a new test step is about to be performed.  Currently
        all this does is log to the test server log, but could be expanded.
        """
        cbl_info(f"Moving to step {self.__step}:")
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        for line in lines:
            cbl_info(f"\t{line}")

        self.last_test_step = (self.__step, lines)
        self.__step += 1

    def skip(self, reason: str) -> None:
        """
        Skips the test with the given reason.

        :param reason: The reason for skipping the test.
        """
        self.__skipped = True
        pytest.skip(reason)

    def skip_if_not(self, condition: bool, reason: str) -> None:
        """
        Skips the test if the given condition is not met.

        :param condition: A callable that returns a boolean indicating whether to skip the test.
        :param reason: The reason for skipping the test.
        """
        if not condition:
            self.skip(reason)

    async def skip_if_not_platform(
        self, server: TestServer, allow_platforms: ServerVariant, reason: str | None = None
    ) -> None:
        """
        Skips the test if the current platform does not match the specified platform.

        :param allow_platforms: The platforms that can run the test.
        :param reason: Why the other platforms cannot run the test, added to the skip message.
        """
        variant = (await server.info).variant
        message = f"{variant} is not in the platforms {allow_platforms}"
        if reason:
            message += f": {reason}"
        self.skip_if_not(variant in allow_platforms, message)

    async def skip_if_cbl_not(self, server: TestServer, constraint: str, reason: str | None = None) -> None:
        """
        Skips the test if the CBL version does not match the specified comparison operation and value.
        CBL JS and CBL React Native are not checked, because their versions (1.x) do not follow the
        other platforms.

        :param constraint: A string representing the comparison operation and version, e.g., ">= 3.3.0".
        :param reason: Why the test needs this version, added to the skip message.
        """
        if (await server.info).variant in ServerVariant.JS | ServerVariant.REACT_NATIVE:
            return

        await self._skip_if_cbl_version_not(server, constraint, reason)

    async def skip_if_cbl_js_not(self, server: TestServer, constraint: str, reason: str | None = None) -> None:
        """
        Skips the test if the server is CBL JS and its version does not match the specified comparison
        operation and value. Other platforms are not affected.

        :param constraint: A string representing the comparison operation and version, e.g., ">= 1.1.0".
        :param reason: Why the test needs this version, added to the skip message.
        """
        if (await server.info).variant != ServerVariant.JS:
            return

        await self._skip_if_cbl_version_not(server, constraint, reason)

    async def skip_if_not_supports(self, server: TestServer, *features: CouchbaseLiteFeature) -> None:
        """
        Skips the test if the server's CBL does not support all of the given features.

        :param features: The features that the test needs.
        """
        for feature in features:
            reason = f"no {feature.value}"
            match feature:
                case CouchbaseLiteFeature.VERSION_VECTORS:
                    await self.skip_if_not_platform(
                        server, ServerVariant.ALL & ~(ServerVariant.JS | ServerVariant.REACT_NATIVE), reason
                    )
                    await self._skip_if_cbl_version_not(server, ">= 4.0.0", reason)
                case CouchbaseLiteFeature.MULTIPEER:
                    await self.skip_if_not_platform(server, ServerVariant.IOS | ServerVariant.ANDROID, reason)
                    await self._skip_if_cbl_version_not(server, ">= 3.3.0", reason)
                case CouchbaseLiteFeature.LEGACY_P2P:
                    await self.skip_if_not_platform(
                        server, ServerVariant.ALL & ~(ServerVariant.JS | ServerVariant.REACT_NATIVE), reason
                    )
                case CouchbaseLiteFeature.DELTA_SYNC | CouchbaseLiteFeature.CUSTOM_REPLICATOR_HEADERS:
                    await self.skip_if_not_platform(server, ServerVariant.ALL & ~ServerVariant.JS, reason)
                case CouchbaseLiteFeature.CUSTOM_CONFLICT_RESOLVER:
                    await self.skip_if_not_platform(server, ServerVariant.ALL & ~ServerVariant.REACT_NATIVE, reason)
                case _:
                    assert_never(feature)

    async def _skip_if_cbl_version_not(self, server: TestServer, constraint: str, reason: str | None) -> None:
        version_str = (await server.info).library_version.split("-")[0]
        self._skip_if_version_not("CBL", version_str, constraint, reason)

    def _skip_if_version_not(self, label: str, version_str: str, constraint: str, reason: str | None) -> None:
        message = f"{label} {version_str} not {constraint}"
        if reason:
            message += f": {reason}"
        self.skip_if_not(Version(version_str) in SpecifierSet(constraint), message)

    async def skip_if_sgw_not(self, sg: SyncGateway, constraint: str, reason: str | None = None) -> None:
        """
        Skips the test if the SGW version does not match the specified comparison operation and value.

        :param sg: The SyncGateway instance to check version for.
        :param constraint: A string representing the comparison operation and version, e.g., ">= 4.0.0".
        :param reason: Why the test needs this version, added to the skip message.
        """
        self._skip_if_version_not("SGW", (await sg.get_version()).version, constraint, reason)
