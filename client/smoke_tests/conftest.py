import os
from pathlib import Path
from cbltest import CBLPyTest

import pytest
import pytest_asyncio

@pytest_asyncio.fixture(scope="session")
async def cblpytest(request: pytest.FixtureRequest):
    config = request.config.getoption("--config")
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    cblpytest = await CBLPyTest.create(config, log_level, test_props, True)
    return cblpytest

@pytest.fixture(scope="session")
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "dataset", "sg")

def pytest_addoption(parser) -> None:
    parser.addoption("--config", metavar="PATH", help="The path to the JSON configuration for CBLPyTest", required=True)
    parser.addoption("--cbl-log-level", metavar="LEVEL", 
                    choices=["error", "warning", "info", "verbose", "debug"], 
                    help="The log level output for the test run",
                    default="verbose")
    parser.addoption("--test-props", metavar="PATH", help="The path to read extra test properties from")
