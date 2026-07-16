import pathlib

import pytest
import pytest_asyncio
from cbltest.api.syncgateway import run_sgcollects


@pytest_asyncio.fixture(scope="session")
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
