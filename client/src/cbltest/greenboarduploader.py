from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from _pytest.reports import TestReport
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions

from cbltest.logging import cbl_warning


class GreenboardUploader(object):
    """
    A class for uploading results to a specified greenboard server bucket
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

        if report.passed:
            self.__pass_count += 1
        elif report.failed:
            self.__fail_count += 1

    def upload(self, platform: str, os_name: str, version: str, sgw_version: str):
        """
        Uploads the results using the specified platform and version.  The reason that they
        are specified here is because they are probably unknown at the time that this object
        is created as they need to be retrieved from the test server.

        :param platform: The platform name (e.g. couchbase-lite-net) as specified by the test server
        :param version: The version string (e.g. 3.2.0-b0136, etc) as specified by the test server
        """
        if self.__overall_fail:
            cbl_warning("Overall result is failure, skipping upload...")
            return

        version_components = version.split("-")
        if len(version_components) != 2:
            version = "0.0.0"
            build = 0
        else:
            version = version_components[0]
            build = int(version_components[1].lstrip("b"))

        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))

        unix_timestamp = (
            datetime.now(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds()

        cluster.bucket("greenboard").default_collection().upsert(
            str(uuid4()),
            {
                "build": build,
                "version": version,
                "sgwVersion": sgw_version,
                "failCount": self.__fail_count,
                "passCount": self.__pass_count,
                "platform": platform,
                "os": os_name,
                "uploaded": unix_timestamp,
            },
        )
