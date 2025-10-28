"""Pytest configuration for SGW QE tests."""

import os
from pathlib import Path

import pytest


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    """Provides the path to the dataset directory for tests."""
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "..", "dataset", "sg")
