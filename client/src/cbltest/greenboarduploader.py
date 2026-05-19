from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from _pytest.reports import TestReport
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import DocumentNotFoundException
from couchbase.options import ClusterOptions
from packaging.version import InvalidVersion, Version

from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.logging import cbl_info, cbl_warning


def _version_sort_key(v: str) -> tuple[Version, int]:
    """Sort key for SGW-style version strings of the form ``<semver>[-<build>]``.

    Splits on the first ``-``: if the suffix is a pure integer, returns
    ``(Version(semver), int(build))`` so that ``3.3.0-99 < 3.3.0-100 <
    3.3.0-1234``. Plain semver (no suffix) sorts as build ``0`` of that
    semver. Non-numeric suffixes fall through to ``Version(v)`` so PEP 440
    pre/post/rc tags still order correctly.
    """
    semver, _, build = v.partition("-")
    if build and build.isdigit():
        return Version(semver), int(build)
    return Version(v), 0


class GreenboardUploader:
    """
    A class for uploading results to a specified greenboard server bucket.

    Two upload paths are supported:

    - **Normal mode** (:py:meth:`upload`) — writes a new per-session document
      with a fresh ``uuid4`` doc id. Used by every regular (non-upgrade) test
      session.
    - **Upgrade matrix mode** (:py:meth:`upload_upgrade_result`) —
      read-merge-upserts a single deterministic document per upgrade type
      (``sgw-upgrade::waterfall`` and ``sgw-upgrade::rolling``). Each doc
      holds a semver-sorted ``versions`` axis plus a ``matrix[from][to]``
      nested map of pass/fail entries. Reruns of the same ``(from, to)``
      pair override their prior entry.
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

    def upload_upgrade_result(
        self,
        upgrade_type: str,
        from_version: str,
        to_version: str,
    ) -> None:
        """Upsert one pass/fail entry into the per-type SGW upgrade matrix doc.

        Doc id is ``sgw-upgrade::{upgrade_type}``; entry is stored at
        ``matrix[from_version][to_version]`` and overrides any prior entry
        for the same pair. ``versions`` axis is the union of all FROM/TO
        versions ever seen, semver-sorted ascending for the UI to render
        as both row and column labels of an N×N grid.
        """
        if (
            self.__pass_count == 0
            and self.__fail_count == 0
            and not self.__overall_fail
        ):
            cbl_info(
                "No tests ran for upgrade upload; skipping "
                f"({upgrade_type} {from_version} -> {to_version})"
            )
            return

        passed = not (self.__overall_fail or self.__fail_count > 0)
        now = datetime.now(timezone.utc)
        unix_ts = (now - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
        entry = {
            "passed": passed,
            "uploaded": unix_ts,
            "date": now.strftime("%Y-%m-%d"),
        }

        doc_id = f"sgw-upgrade::{upgrade_type}"
        coll = self._open_collection()

        doc: dict[str, Any]
        try:
            doc = coll.get(doc_id).content_as[dict]
        except DocumentNotFoundException:
            doc = {
                "type": upgrade_type,
                "lastUpdated": 0.0,
                "versions": [],
                "matrix": {},
            }

        versions = list({*doc.get("versions", []), from_version, to_version})
        try:
            versions.sort(key=_version_sort_key)
        except InvalidVersion:
            cbl_warning(f"Falling back to lexicographic sort for versions {versions}")
            versions.sort()
        doc["versions"] = versions

        doc.setdefault("matrix", {}).setdefault(from_version, {})[to_version] = entry
        doc["lastUpdated"] = unix_ts

        coll.upsert(doc_id, doc)
        cbl_info(
            f"Greenboard upgrade upload: {doc_id} "
            f"{from_version} -> {to_version} ({'pass' if passed else 'fail'})"
        )

    def _open_collection(self):
        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))
        return cluster.bucket("greenboard").default_collection()

    def _upload_document(self, doc: dict) -> None:
        """Upload a document to the greenboard bucket with common fields added."""
        now = datetime.now(timezone.utc)
        unix_timestamp = (
            now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds()

        doc["uploaded"] = unix_timestamp
        doc["date"] = now.strftime("%Y-%m-%d")

        self._open_collection().upsert(str(uuid4()), doc)
