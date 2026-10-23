import os
from collections.abc import Container, Generator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from _pytest.reports import TestReport
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.collection import Collection
from couchbase.options import ClusterOptions
from junitparser import Error, Failure, JUnitXml
from pydantic import BaseModel, ConfigDict, Field

from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.logging import cbl_info, cbl_warning

EDGE_SERVER_PLATFORM = "edge-server"


def count_from_junit_xml(xml_path: Path) -> tuple[int, int, int]:
    """Return ``(passed, failed, errored)`` summed across every
    ``<testsuite>`` in a JUnit XML file at ``xml_path``.

    Per junitparser's mapping of pytest output:

    - ``passed`` = ``tests - failures - errors - skipped`` (the cases that
      ran and asserted successfully).
    - ``failed`` = ``failures`` (cases that ran but assertion-failed).
    - ``errored`` = ``errors`` (cases that never executed — collection
      failure, setup crash, etc.).

    Failures and errors are kept separate so callers can distinguish
    "tests legitimately failed" from "harness was broken and tests didn't
    run." Skipped cases count as neither pass nor fail.

    Used by the greenboard pytest fixture to derive upload counts from
    pytest's ``--junitxml`` output instead of in-process hook-driven
    counters.

    Raises the underlying exception if the file can't be read or parsed.
    """
    xml = JUnitXml.fromfile(str(xml_path))
    total_pass = 0
    total_fail = 0
    total_error = 0
    for suite in xml:
        tests = suite.tests or 0
        failures = suite.failures or 0
        errors = suite.errors or 0
        skipped = suite.skipped or 0
        total_pass += max(0, tests - failures - errors - skipped)
        total_fail += failures
        total_error += errors
    return total_pass, total_fail, total_error


# Greenboard stores one entry per failed/errored test so the UI can show them without Jenkins (which prunes builds).
MAX_FAILURES = 100
MAX_MESSAGE_BYTES = 500
MAX_TRACE_BYTES = 8 * 1024
# Marker on the run doc (absent on old docs) saying its ``K::tests`` and ``K::failures`` sibling docs exist, so the
# frontend never issues a KV get that would 404.
DETAILS_SCHEMA = 1

# Per-test outcomes stored in the ``K::tests`` doc. ``skip`` (which includes xfail) is in neither passCount nor
# failCount; ``notrun`` is only known on the in-process path.
PASS, FAIL, ERROR, SKIP, NOTRUN = "pass", "fail", "error", "skip", "notrun"
_OUTCOME_RANK = {PASS: 0, SKIP: 1, FAIL: 2, ERROR: 3}  # when a test reports several outcomes the worst one wins


def _head(text: str, max_bytes: int) -> str:
    """Keep the start of ``text`` within ``max_bytes`` of UTF-8, cutting on a character boundary."""
    return text.encode()[:max_bytes].decode(errors="ignore")


def _tail(text: str, max_bytes: int) -> str:
    """Keep the end of ``text`` within ``max_bytes`` of UTF-8 (the error is at the bottom of a traceback)."""
    return text.encode()[-max_bytes:].decode(errors="ignore")


def make_failure_entry(
    test: str, kind: str, phase: str | None, message: str | None, trace: str | None
) -> dict[str, Any]:
    """Build one ``failures`` entry. ``trace`` is omitted when absent or empty, never ``""``."""
    lines = (message or "").strip().splitlines()
    entry: dict[str, Any] = {
        "test": test,
        "kind": kind,
        "phase": phase,
        "message": _head(lines[0] if lines else "", MAX_MESSAGE_BYTES),
    }
    clean_trace = _tail((trace or "").strip(), MAX_TRACE_BYTES)
    if clean_trace:
        entry["trace"] = clean_trace
    return entry


def _junit_nodeid(classname: str, name: str) -> str:
    """Rebuild a pytest node id from a JUnit ``classname``/``name``.

    JUnit gives ``tests.QE.test_x.TestX`` + ``test_y[p]``, not the path, so the module is taken to be the first dotted
    segment starting with ``test_``; anything before it is the directory path and anything after is classes.
    """
    parts = classname.split(".") if classname else []
    module_idx = next((i for i, part in enumerate(parts) if part.startswith("test_")), None)
    if module_idx is None:
        return f"{classname}::{name}" if classname else name
    path = "/".join(parts[: module_idx + 1]) + ".py"
    return "::".join([path, *parts[module_idx + 1 :], name])


