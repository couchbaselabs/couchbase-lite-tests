import asyncio
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import aiohttp
import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.greenboarduploader import EDGE_SERVER_PLATFORM, GreenboardUploader, parse_cbl_version, resolve_branch
from cbltest.logging import cbl_info, cbl_warning

# Edge Server only runs on the 3.x datasets and has no dataset version of its own to report.
EDGE_SERVER_DATASET_VERSION: Final[str] = "3.x"

SYNC_GATEWAY_PLATFORM: Final[str] = "sync-gateway"
PROGET_GET_VERSION_URL: Final[str] = "http://proget.build.couchbase.com:8080/api/get_version"

# Test servers report their CBL as the ProGet product, except these.
_PROGET_PRODUCT_OF_CBL: Final[dict[str, str]] = {
    "couchbase-lite-swift": "couchbase-lite-ios",
    "cbl-reactnative": "couchbase-lite-react-native",
}

# Automatic fixture that uploads results to greenboard, if configured in config.json and --no-result-upload isn't set.
# The actual RunResult upload is deferred to pytest_sessionfinish() below, not done in the fixture's own teardown.


@dataclass
class _PendingRunResult:
    """RunResult parameters gathered in the fixture's teardown (while cblpytest's network clients are still alive) for
    pytest_sessionfinish to upload later."""

    test_platform: str
    os_name: str
    library_version: str
    sgw_version: CouchbaseVersion | None
    es_version: CouchbaseVersion | None
    cbs_version: str
    dataset_version: str
    cbl_platform: str
    xmlpath: str | None


class FinishedItems:
    """The node ids of the items that finished their full setup/call/teardown protocol, whatever the outcome.

    An item cut short by a SIGINT/SIGTERM (converted by sigterm_handler.py), a pytest-timeout session-timeout or
    ``--maxfail`` never reaches ``pytest_runtest_logfinish``, and neither does any item the session stopped before
    reaching, so comparing this against ``session.testscollected`` is how a truncated ("incomplete") run is detected.

    Registered from ``pytest_configure``, not from the ``greenboard`` fixture: that session fixture is only set up by
    the first test that is not skipped, and a skip raised in ``pytest_runtest_setup`` (required_topology, cbse_filter,
    ``@pytest.mark.skip``) precedes fixture setup, so a tracker registered there would miss every leading skip and flag
    a complete run incomplete.
    """

    def __init__(self) -> None:
        self.nodeids: set[str] = set()

    def pytest_runtest_logfinish(self, nodeid: str) -> None:
        self.nodeids.add(nodeid)


@dataclass(frozen=True)
class RunningProduct:
    """A product build the run used: CBL (from the test server), Sync Gateway or Edge Server."""

    platform: str  # the greenboard platform the run is filed under when this is the product under test
    product: str  # its ProGet product
    version: str  # x.y.z
    build: int

    def __str__(self) -> str:
        return f"{self.product} {self.version}-{self.build}"


def cbl_running_product(cbl: str, library_version: str) -> RunningProduct | None:
    """The test server's CBL build, from its ``cbl`` and library version (see ``parse_cbl_version``), or None if
    the build is unparseable."""
    version, build = parse_cbl_version(library_version)
    if build is None:
        return None
    return RunningProduct(cbl, _PROGET_PRODUCT_OF_CBL.get(cbl, cbl), version, build)


async def is_prerelease(session: aiohttp.ClientSession, product: RunningProduct) -> bool:
    """Whether ``product`` runs a prerelease build: one of a version not yet released, or not the release build.
    Raises if ProGet cannot answer."""
    async with session.get(
        PROGET_GET_VERSION_URL, params={"product": product.product, "version": product.version}
    ) as resp:
        resp.raise_for_status()
        info = await resp.json(content_type=None)
    return not (info["IsRelease"] and int(info["BuildNumber"]) == product.build)


async def find_product_under_test(running: Sequence[RunningProduct]) -> RunningProduct | None:
    """The product under test: the only one of ``running`` that is a prerelease build. Every greenboard upload has
    exactly one, so None (logged) when there are none or several. A build ProGet cannot check is logged and taken
    for a release, so one failed lookup does not drop a run whose prerelease the other lookups identify."""

    async def check(session: aiohttp.ClientSession, product: RunningProduct) -> bool:
        try:
            return await is_prerelease(session, product)
        except Exception as e:
            cbl_warning(f"Could not check whether {product} is a prerelease, so taking it for a release: {e}")
            return False

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        checks = await asyncio.gather(*(check(session, product) for product in running))
    prereleases = [product for product, prerelease in zip(running, checks, strict=True) if prerelease]
    if len(prereleases) != 1:
        builds = ", ".join(map(str, prereleases)) or "none"
        cbl_warning(
            f"Greenboard upload skipped: a run must have exactly one prerelease build, the product under test, "
            f"but has {len(prereleases)} ({builds}) among {', '.join(map(str, running)) or 'no builds'}"
        )
        return None
    return prereleases[0]


