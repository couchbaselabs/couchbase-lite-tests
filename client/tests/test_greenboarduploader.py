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
from cbltest.api.edgeserver import EdgeServerVersion
from cbltest.api.syncgateway import SyncGateway, SyncGatewayVersion
from cbltest.configparser import ParsedConfig
from cbltest.greenboarduploader import (
    GreenboardUploader,
    RunResult,
    resolve_branch,
    resolve_job_url,
)
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


@pytest.fixture(autouse=True)
def _clear_build_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ``BUILD_URL`` from the test environment so ``resolve_job_url()``
    deterministically returns ``"local"``.

    Without this, a Jenkins-style host that happens to have ``BUILD_URL``
    exported in the shell would leak its real value into doc assertions
    and flake the suite. Tests that exercise the BUILD_URL-present path
    set it explicitly via ``monkeypatch.setenv``.
    """
    monkeypatch.delenv("BUILD_URL", raising=False)


@pytest.fixture(autouse=True)
def _clear_branch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip Jenkins' branch env vars so ``resolve_branch()`` is driven only by
    what each test sets explicitly.

    Same rationale as :func:`_clear_build_url`: a Jenkins agent exports
    ``GIT_BRANCH``/``BRANCH_NAME``, which would otherwise leak a real branch
    into the gate and mask the skip-path assertions. Tests that need a branch
    pass it via ``--branch`` (see ``_make_pytestconfig``) or set the env var
    explicitly with ``monkeypatch.setenv``.
    """
    monkeypatch.delenv("GIT_BRANCH", raising=False)
    monkeypatch.delenv("BRANCH_NAME", raising=False)


def make_report(when: Literal["setup", "call", "teardown"], *, passed: bool = True) -> TestReport:
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


def drive_hook(uploader: GreenboardUploader, report: TestReport, item: MagicMock | None = None) -> None:
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
        mock_response.json.return_value = {"bootstrap": {"server": "couchbase://localhost"}}
        with patch("cbltest.api.syncgateway.requests.get", return_value=mock_response):
            super().__init__("localhost", "admin", "password")
        self._version_str = version_str

    async def get_version(self) -> SyncGatewayVersion:
        return SyncGatewayVersion(self._version_str)


class FakeEdgeServer:
    """Test-only stand-in for EdgeServer that returns a fixed version.

    Unlike :class:`FakeSyncGateway` this does not subclass the real
    ``EdgeServer``: that constructor reads and decodes a config file off disk.
    The greenboard fixture only ever calls ``get_version()``, so a duck type
    is enough.
    """

    def __init__(self, version_str: str) -> None:
        self._version_str = version_str

    async def get_version(self) -> EdgeServerVersion:
        return EdgeServerVersion(self._version_str)


class FakeTestServer(testserver.TestServer):
    """Test-only TestServer that returns a fixed GetRootResponse from get_info."""

    def __init__(self, get_info_fn: Callable[[], GetRootResponse]) -> None:
        super().__init__(RequestFactory(ParsedConfig({})), 0, "http://localhost:8080", "1")
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
    edge_servers: list | None = None,
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
    cblpytest._CBLPyTest__test_servers = test_servers if test_servers is not None else []
    cblpytest._CBLPyTest__sync_gateways = sync_gateways if sync_gateways is not None else []
    cblpytest._CBLPyTest__edge_servers = edge_servers if edge_servers is not None else []
    return cblpytest


