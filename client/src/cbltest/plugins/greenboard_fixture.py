import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.greenboarduploader import EDGE_SERVER_PLATFORM, GreenboardUploader, resolve_branch
from cbltest.logging import cbl_info, cbl_warning

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
    xmlpath: str | None


_uploader_key: Final[pytest.StashKey[GreenboardUploader]] = pytest.StashKey()
_pending_key: Final[pytest.StashKey[_PendingRunResult]] = pytest.StashKey()


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
    upgrade_versions_str = pytestconfig.getoption("--upgrade-versions")
    if not upgrade_versions_str:
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

    if upgrade_versions_str:
        # Upgrade job: record this iteration to a state file. The aggregate batch doc is uploaded once at the end by
        # jenkins/pipelines/QE/upg-sgw/upload_greenboard_batch.py. Doesn't touch items_finished, so no need to defer
        # this to sessionfinish.
        results_file = os.environ.get("SGW_UPGRADE_RESULTS_FILE", "/tmp/sgw_upgrade_results.json")
        # The SGW node under upgrade may be mid-restart during rolling phases; record the iteration anyway
        # (as a failure) rather than dropping it silently.
        sgw_version: CouchbaseVersion | None = None
        if len(cblpytest.sync_gateways) > 0:
            try:
                sgw_version = await cblpytest.sync_gateways[0].get_version()
            except Exception as e:
                cbl_warning(
                    f"Could not fetch SGW version for upgrade record: {e}; recording iteration with sgw_version=None"
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
        es_version: CouchbaseVersion | None = None
        test_platform: str = "sync-gateway"
        os_name: str = "n/a"
        library_version: str = "n/a"
        if len(cblpytest.test_servers) > 0:
            test_server_info = await cblpytest.test_servers[0].info
            # A test carrying an sgw marker belongs to SGW, not the CBL platform, even though it also drives a
            # test server.
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
        # A mixed run keeps the test server's platform, so its CBL results are not filed under edge-server.
        if uploader.has_es_marker() and len(cblpytest.edge_servers) > 0:
            if len(cblpytest.test_servers) == 0:
                test_platform = EDGE_SERVER_PLATFORM
            try:
                es_version = await cblpytest.edge_servers[0].get_admin_client().get_version()
            except Exception as e:
                cbl_warning(f"Could not fetch ES version for greenboard doc: {e}")
        # Edge-Server-only, no min_edge_servers marker: no CBL or SGW version to key the doc on. Skip rather than file
        # it under sync-gateway.
        if test_platform == "sync-gateway" and len(cblpytest.sync_gateways) == 0 and len(cblpytest.test_servers) == 0:
            cbl_warning(
                "Greenboard upload skipped: only Edge Servers are configured but no test "
                "carried the min_edge_servers marker, so the run has no platform to file under"
            )
            return

        # Upload itself is deferred to pytest_sessionfinish -- see its docstring.
        pytestconfig.stash[_pending_key] = _PendingRunResult(
            test_platform=test_platform,
            os_name=os_name,
            library_version=library_version,
            sgw_version=sgw_version,
            es_version=es_version,
            xmlpath=pytestconfig.option.xmlpath,
        )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    """Upload the pending RunResult (if any) and unregister the uploader.

    ``pytest_sessionfinish`` runs after every item's logfinish, including the last, so it's the first point an
    accurate items_finished vs testscollected comparison is possible. ``trylast=True`` further guarantees this runs
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
        incomplete = uploader.items_finished < collected
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
        "--upgrade-versions",
        type=str,
        default=None,
        help="Comma-separated ordered SGW version list for upgrade jobs "
        "(e.g. '3.3.0,4.0.1,4.1.0'). First is the baseline, rest are upgrade "
        "targets. Triggers sgw-upgrade platform upload.",
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


def pytest_configure(config: pytest.Config) -> None:
    """Default ``--junitxml=junit_result.xml`` so pytest_sessionfinish can read pass/fail counts from the XML.

    Done here rather than ``addopts`` in ``client/pyproject.toml``: pytest's rootdir discovery walks up from the cwd
    and picks the repo-root ``pyproject.toml`` for production runs from ``tests/QE``/``tests/dev_e2e``, never reaching
    ``client/pyproject.toml``. An explicit ``--junitxml=<path>`` on the CLI still wins (pytest's last-wins behavior).
    """
    if not getattr(config.option, "xmlpath", None):
        config.option.xmlpath = "junit_result.xml"
