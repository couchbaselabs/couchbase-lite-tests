"""
Install a SIGTERM handler so pytest runs its cleanup methods on SIGTERM the way it does on SIGINT.

Jenkins will issue SIGTERM on a timeout, and this allows junit / greenboard upload to complete.
"""

import signal
from types import FrameType

import pytest


def _sigterm_to_sigint(signum: int, frame: FrameType | None) -> None:
    signal.raise_signal(signal.SIGINT)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    # trylast so we install after any other plugin's handler, not before it.
    signal.signal(signal.SIGTERM, _sigterm_to_sigint)
