"""
Drives the Sync Gateway that `environment/local/start_local.py` manages, so a test can swap the
running binary part way through.

This exists for one reason: the rev tree corruption in CBG-5713 can only be built by a Sync Gateway
that predates the fix, while the repair being tested lives in the developer's working tree. Both have
to appear in a single test run, and Sync Gateway offers no way to change its own version.

Local only. It shells out to `start_local.py` exactly as a developer would, so there is one
implementation of "start Sync Gateway locally" rather than two.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from cbltest.api.syncgateway import SyncGateway

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = REPO_ROOT / "environment" / "local"
START_LOCAL = LOCAL_DIR / "start_local.py"
SGW_BINARY = LOCAL_DIR / "sync_gateway"

# The commit that fixed CBG-5713.  Its parent is the newest Sync Gateway that still builds the
# malformed rev tree, and is otherwise identical to that fix's baseline.
CBG_5713_FIX_COMMIT = "7fb46f5768a67d2396c981d16d8478883f1adfba"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def unavailable_reason(sg: SyncGateway) -> str | None:
    """
    Returns why this Sync Gateway cannot be driven by these helpers, or None if it can.

    Restarting Sync Gateway is only appropriate when it is a local process started from source by
    `start_local.py`.  Anything else - most importantly a provisioned host in CI - must be left alone.
    """
    if sg.hostname not in _LOCAL_HOSTS:
        return f"Sync Gateway is at '{sg.hostname}', and only a local instance may be restarted"
    if not START_LOCAL.exists():
        return f"{START_LOCAL} is missing"
    if not SGW_BINARY.exists():
        return f"{SGW_BINARY} is missing, so Sync Gateway was not started by start_local.py"
    if shutil.which("go") is None:
        return "Go is not on PATH, so a Sync Gateway cannot be built from source"
    return None


class LocalSyncGateway:
    """Starts and restarts the local Sync Gateway, keeping copies of binaries to switch between."""

    def __init__(self, connstr: str) -> None:
        self._connstr = connstr

    def _stash_path(self, label: str) -> Path:
        return LOCAL_DIR / f"sync_gateway.{label}"

    def _start_local(self, *extra_args: str) -> None:
        # sys.executable is the environment pytest is running in, which is the one start_local.py
        # needs: it imports from the repo itself.
        subprocess.run(
            [
                sys.executable,
                str(START_LOCAL),
                "--server",
                "cbs",
                "--connstr",
                self._connstr,
                "--skip-testserver",
                *extra_args,
            ],
            check=True,
            cwd=str(REPO_ROOT),
        )

    def stop(self) -> None:
        """Stops the running Sync Gateway and waits for it to exit."""
        subprocess.run(
            [sys.executable, str(START_LOCAL), "--stop-sync-gateway"],
            check=True,
            cwd=str(REPO_ROOT),
        )

    def stash(self, label: str) -> None:
        """Keeps a copy of the binary that is currently in place, to start again later."""
        shutil.copy2(SGW_BINARY, self._stash_path(label))

    def has_stashed(self, label: str) -> bool:
        return self._stash_path(label).exists()

    def start_stashed(self, label: str) -> None:
        """Puts a previously stashed binary back in place and starts Sync Gateway - no rebuild."""
        stashed = self._stash_path(label)
        if not stashed.exists():
            raise FileNotFoundError(f"No stashed Sync Gateway binary at {stashed}")
        # Overwriting the file while it is being executed leaves the next process to start from it with
        # a torn image, and it dies without logging anything.
        self.stop()
        shutil.copy2(stashed, SGW_BINARY)
        self._start_local("--skip-sync-gateway-build")

    def build_and_start(self, git_ref: str, stash_as: str | None = None) -> None:
        """
        Builds Sync Gateway from source at git_ref and starts it, optionally keeping a copy so the
        next run can skip the build.  Clones the Sync Gateway repo under environment/local if needed.
        """
        # The build writes over the binary, so the running process has to go first - see start_stashed.
        self.stop()
        self._start_local("--git-tag", git_ref)
        if stash_as is not None:
            self.stash(stash_as)
