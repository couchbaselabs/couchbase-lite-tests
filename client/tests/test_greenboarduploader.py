"""Tests for GreenboardUploader and the greenboard fixture."""

import inspect
import json
from collections.abc import AsyncGenerator, Callable, Container, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from unittest.mock import AsyncMock, MagicMock, patch

import asyncstdlib
import pluggy._result
import pytest
from _pytest.reports import TestReport
from cbltest import CBLPyTest
from cbltest.api import testserver
from cbltest.api.couchbaseserver import CouchbaseServer, parse_cbs_version
from cbltest.api.edgeserver import EdgeServer, EdgeServerVersion
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import CouchbaseVersion, SyncGateway, SyncGatewayVersion
from cbltest.configparser import ParsedConfig
from cbltest.greenboarduploader import (
    DETAILS_SCHEMA,
    ERROR,
    FAIL,
    MAX_FAILURES,
    MAX_MESSAGE_BYTES,
    MAX_TRACE_BYTES,
    NOTRUN,
    PASS,
    SKIP,
    GreenboardUploader,
    RunResult,
    outcomes_from_junit_xml,
    resolve_branch,
    resolve_job_url,
    sanitize_text,
)
from cbltest.plugins import greenboard_fixture
from cbltest.requests import RequestFactory
from cbltest.responses import GetRootResponse
from couchbase.cluster import Cluster
from couchbase.collection import Collection

pytest_plugins = ["pytester"]

