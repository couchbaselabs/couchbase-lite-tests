import os
from pathlib import Path

import pytest
from cbltest.utils import verify_lfs_checkout


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    verify_lfs_checkout()
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "dataset", "sg")
