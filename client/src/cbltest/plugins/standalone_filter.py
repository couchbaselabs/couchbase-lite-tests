"""
Run standalone tests only when asked for. A standalone test is one that is too long, or too demanding of its
environment, to run with the rest of a suite.

A test marked ``@pytest.mark.standalone`` is skipped unless the command line names it, by its file or by a node ID
such as ``test_file.py::TestClass::test_name``. Naming a directory, or running a whole suite, does not count.
``-m standalone`` runs every standalone test that is collected.

The skip is added at collection, so it stops the test before any fixture runs, and the autouse cluster_cleanup
does not reset the backend for a test that is not going to run.
"""

import re
from pathlib import Path
from typing import Final

import pytest

_standalone_key: Final[str] = "standalone"


# This makes pytest.mark.standalone available for use in test files.
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{_standalone_key}: marks tests that run only when named on the command line, or selected with -m {_standalone_key}",
    )


def _named_tests(config: pytest.Config) -> list[tuple[Path, list[str]]]:
    """
    Gets the files the command line names, each with the node ID parts that follow it, e.g. ["TestClass", "test_name"]
    for test_file.py::TestClass::test_name. Directories are left out.
    """
    named = []
    for arg in config.args:
        path, *parts = arg.split("::")
        resolved = (config.invocation_params.dir / path).resolve()
        if resolved.is_file():
            named.append((resolved, parts))
    return named


def _is_named(item: pytest.Item, named: list[tuple[Path, list[str]]]) -> bool:
    # The node ID parts after the file name, e.g. ["TestClass", "test_name[param]"]
    item_parts = item.nodeid.split("::")[1:]
    for path, parts in named:
        if item.path.resolve() != path or len(parts) > len(item_parts):
            continue
        # A test named without its parameters, e.g. test_name, names every one of its parametrizations.
        if all(i == p or i.startswith(f"{p}[") for i, p in zip(item_parts, parts, strict=False)):
            return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # A -m expression that names the marker already decides whether these tests run, e.g. "not standalone".
    if re.search(rf"\b{_standalone_key}\b", config.option.markexpr or ""):
        return

    named = _named_tests(config)
    skip = pytest.mark.skip(reason="Standalone test: run it by naming it on the command line, e.g. file.py::test_name")
    for item in items:
        if item.get_closest_marker(_standalone_key) and not _is_named(item, named):
            item.add_marker(skip)
