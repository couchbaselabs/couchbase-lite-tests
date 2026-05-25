import json
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.greenboarduploader import parse_version_and_build
from cbltest.logging import cbl_info, cbl_warning

# This plugin is responsible for writing one "meta sidecar" file per pytest
# session into $GREENBOARD_RESULTS_DIR, alongside the JUnit XML emitted by
# pytest's --junitxml flag. The actual greenboard upload happens once per
# Jenkins build, after all pytest sessions have completed, via the
# `cbltest.greenboard_upload` aggregator entry point.
#
# Sidecar shape (consumed by GreenboardUploader.upload_from_results_dir):
#   {
#     "platform": "sync-gateway" | <test-server-platform>,
#     "os": <test server OS name or "n/a">,
#     "version": <parsed version string for the doc>,
#     "build": <parsed build int for the doc>,
#     "sgwVersion": "<sgw_version>-<sgw_build>" | "n/a"
#   }
#
# Behavior:
#   - If $GREENBOARD_RESULTS_DIR is unset (e.g. local dev), the fixture is a
#     no-op — no sidecar is written and the aggregator will not be invoked.
#   - If --no-result-upload is passed, the fixture is a no-op for that
#     session (no sidecar written), matching the prior semantics: the
#     session's results won't contribute to the aggregated upload.
#   - If the greenboard credentials are missing from the config, no-op.

# Module-level tracker for the @pytest.mark.sgw / @pytest.mark.upg_sgw markers.
# Set during test setup; read at session end to decide the platform tag.
_HAS_SGW_MARKER = False


def pytest_runtest_setup(item: pytest.Item) -> None:
    global _HAS_SGW_MARKER
    if item.get_closest_marker("sgw") or item.get_closest_marker("upg_sgw"):
        _HAS_SGW_MARKER = True


@pytest_asyncio.fixture(scope="session", autouse=True)
async def greenboard(cblpytest: CBLPyTest, pytestconfig: pytest.Config):
    if (
        cblpytest.config.greenboard_username is None
        or cblpytest.config.greenboard_password is None
        or cblpytest.config.greenboard_url is None
    ):
        yield
        return

    if pytestconfig.getoption("--no-result-upload"):
        cbl_info("Greenboard sidecar writing disabled by flag")
        yield
        return

    results_dir_env = os.environ.get("GREENBOARD_RESULTS_DIR")
    if not results_dir_env:
        # No CI results dir configured (e.g. local dev) — no aggregator is
        # going to read sidecars, so don't bother writing one.
        yield
        return
    if len(cblpytest.test_servers) == 0 and len(cblpytest.sync_gateways) == 0:
        yield
        return

    # This is a pytest-ism. You may have noticed it in other tests. The way
    # that fixtures work is that you can yield in the middle and what ends
    # up happening is that all other things happening within the scope will
    # happen, and then return back to this point. Since the scope here is
    # 'session' it basically means "before and after the run"
    yield

    try:
        sgw_version: CouchbaseVersion | None = None
        test_platform: str = "sync-gateway"
        os_name: str = "n/a"
        library_version: str = "n/a"
        if len(cblpytest.test_servers) > 0:
            test_server_info = await cblpytest.test_servers[0].get_info()
            library_version = test_server_info.library_version
            # Keep the platform as SGW if the session had one of the SGW
            # markers — the test might use a test server, but it still
            # belongs to the SGW (or SGW-upgrade) suite, not the CBL one.
            if not _HAS_SGW_MARKER:
                test_platform = test_server_info.cbl
            if "systemName" in test_server_info.device:
                os_name = test_server_info.device["systemName"]
        if len(cblpytest.sync_gateways) > 0:
            sgw_version = await cblpytest.sync_gateways[0].get_version()

        version, build, sgw_version_str = parse_version_and_build(
            test_platform, library_version, sgw_version
        )

        results_dir = Path(results_dir_env)
        results_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = results_dir / f"meta_{uuid.uuid4().hex}.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "platform": test_platform,
                    "os": os_name,
                    "version": version,
                    "build": build,
                    "sgwVersion": sgw_version_str,
                }
            )
        )
        cbl_info(f"Wrote greenboard meta sidecar: {sidecar_path}")
    except Exception as e:
        cbl_warning(f"Failed to write greenboard meta sidecar: {e}")


# This adds CLI options for greenboard result uploads.
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--no-result-upload",
        action="store_true",
        help="Don't write the greenboard meta sidecar for this pytest session "
        "(equivalent to opting this session out of the aggregated upload).",
    )
