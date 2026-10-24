from types import FunctionType

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from cbltest.api.syncgateway import SyncGateway
from cbltest.api.testserver import TestServer
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_info, cbl_warning
from cbltest.responses import ServerVariant


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

    async def skip_if_cbl_react_native_not(
        self, server: TestServer, constraint: str, reason: str | None = None
    ) -> None:
        """
        Skips the test if the server is CBL React Native and its version does not match the specified
        comparison operation and value. Other platforms are not affected.

        :param constraint: A string representing the comparison operation and version, e.g., ">= 1.2.0".
        :param reason: Why the test needs this version, added to the skip message.
        """
        if (await server.info).variant != ServerVariant.REACT_NATIVE:
            return

        await self._skip_if_cbl_version_not(server, constraint, reason)

    async def skip_if_not_supports_version_vectors(self, server: TestServer) -> None:
        """
        Skips the test if the server's CBL does not use version vectors. CBL JS and CBL React Native
        do not support them yet; the other platforms support them from 4.0.0.
        """
        await self.skip_if_not_litecore(server, "no version vectors")
        await self._skip_if_cbl_version_not(server, ">= 4.0.0", "no version vectors")

    async def skip_if_not_supports_multipeer(self, server: TestServer) -> None:
        """
        Skips the test if the server's CBL does not support multipeer replication. CBL JS and CBL React
        Native do not support it; the other platforms support it from 3.3.0.
        """
        await self.skip_if_not_litecore(server, "no multipeer replication")
        await self._skip_if_cbl_version_not(server, ">= 3.3.0", "no multipeer replication")

    async def skip_if_not_supports_custom_conflict_resolver(self, server: TestServer) -> None:
        """
        Skips the test if the server's CBL cannot set a custom conflict resolver on a replicator.
        CBL React Native has no API for one.
        """
        await self.skip_if_not_platform(
            server, ServerVariant.ALL & ~ServerVariant.REACT_NATIVE, "no custom conflict resolver"
        )

    async def skip_if_not_litecore(self, server: TestServer, reason: str | None = None) -> None:
        """
        Skips the test if the server is CBL JS or CBL React Native, whose versions and features do not
        follow the LiteCore-based platforms.

        :param reason: Why the test needs a LiteCore-based platform, added to the skip message.
        """
        await self.skip_if_not_platform(
            server, ServerVariant.ALL & ~(ServerVariant.JS | ServerVariant.REACT_NATIVE), reason
        )

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
