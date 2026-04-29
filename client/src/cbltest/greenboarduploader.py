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

from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.logging import cbl_info, cbl_warning


class GreenboardUploader:
    """
    A class for uploading results to a specified greenboard server bucket.

    Supports two modes:
    - **Normal mode**: uploads results directly at end of pytest session.
    - **Deferred mode** (upgrade jobs): writes pass/fail to a shared JSONL file
      so a final script can upload one combined document per upgrade batch.

    Deferred mode activates when ``SGW_UPGRADE_RESULTS_FILE`` is set in the
    environment.
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
        self.__has_sgw_marker = False

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]):
        outcome = yield
        report: TestReport = outcome.get_result()
        if report.when != "call":
            if report.failed:
                self.__overall_fail = True
            return

        if self.__overall_fail:
            return

        # Track if any test has SGW-focused markers
        if item.get_closest_marker("sgw") or item.get_closest_marker("upg_sgw"):
            self.__has_sgw_marker = True

        if report.passed:
            self.__pass_count += 1
        elif report.failed:
            self.__fail_count += 1

    def has_sgw_marker(self) -> bool:
        """
        Returns True if any test in the session has @pytest.mark.sgw or @pytest.mark.upg_sgw marker
        """
        return self.__has_sgw_marker

    @property
    def is_deferred(self) -> bool:
        """True when running as part of an upgrade batch (deferred upload mode)."""
        return os.environ.get("SGW_UPGRADE_RESULTS_FILE") is not None

    def write_deferred_result(self) -> None:
        """Append this session's pass/fail outcome to the shared results file.

        Each line is a JSON object: ``{"passed": true}`` or ``{"passed": false}``.
        The final upload script reads all lines to determine overall pass/fail.
        """
        results_file = os.environ.get("SGW_UPGRADE_RESULTS_FILE")
        if results_file is None:
            cbl_warning(
                "SGW_UPGRADE_RESULTS_FILE not set, cannot write deferred result"
            )
            return

        passed = not self.__overall_fail and self.__fail_count == 0
        line = json.dumps({"passed": passed})
        Path(results_file).parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, "a") as f:
            f.write(line + "\n")
        cbl_info(f"Deferred upgrade result written: passed={passed}")

    def upload(
        self,
        platform: str,
        os_name: str,
        version: str,
        sgw_version: CouchbaseVersion | None,
    ):
        """
        Uploads the results using the specified platform and version.  The reason that they
        are specified here is because they are probably unknown at the time that this object
        is created as they need to be retrieved from the test server.

        :param platform: The platform name (e.g. couchbase-lite-net) as specified by the test server
        :param version: The version string (e.g. 3.2.0-b0136, etc) as specified by the test server
        :param sgw_version: The parsed SGW CouchbaseVersion object, or None if unavailable
        """
        if self.__overall_fail:
            cbl_warning("Overall result is failure, skipping upload...")
            return

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
            {
                "build": parsed_build,
                "version": parsed_version,
                "sgwVersion": sgw_version_str,
                "failCount": self.__fail_count,
                "passCount": self.__pass_count,
                "platform": platform,
                "os": os_name,
            }
        )

    def upload_upgrade_batch(
        self,
        upgrade_path: list[str],
        target_sgw_version: str,
        target_build: int,
        passed: bool,
    ) -> None:
        """Upload a single combined document for an entire upgrade batch.

        :param upgrade_path: Ordered list of SGW versions tested (e.g. ["3.1.0", "3.2.0", "3.3.0"])
        :param target_sgw_version: Full version string of the final target (e.g. "3.3.0-1234")
        :param target_build: Build number of the target version
        :param passed: Whether the entire upgrade batch passed
        """
        target_version = upgrade_path[-1] if upgrade_path else "0.0.0"

        self._upload_document(
            {
                "build": target_build,
                "version": target_version,
                "sgwVersion": target_sgw_version,
                "upgradePath": upgrade_path,
                "failCount": 0 if passed else 1,
                "passCount": 1 if passed else 0,
                "platform": "sgw-upgrade",
                "os": "n/a",
            }
        )

    def _upload_document(self, doc: dict) -> None:
        """Upload a document to the greenboard bucket with common fields added."""
        now = datetime.now(timezone.utc)
        unix_timestamp = (
            now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds()

        doc["uploaded"] = unix_timestamp
        doc["date"] = now.strftime("%Y-%m-%d")

        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))

        cluster.bucket("greenboard").default_collection().upsert(str(uuid4()), doc)
