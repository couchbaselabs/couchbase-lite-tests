"""
Show the last step marked with CBLTestClass.mark_test_step at the top of the traceback of a failed test, so that
the failure output shows which step the test was on.
"""

from collections.abc import Generator
from typing import Any

import pytest
from _pytest._code.code import ExceptionChainRepr, ReprEntryNative


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any]:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    if not report.failed:
        return

    step = getattr(getattr(item, "instance", None), "last_test_step", None)
    if step is None:
        return

    number, lines = step
    header = f"Last test step ({number})"
    body = "".join(f"\t{line}\n" for line in lines)
    if isinstance(report.longrepr, ExceptionChainRepr):
        text = f"{header}: {lines[0]}\n" if len(lines) == 1 else f"{header}:\n{body}"
        # A native entry prints as plain text, and ahead of the "self = ..." arguments of the first frame.
        reprtraceback = report.longrepr.chain[0][0]
        reprtraceback.reprentries = [ReprEntryNative([text]), *reprtraceback.reprentries]
    else:
        report.sections.insert(0, (header, body))
