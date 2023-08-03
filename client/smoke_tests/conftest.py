import os
from pathlib import Path
from cbltest import CBLPyTest

import pytest

@pytest.fixture
def cblpytest(request: pytest.FixtureRequest) -> CBLPyTest:
    config = request.config.getoption("--config")
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    output = request.config.getoption("--output")
    return CBLPyTest(config, log_level, test_props, output)

@pytest.fixture
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "dataset")