import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from _pytest.reports import TestReport
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from junitparser import JUnitXml
from pydantic import BaseModel, ConfigDict, Field

from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.logging import cbl_info, cbl_warning


def count_from_junit_xml(xml_path: Path) -> tuple[int, int] | None:
    """Return ``(passed, failed)`` summed across every ``<testsuite>`` in
    a JUnit XML file at ``xml_path``, or ``None`` if the file is missing or
    can't be parsed.

    ``passed = tests - failures - errors - skipped``; ``failed`` lumps
    failures and errors together (the greenboard doc only carries a single
    fail bucket). Used by the greenboard pytest fixture to derive upload
    counts from pytest's ``--junitxml`` output instead of in-process
    hook-driven counters.
    """
    xml = JUnitXml.fromfile(str(xml_path))

    total_pass = 0
    total_fail = 0
    suites = list(xml)
    for suite in suites:
        tests = suite.tests or 0
        failures = suite.failures or 0
        errors = suite.errors or 0
        skipped = suite.skipped or 0
        total_pass += max(0, tests - failures - errors - skipped)
        total_fail += failures + errors
    return total_pass, total_fail


class RunResult(BaseModel):
    """
    Store the information for a test run in greenboard
    """

    model_config = ConfigDict(populate_by_name=True)

    build: int  # build number of CBL build
    version: str  # major.minor.patch version of CBL
    sgw_version: str = Field(alias="sgwVersion")  # Sync Gateway version, optional
    fail_count: int = Field(alias="failCount")  # number of failing tests
    pass_count: int = Field(alias="passCount")  # number of passing tests
    platform: str  # CBL platform
    os: str  # Operating system for CBL


class GreenboardUploader:
    """
    A class for uploading results to a specified greenboard server bucket.

    Supports two modes:
    - **Normal mode**: uploads results for regular test sessions.
    - **Upgrade mode** (``SGW_UPGRADE_VERSIONS`` is set): uploads per-step
      upgrade results with ``upgradePath``, ``upgradeFrom``, and ``upgradeTo``
      fields under ``platform="sgw-upgrade"``.
    """

    def __init__(self, url: str, username: str, password: str):
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

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]):
        outcome = yield
        report: TestReport = outcome.get_result()
        if report.when != "call":
            if report.failed:
                self.__overall_fail = True
            return

        # Used by record_upgrade_step to skip iterations where pytest
        # collected zero tests (and no setup crash occurred).
        self.__test_ran = True

        if self.__overall_fail:
            return

        # Track if any test has SGW-focused markers
        if item.get_closest_marker("sgw") or item.get_closest_marker("upg_sgw"):
            self.__has_sgw_marker = True

        if report.passed:
            self.__pass_count += 1
        elif report.failed:
            self.__fail_count += 1

    def upload_from_junit_file(
        self,
        junit_output: Path,
        platform: str,
        os_name: str,
        version: str,
        sgw_version: CouchbaseVersion | None,
    ) -> None:
        """
        Upload one greenboard doc whose pass/fail counts come from a JUnit
        XML file produced by pytest.
        Policy:
        - If ``junit_output`` doesn't exist, fall back to the in-process
          counter (``self.upload()`` without count overrides). This covers
          the cold-start case where pytest never wrote an XML — e.g.
          ``--junitxml`` was explicitly disabled by the caller.
        - If the file exists but reports zero tests, skip the upload (the
          session collected nothing worth recording).
        - If it reports zero passes (a fully-red run), skip the upload per
          the project's "don't post all-failed runs to greenboard" policy.
        - Otherwise, upload with the JUnit-derived counts.

        Parse errors propagate — a malformed JUnit XML is a real bug and
        should fail the Jenkins job loudly.
        """
        if not junit_output.is_file():
            # Pytest didn't write an XML for this session; use the in-process
            # counter populated by pytest_runtest_makereport instead.
            self.upload(platform, os_name, version, sgw_version)
            return

        counts = count_from_junit_xml(junit_output)
        assert counts is not None, f"Failed to parse JUnit XML at {junit_output}"
        junit_pass, junit_fail = counts
        if junit_pass + junit_fail == 0:
            cbl_info(
                f"Greenboard: JUnit XML at {junit_output} reports zero tests; "
                "skipping upload"
            )
            return
        if junit_pass == 0:
            cbl_info(
                f"Greenboard: all tests failed (failCount={junit_fail}); "
                "skipping upload per policy"
            )
            return

        self.upload(
            platform,
            os_name,
            version,
            sgw_version,
            pass_count=junit_pass,
            fail_count=junit_fail,
        )

    def has_sgw_marker(self) -> bool:
        """
        Returns True if any test in the session has @pytest.mark.sgw or @pytest.mark.upg_sgw marker
        """
        return self.__has_sgw_marker

    def upload(
        self,
        platform: str,
        os_name: str,
        version: str,
        sgw_version: CouchbaseVersion | None,
        *,
        pass_count: int | None = None,
        fail_count: int | None = None,
    ):
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
        """
        if self.__overall_fail:
            cbl_warning("Overall result is failure, skipping upload...")
            return

        resolved_pass = pass_count if pass_count is not None else self.__pass_count
        resolved_fail = fail_count if fail_count is not None else self.__fail_count

        parsed_version = "0.0.0"
        parsed_build = 0
        sgw_version_str = "n/a"

        if sgw_version is not None:
            sgw_ver = sgw_version.version
            sgw_build = sgw_version.build_number
            sgw_version_str = f"{sgw_ver}-{sgw_build}"

        if platform == "sync-gateway" and sgw_version is not None:
            # For SGW jobs, use the SGW version directly from the parsed object
            # to avoid the fragile serialize-then-reparse pattern.
            parsed_version = (
                sgw_version.version
                if sgw_version.version and sgw_version.version != "unknown"
                else "0.0.0"
            )
            parsed_build = sgw_version.build_number
        else:
            version_components = version.split("-")

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
                failCount=resolved_fail,
                passCount=resolved_pass,
                platform=platform,
                os=os_name,
            )
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
            cbl_info(
                f"No tests ran for phase={phase!r}; skipping iteration "
                "record (no upload contribution)"
            )
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
            cbl_warning(
                f"Upgrade results file {path} has no iterations; skipping upload"
            )
            return

        upgrade_path = state.get("upgradePath", [])
        # version is always the planned final target so the UI's
        # "filter by target version" picks up this run even when execution
        # stopped early at an intermediate version.
        target_version = (
            upgrade_path[-1]
            if upgrade_path
            else iterations[-1].get("upgradeTo", "0.0.0")
        )

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
            }
        )
        cbl_info(
            f"Upgrade batch uploaded: path={'->'.join(upgrade_path)} "
            f"target={target_version} pass={pass_count} fail={fail_count} "
            f"failedAt={failed_at}"
        )

    def _upload_document(self, test_run: RunResult) -> None:
        self._upsert(test_run.model_dump(by_alias=True))

    def _upsert(self, doc: dict) -> None:
        """Add timestamp fields and write one document to the greenboard bucket."""
        now = datetime.now(timezone.utc)
        unix_timestamp = (
            now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds()

        # Do not add to RunResult since this code will go away shortly
        doc["uploaded"] = unix_timestamp
        doc["date"] = now.strftime("%Y-%m-%d")

        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))

        cluster.bucket("greenboard").default_collection().upsert(str(uuid4()), doc)