def outcomes_from_junit_xml(xml_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return ``(tests, failures)`` for a JUnit XML file: every test's outcome keyed by node id, and a ``failures``
    entry for every ``<failure>`` (kind ``failure``) and ``<error>`` (kind ``error``). Built from the same XML
    :py:func:`count_from_junit_xml` counts, so the two cannot diverge.

    JUnit does not record which phase raised, so ``phase`` is ``"call"`` for a failure and ``None`` for an error. Tests
    that never ran are not in the XML, so there are no ``notrun`` outcomes here.
    """
    tests: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    for suite in JUnitXml.fromfile(str(xml_path)):
        for case in suite:
            nodeid = _junit_nodeid(case.classname or "", case.name or "")
            outcome = PASS
            for result in case.result:
                if isinstance(result, Failure):
                    outcome = _worse(outcome, FAIL)
                    failures.append(make_failure_entry(nodeid, "failure", "call", result.message, result.text))
                elif isinstance(result, Error):
                    outcome = _worse(outcome, ERROR)
                    failures.append(make_failure_entry(nodeid, "error", None, result.message, result.text))
                else:
                    outcome = _worse(outcome, SKIP)
            tests[nodeid] = outcome
    return tests, failures


def _worse(a: str, b: str) -> str:
    """The more severe of two outcomes."""
    return a if _OUTCOME_RANK[a] >= _OUTCOME_RANK[b] else b


def format_cbl_version(version: str | None) -> str:
    """Return a CBL library version (e.g. ``3.2.0-b0136``) as ``"x.y.z-build"`` (``3.2.0-136``), like ``sgwVersion``.
    ``"n/a"`` when no test server supplied a version; an unparseable build leaves the raw string.
    """
    if not version or version == "n/a":
        return "n/a"
    components = version.split("-")
    if len(components) < 2:
        return version
    try:
        return f"{components[0]}-{int(components[1].lstrip('b'))}"
    except ValueError:
        return version


def resolve_job_url() -> str:
    """Return the Jenkins build URL for the current run, or ``"local"`` off-CI.

    Jenkins exports ``BUILD_URL`` automatically for every build — the URL
    of the specific run's status page (e.g.
    ``https://jenkins.example.com/job/foo/123/``). That's exactly the
    target greenboard's bar/matrix graphs should deep-link to, so we
    pass it through verbatim. Local pytest invocations have no
    ``BUILD_URL`` set and there are no persisted Jenkins logs to link
    to; those records carry the literal ``"local"`` so the UI can
    render them without dangling at a dead URL.
    """
    return os.environ.get("BUILD_URL") or "local"


def resolve_branch(override: str | None = None) -> str | None:
    """Return the TDK (tests repo) branch this run executed from, or ``None``.

    "Branch" is the branch of the *couchbase-lite-tests* checkout that produced
    these results — not the Couchbase Lite or Sync Gateway release line. The
    greenboard fixture uploads only from ``main`` so feature-branch or local
    runs never publish results from modified tests.

    Auto-detected — nothing needs to be passed on CI. Resolution order:

    1. ``override`` — the ``--branch`` pytest option; an explicit escape hatch
       for manual runs and tests, rarely used in practice.
    2. ``GIT_BRANCH`` — set by Jenkins' git plugin after ``checkout scm``
       (e.g. ``"origin/main"``); the ``origin/`` prefix is stripped.
    3. ``BRANCH_NAME`` — set by Jenkins multibranch pipelines.

    We read the branch from Jenkins' own environment rather than inspecting the
    working tree with a git library (GitPython/pygit2): Jenkins checks out a
    *detached HEAD* at a specific commit, where ``git.Repo.active_branch``
    raises — there is no active branch to name. Jenkins knows the branch it
    cloned and exports it as ``GIT_BRANCH``, which the pytest process inherits,
    so reading it is both reliable and dependency-free. Off-CI none of these
    are set, so the result is ``None`` — the local-run case, which the fixture
    treats as non-main and skips (a local run must never upload, whatever
    branch it happens to be on).
    """
    branch = override or os.environ.get("GIT_BRANCH") or os.environ.get("BRANCH_NAME")
    if not branch:
        return None
    return branch.removeprefix("origin/") or None


class RunResult(BaseModel):
    """
    Store the information for a test run in greenboard
    """

    model_config = ConfigDict(populate_by_name=True)

    build: int  # build number of the component the run is keyed on (CBL, SGW or ES)
    version: str  # major.minor.patch version of the component the run is keyed on
    sgw_version: str = Field(alias="sgwVersion")  # Sync Gateway version, optional
    es_version: str = Field(alias="esVersion")  # Edge Server version, optional
    fail_count: int = Field(alias="failCount")  # number of failing tests
    pass_count: int = Field(alias="passCount")  # number of passing tests
    platform: str  # CBL platform
    os: str  # Operating system for CBL
    job_url: str = Field(alias="jobUrl")  # Jenkins BUILD_URL, or "local" off-CI
    incomplete: bool = False  # True if the session was cut short before every collected test ran
    collected: int = 0  # Planned test count (session.testscollected); 0 means unknown/not supplied
    skip_count: int = Field(0, alias="skipCount")  # tests skipped or xfailed; missing on old docs means unknown
    dataset_version: str = Field("n/a", alias="datasetVersion")  # dataset version the test server used, or "n/a"
    cbl_platform: str = Field("n/a", alias="cblPlatform")  # CBL platform of the test server, or "n/a"
    cbl_version: str = Field("n/a", alias="cblVersion")  # CBL library "x.y.z-build" from the test server, or "n/a"
    cbs_version: str = Field("n/a", alias="cbsVersion")  # "x.y.z-build", "rosmar" (no CBS) or "n/a" (none/unknown)


class GreenboardUploader:
    """
    Uploads test-run results to a greenboard couchbase bucket.

    Two entry points, each for a different upload-time context:

    - :py:meth:`upload` — in-process pytest fixture path. Pass/fail counts
      come from :py:meth:`pytest_runtest_makereport` tallying ``TestReport``
      objects as tests run within the same session.
    - :py:meth:`upload_from_junit_file` — JUnit-XML-driven path. Pass/fail
      counts come from a JUnit XML file produced by pytest's
      ``--junitxml``. Falls back to :py:meth:`upload` if the file is
      absent. Decouples count-collection from in-process pytest hooks
      (needed for pipelines whose pytest invocations are orchestrated
      from a shell script).
    """

    def __init__(self, url: str, username: str, password: str) -> None:
        if "://" not in url:
            url = f"couchbase://{url}"

        self.__url = url
        self.__username = username
        self.__password = password
        self.__fail_count = 0
        self.__pass_count = 0
        self.__overall_fail = False
        self.__has_sgw_marker = False
        self.__has_es_marker = False
        self.__failures: list[dict[str, Any]] = []
        self.__tests: dict[str, str] = {}

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any]:
        outcome = yield
        report: TestReport = outcome.get_result()
        self.__record_outcome(report)
        if report.when != "call":
            if report.failed:
                self.__overall_fail = True
            return

        # Above the short-circuit: tests that still run after the latch must
        # set this, or an SGW run gets filed under the CBL platform.
        if item.get_closest_marker("sgw"):
            self.__has_sgw_marker = True
        if item.get_closest_marker("min_edge_servers"):
            self.__has_es_marker = True

        if self.__overall_fail:
            return

        if report.passed:
            self.__pass_count += 1
        elif report.failed:
            self.__fail_count += 1
            # Same latch as the counter above, so this list always matches the in-process failCount.
            reprcrash = getattr(report.longrepr, "reprcrash", None)
            self.__failures.append(
                make_failure_entry(
                    report.nodeid,
                    "failure",
                    report.when,
                    reprcrash.message if reprcrash is not None else str(report.longrepr or ""),
                    report.longreprtext,
                )
            )

    def __record_outcome(self, report: TestReport) -> None:
        """Fold one setup/call/teardown report into the test's outcome for the ``tests`` doc."""
        if report.failed:
            outcome = FAIL if report.when == "call" else ERROR
        elif report.skipped:
            outcome = SKIP
        elif report.when == "call":
            outcome = PASS
        else:
            return  # a passing setup/teardown says nothing: the call report decides
        self.__tests[report.nodeid] = _worse(outcome, self.__tests.get(report.nodeid, PASS))

    def has_sgw_marker(self) -> bool:
        """
        Returns True if any test in the session has @pytest.mark.sgw marker
        """
        return self.__has_sgw_marker

    def has_es_marker(self) -> bool:
        """
        Returns True if any test in the session has @pytest.mark.min_edge_servers
        """
        return self.__has_es_marker

    def upload(
        self,
        platform: str,
        os_name: str,
        version: str | None,
        sgw_version: CouchbaseVersion | None,
        es_version: CouchbaseVersion | None,
        *,
        pass_count: int | None = None,
        fail_count: int | None = None,
        incomplete: bool = False,
        collected: int = 0,
        cbs_version: str = "n/a",
        dataset_version: str = "n/a",
        cbl_platform: str = "n/a",
        tests: dict[str, str] | None = None,
        failures: list[dict[str, Any]] | None = None,
        collected_ids: Sequence[str] | None = None,
        finished_ids: Container[str] | None = None,
    ) -> None:
        """
        Uploads the results using the specified platform and version.  The reason that they
        are specified here is because they are probably unknown at the time that this object
        is created as they need to be retrieved from the test server.

        :param platform: The platform name (e.g. couchbase-lite-net) as specified by the test server
        :param version: The version string (e.g. 3.2.0-b0136, etc) as specified by the test server
        :param sgw_version: The parsed SGW CouchbaseVersion object, or None if unavailable
        :param pass_count: Optional override for the pass count. When ``None``
            (default), uses the in-process counter populated by
            :py:meth:`pytest_runtest_makereport`. When provided (e.g. the
            greenboard fixture derived counts from a JUnit XML), the supplied
            value is used instead.
        :param fail_count: Optional override for the fail count. Same
            semantics as ``pass_count``.
        :param incomplete: Whether the pytest session was cut short (e.g. a
            Jenkins timeout) before every collected test ran. Computed by
            the greenboard fixture from the items that finished their runtest protocol vs.
            ``session.testscollected``.
        :param collected: The planned test count (``session.testscollected``).
            0 means unknown/not supplied. Lets the frontend show real
            coverage (e.g. "29/42") for a clean-incomplete run, where
            pass/fail counts alone always read as 100%.

        :param dataset_version: The dataset version the test server used, or ``"n/a"`` when no test server was used.
        :param cbl_platform: The CBL platform of the test server (e.g. ``couchbase-lite-c``), or ``"n/a"`` when no test
            server was used. Unlike ``platform`` it is set even when the run is filed under another component.
        :param cbs_version: The Couchbase Server version string (``"x.y.z-build"``), ``"rosmar"`` or ``"n/a"``.
        :param tests: Every test's outcome keyed by node id. When ``None`` (default), uses the in-process outcomes built
            by :py:meth:`pytest_runtest_makereport`.
        :param failures: The failed/errored test entries. Same default as ``tests``. A caller that supplies its own
            counts must supply the matching ``tests`` and ``failures``, as :py:meth:`upload_from_junit_file` does, so
            they can never disagree.
        :param collected_ids: The node ids of every collected test. Ignored when ``tests`` is supplied (a JUnit XML
            cannot name the tests that never ran).
        :param finished_ids: The node ids of the tests that finished their runtest protocol. With ``collected_ids``,
            a collected test with no recorded outcome is ``skip`` if it finished (only a skip raised before the
            fixtures set up, i.e. before this uploader was registered, leaves no outcome) and ``notrun`` otherwise,
            when ``incomplete``.

        A setup/teardown failure skips the upload unless *both* counts are
        supplied: the in-process counter stops tallying at the failure, so
        anything falling back to it publishes a partial result.
        """
        if self.__overall_fail and (pass_count is None or fail_count is None):
            cbl_warning("Setup/teardown failure, skipping upload")
            return

        resolved_pass = pass_count if pass_count is not None else self.__pass_count
        resolved_fail = fail_count if fail_count is not None else self.__fail_count
        all_failures = failures if failures is not None else self.__failures
        all_tests = dict(tests if tests is not None else self.__tests)
        if tests is None:
            for nodeid in collected_ids or ():
                if nodeid in all_tests:
                    continue
                if nodeid in (finished_ids or ()):
                    all_tests[nodeid] = SKIP
                elif incomplete:
                    all_tests[nodeid] = NOTRUN

        parsed_version = "0.0.0"
        parsed_build = 0
        sgw_version_str = "n/a"
        es_version_str = "n/a"

        if sgw_version is not None:
            sgw_ver = sgw_version.version
            sgw_build = sgw_version.build_number
            sgw_version_str = f"{sgw_ver}-{sgw_build}"

        if es_version is not None:
            es_version_str = f"{es_version.version}-{es_version.build_number}"

        if platform == "sync-gateway" and sgw_version is not None:
            # For SGW jobs, use the SGW version directly from the parsed object
            # to avoid the fragile serialize-then-reparse pattern.
            parsed_version = (
                sgw_version.version if sgw_version.version and sgw_version.version != "unknown" else "0.0.0"
            )
            parsed_build = sgw_version.build_number
        elif platform == EDGE_SERVER_PLATFORM:
            # An ES run is keyed on the ES build, and may not involve CBL at all.
            if es_version is None:
                cbl_warning("Greenboard: platform is edge-server but no ES version was available; skipping upload")
                return
            parsed_version = es_version.version if es_version.version and es_version.version != "unknown" else "0.0.0"
            parsed_build = es_version.build_number
        else:
            version_components = (version or "").split("-")

            if len(version_components) > 0 and version_components[0]:
                parsed_version = version_components[0]

            if len(version_components) > 1:
                try:
                    # Handles build numbers like 'b1234' or just '1234'
                    parsed_build = int(version_components[1].lstrip("b"))
                except ValueError:
                    # If the part after '-' is not a number, build remains 0
                    cbl_warning(f"Could not parse build number from '{version}'")

        self._upload_document(
            RunResult(
                build=parsed_build,
                version=parsed_version,
                sgwVersion=sgw_version_str,
                esVersion=es_version_str,
                failCount=resolved_fail,
                passCount=resolved_pass,
                platform=platform,
                os=os_name,
                jobUrl=resolve_job_url(),
                incomplete=incomplete,
                collected=collected,
                skipCount=sum(1 for outcome in all_tests.values() if outcome == SKIP),
                cbsVersion=cbs_version,
                datasetVersion=dataset_version,
                cblPlatform=cbl_platform,
                cblVersion=format_cbl_version(version),
            ),
            all_tests,
            all_failures[:MAX_FAILURES],
            len(all_failures) > MAX_FAILURES,
        )

    def upload_from_junit_file(
        self,
        junit_output: Path,
        platform: str,
        os_name: str,
        version: str | None,
        sgw_version: CouchbaseVersion | None,
        es_version: CouchbaseVersion | None = None,
        *,
        incomplete: bool = False,
        collected: int = 0,
        cbs_version: str = "n/a",
        dataset_version: str = "n/a",
        cbl_platform: str = "n/a",
        collected_ids: Sequence[str] | None = None,
        finished_ids: Container[str] | None = None,
    ) -> None:
        """
        Upload one greenboard doc whose pass/fail counts come from a JUnit
        XML file produced by pytest.

        :param incomplete: Whether the pytest session was cut short before
            every collected test ran. Passed through verbatim to
            :py:meth:`upload`.
        :param collected: The planned test count. Passed through verbatim to
            :py:meth:`upload`.
        :param cbs_version: Passed through verbatim to :py:meth:`upload`.
        :param dataset_version: Passed through verbatim to :py:meth:`upload`.
        :param cbl_platform: Passed through verbatim to :py:meth:`upload`.
        :param collected_ids: Passed through to :py:meth:`upload`, which only uses it on the no-XML fall-back.
        :param finished_ids: Same as ``collected_ids``.

        Policy:
        - If ``junit_output`` doesn't exist, fall back to the in-process
          counter (``self.upload()`` without count overrides). This covers
          the cold-start case where pytest never wrote an XML — e.g.
          ``--junitxml`` was explicitly disabled by the caller.
        - If the file exists but reports zero tests collected, skip the
          upload (selector misfired or the harness never executed
          anything; no signal worth recording).
        - If every collected test errored before running (zero passes,
          zero failures, errors > 0), skip the upload — that's a
          harness/setup failure, not a real test result. A run with
          legitimate assertion failures DOES upload; a red bar is the
          signal that those tests broke and we want to see it.
        - Otherwise, upload with the JUnit-derived counts. Errors are
          collapsed into ``failCount`` on the doc since the greenboard
          schema doesn't distinguish failures from errors.

        Implementation notes:
        - Parse errors from a malformed JUnit XML propagate to the
          caller — a bad XML is a real bug and should fail the Jenkins
          job loudly.
        - An absent JUnit XML is *not* an error; it's the documented
          fall-back path described in the first bullet.
        """
        if not junit_output.is_file():
            # Pytest didn't write an XML for this session; use the in-process
            # counter populated by pytest_runtest_makereport instead.
            self.upload(
                platform,
                os_name,
                version,
                sgw_version,
                es_version,
                incomplete=incomplete,
                collected=collected,
                cbs_version=cbs_version,
                dataset_version=dataset_version,
                cbl_platform=cbl_platform,
                collected_ids=collected_ids,
                finished_ids=finished_ids,
            )
            return

        junit_pass, junit_fail, junit_error = count_from_junit_xml(junit_output)
        if junit_pass + junit_fail + junit_error == 0:
            cbl_info(f"Greenboard: JUnit XML at {junit_output} reports no tests collected; skipping upload")
            return
        if junit_pass == 0 and junit_fail == 0 and junit_error > 0:
            cbl_info(f"Greenboard: all {junit_error} tests errored before running (harness failure); skipping upload")
            return

        tests, failures = outcomes_from_junit_xml(junit_output)
        self.upload(
            platform,
            os_name,
            version,
            sgw_version,
            es_version,
            pass_count=junit_pass,
            fail_count=junit_fail + junit_error,
            incomplete=incomplete,
            collected=collected,
            cbs_version=cbs_version,
            dataset_version=dataset_version,
            cbl_platform=cbl_platform,
            tests=tests,
            failures=failures,
        )

    def _upload_document(
        self, test_run: RunResult, tests: dict[str, str], failures: list[dict[str, Any]], failures_truncated: bool
    ) -> None:
        """Write the run doc ``K`` plus its heavy per-test siblings ``K::tests`` and ``K::failures``.

        The siblings go first and the run doc last, so a crash part-way leaves harmless orphan siblings rather than a
        run doc claiming ``details`` whose siblings are missing. If a sibling write fails the run doc is still written,
        without ``details``, and the frontend treats that run's test data as unknown.
        """
        key = str(uuid4())
        doc = test_run.model_dump(by_alias=True)
        collection = self._collection()
        try:
            collection.upsert(f"{key}::tests", {"runId": key, "tests": tests})
            collection.upsert(
                f"{key}::failures", {"runId": key, "failures": failures, "failuresTruncated": failures_truncated}
            )
            doc["details"] = DETAILS_SCHEMA
        except Exception as e:
            cbl_warning(f"Could not write per-test greenboard docs for {key}; uploading the run doc without them: {e}")
        self._stamp(doc)
        collection.upsert(key, doc)

    @staticmethod
    def _stamp(doc: dict) -> None:
        now = datetime.now(UTC)
        unix_timestamp = (now - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()

        # Do not add to RunResult since this code will go away shortly
        doc["uploaded"] = unix_timestamp
        doc["date"] = now.strftime("%Y-%m-%d")

    def _collection(self) -> Collection:
        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))

        return cluster.bucket("greenboard").default_collection()
