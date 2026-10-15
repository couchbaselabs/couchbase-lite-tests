import json
import os
import re
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_AUTH_RE = re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)(?:(?:basic|bearer)\s+)?[^\s'\",]+")
_SECRET_RE = re.compile(
    r"(?i)\b([\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key)[\w-]*)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",&}]+"
)
_URL_CREDS_RE = re.compile(r"(://[^/\s:@]+:)[^@\s/]+@")


def sanitize_text(text: str) -> str:
    """Strip ANSI colour codes and redact credentials from failure text before it is uploaded.

    Best effort only: the patterns catch the common shapes (``password=...``, ``Authorization: ...``,
    ``user:pass@host``, ``token=...``) but cannot recognise a secret that has no such label, so this is a safety net,
    not a guarantee.
    """
    text = _ANSI_RE.sub("", text)
    text = _AUTH_RE.sub(r"\1[REDACTED]", text)
    text = _SECRET_RE.sub(r"\1\2[REDACTED]", text)
    return _URL_CREDS_RE.sub(r"\1[REDACTED]@", text)


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
    lines = sanitize_text(message or "").strip().splitlines()
    entry: dict[str, Any] = {
        "test": test,
        "kind": kind,
        "phase": phase,
        "message": _head(lines[0] if lines else "", MAX_MESSAGE_BYTES),
    }
    clean_trace = _tail(sanitize_text(trace or "").strip(), MAX_TRACE_BYTES)
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

    Resolved at upload time (not at uploader construction) because the
    upgrade-batch path runs from a separate Python process invoked by
    the wrapper shell script — the same Jenkins env is still present
    there since it's the same job, and reading env on each call keeps
    a single source of truth without threading the value through
    constructors.
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
    cbs_version: str = Field("n/a", alias="cbsVersion")  # "x.y.z-build", "rosmar" (no CBS) or "n/a" (none/unknown)