def _make_pytestconfig(*, no_upload: bool = False, branch: str | None = "main") -> pytest.Config:
    # Resolve relative to this test file so the helper works regardless of
    # pytest's cwd. A cwd-relative "tests/empty_config.json" only worked
    # when pytest was invoked from the client/ directory.
    args = ["--config", str(Path(__file__).with_name("empty_config.json"))]
    if no_upload:
        args.append("--no-result-upload")
    # Default to the 'main' branch so the greenboard branch gate lets the
    # upload proceed; the fixture only publishes results from main. Pass
    # branch=None to simulate a local run (no --branch, and the autouse
    # fixture strips GIT_BRANCH/BRANCH_NAME) and exercise the skip path.
    if branch is not None:
        args += ["--branch", branch]
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
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b1234", None, None)

        mock_upload.assert_called_once()
        assert mock_upload.call_args[0][0] == RunResult(
            build=1234,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=1,
            passCount=2,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    def test_document_platform_and_os(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-net", "Android", "3.2.0-b0050", None, None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=50,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-net",
            os="Android",
            jobUrl="local",
        )

    def test_version_and_build_parsed_from_version_string(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.1-b0136", None, None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=136,
            version="3.2.1",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    def test_sgw_version_field_with_sgw(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("3.3.3(271;abc)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", sgw, None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="3.3.3-271",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    def test_sgw_platform_uses_sgw_version_for_build(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        sgw = SyncGatewayVersion("4.0.0(350;def)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("sync-gateway", "n/a", "n/a", sgw, None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=350,
            version="4.0.0",
            sgwVersion="4.0.0-350",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="n/a",
            jobUrl="local",
        )

    def test_no_sgw_version_sets_na(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    def test_es_version_field_with_es(self):
        """An ES version on a CBL run is recorded but does not key the run."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        es = EdgeServerVersion("1.1.0(45;abc)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, es)

        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="1.1.0-45",
            failCount=0,
            passCount=1,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    def test_es_platform_uses_es_version_for_build(self):
        """An edge-server run is keyed on the ES build, with no CBL version at all."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        es = EdgeServerVersion("1.1.0(45;abc)")

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("edge-server", "n/a", None, None, es)

        assert mock_upload.call_args[0][0] == RunResult(
            build=45,
            version="1.1.0",
            sgwVersion="n/a",
            esVersion="1.1.0-45",
            failCount=0,
            passCount=1,
            platform="edge-server",
            os="n/a",
            jobUrl="local",
        )

    def test_es_platform_without_es_version_skips_upload(self):
        """platform == edge-server with no ES version has nothing to key on, so
        the doc is dropped rather than written as build 0 of 0.0.0."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("edge-server", "n/a", None, None, None)

        mock_upload.assert_not_called()

    def test_setup_failure_skips_upload(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

        mock_upload.assert_not_called()


class TestGreenboardFixture:
    @pytest.mark.asyncio
    async def test_no_greenboard_config_skips_upload(self):
        """All three credentials must be set; any None means no upload."""
        cblpytest = _make_cblpytest(url=None, username=None, password=None)
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_result_upload_flag_skips_upload(self):
        """--no-result-upload flag suppresses the upload even when config is present."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(no_upload=True)
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_servers_or_gateways_skips_upload(self):
        """No test servers, sync gateways *or* edge servers means nothing to
        report; skip upload."""
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[], edge_servers=[])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_cbl_platform_and_os_from_test_server(self):
        """Platform and OS come from test server info when no SGW markers are present."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001", os_name="iOS")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_sgw_marker_keeps_sync_gateway_platform(self):
        """When a test carries @pytest.mark.sgw the platform stays 'sync-gateway'."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            drive_hook(uploader, make_report("call", passed=True), make_item(markers=["sgw"]))
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="iOS",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_upg_sgw_marker_keeps_sync_gateway_platform(self):
        """@pytest.mark.upg_sgw also forces platform to 'sync-gateway'."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
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
            esVersion="n/a",
            failCount=0,
            passCount=1,
            platform="sync-gateway",
            os="iOS",
            jobUrl="local",
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
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="n/a",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_sgw_version_populated_from_gateway(self):
        """SGW version is fetched from sync_gateways[0] and appears in the document."""
        sgw = FakeSyncGateway("3.3.3(271;abc)")
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="3.3.3-271",
            esVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_only_sync_gateway_no_test_server(self):
        """Only sync_gateways present (no test servers) still triggers upload with sync-gateway platform."""
        sgw = FakeSyncGateway("4.0.0(350;def)")
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=350,
            version="4.0.0",
            sgwVersion="4.0.0-350",
            esVersion="n/a",
            failCount=0,
            passCount=0,
            platform="sync-gateway",
            os="n/a",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_es_marker_sets_edge_server_platform(self):
        """@pytest.mark.es plus a live Edge Server switches the platform to
        edge-server and keys the doc on the ES build."""
        es = FakeEdgeServer("1.1.0(45;abc)")
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            drive_hook(uploader, make_report("call", passed=True), make_item(markers=["es"]))
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
        assert mock_upload.call_args[0][0] == RunResult(
            build=45,
            version="1.1.0",
            sgwVersion="n/a",
            esVersion="1.1.0-45",
            failCount=0,
            passCount=1,
            platform="edge-server",
            os="n/a",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_edge_server_present_without_es_marker_keeps_cbl_platform(self):
        """An Edge Server in the config is not on its own enough to retarget the
        doc: without @pytest.mark.es the run stays a CBL run."""
        server = _make_server()
        es = FakeEdgeServer("1.1.0(45;abc)")
        cblpytest = _make_cblpytest(test_servers=[server], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert mock_upload.call_args[0][0] == RunResult(
            build=1,
            version="3.2.0",
            sgwVersion="n/a",
            esVersion="n/a",
            failCount=0,
            passCount=0,
            platform="couchbase-lite-ios",
            os="iOS",
            jobUrl="local",
        )

    @pytest.mark.asyncio
    async def test_upload_exception_propagates_and_plugin_unregistered(self):
        """An exception from _upload_document propagates (fail-loud policy);
        the finally block still unregisters the plugin so the next session
        starts clean."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with (
            patch(
                "cbltest.greenboarduploader.GreenboardUploader._upload_document",
                side_effect=RuntimeError("connection refused"),
            ),
            pytest.raises(RuntimeError, match="connection refused"),
        ):
            await _run_fixture(_raw_greenboard(cblpytest, config))
        assert not any(isinstance(p, GreenboardUploader) for p in config.pluginmanager.get_plugins())

    @pytest.mark.asyncio
    async def test_uploader_registered_before_yield_unregistered_after(self):
        """The uploader is a registered plugin during the session and cleaned up afterward."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document"):
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
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
        version: str | None,
        sgw=None,
        es=None,
    ) -> dict:
        mock_collection = MagicMock(spec=Collection)
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.bucket.return_value.default_collection.return_value = mock_collection

        with (
            patch("cbltest.greenboarduploader.Cluster", return_value=mock_cluster),
            patch("cbltest.greenboarduploader.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = FIXED_NOW
            mock_dt.side_effect = datetime
            uploader.upload(platform, os_name, version, sgw, es)

        _, doc = mock_collection.upsert.call_args[0]
        return doc

    def test_all_fields_standard_run(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=False))

        doc = self._upload_and_capture(uploader, "couchbase-lite-ios", "iOS", "3.2.0-b1234")

        assert doc == {
            **RunResult(
                build=1234,
                version="3.2.0",
                sgwVersion="n/a",
                esVersion="n/a",
                failCount=1,
                passCount=2,
                platform="couchbase-lite-ios",
                os="iOS",
                jobUrl="local",
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
                esVersion="n/a",
                failCount=0,
                passCount=1,
                platform="sync-gateway",
                os="n/a",
                jobUrl="local",
            ).model_dump(by_alias=True),
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }

    def test_all_fields_es_run(self):
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        es = EdgeServerVersion("1.1.0(45;abc)")

        doc = self._upload_and_capture(uploader, "edge-server", "n/a", None, None, es)

        assert doc == {
            **RunResult(
                build=45,
                version="1.1.0",
                sgwVersion="n/a",
                esVersion="1.1.0-45",
                failCount=0,
                passCount=1,
                platform="edge-server",
                os="n/a",
                jobUrl="local",
            ).model_dump(by_alias=True),
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }


class TestResolveJobUrl:
    """Direct unit tests for :func:`resolve_job_url`.

    Documents the contract greenboard's bar/matrix graphs depend on:
    a real Jenkins ``BUILD_URL`` flows through verbatim; off-CI runs
    (or runs where the env var is explicitly cleared) collapse to the
    literal ``"local"`` so the UI never deep-links to a dead URL.
    """

    def test_build_url_present_returns_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUILD_URL", "https://jenkins.example.com/job/foo/123/")
        assert resolve_job_url() == "https://jenkins.example.com/job/foo/123/"

    def test_build_url_absent_returns_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BUILD_URL", raising=False)
        assert resolve_job_url() == "local"

    def test_build_url_empty_returns_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty-string env value is operationally indistinguishable from
        # "not on a Jenkins run" — collapse it to "local" so we never write
        # a bare empty string into the greenboard doc.
        monkeypatch.setenv("BUILD_URL", "")
        assert resolve_job_url() == "local"


class TestJobUrlPropagation:
    """End-to-end coverage: a real ``BUILD_URL`` reaches the uploaded doc
    on both upload paths (standard ``upload`` and ``upload_upgrade_batch``).
    """

    def test_build_url_propagates_to_standard_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        build_url = "https://jenkins.example.com/job/cbl-ios/456/"
        monkeypatch.setenv("BUILD_URL", build_url)
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b1234", None, None)

        assert mock_upload.call_args[0][0].job_url == build_url

    def test_build_url_propagates_to_upgrade_batch(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        build_url = "https://jenkins.example.com/job/upg-sgw/789/"
        monkeypatch.setenv("BUILD_URL", build_url)

        # Minimal results file representing a clean two-step upgrade run.
        results_file = tmp_path / "sgw_upgrade_results.json"
        results_file.write_text(
            '{"upgradePath": ["3.3.0", "4.0.0"], "iterations": ['
            '{"phase": "initial", "nodeIndex": null, "upgradeFrom": "initial", '
            '"upgradeTo": "3.3.0", "build": 100, "passCount": 5, "failCount": 0, '
            '"failed": false}, '
            '{"phase": "complete", "nodeIndex": null, "upgradeFrom": "3.3.0", '
            '"upgradeTo": "4.0.0", "build": 200, "passCount": 5, "failCount": 0, '
            '"failed": false}]}'
        )

        uploader = make_uploader()
        with patch.object(uploader, "_upsert") as mock_upsert:
            uploader.upload_upgrade_batch(str(results_file))

        doc = mock_upsert.call_args[0][0]
        assert doc["jobUrl"] == build_url
        assert doc["platform"] == "sgw-upgrade"


class TestResolveBranch:
    """Direct unit tests for :func:`resolve_branch`.

    Documents the contract the greenboard branch gate depends on: an explicit
    ``--branch`` override wins, otherwise Jenkins' ``GIT_BRANCH`` (with the
    ``origin/`` prefix stripped) then ``BRANCH_NAME``; none set collapses to
    ``None``, the local-run case the gate treats as non-main. GitPython is
    deliberately not consulted — Jenkins checks out a detached HEAD where it
    could not name the branch (see resolve_branch docstring).
    """

    def test_override_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_BRANCH", "origin/release/3.3")
        assert resolve_branch("main") == "main"

    def test_git_branch_used_when_no_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_BRANCH", "main")
        assert resolve_branch() == "main"
        assert resolve_branch(None) == "main"

    def test_git_branch_origin_prefix_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_BRANCH", "origin/main")
        assert resolve_branch() == "main"

    def test_slashed_branch_preserved_after_origin_strip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Only the leading "origin/" is removed; release/X.Y stays intact.
        monkeypatch.setenv("GIT_BRANCH", "origin/release/3.3")
        assert resolve_branch() == "release/3.3"

    def test_branch_name_fallback_for_multibranch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Multibranch pipelines set BRANCH_NAME (no origin/ prefix) instead.
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        monkeypatch.setenv("BRANCH_NAME", "main")
        assert resolve_branch() == "main"

    def test_git_branch_precedes_branch_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_BRANCH", "origin/main")
        monkeypatch.setenv("BRANCH_NAME", "some-feature")
        assert resolve_branch() == "main"

    def test_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        monkeypatch.delenv("BRANCH_NAME", raising=False)
        assert resolve_branch() is None

    def test_empty_values_collapse_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty string is operationally indistinguishable from unset — the
        # same reason resolve_job_url collapses "" to "local".
        monkeypatch.setenv("GIT_BRANCH", "")
        monkeypatch.setenv("BRANCH_NAME", "")
        assert resolve_branch("") is None
        assert resolve_branch(None) is None


class TestBranchGate:
    """The greenboard fixture uploads results only from the 'main' tests
    branch. Feature-branch and local runs carry potentially-modified tests, so
    their results must never be published; the upgrade path stays exempt.
    """

    @pytest.mark.asyncio
    async def test_main_branch_uploads(self) -> None:
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch="main")
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_main_branch_skips_upload(self) -> None:
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch="my-feature-branch")
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_run_skips_upload(self) -> None:
        """No --branch and GIT_BRANCH/BRANCH_NAME stripped => resolve_branch()
        is None => treated as a local run => upload skipped."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch=None)
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_git_branch_env_enables_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI feeds the branch via Jenkins' GIT_BRANCH env var (not --branch);
        'origin/main' there must strip to 'main' and enable the upload."""
        monkeypatch.setenv("GIT_BRANCH", "origin/main")
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch=None)
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_upgrade_path_exempt_from_branch_gate(self) -> None:
        """The upgrade path records regardless of branch. The upg-sgw pipeline
        is deprecated and out of scope, so its per-step recording stays
        unconditional even when the branch resolves non-main."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        # --upgrade-versions set, no --branch and GIT_BRANCH/BRANCH_NAME
        # stripped => the branch resolves non-main, yet the upgrade path runs.
        args = [
            "--config",
            str(Path(__file__).with_name("empty_config.json")),
            "--upgrade-versions",
            "3.3.0,4.0.0",
        ]
        config = pytest.Config.fromdictargs({}, args)
        with patch("cbltest.greenboarduploader.GreenboardUploader.record_upgrade_step") as mock_record:
            await _run_fixture(_raw_greenboard(cblpytest, config))
        mock_record.assert_called_once()