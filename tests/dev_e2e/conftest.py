import os
from pathlib import Path

import pytest
from cbltest.utils import verify_lfs_checkout

_THIS_DIR = Path(__file__).resolve().parent


# Auto-tag every test under tests/dev_e2e with the `nightly` marker so the
# nightly SGW job can select them with `-m "(sgw or nightly) and
# min_sync_gateways"` without touching each test file. The `and
# min_sync_gateways` half of that expression is what excludes the P2P-only
# tests here (e.g. test_multipeer.py), which never talk to Sync Gateway.
#
# This hook is registered by every conftest in the collection tree, so it must
# only mark the items that live under *this* directory — otherwise a combined
# `tests/`-level run would also tag the QE suite.
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if _THIS_DIR in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.nightly)


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    verify_lfs_checkout()
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "dataset", "sg")
