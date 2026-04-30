import os
from datetime import datetime, timedelta, timezone
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
    def is_upgrade(self) -> bool:
        """True when running as part of an SGW upgrade pipeline."""
        return os.environ.get("SGW_UPGRADE_VERSIONS") is not None

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

    def upload_upgrade_step(self, sgw_version: CouchbaseVersion | None) -> None:
        """Upload results for a single upgrade step.

        Reads upgrade context from environment variables:
        - ``SGW_UPGRADE_VERSIONS``: comma-separated ordered version list
        - ``SGW_UPGRADE_FROM``: version being upgraded from (this step)

        :param sgw_version: The current SGW version (target of this step)
        """
        if self.__overall_fail:
            cbl_warning("Overall result is failure, skipping upload...")
            return

        versions_str = os.environ.get("SGW_UPGRADE_VERSIONS", "")
        upgrade_path = [v.strip() for v in versions_str.split(",") if v.strip()]
        upgrade_from = os.environ.get("SGW_UPGRADE_FROM", "initial")

        # Target version: from the running SGW or last in upgrade path
        target_version = upgrade_path[-1] if upgrade_path else "0.0.0"
        target_build = 0
        if sgw_version is not None:
            target_version = sgw_version.version or target_version
            target_build = sgw_version.build_number

        # upgradeTo is the current step's destination
        upgrade_to = os.environ.get("SGW_VERSION_UNDER_TEST", target_version)

        self._upload_document(
            {
                "build": target_build,
                "version": target_version,
                "upgradePath": upgrade_path,
                "upgradeFrom": upgrade_from,
                "upgradeTo": upgrade_to,
                "failCount": self.__fail_count,
                "passCount": self.__pass_count,
                "platform": "sgw-upgrade",
            }
        )
        cbl_info(
            f"Upgrade step uploaded: {upgrade_from} → {upgrade_to} "
            f"(pass={self.__pass_count}, fail={self.__fail_count})"
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
