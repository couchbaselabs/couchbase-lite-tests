import re
import tempfile
import zipfile
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    IndexConfig,
    ScopeConfig,
    SGCollectRedactLevel,
)

# Records Sync Gateway logs verbatim as debug internals: JSON error payloads from Couchbase
# Server, and Go struct dumps.  Sensitive data in them is not a redaction failure.
_VERBATIM_RECORD_MARKERS = (
    b'{"statement":',
    b'"errors":[',
    b'"client_context_id":',
    b'{"code":',
    b'"http_status_code":',
    b"roleImpl:{",
    b"userImplBody:{",
    b"docID:_sync:user:",
    b"&{roleImpl:",
)

# Records Sync Gateway leaves sensitive data untagged in.  These are real redaction failures,
# so drop a marker as soon as its bug is fixed.
_KNOWN_UNTAGGED_MARKERS = (
    b"invalidates channels of",  # CBG-5836
)

_SKIPPED_RECORD_MARKERS = _VERBATIM_RECORD_MARKERS + _KNOWN_UNTAGGED_MARKERS


def assert_no_untagged_sensitive_data(
    log_file: Path,
    sensitive_patterns: list[str],
) -> bool:
    """
    Asserts that a log file carries no sensitive data outside a pair of <ud>...</ud> tags,
    failing on the first occurrence.  Reads one line at a time and matches on raw bytes, since
    a log is too big to hold in memory and a record can quote bytes that are not valid UTF-8,
    such as the character an invalid-JSON error complains about.  Sync Gateway writes one
    record per line, so the line is the whole context of a match.

    :param log_file: The log file to scan
    :param sensitive_patterns: List of sensitive strings to look for (e.g., doc IDs, usernames)
    :return: Whether any line carried a <ud> tag
    """
    has_ud_tags = False
    with log_file.open("rb") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip(b"\r\n")
            has_ud_tags = has_ud_tags or b"<ud>" in line
            if any(marker in line for marker in _SKIPPED_RECORD_MARKERS):
                continue

            for pattern in sensitive_patterns:
                for match in re.finditer(re.escape(pattern.encode()), line):
                    before = line[: match.start()]
                    # Tagged when the last tag before the match opens a span that closes after it
                    if before.rfind(b"<ud>") > before.rfind(b"</ud>") and b"</ud>" in line[match.end() :]:
                        continue

                    pytest.fail(
                        f"Untagged '{pattern}' in {log_file.name} line {line_number}: {line.decode(errors='replace')}"
                    )

    return has_ud_tags


