from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from junitparser import JUnitXml, TestSuite

from cbltest.api.syncgateway import CouchbaseVersion
from cbltest.logging import cbl_info, cbl_warning


def parse_version_and_build(
    platform: str, version: str, sgw_version: CouchbaseVersion | None
) -> tuple[str, int, str]:
    """
    Compute the ``(version, build, sgwVersion)`` triple that should land on a
    greenboard doc, given a platform and the raw values reported by the test
    server / SGW.

    The first two are the doc's ``version`` and ``build`` fields; the third
    is the ``sgwVersion`` field. Centralising the parsing here lets both the
    in-process fixture (which produces sidecar files) and the aggregator
    (which never sees the live test server) agree on the same shape.
    """
    parsed_version = "0.0.0"
    parsed_build = 0
    sgw_version_str = "n/a"

    if sgw_version is not None:
        sgw_version_str = f"{sgw_version.version}-{sgw_version.build_number}"

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

    return parsed_version, parsed_build, sgw_version_str


def _suite_counts(suite: TestSuite) -> tuple[int, int]:
    """Return ``(passed, failed)`` for a single JUnit ``<testsuite>``.

    ``passed = tests - failures - errors - skipped``; failures and errors are
    both lumped into the failed bucket since the greenboard doc only carries
    pass/fail counts.
    """
    tests = suite.tests or 0
    failures = suite.failures or 0
    errors = suite.errors or 0
    skipped = suite.skipped or 0
    passed = max(0, tests - failures - errors - skipped)
    failed = failures + errors
    return passed, failed