class GreenboardUploader:
    """
    Uploads test-run results to a greenboard couchbase bucket.

    Three entry points, each for a different upload-time context:

    - :py:meth:`upload` — in-process pytest fixture path. Pass/fail counts
      come from :py:meth:`pytest_runtest_makereport` tallying ``TestReport``
      objects as tests run within the same session.
    - :py:meth:`upload_from_junit_file` — JUnit-XML-driven path. Pass/fail
      counts come from a JUnit XML file produced by pytest's
      ``--junitxml``. Falls back to :py:meth:`upload` if the file is
      absent. Decouples count-collection from in-process pytest hooks
      (needed for pipelines whose pytest invocations are orchestrated
      from a shell script).
    - :py:meth:`record_upgrade_step` + :py:meth:`upload_upgrade_batch` —
      legacy upgrade-job path. Each pytest session appends to a JSON
      state file; the wrapper script invokes ``upload_upgrade_batch`` at
      the end to emit one aggregate ``platform="sgw-upgrade"`` doc.
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
        self.__test_ran = False
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

        # Used by record_upgrade_step to skip iterations where pytest
        # collected zero tests (and no setup crash occurred).
        self.__test_ran = True

        # Above the short-circuit: tests that still run after the latch must
        # set this, or an SGW run gets filed under the CBL platform.
        if item.get_closest_marker("sgw") or item.get_closest_marker("upg_sgw"):
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
        Returns True if any test in the session has @pytest.mark.sgw or @pytest.mark.upg_sgw marker
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
            tests=tests,
            failures=failures,
        )

    def record_upgrade_step(
        self,
        results_file: str,
        sgw_version: CouchbaseVersion | None,
        upgrade_versions_str: str,
        phase: str | None,
        node_index: str | None,
    ) -> None:
        """Append this iteration's result to a JSON state file.

        The aggregated batch document is uploaded later (once per upgrade
        run) by ``upload_upgrade_batch``. Failed iterations are recorded
        too so the UI can surface where in the upgrade sequence the
        failure occurred.

        :param results_file: Path to the JSON state file to append to
        :param sgw_version: Current SGW version (target of this step)
        :param upgrade_versions_str: Comma-separated ordered version list
        :param phase: SGW_UPGRADE_PHASE env value (e.g. "initial",
            "rolling_node_0", "complete")
        :param node_index: SGW_UPGRADED_NODE_INDEX env value, if any
        """
        upgrade_path = [v.strip() for v in upgrade_versions_str.split(",") if v.strip()]

        # No tests collected AND no setup crash means nothing was ever
        # attempted (e.g. wrong marker filter). Don't record an iteration
        # — the chart shouldn't show a row for a run that never executed.
        if not self.__test_ran and not self.__overall_fail:
            cbl_info(f"No tests ran for phase={phase!r}; skipping iteration record (no upload contribution)")
            return

        # Resolve the destination version of this iteration. Live SGW is
        # primary; on get_version() failure the caller passes None and we
        # fall back to the shell-exported step target so the dot still
        # maps to the right node on the chart. Last-resort is the planned
        # final target.
        target_build = 0
        if sgw_version is not None and sgw_version.version:
            current_version = sgw_version.version
            target_build = sgw_version.build_number
        else:
            current_version = os.environ.get("SGW_VERSION_UNDER_TEST") or (
                upgrade_path[-1] if upgrade_path else "0.0.0"
            )

        upgrade_from = "initial"
        for i, v in enumerate(upgrade_path):
            if v == current_version and i > 0:
                upgrade_from = upgrade_path[i - 1]
                break

        # Any deviation from "tests ran and all passed" is a failure.
        # Includes: a test failed (call phase) or setup/teardown crashed
        # (overall_fail). Zero-collected was already short-circuited above.
        had_test_failures = self.__fail_count > 0
        setup_failure = self.__overall_fail
        failed = had_test_failures or setup_failure

        # Surface non-test-call failures as at least one failed count so
        # the top-level batch doc's failCount is correctly 1, not 0.
        fail_count = self.__fail_count
        if failed and fail_count == 0:
            fail_count = 1

        iteration = {
            "phase": phase,
            "nodeIndex": int(node_index) if node_index is not None else None,
            "upgradeFrom": upgrade_from,
            "upgradeTo": current_version,
            "build": target_build,
            "passCount": self.__pass_count,
            "failCount": fail_count,
            "failed": failed,
        }

        path = Path(results_file)
        if path.exists():
            try:
                state = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                cbl_warning(f"Could not read existing results file {path}: {e}")
                state = {}
        else:
            state = {}

        state.setdefault("upgradePath", upgrade_path)
        state.setdefault("iterations", []).append(iteration)
        path.write_text(json.dumps(state, indent=2))
        cbl_info(
            f"Upgrade step recorded ({phase}): {upgrade_from} → {current_version} "
            f"(pass={self.__pass_count}, fail={self.__fail_count})"
        )

    def upload_upgrade_batch(self, results_file: str) -> None:
        """Upload one aggregate document for the whole upgrade run.

        Reads the iterations recorded by ``record_upgrade_step`` and emits
        a single greenboard doc summarising the run. If any iteration
        failed, ``failedAt`` points at the first failed iteration so the
        UI can show where in the sequence the run broke.
        """
        path = Path(results_file)
        if not path.exists():
            cbl_warning(f"No upgrade results file at {path}; nothing to upload")
            return

        try:
            state = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            cbl_warning(f"Could not parse upgrade results file {path}: {e}")
            return

        iterations = state.get("iterations", [])
        if not iterations:
            cbl_warning(f"Upgrade results file {path} has no iterations; skipping upload")
            return

        upgrade_path = state.get("upgradePath", [])
        # version is always the planned final target so the UI's
        # "filter by target version" picks up this run even when execution
        # stopped early at an intermediate version.
        target_version = upgrade_path[-1] if upgrade_path else iterations[-1].get("upgradeTo", "0.0.0")

        failed_at = None
        for i in iterations:
            if i.get("failed"):
                failed_at = {
                    "phase": i.get("phase"),
                    "upgradeFrom": i.get("upgradeFrom"),
                    "upgradeTo": i.get("upgradeTo"),
                    "nodeIndex": i.get("nodeIndex"),
                }
                break

        # One upgrade batch == one upgrade test from the UI's POV. Bars are
        # built by the UI by aggregating across past runs that share
        # (version, upgradePath); per-run pass/fail is therefore 1/0.
        if failed_at is None:
            pass_count, fail_count = 1, 0
            target_build = iterations[-1].get("build", 0)
        else:
            pass_count, fail_count = 0, 1
            # The planned target build was never reached; per-iteration
            # `build` fields preserve what was actually running at each step.
            target_build = 0

        self._upsert(
            {
                "build": target_build,
                "version": target_version,
                "upgradePath": upgrade_path,
                "iterations": iterations,
                "passCount": pass_count,
                "failCount": fail_count,
                "failedAt": failed_at,
                "platform": "sgw-upgrade",
                "jobUrl": resolve_job_url(),
            }
        )
        cbl_info(
            f"Upgrade batch uploaded: path={'->'.join(upgrade_path)} "
            f"target={target_version} pass={pass_count} fail={fail_count} "
            f"failedAt={failed_at}"
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

    def _upsert(self, doc: dict) -> None:
        """Add timestamp fields and write one document to the greenboard bucket."""
        self._stamp(doc)
        self._collection().upsert(str(uuid4()), doc)

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
