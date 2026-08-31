import os
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.utils import verify_lfs_checkout
from es_remote import es_skip_reason_for_file, es_skip_reason_for_test, install_es_remote, load_es_remote_skips


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    verify_lfs_checkout()
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "dataset", "sg")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--cbl-remote",
        choices=["sgw", "es"],
        default="sgw",
        help="Replicator remote: Sync Gateway (default) or Edge Server",
    )
    parser.addoption(
        "--investigate-es-hangs",
        action="store_true",
        default=False,
        help="Do not skip known ES interop hang tests (for debugging)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--cbl-remote") != "es":
        return
    if config.getoption("--investigate-es-hangs"):
        return
    config_path = config.getoption("--config")
    skip_files, skip_tests = load_es_remote_skips(config_path)
    for item in items:
        path = Path(str(item.path))
        if path.parent.name == "edge_server" or path.name in skip_files:
            item.add_marker(pytest.mark.skip(reason=es_skip_reason_for_file(path.name)))
            continue
        base = item.name.split("[")[0]
        if base in skip_tests:
            item.add_marker(pytest.mark.skip(reason=es_skip_reason_for_test(base)))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _install_es_remote_if_requested(
    request: pytest.FixtureRequest,
    cblpytest: CBLPyTest,
    dataset_path: Path,
) -> None:
    if request.config.getoption("--cbl-remote") != "es":
        return
    install_es_remote(cblpytest, dataset_path)
