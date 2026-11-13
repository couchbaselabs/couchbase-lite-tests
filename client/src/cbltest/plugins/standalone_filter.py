"""
Run standalone tests only when asked for. A standalone test is one that is too long, or too demanding of its
environment, to run with the rest of a suite.

A test marked ``@pytest.mark.standalone`` is skipped unless the -m expression names the marker, e.g.
``pytest -m standalone test_file.py``. Naming the test's file or node ID on its own does not run it.

The skip is added at collection, so it stops the test before any fixture runs, and the autouse cluster_cleanup
does not reset the backend for a test that is not going to run.
"""

import re
from typing import Final

import pytest

_standalone_key: Final[str] = "standalone"


# This makes pytest.mark.standalone available for use in test files.
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{_standalone_key}: marks tests that run only when the -m expression names {_standalone_key}",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # A -m expression that names the marker already decides whether these tests run, e.g. "not standalone".
    if re.search(rf"\b{_standalone_key}\b", config.option.markexpr or ""):
        return

    skip = pytest.mark.skip(reason=f"Standalone test: run it with -m {_standalone_key}")
    for item in items:
        if item.get_closest_marker(_standalone_key):
            item.add_marker(skip)
