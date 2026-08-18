"""
Bridge the CBL_PYTEST_SESSION_TIMEOUT environment variable to pytest-timeout's --session-timeout.

pytest-timeout reads PYTEST_TIMEOUT from the environment for the per-test timeout, but has no environment variable
for the whole-session timeout. This plugin adds one: CI sets a single variable (CBL_PYTEST_SESSION_TIMEOUT, in
seconds) as the source of truth for pytest's graceful-stop budget, and a Jenkins stage can derive its own hard
timeout from the same value -- so the two can never drift out of order. An explicit --session-timeout on the CLI
still wins.
"""

import os

import pytest

_ENV_VAR = "CBL_PYTEST_SESSION_TIMEOUT"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # tryfirst so we set session_timeout BEFORE pytest-timeout's pytest_configure reads it.
    raw = os.environ.get(_ENV_VAR)
    if not raw:
        return

    try:
        seconds = float(raw)
    except ValueError:
        raise pytest.UsageError(f"{_ENV_VAR} must be a number of seconds, got {raw!r}") from None

    # An explicit --session-timeout on the CLI wins over the environment variable.
    if config.getoption("session_timeout", None) is None:
        config.option.session_timeout = seconds
