import asyncio
import pathlib
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest.api.syncgateway import SyncGateway
from cbltest.logging import cbl_error, cbl_info


async def run_sgcollects(
    sync_gateways: list[SyncGateway], output_dir: Path
) -> list[Path]:
    """
    Runs SGCollect on every given Sync Gateway node in parallel, downloading each
    resulting zip into output_dir, and logs a summary of what was collected.

    Per-node failures are logged as errors (not raised).

    :param sync_gateways: The Sync Gateway nodes to collect from
    :param output_dir: Local directory to download the resulting zips into
    :return: The local paths of the zips that were successfully collected
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    async def _collect_one(sg: SyncGateway) -> Path | None:
        try:
            return await sg.run_sgcollect(output_dir)
        except Exception as e:
            cbl_error(
                f"sgcollect: failed to collect logs from {sg.hostname}: {e}",
                include_stack=False,
            )

    results = await asyncio.gather(*(_collect_one(sg) for sg in sync_gateways))
    collected = [path for path in results if path is not None]
    cbl_info(
        f"sgcollect: collected {len(collected)}/{len(results)} node(s) to "
        f"{output_dir}: {[str(p) for p in collected]}"
    )
    if len(collected) < len(results):
        cbl_error(
            f"sgcollect: {len(results) - len(collected)}/{len(results)} node(s) "
            "failed to collect logs, see errors above",
            include_stack=False,
        )
    return collected


@pytest_asyncio.fixture(scope="session", autouse=True)
async def sgcollect_session(cblpytest, request: pytest.FixtureRequest):
    yield
    if (
        request.config.getoption("--sgcollect-on-test-failure")
        and request.session.testsfailed
    ):
        await run_sgcollects(cblpytest.sync_gateways, pathlib.Path.cwd())


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--sgcollect-on-test-failure",
        action="store_true",
        default=False,
        help="Run sgcollect_info on every Sync Gateway node when at least one "
        "test in the session fails, and download the resulting zip(s) into the "
        "current working directory at the end of the tests",
    )