FIXED_NOW = datetime(2024, 3, 15, 12, 0, 0, tzinfo=UTC)
FIXED_UNIX_TS = (FIXED_NOW - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()

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


def make_report(when: Literal["setup", "call", "teardown"], *, passed: bool = True, nodeid: str = "") -> TestReport:
    return TestReport(
        nodeid=nodeid,
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


def finish_item(config: pytest.Config, nodeid: str) -> None:
    """Simulate pytest's ``pytest_runtest_logfinish`` for one item completing its whole runtest protocol. A truncated
    run simply never calls this for the cut-short item."""
    config.stash[greenboard_fixture._finished_key].pytest_runtest_logfinish(nodeid)


class FakeSyncGateway(SyncGateway):
    """Test-only SyncGateway that returns a fixed version without network calls."""

    def __init__(self, version_str: str, *, rosmar: bool = False, rosmar_error: bool = False) -> None:
        super().__init__("localhost", "admin", "password")
        self._version_str = version_str
        self._rosmar = rosmar
        self._rosmar_error = rosmar_error

    async def get_version(self) -> SyncGatewayVersion:
        return SyncGatewayVersion(self._version_str)

    @property
    async def using_rosmar(self) -> bool:
        if self._rosmar_error:
            raise CblTestError("startup config unavailable")
        return self._rosmar


class FakeCouchbaseServer(CouchbaseServer):
    """Test-only CouchbaseServer that returns a fixed version (or fails), skipping the real constructor."""

    def __init__(self, version: str | None = "7.6.4-5146") -> None:
        self._version = version

    async def get_version(self) -> str:
        if self._version is None:
            raise CblTestError("GET /pools returned 500")
        return self._version


class FakeEdgeServer(EdgeServer):
    """Test-only EdgeServer that returns a fixed version.

    The real constructor reads and decodes a config file off disk, so it is
    skipped; the greenboard fixture only ever calls ``get_version()``.
    """

    def __init__(self, version_str: str) -> None:
        self._version_str = version_str

    async def get_version(self) -> CouchbaseVersion:
        return EdgeServerVersion(self._version_str)


class FakeEdgeServerManager(EdgeServerManager):
    """``CBLPyTest.edge_servers`` holds managers, and greenboard takes a client from one."""

    def __init__(self, edge_server: EdgeServer) -> None:
        self._edge_server = edge_server

    def get_admin_client(self) -> EdgeServer:
        return self._edge_server


class FakeTestServer(testserver.TestServer):
    """Test-only TestServer whose info comes from get_info_fn."""

    def __init__(self, get_info_fn: Callable[[], GetRootResponse]) -> None:
        super().__init__(RequestFactory(ParsedConfig({})), 0, "http://localhost:8080", "1")
        self._get_info_fn = get_info_fn

    @asyncstdlib.cached_property
    async def info(self) -> GetRootResponse:
        return self._get_info_fn()


class FakeCBLPyTest(CBLPyTest):
    """Test-only CBLPyTest that supplies fakes directly.

    The real constructor builds TestServer/SyncGateway/CouchbaseServer objects
    from the config, and SyncGateway.__init__ makes a network call, so it cannot
    be used here. Only the three properties greenboard actually reads are
    overridden; the rest of CBLPyTest is deliberately left unwired.
    """

    def __init__(
        self,
        config: ParsedConfig,
        test_servers: Sequence[testserver.TestServer],
        sync_gateways: Sequence[SyncGateway],
        edge_servers: Sequence[EdgeServerManager],
        couchbase_servers: Sequence[CouchbaseServer] = (),
    ) -> None:
        self._config = config
        self._couchbase_servers = couchbase_servers
        self._test_servers = test_servers
        self._sync_gateways = sync_gateways
        self._edge_servers = edge_servers

    @property
    def config(self) -> ParsedConfig:
        return self._config

    @property
    def test_servers(self) -> Sequence[testserver.TestServer]:
        return self._test_servers

    @property
    def sync_gateways(self) -> Sequence[SyncGateway]:
        return self._sync_gateways

    @property
    def edge_servers(self) -> Sequence[EdgeServerManager]:
        return self._edge_servers

    @property
    def couchbase_servers(self) -> Sequence[CouchbaseServer]:
        return self._couchbase_servers


def _make_cblpytest(
    *,
    url: str | None = "couchbase://greenboard.example.com",
    username: str | None = "fakeuser",
    password: str | None = "fakepass",
    test_servers: Sequence[testserver.TestServer] | None = None,
    sync_gateways: Sequence[SyncGateway] | None = None,
    edge_servers: Sequence[EdgeServerManager] | None = None,
    couchbase_servers: Sequence[CouchbaseServer] | None = None,
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
    return FakeCBLPyTest(config, test_servers or [], sync_gateways or [], edge_servers or [], couchbase_servers or [])


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
    config = pytest.Config.fromdictargs({}, args)
    # pytest_configure doesn't fire for a synthetic Config, so install what it would.
    greenboard_fixture.track_finished_items(config)
    return config


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


async def _run_fixture(gen: AsyncGenerator) -> None:
    """Drive an async generator fixture through setup and teardown."""
    await gen.__anext__()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


def _make_session(config: pytest.Config, *, testscollected: int = 0) -> pytest.Session:
    """A ``pytest.Session`` bound to the same ``config`` used to drive the
    fixture, so they share a stash and pluginmanager. ``testscollected``
    defaults to 0, matching the zero items finished by default (incomplete=False)."""
    session = pytest.Session.from_config(config)
    session.testscollected = testscollected
    return session


def finish_session(config: pytest.Config, *, testscollected: int = 0) -> None:
    """Run pytest_sessionfinish the way pytest would, after the fixture has
    been driven to completion."""
    greenboard_fixture.pytest_sessionfinish(_make_session(config, testscollected=testscollected))


class TestCblpytestHelperFidelity:
    """Guard the shape of ``_make_cblpytest`` against ``CBLPyTest`` itself.

    ``CBLPyTest.sync_gateways`` is derived from ``clusters[0].sync_gateways``,
    not from an attribute of its own, so the helper has to populate a cluster.
    These tests fail loudly if that wiring drifts, instead of silently handing
    the fixture an empty gateway list.
    """

    @pytest.mark.asyncio
    async def test_sync_gateways_surface_through_cluster(self) -> None:
        sgw = FakeSyncGateway("4.0.0(350;def)")
        assert list(_make_cblpytest(sync_gateways=[sgw]).sync_gateways) == [sgw]

    def test_sync_gateways_default_to_empty(self) -> None:
        assert list(_make_cblpytest().sync_gateways) == []

    @pytest.mark.asyncio
    async def test_test_servers_and_edge_servers_surface(self) -> None:
        server = _make_server()
        es = FakeEdgeServerManager(FakeEdgeServer("1.1.0(45;abc)"))
        cblpytest = _make_cblpytest(test_servers=[server], edge_servers=[es])
        assert list(cblpytest.test_servers) == [server]
        assert list(cblpytest.edge_servers) == [es]


class TestGreenboardUploaderDocument:
    def test_pass_and_fail_counts_in_document(self) -> None:
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

    def test_document_platform_and_os(self) -> None:
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

    def test_version_and_build_parsed_from_version_string(self) -> None:
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

    def test_sgw_version_field_with_sgw(self) -> None:
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

    def test_sgw_platform_uses_sgw_version_for_build(self) -> None:
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

    def test_no_sgw_version_sets_na(self) -> None:
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

    def test_es_version_field_with_es(self) -> None:
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

    def test_es_platform_uses_es_version_for_build(self) -> None:
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

    def test_es_platform_without_es_version_skips_upload(self) -> None:
        """platform == edge-server with no ES version has nothing to key on, so
        the doc is dropped rather than written as build 0 of 0.0.0."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("edge-server", "n/a", None, None, None)

        mock_upload.assert_not_called()

    def test_incomplete_defaults_to_false(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

        assert mock_upload.call_args[0][0].incomplete is False

    def test_incomplete_true_propagates_to_document(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, incomplete=True)

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
            incomplete=True,
        )

    def test_incomplete_true_propagates_through_junit_file_path(self, tmp_path: Path) -> None:
        """upload_from_junit_file's ``incomplete`` kwarg reaches the document
        the same way its explicit pass/fail overrides do."""
        junit_output = tmp_path / "junit_result.xml"
        junit_output.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="s" tests="2" failures="0" '
            'errors="0" skipped="0"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>'
        )
        uploader = make_uploader()

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload_from_junit_file(
                junit_output, "couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, incomplete=True
            )

        assert mock_upload.call_args[0][0].incomplete is True

    def test_collected_defaults_to_zero(self) -> None:
        """0 means "unknown/not supplied" — old docs and callers that don't
        pass collected should read the same as before this field existed."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

        assert mock_upload.call_args[0][0].collected == 0

    def test_collected_propagates_to_document(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, collected=42)

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
            collected=42,
        )

    def test_collected_propagates_through_junit_file_path(self, tmp_path: Path) -> None:
        """upload_from_junit_file's ``collected`` kwarg reaches the document
        the same way its ``incomplete`` kwarg does."""
        junit_output = tmp_path / "junit_result.xml"
        junit_output.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="s" tests="2" failures="0" '
            'errors="0" skipped="0"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>'
        )
        uploader = make_uploader()

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload_from_junit_file(
                junit_output, "couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, collected=42
            )

        assert mock_upload.call_args[0][0].collected == 42


class TestFinishedItemsTracking:
    """``FinishedItems`` (driven by pytest's real ``pytest_runtest_logfinish`` hook) is what the greenboard fixture
    compares against ``session.testscollected`` to detect a session cut short mid-run."""

    def test_starts_empty(self) -> None:
        assert greenboard_fixture.FinishedItems().nodeids == set()

    def test_records_each_finished_node_id_once(self) -> None:
        tracker = greenboard_fixture.FinishedItems()
        tracker.pytest_runtest_logfinish("t.py::a")
        tracker.pytest_runtest_logfinish("t.py::a")
        tracker.pytest_runtest_logfinish("t.py::b")
        assert tracker.nodeids == {"t.py::a", "t.py::b"}

    def test_makereport_alone_does_not_count_as_finished(self) -> None:
        """A report without a matching logfinish (an item cut short by SIGINT/SIGTERM/session-timeout) must not count
        as finished."""
        config = _make_pytestconfig()
        drive_hook(make_uploader(), make_report("call", passed=True, nodeid="t.py::a"))
        assert config.stash[greenboard_fixture._finished_key].nodeids == set()

    def test_configure_hook_installs_tracker_before_any_fixture(self) -> None:
        config = pytest.Config.fromdictargs({}, ["--config", str(Path(__file__).with_name("empty_config.json"))])
        greenboard_fixture.pytest_configure(config)
        assert config.stash[greenboard_fixture._finished_key] in config.pluginmanager.get_plugins()


class TestOverallFailureGuard:
    """``__overall_fail`` latches on any failed setup/teardown report. It
    suppresses the in-process counter, which stops tallying at that point, but
    not counts supplied by the caller, which are a full tally from a JUnit XML."""

    def test_no_counts_skips_upload(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

        mock_upload.assert_not_called()

    def test_explicit_counts_still_upload(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, pass_count=7, fail_count=2)

        doc = mock_upload.call_args[0][0]
        assert (doc.pass_count, doc.fail_count) == (7, 2)

    def test_partial_counts_skip_upload(self) -> None:
        """One override leaves the other on the truncated in-process counter."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("setup", passed=False))

        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None, pass_count=7)

        mock_upload.assert_not_called()

    def test_sgw_marker_still_recorded(self) -> None:
        """The marker picks the greenboard platform, so the latch must not stop it."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))
        drive_hook(uploader, make_report("call", passed=True), make_item(["sgw"]))

        assert uploader.has_sgw_marker()


def write_junit_xml(path: Path, *, tests: int, failures: int, errors: int, skipped: int = 0) -> Path:
    """Write a minimal pytest-shaped JUnit XML carrying the given tallies."""
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        "<testsuites>"
        f'<testsuite name="pytest" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"></testsuite>'
        "</testsuites>"
    )
    return path


def upload_junit(uploader: GreenboardUploader, xml: Path) -> MagicMock:
    """Drive the JUnit upload path, returning the patched ``_upload_document``."""
    with patch.object(uploader, "_upload_document") as mock_upload:
        uploader.upload_from_junit_file(xml, "couchbase-lite-ios", "iOS", "3.2.0-b0001", None)
    return mock_upload


class TestUploadFromJunitFile:
    def test_counts_derived_from_xml(self, tmp_path: Path) -> None:
        # 5 tests - 1 failure - 1 error - 1 skip = 2 passes. Errors fold into
        # failCount; the greenboard schema has no separate field for them.
        xml = write_junit_xml(tmp_path / "junit.xml", tests=5, failures=1, errors=1, skipped=1)

        doc = upload_junit(make_uploader(), xml).call_args[0][0]
        assert (doc.pass_count, doc.fail_count) == (2, 2)

    def test_uploads_despite_setup_failure(self, tmp_path: Path) -> None:
        """The regression this change fixes: a fixture crash used to discard the
        whole run, even though the XML tally is complete."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))
        xml = write_junit_xml(tmp_path / "junit.xml", tests=3, failures=1, errors=1)

        doc = upload_junit(uploader, xml).call_args[0][0]
        assert (doc.pass_count, doc.fail_count) == (1, 2)

    def test_all_failed_still_uploads(self, tmp_path: Path) -> None:
        """Tests that ran and failed are a real result: a red bar is the signal."""
        xml = write_junit_xml(tmp_path / "junit.xml", tests=3, failures=3, errors=0)

        doc = upload_junit(make_uploader(), xml).call_args[0][0]
        assert (doc.pass_count, doc.fail_count) == (0, 3)

    def test_all_errored_skips_upload(self, tmp_path: Path) -> None:
        """Nothing ran: a harness failure, not a test result."""
        xml = write_junit_xml(tmp_path / "junit.xml", tests=3, failures=0, errors=3)

        upload_junit(make_uploader(), xml).assert_not_called()

    def test_no_tests_collected_skips_upload(self, tmp_path: Path) -> None:
        xml = write_junit_xml(tmp_path / "junit.xml", tests=0, failures=0, errors=0)

        upload_junit(make_uploader(), xml).assert_not_called()

    def test_missing_file_falls_back_to_in_process_counter(self, tmp_path: Path) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        drive_hook(uploader, make_report("call", passed=False))

        doc = upload_junit(uploader, tmp_path / "absent.xml").call_args[0][0]
        assert (doc.pass_count, doc.fail_count) == (1, 1)

    def test_missing_file_with_setup_failure_skips_upload(self, tmp_path: Path) -> None:
        """The missing-file fall-back reads the in-process counter, so the guard
        still applies."""
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))

        upload_junit(uploader, tmp_path / "absent.xml").assert_not_called()


class TestGreenboardFixture:
    """Drives the ``greenboard`` fixture, then calls ``finish_session`` to
    trigger the actual upload -- mirroring the fixture's two-stage design.
    ``TestRealPytestLifecycle`` below additionally verifies that split
    against pytest's real hook-execution order, not just this manual call."""

    @pytest.mark.asyncio
    async def test_no_greenboard_config_skips_upload(self) -> None:
        """All three credentials must be set; any None means no upload."""
        cblpytest = _make_cblpytest(url=None, username=None, password=None)
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_result_upload_flag_skips_upload(self) -> None:
        """--no-result-upload flag suppresses the upload even when config is present."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(no_upload=True)
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_servers_or_gateways_skips_upload(self) -> None:
        """No test servers, sync gateways or edge servers means nothing to
        report; skip upload."""
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[], edge_servers=[])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_cbl_platform_and_os_from_test_server(self) -> None:
        """Platform and OS come from test server info when no SGW markers are present."""
        server = _make_server(cbl="couchbase-lite-ios", library_version="3.2.0-b0001", os_name="iOS")
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
    async def test_sgw_marker_keeps_sync_gateway_platform(self) -> None:
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
            finish_session(config)
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
    async def test_upg_sgw_marker_keeps_sync_gateway_platform(self) -> None:
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
            finish_session(config)
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
    async def test_os_name_defaults_to_na_without_system_name(self) -> None:
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
            finish_session(config)
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
    async def test_sgw_version_populated_from_gateway(self) -> None:
        """SGW version is fetched from sync_gateways[0] and appears in the document."""
        sgw = FakeSyncGateway("3.3.3(271;abc)")
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
    async def test_only_sync_gateway_no_test_server(self) -> None:
        """Only sync_gateways present (no test servers) still triggers upload with sync-gateway platform."""
        sgw = FakeSyncGateway("4.0.0(350;def)")
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[sgw])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
    async def test_es_marker_sets_edge_server_platform(self) -> None:
        """@pytest.mark.min_edge_servers plus a live Edge Server switches the platform
        to edge-server and keys the doc on the ES build."""
        es = FakeEdgeServerManager(FakeEdgeServer("1.1.0(45;abc)"))
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            drive_hook(uploader, make_report("call", passed=True), make_item(markers=["min_edge_servers"]))
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            finish_session(config)
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
    async def test_edge_server_present_without_es_marker_keeps_cbl_platform(self) -> None:
        """An Edge Server in the config is not on its own enough to retarget the
        doc: without @pytest.mark.min_edge_servers the run stays a CBL run."""
        server = _make_server()
        es = FakeEdgeServerManager(FakeEdgeServer("1.1.0(45;abc)"))
        cblpytest = _make_cblpytest(test_servers=[server], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
    async def test_edge_server_only_without_es_marker_skips_upload(self) -> None:
        """An Edge-Server-only topology whose tests never carried
        @pytest.mark.min_edge_servers has no version to key a doc on: there is
        no CBL library version and no SGW version. Skip rather than file the
        run under the default sync-gateway platform."""
        es = FakeEdgeServerManager(FakeEdgeServer("1.1.0(45;abc)"))
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            drive_hook(uploader, make_report("call", passed=True), make_item())
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            # Unregistration is deferred to pytest_sessionfinish, below.
            assert config.pluginmanager.is_registered(uploader)
            finish_session(config)
        mock_upload.assert_not_called()
        assert not config.pluginmanager.is_registered(uploader)

    @pytest.mark.asyncio
    async def test_sync_gateway_with_unmarked_edge_server_still_uploads(self) -> None:
        """The Edge-Server-only skip must not swallow a plain SGW run that
        happens to have an Edge Server in the topology: the SGW version is a
        valid key, so the doc is uploaded under sync-gateway."""
        sgw = FakeSyncGateway("4.0.0(350;def)")
        es = FakeEdgeServerManager(FakeEdgeServer("1.1.0(45;abc)"))
        cblpytest = _make_cblpytest(test_servers=[], sync_gateways=[sgw], edge_servers=[es])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
    async def test_es_marker_with_unreachable_edge_server_skips_upload(self) -> None:
        """An ES-marked run whose get_version() fails has no ES build to key on;
        the platform is still edge-server, and upload() skips instead of
        publishing a 0.0.0 doc."""

        class UnreachableEdgeServer(FakeEdgeServer):
            async def get_version(self) -> CouchbaseVersion:
                raise RuntimeError("connection refused")

        cblpytest = _make_cblpytest(
            test_servers=[], sync_gateways=[], edge_servers=[FakeEdgeServerManager(UnreachableEdgeServer("n/a"))]
        )
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            drive_hook(uploader, make_report("call", passed=True), make_item(markers=["min_edge_servers"]))
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            finish_session(config)
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_exception_propagates_and_plugin_unregistered(self) -> None:
        """An exception from _upload_document propagates out of
        pytest_sessionfinish; its finally block still unregisters the
        plugin."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch(
            "cbltest.greenboarduploader.GreenboardUploader._upload_document",
            side_effect=RuntimeError("connection refused"),
        ):
            await _run_fixture(_raw_greenboard(cblpytest, config))
            with pytest.raises(RuntimeError, match="connection refused"):
                finish_session(config)
        assert not any(isinstance(p, GreenboardUploader) for p in config.pluginmanager.get_plugins())

    @pytest.mark.asyncio
    async def test_uploader_registered_before_yield_unregistered_after(self) -> None:
        """Registered through the fixture's own teardown; only
        pytest_sessionfinish unregisters it."""
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
            assert config.pluginmanager.is_registered(uploader)
            finish_session(config)
        assert not config.pluginmanager.is_registered(uploader)

    @pytest.mark.asyncio
    async def test_incomplete_true_when_session_cut_short(self) -> None:
        """Fewer items finished than were collected sets incomplete=True and
        reports the full planned count via ``collected`` (so the frontend
        can show real coverage, e.g. "2/3", instead of a bare pass/fail
        ratio)."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            for nodeid in ("t.py::a", "t.py::b"):
                drive_hook(uploader, make_report("call", passed=True, nodeid=nodeid))
                finish_item(config, nodeid)
            drive_hook(uploader, make_report("call", passed=True, nodeid="t.py::c"))  # third item cut short
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            finish_session(config, testscollected=3)
        doc = mock_upload.call_args[0][0]
        assert (doc.incomplete, doc.collected) == (True, 3)

    @pytest.mark.asyncio
    async def test_incomplete_false_when_all_collected_items_finish(self) -> None:
        """A clean, fully-completed run still reports its planned count via
        ``collected`` — the frontend doesn't need incomplete=True to show
        coverage, just a nonzero denominator."""
        server = _make_server()
        cblpytest = _make_cblpytest(test_servers=[server])
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            gen = _raw_greenboard(cblpytest, config)
            await gen.__anext__()
            uploader = next(p for p in config.pluginmanager.get_plugins() if isinstance(p, GreenboardUploader))
            for nodeid, passed in (("t.py::a", True), ("t.py::b", False)):
                drive_hook(uploader, make_report("call", passed=passed, nodeid=nodeid))
                finish_item(config, nodeid)
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            finish_session(config, testscollected=2)
        doc = mock_upload.call_args[0][0]
        assert (doc.incomplete, doc.collected) == (False, 2)


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
        sgw: CouchbaseVersion | None = None,
        es: EdgeServerVersion | None = None,
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

    def test_all_fields_standard_run(self) -> None:
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
            "details": DETAILS_SCHEMA,
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }

    def test_all_fields_sgw_run(self) -> None:
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
            "details": DETAILS_SCHEMA,
            "uploaded": FIXED_UNIX_TS,
            "date": "2024-03-15",
        }

    def test_all_fields_es_run(self) -> None:
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
            "details": DETAILS_SCHEMA,
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
            finish_session(config)
        mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_main_branch_skips_upload(self) -> None:
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch="my-feature-branch")
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
        mock_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_run_skips_upload(self) -> None:
        """No --branch and GIT_BRANCH/BRANCH_NAME stripped => resolve_branch()
        is None => treated as a local run => upload skipped."""
        cblpytest = _make_cblpytest(test_servers=[_make_server()])
        config = _make_pytestconfig(branch=None)
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
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
            finish_session(config)
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
            finish_session(config)
        mock_record.assert_called_once()


# Overrides the real `cblpytest` fixture by name to avoid real network I/O,
# while still exercising the real greenboard_fixture module end to end.
# `_upload_document` writes the captured RunResult to a JSON file, since
# the subprocess can't hand a Python object back to the outer test.
_LIFECYCLE_CONFTEST = """
import json
from pathlib import Path

