"""
Pytest plugin: convert SIGTERM into SIGINT so pytest runs its normal cleanup.

Jenkins terminates a timed-out or aborted step with SIGTERM, then SIGKILLs after a short grace period (~60s on a
VM agent, ~10s on Docker). pytest only performs graceful shutdown on SIGINT (KeyboardInterrupt); on a bare SIGTERM
it dies immediately without running fixture finalizers, so junit, greenboard, and sgcollect cleanup are all skipped.
Re-raising SIGTERM as SIGINT lets pytest tear down gracefully within that grace window.

This is the last-ditch backstop. The primary graceful-exit path is pytest-timeout's --session-timeout, which stops
the session (with a full cleanup runway) BEFORE Jenkins' own timeout fires; this handler only matters if Jenkins
sends SIGTERM anyway (e.g. a pipeline-level timeout or a manual abort).

To stay a good citizen when pytest is embedded in another runner: we only take over SIGTERM when it is still the
default disposition (so we never clobber a handler some outer tool installed), and we restore whatever was there in
pytest_unconfigure.
"""

import signal
from types import FrameType
from typing import Any

import pytest

# The SIGTERM handler that was in place before we installed ours, saved so
# pytest_unconfigure can restore it. _UNSET means we did not install a handler
# (nothing to restore).
_UNSET: Any = object()
_prev_sigterm_handler: Any = _UNSET


def _sigterm_to_sigint(signum: int, frame: FrameType | None) -> None:
    # Re-deliver as SIGINT so pytest's graceful KeyboardInterrupt handling runs its fixture finalizers.
    signal.raise_signal(signal.SIGINT)


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    global _prev_sigterm_handler

    # Only take over the DEFAULT disposition. If another runner/tool already installed a SIGTERM handler (or set it
    # to ignore, or it was installed from non-Python code), respect that instead of clobbering it.
    current = signal.getsignal(signal.SIGTERM)
    if current is not signal.SIG_DFL:
        return

    try:
        # signal.signal() only works on the main thread; pytest_configure runs there, but guard anyway in case
        # pytest is driven off-thread by an embedding runner.
        signal.signal(signal.SIGTERM, _sigterm_to_sigint)
    except ValueError:
        return

    _prev_sigterm_handler = current


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    global _prev_sigterm_handler
    if _prev_sigterm_handler is _UNSET:
        return

    try:
        signal.signal(signal.SIGTERM, _prev_sigterm_handler)
    except ValueError:
        pass
    _prev_sigterm_handler = _UNSET