_finished_key: Final[pytest.StashKey[FinishedItems]] = pytest.StashKey()
_uploader_key: Final[pytest.StashKey[GreenboardUploader]] = pytest.StashKey()
_pending_key: Final[pytest.StashKey[_PendingRunResult]] = pytest.StashKey()


async def resolve_cbs_version(cblpytest: CBLPyTest) -> str:
    """The Couchbase Server version for the greenboard doc: ``"rosmar"`` when Sync Gateway runs on rosmar (no CBS
    involved), else the first CBS node's ``x.y.z-build``, else ``"n/a"`` (no CBS, or the lookup failed). Never raises,
    so it cannot block the upload."""
    if len(cblpytest.sync_gateways) > 0:
        try:
            if await cblpytest.sync_gateways[0].using_rosmar:
                return "rosmar"
        except Exception as e:
            cbl_warning(f"Could not determine whether SGW uses rosmar for greenboard doc: {e}")
    if len(cblpytest.couchbase_servers) == 0:
        return "n/a"
    try:
        return await cblpytest.couchbase_servers[0].get_version()
    except Exception as e:
        cbl_warning(f"Could not fetch CBS version for greenboard doc: {e}")
        return "n/a"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def greenboard(cblpytest: CBLPyTest, pytestconfig: pytest.Config) -> AsyncGenerator[None]:
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
    if len(cblpytest.test_servers) == 0 and len(cblpytest.sync_gateways) == 0 and len(cblpytest.edge_servers) == 0:
        yield
        return

    # Only results produced from the 'main' tests branch are allowed
    # into greenboard.
    branch = resolve_branch(pytestconfig.getoption("--branch"))
    if branch != "main":
        cbl_info(
            "Greenboard upload skipped: results are uploaded only from "
            f"the 'main' tests branch (resolved branch: {branch or 'local'})"
        )
        yield
        return

    uploader = GreenboardUploader(
        cblpytest.config.greenboard_url,
        cblpytest.config.greenboard_username,
        cblpytest.config.greenboard_password,
    )
    pytestconfig.pluginmanager.register(uploader)
    # Stashed before any of the awaits below so pytest_sessionfinish can always find (and unregister) this uploader,
    # even on a partial failure.
    pytestconfig.stash[_uploader_key] = uploader

    yield

    # The run is filed under its product under test: the one prerelease build among those it ran.
    running: list[RunningProduct] = []
    sgw_version: CouchbaseVersion | None = None
    es_version: CouchbaseVersion | None = None
    os_name: str = "n/a"
    library_version: str = "n/a"
    dataset_version: str = "n/a"
    cbl_platform: str = "n/a"
    if len(cblpytest.test_servers) > 0:
        test_server_info = await cblpytest.test_servers[0].info
        library_version = test_server_info.library_version
        dataset_version = cblpytest.test_servers[0].dataset_version
        cbl_platform = test_server_info.cbl
        if "systemName" in test_server_info.device:
            os_name = test_server_info.device["systemName"]
        if (cbl := cbl_running_product(cbl_platform, library_version)) is not None:
            running.append(cbl)
        else:
            cbl_warning(f"Could not parse the CBL version '{library_version}' for greenboard doc")
    if len(cblpytest.sync_gateways) > 0:
        try:
            sgw_version = await cblpytest.sync_gateways[0].get_version()
            running.append(
                RunningProduct(SYNC_GATEWAY_PLATFORM, "sync_gateway", sgw_version.version, sgw_version.build_number)
            )
        except Exception as e:
            cbl_warning(f"Could not fetch SGW version for greenboard doc: {e}")
    if len(cblpytest.edge_servers) > 0:
        try:
            es_version = await cblpytest.edge_servers[0].get_admin_client().get_version()
            running.append(
                RunningProduct(
                    EDGE_SERVER_PLATFORM, "couchbase-edge-server", es_version.version, es_version.build_number
                )
            )
        except Exception as e:
            cbl_warning(f"Could not fetch ES version for greenboard doc: {e}")

    under_test = await find_product_under_test(running)
    if under_test is None:
        return
    test_platform = under_test.platform
    if test_platform == EDGE_SERVER_PLATFORM and len(cblpytest.test_servers) == 0:
        dataset_version = EDGE_SERVER_DATASET_VERSION

    # Upload itself is deferred to pytest_sessionfinish -- see its docstring.
    pytestconfig.stash[_pending_key] = _PendingRunResult(
        test_platform=test_platform,
        os_name=os_name,
        library_version=library_version,
        sgw_version=sgw_version,
        es_version=es_version,
        cbs_version=await resolve_cbs_version(cblpytest),
        dataset_version=dataset_version,
        cbl_platform=cbl_platform,
        xmlpath=pytestconfig.option.xmlpath,
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    """Upload the pending RunResult (if any) and unregister the uploader.

    ``pytest_sessionfinish`` runs after every item's logfinish, including the last, so it's the first point an
    accurate finished-items vs testscollected comparison is possible. ``trylast=True`` further guarantees this runs
    after (a) pytest's own catch-all session-fixture teardown (``_pytest.runner.pytest_sessionfinish``, default
    priority -- what actually invokes the fixture's teardown in a SIGTERM/SIGINT/ session-timeout-interrupted run,
    since the per-item chain never reaches ``nextitem=None`` there) and (b) the junitxml plugin (also default priority)
    writing ``--junitxml``'s output, which ``upload_from_junit_file`` reads.
    """
    uploader = session.config.stash.get(_uploader_key, None)
    if uploader is None:
        return
    try:
        pending = session.config.stash.get(_pending_key, None)
        if pending is None:
            return
        collected = session.testscollected
        finished_ids = session.config.stash[_finished_key].nodeids
        incomplete = len(finished_ids) < collected
        collected_ids = [item.nodeid for item in session.items]
        if pending.xmlpath:
            uploader.upload_from_junit_file(
                Path(pending.xmlpath),
                pending.test_platform,
                pending.os_name,
                pending.library_version,
                pending.sgw_version,
                pending.es_version,
                incomplete=incomplete,
                collected=collected,
                cbs_version=pending.cbs_version,
                dataset_version=pending.dataset_version,
                cbl_platform=pending.cbl_platform,
                collected_ids=collected_ids,
                finished_ids=finished_ids,
            )
        else:
            # No --junitxml (pytest_configure defaults it, but that hook doesn't fire for synthetic Configs in unit
            # tests). Falls back to the in-process counter.
            uploader.upload(
                pending.test_platform,
                pending.os_name,
                pending.library_version,
                pending.sgw_version,
                pending.es_version,
                incomplete=incomplete,
                collected=collected,
                cbs_version=pending.cbs_version,
                dataset_version=pending.dataset_version,
                cbl_platform=pending.cbl_platform,
                collected_ids=collected_ids,
                finished_ids=finished_ids,
            )
    finally:
        session.config.pluginmanager.unregister(uploader)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--no-result-upload",
        action="store_true",
        help="Don't upload results to greenboard",
    )
    group.addoption(
        "--branch",
        type=str,
        default=None,
        help="Optional override for the couchbase-lite-tests (TDK) branch this "
        "run executed from; greenboard results are uploaded only when it "
        "resolves to 'main'. Normally left unset: the branch is auto-detected "
        "from Jenkins' GIT_BRANCH/BRANCH_NAME. Unset off-CI means a local run, "
        "treated as non-main and skipped.",
    )


def track_finished_items(config: pytest.Config) -> FinishedItems:
    """Register (and stash) the tracker that ``pytest_sessionfinish`` reads."""
    tracker = FinishedItems()
    config.stash[_finished_key] = tracker
    config.pluginmanager.register(tracker)
    return tracker


def pytest_configure(config: pytest.Config) -> None:
    """Default ``--junitxml=junit_result.xml`` so pytest_sessionfinish can read pass/fail counts from the XML.

    Done here rather than ``addopts`` in ``client/pyproject.toml``: pytest's rootdir discovery walks up from the cwd
    and picks the repo-root ``pyproject.toml`` for production runs from ``tests/functional``/``tests/multiplatform``/``tests/upgrade_sgw``, never reaching
    ``client/pyproject.toml``. An explicit ``--junitxml=<path>`` on the CLI still wins (pytest's last-wins behavior).
    """
    if not getattr(config.option, "xmlpath", None):
        config.option.xmlpath = "junit_result.xml"
    track_finished_items(config)
