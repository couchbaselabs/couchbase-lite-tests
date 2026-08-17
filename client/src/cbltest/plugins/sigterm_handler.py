"""
Pytest plugin: convert SIGTERM into SIGINT so pytest runs its normal cleanup.

Jenkins terminates a timed-out or aborted step with SIGTERM, then SIGKILLs after a short grace period (~60s on a
VM agent, ~10s on Docker). pytest only performs graceful shutdown on SIGINT (KeyboardInterrupt); on a bare SIGTERM
it dies immediately without running fixture finalizers, so junit, greenboard, and sgcollect cleanup are all skipped.
Re-raising SIGTERM as SIGINT lets pytest tear down gracefully within that grace window.

This is the last-ditch backstop. The primary graceful-exit path is pytest-timeout's --session-timeout, which stops
the session (with a full cleanup runway) BEFORE Jenkins' own timeout fires; this handler only matters if Jenkins
sends SIGTERM anyway (e.g. a pipeline-level timeout or a manual abort).
"""

import signal
from types import FrameType

import pytest


def _sigterm_to_sigint(signum: int, frame: FrameType | None) -> None:
    # Re-deliver as SIGINT so pytest's graceful KeyboardInterrupt handling runs its fixture finalizers.
    signal.raise_signal(signal.SIGINT)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    # signal.signal() must be called from the main thread; pytest_configure runs there. trylast so any
    # pytest-internal SIGINT setup is already in place.
    try:
        signal.signal(signal.SIGTERM, _sigterm_to_sigint)
    except (ValueError, OSError):
        # Not on the main thread (e.g. embedded in another runner); skip quietly.
        pass
