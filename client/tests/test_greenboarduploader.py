"""Tests for GreenboardUploader and the greenboard fixture."""

import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast
from unittest.mock import MagicMock, patch

import pluggy._result
import pytest
from _pytest.reports import TestReport
from cbltest import CBLPyTest
from cbltest.api import testserver
from cbltest.api.syncgateway import SyncGateway, SyncGatewayVersion
from cbltest.configparser import ParsedConfig
from cbltest.greenboarduploader import GreenboardUploader, RunResult
from cbltest.plugins import greenboard_fixture
from cbltest.requests import RequestFactory
from cbltest.responses import GetRootResponse
from couchbase.cluster import Cluster
from couchbase.collection import Collection

FIXED_NOW = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
FIXED_UNIX_TS = (FIXED_NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()

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


class FakeSyncGateway(SyncGateway):
    """Test-only SyncGateway that returns a fixed version without network calls."""

    def __init__(self, version_str: str) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bootstrap": {"server": "couchbase://localhost"}
        }
        with patch("cbltest.api.syncgateway.requests.get", return_value=mock_response):
            super().__init__("localhost", "admin", "password")
        self._version_str = version_str

    async def get_version(self) -> SyncGatewayVersion:
        return SyncGatewayVersion(self._version_str)


class FakeTestServer(testserver.TestServer):
    """Test-only TestServer that returns a fixed GetRootResponse from get_info."""

    def __init__(self, get_info_fn: Callable[[], GetRootResponse]) -> None:
        super().__init__(
            RequestFactory(ParsedConfig({})), 0, "http://localhost:8080", "1"
        )
        self._get_info_fn = get_info_fn

    async def get_info(self) -> GetRootResponse:
        return self._get_info_fn()


def _make_cblpytest(
    *,
    url: str | None = "couchbase://greenboard.example.com",
    username: str | None = "fakeuser",
    password: str | None = "fakepass",
    test_servers: list | None = None,
    sync_gateways: list | None = None,
) -> CBLPyTest:
    if url is not None and username is not None and password is not None:
        config = ParsedConfig(
            {
                "greenboard": {
                    "hostname": url,
                    "username": username,
                    "password": password,
                }
            }
        )
    else:
        config = ParsedConfig({})
    cblpytest = CBLPyTest.__new__(CBLPyTest)
    cblpytest._CBLPyTest__config = config
    cblpytest._CBLPyTest__test_servers = (
        test_servers if test_servers is not None else []
    )
    cblpytest._CBLPyTest__sync_gateways = (
        sync_gateways if sync_gateways is not None else []
    )
    return cblpytest


def _make_pytestconfig(*, no_upload: bool = False) -> pytest.Config:
    # Resolve relative to this test file so the helper works regardless of
    # pytest's cwd. A cwd-relative "tests/empty_config.json" only worked
    # when pytest was invoked from the client/ directory.
    args = ["--config", str(Path(__file__).with_name("empty_config.json"))]
    if no_upload:
        args.append("--no-result-upload")
    return pytest.Config.fromdictargs({}, args)


