"""Tests for GreenboardUploader and the greenboard fixture."""

import inspect
from typing import Literal, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pluggy._result
import pytest
from _pytest.reports import TestReport
from cbltest import CBLPyTest
from cbltest.api.syncgateway import SyncGatewayVersion
from cbltest.api.testserver import TestServer
from cbltest.configparser import ParsedConfig
from cbltest.greenboarduploader import GreenboardUploader, IntegrationTestRun
from cbltest.plugins import greenboard_fixture
from cbltest.responses import GetRootResponse

# Importing `greenboard` directly into module scope would expose it as an autouse
# fixture to pytest. Access via the module and unwrap to get the raw async generator.
_raw_greenboard = inspect.unwrap(greenboard_fixture.greenboard)


def make_report(
    when: Literal["setup", "call", "teardown"], *, passed: bool = True
) -> TestReport:
    return TestReport(
        nodeid="",
        location=("", 0, ""),
        keywords={},
        outcome="passed" if passed else "failed",
        longrepr=None,
        when=when,
    )


def make_item(markers: list[str] | None = None) -> MagicMock:
    item = MagicMock(spec=pytest.Item)
    active = set(markers or [])
    item.get_closest_marker.side_effect = lambda name: name if name in active else None
    return item


def drive_hook(
    uploader: GreenboardUploader, report: TestReport, item: MagicMock | None = None
) -> None:
    """Advance the hookwrapper generator for one TestReport."""
    if item is None:
        item = make_item()
    outcome = pluggy._result.Result.from_call(lambda: report)
    gen = uploader.pytest_runtest_makereport(
        item=item, call=cast(pytest.CallInfo[None], MagicMock(spec=pytest.CallInfo))
    )
    next(gen)
    try:
        gen.send(outcome)
    except StopIteration:
        pass


def make_uploader() -> GreenboardUploader:
    return GreenboardUploader("couchbase://localhost", "user", "pass")


# ---------------------------------------------------------------------------
# Helpers for fixture tests
# ---------------------------------------------------------------------------


def _make_cblpytest(
    *,
    url: str | None = "couchbase://greenboard.example.com",
    username: str | None = "fakeuser",
    password: str | None = "fakepass",
    test_servers: list | None = None,
    sync_gateways: list | None = None,
) -> MagicMock:
    mock = MagicMock(spec=CBLPyTest)
    mock.config = MagicMock(spec=ParsedConfig)
    mock.config.greenboard_url = url
    mock.config.greenboard_username = username
    mock.config.greenboard_password = password
    mock.test_servers = test_servers if test_servers is not None else []
    mock.sync_gateways = sync_gateways if sync_gateways is not None else []
    return mock


def _make_pytestconfig(*, no_upload: bool = False) -> MagicMock:
    mock = MagicMock(spec=pytest.Config)
    mock.getoption.return_value = no_upload
    mock.pluginmanager = MagicMock(spec=pytest.PytestPluginManager)
    return mock


def _make_server(
    *,
    cbl: str = "couchbase-lite-ios",
    library_version: str = "3.2.0-b0001",
    os_name: str = "iOS",
) -> MagicMock:
    info = GetRootResponse(
        status_code=200,
        uuid="test-uuid",
        json={
            "version": library_version,
            "apiVersion": 1,
            "cbl": cbl,
            "device": {"systemName": os_name},
        },
    )
    server = MagicMock(spec=TestServer)
    server.get_info = AsyncMock(return_value=info)
    return server


async def _run_fixture(gen) -> None:
    """Drive an async generator fixture through setup and teardown."""
    await gen.__anext__()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


