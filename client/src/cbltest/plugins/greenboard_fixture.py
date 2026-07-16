import os
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.logging import cbl_info, cbl_warning

# This plugin provides an automatic (i.e. not used directly by tests)
# fixture that will upload test results to greenboard, if it is
# properly set up in config.json (see the schema for that file)
# and if the --no-result-upload flag is not set on the command line.
#
# For upgrade jobs (SGW_UPGRADE_VERSIONS is set), each pytest session
# uploads its own per-step result directly under platform="sgw-upgrade".


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
        cbl_info("Greenboard uploading disabled by flag")
        yield
        return
    if len(cblpytest.test_servers) == 0 and len(cblpytest.sync_gateways) == 0:
        yield
        return

    uploader = GreenboardUploader(
        cblpytest.config.greenboard_url,
        cblpytest.config.greenboard_username,
        cblpytest.config.greenboard_password,
    )
    pytestconfig.pluginmanager.register(uploader)

    # This is a pytest-ism.  You may have noticed it in other tests.  The
    # way that fixtures work is that you can yield in the middle and what
    # ends up happening is that all other things happening within the scope
    # will happen, and then return back to this point.  Since the scope here
    # is 'session' it basically means "before and after the run"
    yield

    try:
        upgrade_versions_str = pytestconfig.getoption("--upgrade-versions")
        if upgrade_versions_str:
            # Upgrade job — record this iteration's result to a state file.
            # The aggregate batch document is uploaded once at the end of
            # the upgrade run by jenkins/pipelines/QE/upg-sgw/upload_greenboard_batch.py.
            # Default matches the shell wrapper's path so direct pytest
            # invocations still record correctly.
            results_file = os.environ.get("SGW_UPGRADE_RESULTS_FILE", "/tmp/sgw_upgrade_results.json")
            # During rolling phases the SGW node under upgrade may be
            # destroyed/restarting and get_version() will raise. We must
            # still record the iteration (with sgw_version=None) so the
            # failure shows up as a red dot on the track chart instead
            # of being silently dropped.
            sgw_version: CouchbaseVersion | None = None
            if len(cblpytest.sync_gateways) > 0:
                try:
                    sgw_version = await cblpytest.sync_gateways[0].get_version()
                except Exception as e:
                    cbl_warning(
                        f"Could not fetch SGW version for upgrade record: {e}; "
                        "recording iteration with sgw_version=None"
                    )
            uploader.record_upgrade_step(
                results_file,
                sgw_version,
                upgrade_versions_str,
                os.environ.get("SGW_UPGRADE_PHASE"),
                os.environ.get("SGW_UPGRADED_NODE_INDEX"),
            )
        else:
            sgw_version: CouchbaseVersion | None = None
            test_platform: str = "sync-gateway"
            os_name: str = "n/a"
            library_version: str = "n/a"
            if len(cblpytest.test_servers) > 0:
                test_server_info = await cblpytest.test_servers[0].get_info()
                # Keep the platform as SGW if it has one of the sgw markers, since
                # the test might still use test server with it, but still belong
                # to SGW and not CBL test platform.
                library_version = test_server_info.library_version
                if not uploader.has_sgw_marker():
                    test_platform = test_server_info.cbl
                if "systemName" in test_server_info.device:
                    os_name = test_server_info.device["systemName"]
            if len(cblpytest.sync_gateways) > 0:
                try:
                    sgw_version = await cblpytest.sync_gateways[0].get_version()
                except Exception as e:
                    cbl_warning(f"Could not fetch SGW version for greenboard doc: {e}")
            xmlpath = pytestconfig.option.xmlpath
            if xmlpath:
                uploader.upload_from_junit_file(
                    Path(xmlpath),
                    test_platform,
                    os_name,
                    library_version,
                    sgw_version,
                )
            else:
                # No --junitxml configured. Normally our pytest_configure
                # hook defaults this to "junit_result.xml", but it doesn't
                # fire for synthetic Configs (e.g. ones built via
                # pytest.Config.fromdictargs in unit tests). Fall back to
                # the in-process counter — mirrors upload_from_junit_file's
                # file-missing branch.
                uploader.upload(test_platform, os_name, library_version, sgw_version)
    finally:
        pytestconfig.pluginmanager.unregister(uploader)


# This adds CLI options for greenboard result uploads.
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--no-result-upload",
        action="store_true",
        help="Don't upload results to greenboard",
    )
    group.addoption(
        "--upgrade-versions",
        type=str,
        default=None,
        help="Comma-separated ordered SGW version list for upgrade jobs "
        "(e.g. '3.3.0,4.0.1,4.1.0'). First is the baseline, rest are upgrade "
        "targets. Triggers sgw-upgrade platform upload.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Default ``--junitxml=junit_result.xml`` so the greenboard fixture's
    session-finish step can read pass/fail counts from the XML.

    Doing this in code (instead of via ``addopts`` in ``client/pyproject.toml``)
    is necessary because pytest's rootdir discovery walks up from the cwd and
    typically picks the repo-root ``pyproject.toml`` for production runs from
    ``tests/QE`` or ``tests/dev_e2e`` — never reaching ``client/pyproject.toml``.
    The plugin's entry-point registration guarantees this hook fires on every
    pytest invocation that imports ``cbltest``.

    Users can override with ``--junitxml=<path>`` on the CLI; pytest's
    last-wins behavior leaves the explicit flag in charge.
    """
    if not getattr(config.option, "xmlpath", None):
        config.option.xmlpath = "junit_result.xml"
