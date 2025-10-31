import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "dataset", "sg")
