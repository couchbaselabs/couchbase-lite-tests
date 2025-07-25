import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.logging import cbl_info

# This plugin provides an automatic (i.e. not used directly by tests)
# fixture that will upload test results to greenboard, if it is
# properly set up in config.json (see the schema for that file)
# and if the --no-result-upload flag is not set on the command line.


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

    test_server_info = await cblpytest.test_servers[0].get_info()
    sgw_version: str = "n/a"
    if len(cblpytest.sync_gateways) > 0:
        sgw_version_parts = await cblpytest.sync_gateways[0].get_version()
        sgw_version = f"{sgw_version_parts.version}-{sgw_version_parts.build_number}"
    os_name = (
        test_server_info.device["systemName"]
        if "systemName" in test_server_info.device
        else ""
    )
    uploader.upload(
        test_server_info.cbl,
        os_name,
        test_server_info.library_version,
        sgw_version
    )
    pytestconfig.pluginmanager.unregister(uploader)


# This adds the --no-result-upload option to the pytest command line.
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--no-result-upload",
        action="store_true",
        help="Don't upload results to greenboard",
    )