import asyncstdlib
import pytest_asyncio
from cbltest.api import testserver
from cbltest.configparser import ParsedConfig
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.requests import RequestFactory
from cbltest.responses import GetRootResponse

CAPTURED_PATH = Path(__file__).parent / "captured_doc.json"


def _fake_upload_document(self, test_run, *_):
    CAPTURED_PATH.write_text(json.dumps(test_run.model_dump(by_alias=True)))


GreenboardUploader._upload_document = _fake_upload_document


class _FakeConfig:
    greenboard_username = "user"
    greenboard_password = "pass"
    greenboard_url = "couchbase://localhost"


class _FakeTestServer(testserver.TestServer):
    def __init__(self):
        super().__init__(RequestFactory(ParsedConfig({})), 0, "http://localhost:8080", "1")

    @asyncstdlib.cached_property
    async def info(self):
        return GetRootResponse(
            status_code=200,
            uuid="test-uuid",
            json={"version": "3.2.0-b0001", "apiVersion": 1, "cbl": "couchbase-lite-ios", "device": {}},
        )


class _FakeCBLPyTest:
    def __init__(self):
        # Built here, not as a class attribute: _FakeTestServer() needs a
        # running event loop (aiohttp.ClientSession), which only exists once
        # the async fixture body below starts executing.
        self.config = _FakeConfig()
        self.test_servers = [_FakeTestServer()]
        self.sync_gateways = []
        self.edge_servers = []
        self.couchbase_servers = []


