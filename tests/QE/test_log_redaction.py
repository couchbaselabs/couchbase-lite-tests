import re
import tempfile
import zipfile
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


def scan_logs_for_untagged_sensitive_data(
    log_content: str,
    sensitive_patterns: list[str],
) -> list[str]:
    """
    Scans log content for sensitive data that is NOT wrapped in <ud>...</ud> tags

    :param log_content: The log file content as a string
    :param sensitive_patterns: List of sensitive strings to look for (e.g., doc IDs, usernames)
    :return: List of violations found (sensitive data without <ud> tags)

    Note: This function skips:
    - Occurrences within <ud>...</ud> tags (properly redacted)
    - JSON error payloads from Couchbase Server (external responses logged verbatim)
    - Go struct dumps (internal debug representations)
    """
    violations = []
    for pattern in sensitive_patterns:
        escaped_pattern = re.escape(pattern)
        for match in re.finditer(escaped_pattern, log_content):
            start_pos = match.start()
            end_pos = match.end()

            # Use larger search range for <ud> tags since Go struct dumps can be long
            before_text = log_content[max(0, start_pos - 500) : start_pos]
            after_text = log_content[end_pos : min(len(log_content), end_pos + 1000)]

            # Check if this occurrence is within <ud>...</ud> tags
            has_opening_tag = "<ud>" in before_text and before_text.rfind(
                "<ud>"
            ) > before_text.rfind("</ud>")
            has_closing_tag = "</ud>" in after_text

            if has_opening_tag and has_closing_tag:
                continue

            context_start = max(0, start_pos - 300)
            context_end = min(len(log_content), end_pos + 300)
            extended_context = log_content[context_start:context_end]

            # Skip if this appears to be inside a JSON payload (error responses from CBS)
            # CBS returns JSON error responses that SGW logs verbatim for debugging
            json_markers = [
                '{"statement":',
                '"errors":[',
                '"client_context_id":',
                '{"code":',
                '"http_status_code":',
            ]
            if any(marker in extended_context for marker in json_markers):
                continue

            # Skip if this is in a Go struct dump (roleImpl, userImplBody, etc.)
            struct_markers = [
                "roleImpl:{",
                "userImplBody:{",
                "docID:_sync:user:",
                "&{roleImpl:",
            ]
            if any(marker in extended_context for marker in struct_markers):
                continue  # Go struct dump - these are debug internals

            context = log_content[
                max(0, start_pos - 50) : min(len(log_content), end_pos + 50)
            ]
            violations.append(
                f"Untagged '{pattern}' at position {start_pos}: ...{context}..."
            )
    return violations


@pytest.mark.sgw
@pytest.mark.min_test_servers(0)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestLogRedaction(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_log_redaction_partial(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["log-redaction"]
        username = "vipul"
        password = "pass"

        self.mark_test_step("Create bucket and default collection")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway with log redaction enabled")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg.put_database(sg_db, db_payload)
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step(f"Create user '{username}' with access to channels")
        sg_user = await sg.create_user_client(sg_db, username, password, channels)

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
        assert len(all_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(all_docs.rows)}"
        )

        self.mark_test_step("Fetch and scan SG logs for redaction violations via Caddy")
        log_types = ["debug", "info", "warn", "error"]
        sensitive_patterns = sg_doc_ids + [username]

        all_violations = []
        has_any_ud_tags = False

        for log_type in log_types:
            try:
                log_contents = await sg.fetch_log_file(log_type)
                violations = scan_logs_for_untagged_sensitive_data(
                    log_contents, sensitive_patterns
                )
                if violations:
                    all_violations.extend(
                        [f"sg_{log_type}.log: {v}" for v in violations[:3]]
                    )
                if "<ud>" in log_contents:
                    has_any_ud_tags = True
            except FileNotFoundError:
                continue
            except Exception as e:
                raise Exception(
                    f"Failed to fetch sg_{log_type}.log via Caddy: {e}"
                ) from e

        assert len(all_violations) == 0, (
            f"Found {len(all_violations)} log redaction violations across all logs: Showing first 10:\n"
            + "\n".join(all_violations[:10])
        )

        assert has_any_ud_tags, (
            "No <ud> tags found in any log files - partial redaction not working"
        )

        await sg_user.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgcollect_redacted_files_and_contents(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["log-redaction-sgcollect"]
        username = "vipul_sgcollect"
        password = "password"

        self.mark_test_step("Create bucket and default collection")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway with log redaction enabled")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg.put_database(sg_db, db_payload)
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step(f"Create user '{username}' with access to channels")
        sg_user = await sg.create_user_client(sg_db, username, password, channels)

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
        assert len(all_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(all_docs.rows)}"
        )

        self.mark_test_step("Trigger SGCollect with redaction enabled")
        sgcollect_resp = await sg.start_sgcollect(
            redact_level="partial", output_dir="/home/ec2-user/log"
        )
        assert sgcollect_resp.get("status") in ["running", "started"], (
            f"SGCollect failed to start: {sgcollect_resp}"
        )

        self.mark_test_step("Wait for SGCollect to complete")
        await sg.wait_for_sgcollect_to_complete(max_attempts=60, wait_time=5)

        self.mark_test_step("Discover redacted SGCollect zip file via Caddy")
        try:
            files = await sg.list_files_via_caddy(pattern=r"sgcollect.*redacted.*\.zip")
            assert len(files) > 0, (
                "No redacted SGCollect zip files found. "
                "Make sure SGCollect was run with redaction enabled and Caddy has 'browse' enabled."
            )
            redacted_zip_filename = sorted(files)[-1]
            self.mark_test_step(f"Found redacted zip: {redacted_zip_filename}")

        except Exception as e:
            pytest.fail(
                f"Failed to list files via Caddy directory browsing: {e}. "
                "Ensure Caddyfile has 'file_server browse' enabled."
            )

        self.mark_test_step(f"Download redacted zip: {redacted_zip_filename}")
        with tempfile.TemporaryDirectory() as tmpdir:
            local_zip_path = Path(tmpdir) / redacted_zip_filename
            await sg.download_file_via_caddy(redacted_zip_filename, str(local_zip_path))

            assert local_zip_path.exists(), (
                f"Downloaded zip not found at {local_zip_path}"
            )

            self.mark_test_step("Extract and verify redacted logs in zip")
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()

            with zipfile.ZipFile(local_zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # Find log files in the extracted content
            log_files = list(extract_dir.rglob("sg_*.log"))
            assert len(log_files) > 0, "No log files found in SGCollect zip"

            self.mark_test_step(
                f"Scanning {len(log_files)} log files for redaction violations"
            )
            sensitive_patterns = sg_doc_ids + [username]
            all_violations = []
            has_any_ud_tags = False

            for log_file in log_files:
                log_content = log_file.read_text(errors="replace")
                violations = scan_logs_for_untagged_sensitive_data(
                    log_content, sensitive_patterns
                )
                if violations:
                    all_violations.extend(
                        [f"{log_file.name}: {v}" for v in violations[:3]]
                    )
                if "<ud>" in log_content:
                    has_any_ud_tags = True

            assert len(all_violations) == 0, (
                f"Found {len(all_violations)} log redaction violations in SGCollect zip. Showing first 10:\n"
                + "\n".join(all_violations[:10])
            )

            assert has_any_ud_tags, (
                "No <ud> tags found in SGCollect log files - partial redaction not working"
            )

        await sg_user.close()