class GreenboardUploader:
    """
    Uploads a single per-Jenkins-build document to the greenboard bucket.

    The class is a thin wrapper around the Couchbase SDK and the JUnit XML +
    sidecar aggregation logic. There is no per-test in-process state: the
    pytest fixture writes meta sidecars and ``--junitxml`` files into a
    per-build results directory, and :py:meth:`upload_from_results_dir` reads
    that directory at the end of the Jenkins build to produce one doc.
    """

    def __init__(self, url: str, username: str, password: str):
        if "://" not in url:
            url = f"couchbase://{url}"

        self.__url = url
        self.__username = username
        self.__password = password

    def upload(
        self,
        *,
        platform: str,
        os_name: str,
        version: str,
        build: int,
        sgw_version_str: str,
        pass_count: int,
        fail_count: int,
        build_url: str | None = None,
        upgrade_to: str | None = None,
    ) -> None:
        """
        Upload a single greenboard doc with a fresh ``uuid4`` id.

        Caller is responsible for having already filtered out the no-upload
        cases (zero tests, zero passes). This method assumes the data is
        worth persisting.
        """
        doc: dict = {
            "build": build,
            "version": version,
            "sgwVersion": sgw_version_str,
            "failCount": fail_count,
            "passCount": pass_count,
            "platform": platform,
            "os": os_name,
        }
        if build_url:
            doc["buildUrl"] = build_url
        if upgrade_to:
            doc["upgradeTo"] = upgrade_to

        now = datetime.now(timezone.utc)
        unix_timestamp = (
            now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds()
        doc["uploaded"] = unix_timestamp
        doc["date"] = now.strftime("%Y-%m-%d")

        self._open_collection().upsert(str(uuid4()), doc)
        cbl_info(
            f"Greenboard upload: passCount={pass_count} failCount={fail_count} "
            f"platform={platform} buildUrl={build_url or '-'} "
            f"upgradeTo={upgrade_to or '-'}"
        )

    @classmethod
    def upload_from_results_dir(
        cls,
        url: str,
        username: str,
        password: str,
        results_dir: Path,
        *,
        build_url: str | None = None,
        upgrade_to: str | None = None,
    ) -> None:
        """
        Aggregate every ``junit_*.xml`` + ``meta_*.json`` pair found in
        ``results_dir`` and produce a single greenboard upload.

        No-op conditions (silently skip the upload):

        - ``results_dir`` doesn't exist or contains no meta sidecars.
        - All JUnit XMLs report zero tests (nothing actually ran).
        - The aggregated pass count is zero (all failures / a fully red run
          should not produce a doc, per design).

        Hard error (raises):

        - Meta sidecars disagree on ``platform`` or ``os``. Within one
          Jenkins build these must be identical; disagreement signals a real
          configuration bug.
        """
        results_dir = Path(results_dir)
        if not results_dir.is_dir():
            cbl_info(f"Greenboard results dir {results_dir} not found; skipping upload")
            return

        meta_files = sorted(
            results_dir.glob("meta_*.json"), key=lambda p: p.stat().st_mtime
        )
        if not meta_files:
            cbl_info(
                f"No meta_*.json sidecars in {results_dir}; skipping greenboard upload"
            )
            return

        xml_files = sorted(
            results_dir.glob("junit_*.xml"), key=lambda p: p.stat().st_mtime
        )
        total_pass = 0
        total_fail = 0
        any_tests = False
        for xml_path in xml_files:
            try:
                xml = JUnitXml.fromfile(str(xml_path))
            except Exception as e:
                cbl_warning(f"Failed to parse {xml_path}: {e}")
                continue
            # JUnitXml can be a single TestSuite or a TestSuites container.
            suites = list(xml) if isinstance(xml, JUnitXml) else [xml]
            for suite in suites:
                if not isinstance(suite, TestSuite):
                    continue
                if (suite.tests or 0) == 0:
                    continue
                any_tests = True
                p, f = _suite_counts(suite)
                total_pass += p
                total_fail += f

        if not any_tests:
            cbl_info(
                f"All JUnit XMLs in {results_dir} report zero tests; "
                "skipping greenboard upload"
            )
            return
        if total_pass == 0:
            cbl_info(
                f"Greenboard: passCount=0 (failCount={total_fail}) — "
                "fully-failed run, skipping upload per policy"
            )
            return

        # Use the chronologically-first sidecar's metadata for version/sgwVersion
        # — for upgrade tests that's the pre-upgrade (FROM) run, which matches
        # the convention that `version`/`build`/`sgwVersion` reflect the "from"
        # side and `upgradeTo` records the target.
        import json

        metas: list[dict] = []
        for mp in meta_files:
            try:
                metas.append(json.loads(mp.read_text()))
            except Exception as e:
                cbl_warning(f"Failed to read meta sidecar {mp}: {e}")
        if not metas:
            cbl_info("No readable meta sidecars; skipping greenboard upload")
            return

        # Consistency check on non-version fields.
        platforms = {m.get("platform") for m in metas}
        oses = {m.get("os") for m in metas}
        if len(platforms) > 1:
            raise ValueError(
                f"Meta sidecars disagree on platform: {platforms}. "
                "All pytest invocations in one Jenkins build must report the "
                "same platform."
            )
        if len(oses) > 1:
            raise ValueError(
                f"Meta sidecars disagree on os: {oses}. "
                "All pytest invocations in one Jenkins build must report the "
                "same os."
            )

        first = metas[0]
        platform = first.get("platform") or "sync-gateway"
        os_name = first.get("os") or "n/a"
        version = first.get("version") or "0.0.0"
        build = int(first.get("build") or 0)
        sgw_version_str = first.get("sgwVersion") or "n/a"

        uploader = cls(url, username, password)
        uploader.upload(
            platform=platform,
            os_name=os_name,
            version=version,
            build=build,
            sgw_version_str=sgw_version_str,
            pass_count=total_pass,
            fail_count=total_fail,
            build_url=build_url,
            upgrade_to=upgrade_to,
        )

    def _open_collection(self):
        auth = PasswordAuthenticator(self.__username, self.__password)
        opts = ClusterOptions(auth)
        cluster = Cluster(self.__url, opts)
        cluster.wait_until_ready(timedelta(seconds=10))
        return cluster.bucket("greenboard").default_collection()