@pytest.mark.sgw
@pytest.mark.min_test_servers(0)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestLogRedaction(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_log_redaction_partial(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        self.skip_if_not(
            sg.has_caddy_sidecar,
            "Caddy sidecar is not reachable on this Sync Gateway host",
        )
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["log-redaction"]
        username = "vipul"
        password = "pass"

        self.mark_test_step("Configure Sync Gateway with log redaction enabled")
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to channels")
        async with sg.create_user_client(sg_db, username, password, channels) as sg_user:
            self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
            sg_docs: list[DocumentUpdateEntry] = []
            sg_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"sg_doc_{i}"
                sg_doc_ids.append(doc_id)
                sg_docs.append(
                    DocumentUpdateEntry(
                        doc_id,
                        None,
                        body={
                            "type": "test_doc",
                            "index": i,
                            "channels": channels,
                        },
                    )
                )
            await sg.update_documents(sg_db, sg_docs, "_default", "_default")

            self.mark_test_step("Verify docs were created (public API)")
            all_docs = await sg_user.get_all_documents(sg_db, "_default", "_default")
            assert len(all_docs.rows) == num_docs, f"Expected {num_docs} docs, got {len(all_docs.rows)}"

            self.mark_test_step("Fetch and scan SG logs for redaction violations via Caddy")
            log_types = ["debug", "info", "warn", "error"]
            sensitive_patterns = sg_doc_ids + [username]

            has_any_ud_tags = False

            with tempfile.TemporaryDirectory() as tmpdir:
                for log_type in log_types:
                    log_file = await sg.fetch_log_file(log_type, Path(tmpdir) / f"sg_{log_type}.log")
                    has_any_ud_tags |= assert_no_untagged_sensitive_data(log_file, sensitive_patterns)

            assert has_any_ud_tags, "No <ud> tags found in any log files - partial redaction not working"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgcollect_redacted_files_and_contents(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        self.skip_if_not(
            sg.has_caddy_sidecar,
            "Caddy sidecar is not reachable on this Sync Gateway host",
        )
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["log-redaction-sgcollect"]
        username = "vipul_sgcollect"
        password = "password"

        self.mark_test_step("Configure Sync Gateway with log redaction enabled")
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to channels")
        async with sg.create_user_client(sg_db, username, password, channels) as sg_user:
            self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
            sg_docs: list[DocumentUpdateEntry] = []
            sg_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"sgcollect_doc_{i}"
                sg_doc_ids.append(doc_id)
                sg_docs.append(
                    DocumentUpdateEntry(
                        doc_id,
                        None,
                        body={
                            "type": "test_doc_sgcollect",
                            "index": i,
                            "channels": channels,
                        },
                    )
                )
            await sg.update_documents(sg_db, sg_docs, "_default", "_default")

            self.mark_test_step("Verify docs were created")
            all_docs = await sg_user.get_all_documents(sg_db, "_default", "_default")
            assert len(all_docs.rows) == num_docs, f"Expected {num_docs} docs, got {len(all_docs.rows)}"

            self.mark_test_step("Trigger SGCollect with redaction enabled")
            sgcollect_resp = await sg.start_sgcollect(
                redact_level=SGCollectRedactLevel.PARTIAL,
                output_dir="/home/ec2-user/log",
            )
            assert sgcollect_resp.get("status") in ["running", "started"], (
                f"SGCollect failed to start: {sgcollect_resp}"
            )

            self.mark_test_step("Wait for SGCollect to complete")
            await sg.wait_for_sgcollect_to_complete(max_attempts=60, wait_time=5)

            self.mark_test_step("Discover redacted SGCollect zip file via Caddy")
            try:
                files = await sg.caddy.list(pattern=r"sgcollect.*redacted.*\.zip")
                assert len(files) > 0, (
                    "No redacted SGCollect zip files found. "
                    "Make sure SGCollect was run with redaction enabled and Caddy has 'browse' enabled."
                )
                redacted_zip_filename = max(files)
                self.mark_test_step(f"Found redacted zip: {redacted_zip_filename}")

            except Exception as e:
                pytest.fail(
                    f"Failed to list files via Caddy directory browsing: {e}. Ensure Caddyfile has 'file_server browse' enabled."
                )

            self.mark_test_step(f"Download redacted zip: {redacted_zip_filename}")
            with tempfile.TemporaryDirectory() as tmpdir:
                local_zip_path = Path(tmpdir) / redacted_zip_filename
                await sg.caddy.download(redacted_zip_filename, local_zip_path)

                assert local_zip_path.exists(), f"Downloaded zip not found at {local_zip_path}"

                self.mark_test_step("Extract and verify redacted logs in zip")
                extract_dir = Path(tmpdir) / "extracted"
                extract_dir.mkdir()

                with zipfile.ZipFile(local_zip_path, "r") as zf:
                    zf.extractall(extract_dir)

                # Find log files in the extracted content
                log_files = list(extract_dir.rglob("sg_*.log"))
                assert len(log_files) > 0, "No log files found in SGCollect zip"

                self.mark_test_step(f"Scanning {len(log_files)} log files for redaction violations")
                sensitive_patterns = sg_doc_ids + [username]
                has_any_ud_tags = False

                for log_file in log_files:
                    has_any_ud_tags |= assert_no_untagged_sensitive_data(log_file, sensitive_patterns)

                assert has_any_ud_tags, "No <ud> tags found in SGCollect log files - partial redaction not working"