@pytest_asyncio.fixture(scope="session")
async def cblpytest():
    yield _FakeCBLPyTest()
"""

_LIFECYCLE_ARGS = (
    "--config",
    str(Path(__file__).with_name("empty_config.json")),
    "--branch",
    "main",
    "-p",
    "no:randomly",
    # cluster_cleanup is autouse and expects a real CBLPyTest.clusters;
    # irrelevant to what's under test here (incomplete/collected detection).
    "-p",
    "no:cluster_cleanup",
)


class TestRealPytestLifecycle:
    """Runs a real pytest sub-session -- through pytest's actual hook
    dispatch, not manually-driven mocks -- against the real
    ``greenboard_fixture`` module. Regression coverage for the bug where
    reading ``items_finished`` inside the fixture's own teardown always
    undercounted the last item (it fires before that item's
    ``pytest_runtest_logfinish``), flagging every complete run incomplete.
    A manually-driven test can't catch this, since it controls exactly when
    each hook fires instead of letting pytest's own scheduler decide.
    ``runpytest_subprocess`` (a real, isolated process) is required here so
    the sandboxed conftest's class-level ``_upload_document`` patch can't
    leak into this file's own process.
    """

    def test_complete_run_not_flagged_incomplete(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest(_LIFECYCLE_CONFTEST)
        pytester.makepyfile("""
            import pytest


            @pytest.mark.asyncio
            async def test_one():
                pass


            @pytest.mark.asyncio
            async def test_two():
                pass


            @pytest.mark.asyncio
            async def test_three():
                pass
        """)
        result = pytester.runpytest_subprocess(*_LIFECYCLE_ARGS)
        result.assert_outcomes(passed=3)

        captured_path = pytester.path / "captured_doc.json"
        assert captured_path.is_file(), (
            f"greenboard never uploaded a doc -- pytest output:\n{result.stdout.str()}\n{result.stderr.str()}"
        )
        doc = json.loads(captured_path.read_text())
        assert (doc["passCount"], doc["failCount"], doc["incomplete"], doc["collected"]) == (3, 0, False, 3)

    def test_maxfail_stops_early_flags_incomplete(self, pytester: pytest.Pytester) -> None:
        """``--maxfail=1`` stops the session after the first failure via the
        same ``session.shouldfail`` early-exit path a session-timeout uses --
        a real, genuinely truncated session."""
        pytester.makeconftest(_LIFECYCLE_CONFTEST)
        pytester.makepyfile("""
            import pytest


            @pytest.mark.asyncio
            async def test_one():
                pass


            @pytest.mark.asyncio
            async def test_two():
                assert False


            @pytest.mark.asyncio
            async def test_three():
                pass
        """)
        result = pytester.runpytest_subprocess(*_LIFECYCLE_ARGS, "--maxfail=1")
        result.assert_outcomes(passed=1, failed=1)

        captured_path = pytester.path / "captured_doc.json"
        assert captured_path.is_file(), (
            f"greenboard never uploaded a doc -- pytest output:\n{result.stdout.str()}\n{result.stderr.str()}"
        )
        doc = json.loads(captured_path.read_text())
        # test_three never ran: 2 finished out of 3 collected.
        assert (doc["passCount"], doc["failCount"], doc["incomplete"], doc["collected"]) == (1, 1, True, 3)


class TestCbsVersion:
    @pytest.mark.parametrize(
        "raw",
        ["7.6.4-5146-enterprise", "7.6.4-5146-community", "7.6.4-5146"],
    )
    def test_edition_suffix_stripped(self, raw: str) -> None:
        assert parse_cbs_version(raw) == "7.6.4-5146"

    def test_unrecognised_version_raises(self) -> None:
        with pytest.raises(CblTestError):
            parse_cbs_version("")

    @pytest.mark.asyncio
    async def test_get_version_reads_pools(self) -> None:
        server = CouchbaseServer.__new__(CouchbaseServer)
        send = AsyncMock(return_value={"implementationVersion": "7.6.4-5146-enterprise"})
        with patch.object(CouchbaseServer, "_CouchbaseServer__send_request", send):
            assert await server.get_version() == "7.6.4-5146"
        send.assert_awaited_once_with("get", "/pools")

    async def _doc(
        self,
        sync_gateways: Sequence[SyncGateway] | None = None,
        couchbase_servers: Sequence[CouchbaseServer] | None = None,
    ) -> RunResult:
        cblpytest = _make_cblpytest(
            test_servers=[_make_server()], sync_gateways=sync_gateways, couchbase_servers=couchbase_servers
        )
        config = _make_pytestconfig()
        with patch("cbltest.greenboarduploader.GreenboardUploader._upload_document") as mock_upload:
            await _run_fixture(_raw_greenboard(cblpytest, config))
            finish_session(config)
        return mock_upload.call_args[0][0]

    @pytest.mark.asyncio
    async def test_cbs_version_recorded(self) -> None:
        doc = await self._doc(
            sync_gateways=[FakeSyncGateway("3.3.3(271;abc)")], couchbase_servers=[FakeCouchbaseServer()]
        )
        assert doc.cbs_version == "7.6.4-5146"

    @pytest.mark.asyncio
    async def test_cbl_run_without_sgw_still_gets_cbs_version(self) -> None:
        doc = await self._doc(couchbase_servers=[FakeCouchbaseServer()])
        assert doc.cbs_version == "7.6.4-5146"

    @pytest.mark.asyncio
    async def test_lookup_failure_gives_na_and_still_uploads(self) -> None:
        doc = await self._doc(couchbase_servers=[FakeCouchbaseServer(None)])
        assert doc.cbs_version == "n/a"

    @pytest.mark.asyncio
    async def test_rosmar_wins_over_present_cbs(self) -> None:
        doc = await self._doc(
            sync_gateways=[FakeSyncGateway("4.0.0(350;def)", rosmar=True)], couchbase_servers=[FakeCouchbaseServer()]
        )
        assert doc.cbs_version == "rosmar"

    @pytest.mark.asyncio
    async def test_rosmar_check_failure_falls_back_to_cbs(self) -> None:
        doc = await self._doc(
            sync_gateways=[FakeSyncGateway("4.0.0(350;def)", rosmar_error=True)],
            couchbase_servers=[FakeCouchbaseServer()],
        )
        assert doc.cbs_version == "7.6.4-5146"

    @pytest.mark.asyncio
    async def test_no_cbs_gives_na(self) -> None:
        doc = await self._doc(sync_gateways=[FakeSyncGateway("3.3.3(271;abc)")])
        assert doc.cbs_version == "n/a"


class TestSanitizeText:
    def test_ansi_stripped(self) -> None:
        assert sanitize_text("\x1b[31mE\x1b[0m   assert 1 == 2") == "E   assert 1 == 2"

    @pytest.mark.parametrize(
        "text, secret",
        [
            ("connect password=hunter2 failed", "hunter2"),
            ("{'password': 'hunter2'}", "hunter2"),
            ('{"admin_password": "hunter2"}', "hunter2"),
            ("Authorization: Basic aHVudGVyMg==", "aHVudGVyMg=="),
            ("headers={'Authorization': 'Bearer abc.def'}", "abc.def"),
            ("GET http://admin:hunter2@host:4985/db", "hunter2"),
            ("api_key=hunter2", "hunter2"),
        ],
    )
    def test_secrets_redacted(self, text: str, secret: str) -> None:
        out = sanitize_text(text)
        assert secret not in out
        assert "[REDACTED]" in out

    def test_plain_text_untouched(self) -> None:
        assert sanitize_text("AssertionError: assert 1 == 2") == "AssertionError: assert 1 == 2"


def write_junit_cases(path: Path, cases: str, *, tests: int, failures: int, errors: int) -> Path:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        f'<testsuite name="pytest" tests="{tests}" failures="{failures}" errors="{errors}" skipped="0">'
        f"{cases}</testsuite></testsuites>"
    )
    return path


_FAIL_CASE = (
    '<testcase classname="tests.QE.test_db_gone.TestDbGone" name="test_x[param]">'
    '<failure message="AssertionError: boom&#10;assert 1 == 2">Traceback\nassert 1 == 2</failure></testcase>'
)
_ERROR_CASE = (
    '<testcase classname="tests.QE.test_other" name="test_y"><error message="failed on setup">tb</error></testcase>'
)
_PASS_CASE = '<testcase classname="tests.QE.test_other" name="test_ok"/>'


@dataclass
class Uploaded:
    """The arguments the uploader handed to ``_upload_document``."""

    run: RunResult
    tests: dict[str, str]
    failures: list[dict]
    truncated: bool


def uploaded(mock_upload: MagicMock) -> Uploaded:
    return Uploaded(*mock_upload.call_args[0])


def make_named_report(
    nodeid: str, when: Literal["setup", "call", "teardown"], outcome: Literal["passed", "failed", "skipped"]
) -> TestReport:
    return TestReport(
        nodeid=nodeid,
        location=("", 0, ""),
        keywords={},
        outcome=outcome,
        longrepr=None,
        when=when,
    )


def upload_in_process(
    uploader: GreenboardUploader,
    *,
    pass_count: int | None = None,
    fail_count: int | None = None,
    incomplete: bool = False,
    collected_ids: Sequence[str] | None = None,
    finished_ids: Container[str] | None = None,
) -> Uploaded:
    with patch.object(uploader, "_upload_document") as mock_upload:
        uploader.upload(
            "couchbase-lite-ios",
            "iOS",
            "3.2.0-b0001",
            None,
            None,
            pass_count=pass_count,
            fail_count=fail_count,
            incomplete=incomplete,
            collected_ids=collected_ids,
            finished_ids=finished_ids,
        )
    return uploaded(mock_upload)


def count(tests: dict[str, str], outcome: str) -> int:
    return sum(1 for v in tests.values() if v == outcome)


class TestFailuresList:
    def test_junit_entries_for_failure_and_error(self, tmp_path: Path) -> None:
        xml = write_junit_cases(
            tmp_path / "j.xml", _FAIL_CASE + _ERROR_CASE + _PASS_CASE, tests=3, failures=1, errors=1
        )

        up = uploaded(upload_junit(make_uploader(), xml))

        assert up.failures == [
            {
                "test": "tests/QE/test_db_gone.py::TestDbGone::test_x[param]",
                "kind": "failure",
                "phase": "call",
                "message": "AssertionError: boom",
                "trace": "Traceback\nassert 1 == 2",
            },
            {
                "test": "tests/QE/test_other.py::test_y",
                "kind": "error",
                "phase": None,
                "message": "failed on setup",
                "trace": "tb",
            },
        ]
        # Option A: failCount still folds errors in, and the list matches it.
        assert up.run.fail_count == len(up.failures) == 2
        assert up.truncated is False

    def test_junit_path_ignores_in_process_outcomes(self, tmp_path: Path) -> None:
        """A hook-recorded failure must not leak into a JUnit-derived upload."""
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("in/process.py::test_z", "call", "failed"))
        xml = write_junit_cases(tmp_path / "j.xml", _FAIL_CASE + _PASS_CASE, tests=2, failures=1, errors=0)

        up = uploaded(upload_junit(uploader, xml))

        assert [f["test"] for f in up.failures] == ["tests/QE/test_db_gone.py::TestDbGone::test_x[param]"]
        assert "in/process.py::test_z" not in up.tests
        assert up.run.fail_count == len(up.failures) == 1

    def test_junit_path_with_setup_latch_uses_xml_outcomes(self, tmp_path: Path) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))
        xml = write_junit_cases(tmp_path / "j.xml", _ERROR_CASE + _PASS_CASE, tests=2, failures=0, errors=1)

        up = uploaded(upload_junit(uploader, xml))

        assert [f["kind"] for f in up.failures] == ["error"]
        assert count(up.tests, ERROR) == 1

    def test_in_process_entries_match_fail_count(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("call", passed=True))
        report = make_report("call", passed=False)
        report.nodeid = "tests/QE/test_a.py::test_x"
        drive_hook(uploader, report)

        up = upload_in_process(uploader)

        assert up.run.fail_count == len(up.failures) == 1
        assert up.failures[0]["test"] == "tests/QE/test_a.py::test_x"
        assert up.failures[0]["kind"] == "failure"
        assert up.failures[0]["phase"] == "call"
        assert "trace" not in up.failures[0]

    def test_in_process_list_stops_at_latch(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_report("setup", passed=False))
        drive_hook(uploader, make_report("call", passed=False))

        assert upload_in_process(uploader, pass_count=0, fail_count=0).failures == []

    def test_entries_capped_and_flagged(self, tmp_path: Path) -> None:
        cases = "".join(
            f'<testcase classname="a.test_m" name="t{i}"><failure message="m">tb</failure></testcase>'
            for i in range(MAX_FAILURES + 5)
        )
        xml = write_junit_cases(tmp_path / "j.xml", cases, tests=MAX_FAILURES + 5, failures=MAX_FAILURES + 5, errors=0)

        up = uploaded(upload_junit(make_uploader(), xml))

        assert len(up.failures) == MAX_FAILURES
        assert up.truncated is True
        assert up.run.fail_count == MAX_FAILURES + 5
        # ::tests is never capped, so it still names every failed test.
        assert count(up.tests, FAIL) == MAX_FAILURES + 5

    def test_trace_keeps_tail_on_char_boundary_and_message_is_capped(self, tmp_path: Path) -> None:
        trace = "head-" + "é" * MAX_TRACE_BYTES + "-TAIL"
        message = "x" * (MAX_MESSAGE_BYTES + 100)
        cases = f'<testcase classname="a.test_m" name="t"><failure message="{message}">{trace}</failure></testcase>'
        xml = write_junit_cases(tmp_path / "j.xml", cases, tests=1, failures=1, errors=0)

        entry = uploaded(upload_junit(make_uploader(), xml)).failures[0]

        assert len(entry["trace"].encode()) <= MAX_TRACE_BYTES
        assert entry["trace"].endswith("-TAIL")
        assert "head-" not in entry["trace"]
        assert len(entry["message"].encode()) == MAX_MESSAGE_BYTES

    def test_empty_trace_is_omitted(self, tmp_path: Path) -> None:
        cases = '<testcase classname="a.test_m" name="t"><failure message="m"></failure></testcase>'
        xml = write_junit_cases(tmp_path / "j.xml", cases, tests=1, failures=1, errors=0)

        assert "trace" not in uploaded(upload_junit(make_uploader(), xml)).failures[0]

    def test_secrets_scrubbed_in_message_and_trace(self, tmp_path: Path) -> None:
        cases = (
            '<testcase classname="a.test_m" name="t"><failure message="bad password=hunter2">'
            "GET http://admin:hunter2@host/db</failure></testcase>"
        )
        xml = write_junit_cases(tmp_path / "j.xml", cases, tests=1, failures=1, errors=0)

        entry = uploaded(upload_junit(make_uploader(), xml)).failures[0]

        assert "hunter2" not in entry["message"]
        assert "hunter2" not in entry["trace"]


class TestTestOutcomes:
    """The ``K::tests`` doc and its invariants against passCount/failCount."""

    def test_junit_outcomes_and_invariants(self, tmp_path: Path) -> None:
        skipped = '<testcase classname="a.test_s" name="t"><skipped message="xfail"/></testcase>'
        xml = write_junit_cases(
            tmp_path / "j.xml", _FAIL_CASE + _ERROR_CASE + _PASS_CASE + skipped, tests=4, failures=1, errors=1
        )
        xml.write_text(xml.read_text().replace('skipped="0"', 'skipped="1"'))

        up = uploaded(upload_junit(make_uploader(), xml))

        assert up.tests == {
            "tests/QE/test_db_gone.py::TestDbGone::test_x[param]": FAIL,
            "tests/QE/test_other.py::test_y": ERROR,
            "tests/QE/test_other.py::test_ok": PASS,
            "a/test_s.py::t": SKIP,
        }
        assert count(up.tests, PASS) == up.run.pass_count
        assert count(up.tests, FAIL) + count(up.tests, ERROR) == up.run.fail_count
        assert NOTRUN not in up.tests.values()

    def test_junit_test_ids_match_failure_ids(self, tmp_path: Path) -> None:
        xml = write_junit_cases(
            tmp_path / "j.xml", _FAIL_CASE + _ERROR_CASE + _PASS_CASE, tests=3, failures=1, errors=1
        )

        up = uploaded(upload_junit(make_uploader(), xml))

        for entry in up.failures:
            assert up.tests[entry["test"]] == (FAIL if entry["kind"] == "failure" else ERROR)

    def test_junit_never_reports_notrun_even_when_incomplete(self, tmp_path: Path) -> None:
        xml = write_junit_cases(tmp_path / "j.xml", _FAIL_CASE + _PASS_CASE, tests=2, failures=1, errors=0)
        uploader = make_uploader()
        with patch.object(uploader, "_upload_document") as mock_upload:
            uploader.upload_from_junit_file(
                xml, "couchbase-lite-ios", "iOS", "3.2.0-b0001", None, incomplete=True, collected_ids=["x::never_ran"]
            )

        assert NOTRUN not in uploaded(mock_upload).tests.values()

    def test_in_process_outcomes_and_invariants(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::a", "call", "passed"))
        drive_hook(uploader, make_named_report("t.py::b", "call", "passed"))
        drive_hook(uploader, make_named_report("t.py::c", "call", "failed"))
        drive_hook(uploader, make_named_report("t.py::d", "call", "skipped"))  # includes xfail
        drive_hook(uploader, make_named_report("t.py::e", "setup", "skipped"))  # skipped before the call phase

        up = upload_in_process(uploader)

        assert up.tests == {"t.py::a": PASS, "t.py::b": PASS, "t.py::c": FAIL, "t.py::d": SKIP, "t.py::e": SKIP}
        assert count(up.tests, PASS) == up.run.pass_count == 2
        assert count(up.tests, FAIL) == up.run.fail_count == 1
        assert ERROR not in up.tests.values()
        assert [f["test"] for f in up.failures] == ["t.py::c"]

    def test_in_process_notrun_only_when_incomplete(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::a", "call", "passed"))
        ids = ["t.py::a", "t.py::b", "t.py::c"]

        complete = upload_in_process(uploader, incomplete=False, collected_ids=ids)
        incomplete = upload_in_process(uploader, incomplete=True, collected_ids=ids)

        assert complete.tests == {"t.py::a": PASS}
        assert incomplete.tests == {"t.py::a": PASS, "t.py::b": NOTRUN, "t.py::c": NOTRUN}
        assert incomplete.run.pass_count == 1  # notrun never counts

    def test_skip_count_junit_includes_xfail(self, tmp_path: Path) -> None:
        skipped = (
            '<testcase classname="a.test_s" name="t1"><skipped message="s"/></testcase>'
            '<testcase classname="a.test_s" name="t2"><skipped type="pytest.xfail" message="xfail"/></testcase>'
        )
        xml = write_junit_cases(tmp_path / "j.xml", _PASS_CASE + skipped, tests=3, failures=0, errors=0)
        xml.write_text(xml.read_text().replace('skipped="0"', 'skipped="2"'))

        up = uploaded(upload_junit(make_uploader(), xml))

        assert up.run.skip_count == count(up.tests, SKIP) == 2
        assert up.run.pass_count == 1

    def test_skip_count_in_process_and_finished_but_unrecorded_is_skip(self) -> None:
        """A test that finished with no outcome recorded can only be a skip raised before the uploader was
        registered."""
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::ran", "call", "passed"))
        drive_hook(uploader, make_named_report("t.py::xfailed", "call", "skipped"))
        ids = ["t.py::early_skip", "t.py::ran", "t.py::xfailed", "t.py::never"]

        up = upload_in_process(
            uploader,
            incomplete=True,
            collected_ids=ids,
            finished_ids={"t.py::early_skip", "t.py::ran", "t.py::xfailed"},
        )

        assert up.tests == {"t.py::early_skip": SKIP, "t.py::ran": PASS, "t.py::xfailed": SKIP, "t.py::never": NOTRUN}
        assert up.run.skip_count == 2

    def test_skip_count_defaults_to_zero(self) -> None:
        assert upload_in_process(make_uploader()).run.skip_count == 0

    def test_in_process_setup_error_is_recorded_as_error(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::a", "setup", "failed"))

        assert upload_in_process(uploader, pass_count=0, fail_count=0).tests == {"t.py::a": ERROR}

    def test_teardown_error_overrides_passed_call(self) -> None:
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::a", "call", "passed"))
        drive_hook(uploader, make_named_report("t.py::a", "teardown", "failed"))

        assert upload_in_process(uploader, pass_count=0, fail_count=0).tests == {"t.py::a": ERROR}

    def test_outcomes_from_junit_xml_helper(self, tmp_path: Path) -> None:
        xml = write_junit_cases(tmp_path / "j.xml", _PASS_CASE, tests=1, failures=0, errors=0)

        assert outcomes_from_junit_xml(xml) == ({"tests/QE/test_other.py::test_ok": PASS}, [])


class TestSiblingDocuments:
    """One upload writes ``K::tests`` and ``K::failures`` first and the run doc ``K`` last."""

    def _real_upload(self, uploader: GreenboardUploader, collection: MagicMock) -> None:
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.bucket.return_value.default_collection.return_value = collection
        with patch("cbltest.greenboarduploader.Cluster", return_value=mock_cluster):
            uploader.upload("couchbase-lite-ios", "iOS", "3.2.0-b0001", None, None)

    def _uploader_with_one_failure(self) -> GreenboardUploader:
        uploader = make_uploader()
        drive_hook(uploader, make_named_report("t.py::a", "call", "passed"))
        drive_hook(uploader, make_named_report("t.py::b", "call", "failed"))
        return uploader

    def test_three_docs_siblings_first_run_doc_last(self) -> None:
        collection = MagicMock(spec=Collection)

        self._real_upload(self._uploader_with_one_failure(), collection)

        (tests_key, tests_doc), (failures_key, failures_doc), (key, run_doc) = (
            call.args for call in collection.upsert.call_args_list
        )
        assert tests_key == f"{key}::tests"
        assert failures_key == f"{key}::failures"
        assert tests_doc == {"runId": key, "tests": {"t.py::a": PASS, "t.py::b": FAIL}}
        assert failures_doc == {
            "runId": key,
            "failures": [{"test": "t.py::b", "kind": "failure", "phase": "call", "message": ""}],
            "failuresTruncated": False,
        }
        assert run_doc["details"] == DETAILS_SCHEMA
        assert "failures" not in run_doc
        assert "failuresTruncated" not in run_doc
        assert run_doc["passCount"] == 1
        assert run_doc["failCount"] == 1

    def test_sibling_write_failure_still_uploads_run_doc_without_details(self) -> None:
        collection = MagicMock(spec=Collection)
        calls: list[str] = []

        def upsert(key: str, doc: dict) -> None:
            if key.endswith("::failures"):
                raise RuntimeError("write failed")
            calls.append(key)

        collection.upsert.side_effect = upsert

        self._real_upload(self._uploader_with_one_failure(), collection)

        run_key = calls[-1]
        assert "::" not in run_key
        assert collection.upsert.call_args[0][0] == run_key
        assert "details" not in collection.upsert.call_args[0][1]

    def test_run_doc_has_no_details_when_never_called_for_upgrade_batch(self, tmp_path: Path) -> None:
        results_file = tmp_path / "r.json"
        results_file.write_text(
            '{"upgradePath": ["3.3.0"], "iterations": [{"phase": "initial", "nodeIndex": null, '
            '"upgradeFrom": "initial", "upgradeTo": "3.3.0", "build": 1, "passCount": 1, "failCount": 0, '
            '"failed": false}]}'
        )
        uploader = make_uploader()
        with patch.object(uploader, "_upsert") as mock_upsert:
            uploader.upload_upgrade_batch(str(results_file))

        assert "details" not in mock_upsert.call_args[0][0]

    def test_leading_skips_do_not_flag_a_complete_run_incomplete(self, pytester: pytest.Pytester) -> None:
        """Regression: skips raised before fixture setup (``@pytest.mark.skip``, topology/cbse skips) used to finish
        before the ``greenboard`` fixture registered its counter, so a run that finished cleanly read as incomplete."""
        pytester.makeconftest(_LIFECYCLE_CONFTEST)
        pytester.makepyfile("""
            import pytest


            @pytest.mark.skip
            def test_skip_one():
                pass


            @pytest.mark.skip
            def test_skip_two():
                pass


            @pytest.mark.asyncio
            async def test_one():
                pass


            @pytest.mark.asyncio
            async def test_two():
                pass
        """)
        result = pytester.runpytest_subprocess(*_LIFECYCLE_ARGS)
        result.assert_outcomes(passed=2, skipped=2)

        doc = json.loads((pytester.path / "captured_doc.json").read_text())
        assert (doc["passCount"], doc["skipCount"], doc["incomplete"], doc["collected"]) == (2, 2, False, 4)

    def test_real_truncation_after_leading_skip_still_flagged_incomplete(self, pytester: pytest.Pytester) -> None:
        """The fix must not lose true positives: a genuinely cut-short session is still incomplete."""
        pytester.makeconftest(_LIFECYCLE_CONFTEST)
        pytester.makepyfile("""
            import pytest


            @pytest.mark.skip
            def test_skip():
                pass


            @pytest.mark.asyncio
            async def test_one():
                assert False


            @pytest.mark.asyncio
            async def test_two():
                pass
        """)
        result = pytester.runpytest_subprocess(*_LIFECYCLE_ARGS, "--maxfail=1")
        result.assert_outcomes(failed=1, skipped=1)

        doc = json.loads((pytester.path / "captured_doc.json").read_text())
        assert (doc["incomplete"], doc["collected"], doc["skipCount"]) == (True, 3, 1)
