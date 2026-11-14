from pathlib import Path
from typing import Final

import pytest

# This plugin keeps the stress tests (long-running stress, soak and chaos tests) apart from the regular ones.
# A suite keeps its stress tests in a folder named "stress". Without --stress, those folders are not
# collected, so an ordinary run never starts a test meant to run for hours. With --stress, only those
# folders are collected.

_stress_dir: Final[str] = "stress"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--stress",
        action="store_true",
        default=False,
        help=f"Run only the stress tests (the '{_stress_dir}' folders), which are skipped otherwise",
    )


def _in_stress_dir(collection_path: Path, config: pytest.Config) -> bool:
    # Only folders below the root count, so a checkout that happens to sit under a "stress" folder
    # is not mistaken for one.
    try:
        parts = collection_path.relative_to(config.rootpath).parts
    except ValueError:
        parts = collection_path.parts
    return _stress_dir in parts


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    # None, not False, leaves the decision to the other plugins and pytest's own rules.
    if config.getoption("--stress"):
        if collection_path.is_file() and not _in_stress_dir(collection_path, config):
            return True
    elif collection_path.is_dir() and collection_path.name == _stress_dir:
        return True
    return None
