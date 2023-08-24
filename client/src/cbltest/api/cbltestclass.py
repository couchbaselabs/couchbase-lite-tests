from abc import ABC

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_info

class CBLTestClass(ABC):
    def setup_method(self, method) -> None:
        CBLPyTestGlobal.running_test_name = method.__name__
        cbl_info(f"Starting test: {method.__name__}")

    def mark_test_step(sekf, description: str) -> None:
        """
        Lets the TDK know that a new test step is about to be performed.  Currently
        all this does is log to the test server log, but could be expanded.
        """
        cbl_info("Moving to next step:")
        for line in description.splitlines():
            stripped_line = line.strip()
            if len(stripped_line) == 0:
                continue

            cbl_info(f"\t{stripped_line}")