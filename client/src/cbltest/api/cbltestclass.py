from abc import ABC

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_info, cbl_warning


class CBLTestClass(ABC):
    def setup_method(self, method) -> None:
        CBLPyTestGlobal.running_test_name = method.__name__
        cbl_info(f"Starting test: {method.__name__}")
        self.__step: int = 1

    def teardown_method(self, method) -> None:
        if self.__step == 1:
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