def _make_server(
    *,
    cbl: str = "couchbase-lite-ios",
    library_version: str = "3.2.0-b0001",
    os_name: str = "iOS",
) -> testserver.TestServer:
    return FakeTestServer(
        lambda: GetRootResponse(
            status_code=200,
            uuid="test-uuid",
            json={
                "version": library_version,
                "apiVersion": 1,
                "cbl": cbl,
                "device": {"systemName": os_name},
            },
        )
    )


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
        assert mock_upload.call_args[0][0] == RunResult(
            build=1234,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=1,
            passCount=2,
            platform="couchbase-lite-ios",
            os="iOS",
        )

    def test_document_platform_and_os(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-net", "Android", "3.2.0-b0050", None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=50,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-net",
            os="Android",
        )

    def test_version_and_build_parsed_from_version_string(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.1-b0136", None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=136,
            version="3.2.1",
            sgwVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
        )

    def test_sgw_version_field_with_sgw(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("3.3.3(271;abc)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", sgw)

        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="3.3.3-271",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
        )

    def test_sgw_platform_uses_sgw_version_for_build(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("4.0.0(350;def)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("sync-gateway", "n/a", "n/a", sgw)

        assert mock_upload.call_args[0][0] == RunResult(
            build=350,
            version="4.0.0",
            sgwVersion="4.0.0-350",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="n/a",
        )

    def test_no_sgw_version_sets_na(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
        )

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
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="iOS",
        )

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
            await gen.__anext__()
            uploader = next(
                p
                for p in config.pluginmanager.get_plugins()
                if isinstance(p, GreenboardUploader)
            )
            drive_hook(
                uploader, make_report("call", passed=True), make_item(markers=["sgw"])
            )
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="iOS",
        )

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
            uploader = next(
                p
                for p in config.pluginmanager.get_plugins()
                if isinstance(p, GreenboardUploader)
            )
            drive_hook(
                uploader,
                make_report("call", passed=True),
                make_item(markers=["upg_sgw"]),
            )
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="iOS",
        )

    @pytest.mark.asyncio
    async def test_os_name_defaults_to_na_without_system_name(self):
        """If the device dict has no 'systemName' key, os stays 'n/a'."""
        server = FakeTestServer(
            lambda: GetRootResponse(
                status_code=200,
                uuid="test-uuid",
                json={
                    "version": "3.2.0-b0001",
                    "apiVersion": 1,
                    "cbl": "couchbase-lite-ios",
                    "device": {},
                },
            )
        )
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="n/a",
        )

    @pytest.mark.asyncio
    async def test_sgw_version_populated_from_gateway(self):
        """SGW version is fetched from sync_gateways[0] and appears in the document."""
        sgw = FakeSyncGateway("3.3.3(271;abc)")
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="3.3.3-271",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="iOS",
        )

    @pytest.mark.asyncio
    async def test_only_sync_gateway_no_test_server(self):
        """Only sync_gateways present (no test servers) still triggers upload with sync-gateway platform."""
        sgw = FakeSyncGateway("4.0.0(350;def)")
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document"
        ) as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=350,
            version="4.0.0",
            sgwVersion="4.0.0-350",
            failCount=0,
            passCount=0,
            platform="sync-gateway",
            os="n/a",
        )

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
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert not any(
            isinstance(p, GreenboardUploader)
            for p in config.pluginmanager.get_plugins()
        )

    @pytest.mark.asyncio
    async def test_uploader_registered_before_yield_unregistered_after(self):
        """The uploader is a registered plugin during the session and cleaned up afterward."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document"):
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(
                p
                for p in config.pluginmanager.get_plugins()
                if isinstance(p, GreenboardUploader)
            )
            assert config.pluginmanager.is_registered(uploader)
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        assert not config.pluginmanager.is_registered(uploader)


class TestRunResultFullDocument:
    """Verify every field written to the greenboard bucket, including timestamp fields.

    These tests let the real _upsert run but mock out the Couchbase Cluster and
    freeze datetime.now so the uploaded / date fields are deterministic.
    """

    def _upload_and_capture(
        self,
        uploader: GreenboardUploader,
        platform: str,
        os_name: str,
        version: str,
        sgw=None,
    ) -> dict:
        mock_collection = MagicMock(spec=Collection)
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.bucket.return_value.default_collection.return_value = (
            mock_collection
        )

        with (
            patch("cbltest.greenboarduploader.Cluster", return_value=mock_cluster),
            patch("cbltest.greenboarduploader.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = FIXED_NOW
            mock_dt.side_effect = datetime
            uploader.upload(platform, os_name, version, sgw)

        _, doc = mock_collection.upsert.call_args[0]
        return doc

    def test_all_fields_standard_run(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=False))

        doc = self._upload_and_capture(
            uploader, "couchbase-lite-ios", "iOS", "3.2.0-b1234"
        )

        assert doc == {
            **RunResult(
                build=1234,
                version="3.2.0",
                sgwVersion="n/a",
                failCount=1,
                passCount=2,
                platform="couchbase-lite-ios",
                os="iOS",
            ).model_dump(by_alias=True),
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }

    def test_all_fields_sgw_run(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("4.0.0(350;def)")

        doc = self._upload_and_capture(uploader, "sync-gateway", "n/a", "n/a", sgw)

        assert doc == {
            **RunResult(
                build=350,
                version="4.0.0",
                sgwVersion="4.0.0-350",
                failCount=0,
                passCount=1,
                platform="sync-gateway",
                os="n/a",
            ).model_dump(by_alias=True),
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }
