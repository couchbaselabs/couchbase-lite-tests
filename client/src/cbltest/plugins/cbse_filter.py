from typing import Final

import pytest

# This plugin provides a way to filter tests based on CBSE ticket numbers.
# It allows you to mark tests with a specific CBSE ticket number and then
# run only those tests that are related to a specific ticket number.

_cbse_key: Final[str] = "cbse"


# This makes pytest.mark.cbse(num) available for use in test files.
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{_cbse_key}(num): marks tests to verify a specific CBSE ticket",
    )


# This runs at the beginning of each test to check if CBSE filtering
# was requested.
def pytest_runtest_setup(item: pytest.Function) -> None:
    specified_cbse = item.config.getoption("--cbse")
    if specified_cbse is None:
        return

    cbse_nums = [mark.args[0] for mark in item.iter_markers(name="cbse")]
    if not cbse_nums or int(specified_cbse) not in cbse_nums:
        pytest.skip(f"Unrelated to CBSE-{specified_cbse}")


# This adds the --cbse command line option to pytest.
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--cbse",
        metavar="ticket_num",
        help="If specified, only run the test(s) for a specific CBSE ticket",
    )
