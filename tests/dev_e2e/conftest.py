import os
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest.utils import verify_lfs_checkout
from es_remote import ES_SKIP_FILES, ES_SKIP_TEST_NAMES, install_es_remote


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


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--cbl-remote") != "es":
        return
    if config.getoption("--investigate-es-hangs"):
        return
    skip = pytest.mark.skip(
        reason="Requires Sync Gateway features (channels/roles/CBS); skipped for --cbl-remote=es"
    )
    for item in items:
        path = Path(str(item.path))
        if (
            path.parent.name == "edge_server"
            or path.name in ES_SKIP_FILES
            or item.name.split("[")[0] in ES_SKIP_TEST_NAMES
        ):
            item.add_marker(skip)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _install_es_remote_if_requested(
    request: pytest.FixtureRequest,
    cblpytest,
    dataset_path: Path,
):
    if request.config.getoption("--cbl-remote") != "es":
        return
    install_es_remote(cblpytest, dataset_path)
