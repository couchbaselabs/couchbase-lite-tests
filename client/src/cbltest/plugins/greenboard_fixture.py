import os

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.logging import cbl_info, cbl_warning

# This plugin provides an automatic (i.e. not used directly by tests)
# fixture that will upload test results to greenboard, if it is properly
# set up in config.json (see the schema for that file) and if the
# --no-result-upload flag is not set on the command line.
#
# Two upload paths:
#   - Normal sessions go through GreenboardUploader.upload().
#   - SGW upgrade sessions (with SGW_UPGRADE_FROM and SGW_UPGRADE_TO env
#     vars set) go through GreenboardUploader.upload_upgrade_result(),
#     which merges this run's pass/fail entry into a per-type matrix doc
#     (sgw-upgrade::waterfall or sgw-upgrade::rolling). The upgrade type
#     is derived from the invoked test file name.


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

    yield

    try:
        upg_from = os.environ.get("SGW_UPGRADE_FROM")
        upg_to = os.environ.get("SGW_UPGRADE_TO")
        if upg_from and upg_to:
            upgrade_type = (
                "rolling"
                if any("test_rolling_upgrade_sgw" in a for a in pytestconfig.args)
                else "waterfall"
            )
            uploader.upload_upgrade_result(upgrade_type, upg_from, upg_to)
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
                sgw_version = await cblpytest.sync_gateways[0].get_version()
            uploader.upload(test_platform, os_name, library_version, sgw_version)
    except Exception as e:
        cbl_warning(f"Failed to upload results to Greenboard: {e}")
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
