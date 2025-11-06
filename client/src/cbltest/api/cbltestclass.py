from abc import ABC

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from cbltest.api.syncgateway import SyncGateway
from cbltest.api.testserver import TestServer
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_info, cbl_warning
from cbltest.responses import ServerVariant


class CBLTestClass(ABC):
    def setup_method(self, method) -> None:
        CBLPyTestGlobal.running_test_name = method.__name__
        cbl_info(f"Starting test: {method.__name__}")
        self.__step: int = 1
        self.__skipped: bool = False

    def teardown_method(self, method) -> None:
        if self.__step == 1 and not self.__skipped:
            cbl_warning(
                f"No test steps marked in {method.__name__}, did you forget to use self.mark_test_step()?"
            )

    def mark_test_step(self, description: str) -> None:
        """
        Lets the TDK know that a new test step is about to be performed.  Currently
        all this does is log to the test server log, but could be expanded.
        """
        cbl_info(f"Moving to step {self.__step}:")
        self.__step += 1
        for line in description.splitlines():
            stripped_line = line.strip()
            if len(stripped_line) == 0:
                continue

            cbl_info(f"\t{stripped_line}")

    def skip(self, reason: str):
        """
        Skips the test with the given reason.

        :param reason: The reason for skipping the test.
        """
        self.__skipped = True
        pytest.skip(reason)

    def skip_if_not(self, condition: bool, reason: str):
        """
        Skips the test if the given condition is not met.

        :param condition: A callable that returns a boolean indicating whether to skip the test.
        :param reason: The reason for skipping the test.
        """
        if not condition:
            self.skip(reason)

    async def skip_if_not_platform(
        self, server: TestServer, allow_platforms: ServerVariant
    ):
        """
        Skips the test if the current platform does not match the specified platform.

        :param platform: The platform to check against.
        """
        variant = (await server.get_info()).variant
        self.skip_if_not(
            variant in allow_platforms,
            f"{variant} is not in the platforms {allow_platforms}",
        )

    async def skip_if_cbl_not(self, server: TestServer, constraint: str):
        """
        Skips the test if the CBL version does not match the specified comparison operation and value.

        :param constraint: A string representing the comparison operation and version, e.g., ">= 3.3.0".
        """
        version_str = (await server.get_info()).library_version.split("-")[0]
        version = Version(version_str)
        spec = SpecifierSet(constraint)
        self.skip_if_not(version in spec, f"CBL {version_str} not {constraint}")

    async def skip_if_sgw_not(self, sg: SyncGateway, constraint: str):
        """
        Skips the test if the SGW version does not match the specified comparison operation and value.

        :param sg: The SyncGateway instance to check version for.
        :param constraint: A string representing the comparison operation and version, e.g., ">= 4.0.0".
        """
        sgw_version_obj = await sg.get_version()
        version_str = sgw_version_obj.version
        version = Version(version_str)
        spec = SpecifierSet(constraint)
        self.skip_if_not(version in spec, f"SGW {version_str} not {constraint}")
