import asyncio
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.logging import cbl_error, cbl_info


async def run_es_collects(edge_servers: Sequence[EdgeServerManager], output_dir: Path) -> list[Path]:
    """
    Collects logs from every given Edge Server node in parallel, downloading each resulting
    archive into output_dir, and logs a summary. Per-node failures are logged as errors (not raised).

    :param edge_servers: The Edge Server nodes to collect from
    :param output_dir: Local directory to download the resulting archives into
    :return: The local paths of the archives that were successfully collected
    """

    async def _collect_one(es: EdgeServerManager) -> Path | None:
        try:
            return await es.collect_logs(output_dir)
        except Exception as e:
            cbl_error(
                f"es-collect: failed to collect logs from {es.hostname}: {e}",
                include_stack=False,
            )
            return None

    results = await asyncio.gather(*(_collect_one(es) for es in edge_servers))
    collected = [path for path in results if path is not None]
    cbl_info(
        f"es-collect: collected {len(collected)}/{len(results)} node(s) to {output_dir}: {[str(p) for p in collected]}"
    )
    if len(collected) < len(results):
        cbl_error(
            f"es-collect: {len(results) - len(collected)}/{len(results)} node(s) "
            "failed to collect logs, see errors above",
            include_stack=False,
        )
    return collected


@pytest_asyncio.fixture(scope="session", autouse=True)
async def es_collect_session(cblpytest: CBLPyTest, request: pytest.FixtureRequest) -> AsyncGenerator[None]:
    yield
    if request.config.getoption("--es-collect") and request.session.testsfailed:
        await run_es_collects(cblpytest.edge_servers, Path.cwd())


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--es-collect",
        action="store_true",
        default=False,
        help="Collect Edge Server logs, config and system info from every "
        "Edge Server node when at least one test in the session fails, and "
        "download the resulting archive(s) into the current working directory "
        "at the end of the tests",
    )