class TestGreenboardUploaderDocument:
    def test_pass_and_fail_counts_in_document(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b1234", None)

        mock_upload.assert_called_once()
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.pass_count == 2
        assert test_run.fail_count == 1

    def test_document_platform_and_os(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-net", "Android", "3.2.0-b0050", None)

        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.platform == "couchbase-lite-net"
        assert test_run.os == "Android"

    def test_version_and_build_parsed_from_version_string(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.1-b0136", None)

        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.version == "3.2.1"
        assert test_run.build == 136

    def test_sgw_version_field_with_sgw(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("3.3.3(271;abc)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", sgw)

        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.sgw_version == "3.3.3-271"

    def test_sgw_platform_uses_sgw_version_for_build(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("4.0.0(350;def)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("sync-gateway", "n/a", "n/a", sgw)

        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.version == "4.0.0"
        assert test_run.build == 350
        assert test_run.platform == "sync-gateway"

    def test_no_sgw_version_sets_na(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None)

        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.sgw_version == "n/a"

    def test_setup_failure_skips_upload(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None)

        mock_upload.assert_not_called()


class TestGreenboardFixture:
    @pytest.mark.asyncio
    async def test_no_greenboard_config_skips_upload(self):
        """All three credentials must be set; any None means no upload."""
        cblpytest = _make_cblpytest(url=None, username=None, password=None)
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_config_skips_upload(self):
        """URL present but missing username/password still skips upload."""
        cblpytest = _make_cblpytest(username=None, password=None)
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_result_upload_flag_skips_upload(self):
        """--no-result-upload flag suppresses the upload even when config is present."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(no_upload=True)
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_servers_or_gateways_skips_upload(self):
        """Empty test_servers and sync_gateways means nothing to report; skip upload."""
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_cbl_platform_and_os_from_test_server(self):
        """Platform and OS come from test server info when no SGW markers are present."""
        server = _make_server(
            cbl="couchbase-lite-ios", library_version="3.2.0-b0001", os_name="iOS"
        )
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.platform == "couchbase-lite-ios"
        assert test_run.os == "iOS"
        assert test_run.version == "3.2.0"
        assert test_run.build == 1

    @pytest.mark.asyncio
    async def test_sgw_marker_keeps_sync_gateway_platform(self):
        """When a test carries @pytest.mark.sgw the platform stays 'sync-gateway'."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()  # setup — uploader created and registered
            uploader = config.pluginmanager.register.call_args[0][0]
            drive_hook(
                uploader, make_report("call", passed=True), make_item(markers=["sgw"])
            )
            try:
                await gen.__anext__()  # teardown — upload called
            except StopAsyncIteration:
                pass
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.platform == "sync-gateway"

    @pytest.mark.asyncio
    async def test_upg_sgw_marker_keeps_sync_gateway_platform(self):
        """@pytest.mark.upg_sgw also forces platform to 'sync-gateway'."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = config.pluginmanager.register.call_args[0][0]
            drive_hook(
                uploader,
                make_report("call", passed=True),
                make_item(markers=["upg_sgw"]),
            )
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.platform == "sync-gateway"

    @pytest.mark.asyncio
    async def test_os_name_defaults_to_na_without_system_name(self):
        """If the device dict has no 'systemName' key, os stays 'n/a'."""
        info = GetRootResponse(
            status_code=200,
            uuid="test-uuid",
            json={
                "version": "3.2.0-b0001",
                "apiVersion": 1,
                "cbl": "couchbase-lite-ios",
                "device": {},
            },
        )
        server = MagicMock(spec=TestServer)
        server.get_info = AsyncMock(return_value=info)
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.os == "n/a"

    @pytest.mark.asyncio
    async def test_sgw_version_populated_from_gateway(self):
        """SGW version is fetched from sync_gateways[0] and appears in the document."""
        sgw = MagicMock()
        sgw.get_version = AsyncMock(return_value=SyncGatewayVersion("3.3.3(271;abc)"))
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.sgw_version == "3.3.3-271"

    @pytest.mark.asyncio
    async def test_only_sync_gateway_no_test_server(self):
        """Only sync_gateways present (no test servers) still triggers upload with sync-gateway platform."""
        sgw = MagicMock()
        sgw.get_version = AsyncMock(return_value=SyncGatewayVersion("4.0.0(350;def)"))
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_called_once()
        test_run: IntegrationTestRun = mock_upload.call_args[0][0]
        assert test_run.platform == "sync-gateway"
        assert test_run.os == "n/a"
        assert test_run.sgw_version == "4.0.0-350"

    @pytest.mark.asyncio
    async def test_upload_exception_is_caught_and_plugin_unregistered(self):
        """An exception from _upload_document is swallowed; the finally block still unregisters."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document",
            side_effect=RuntimeError("connection refused"),
        ):
            await _run_fixture(_raw_greenboard(cblpytest, config))  # must not raise
        config.pluginmanager.unregister.assert_called_once()

    @pytest.mark.asyncio
    async def test_uploader_registered_before_yield_unregistered_after(self):
        """The uploader is a registered plugin during the session and cleaned up afterward."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document"):
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()  # setup
            uploader = config.pluginmanager.register.call_args[0][0]
            assert isinstance(uploader, GreenboardUploader)
            config.pluginmanager.unregister.assert_not_called()
            try:
                await gen.__anext__()  # teardown
            except StopAsyncIteration:
                pass
        config.pluginmanager.unregister.assert_called_once_with(uploader)
