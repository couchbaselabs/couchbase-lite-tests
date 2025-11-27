import re
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
    """
    violations = []
    for pattern in sensitive_patterns:
        escaped_pattern = re.escape(pattern)
        for match in re.finditer(escaped_pattern, log_content):
            start_pos = match.start()
            end_pos = match.end()

            # Check if this occurrence is within <ud>...</ud> tags
            before_text = log_content[max(0, start_pos - 100) : start_pos]
            after_text = log_content[end_pos : min(len(log_content), end_pos + 100)]

            has_opening_tag = "<ud>" in before_text and before_text.rfind(
                "<ud>"
            ) > before_text.rfind("</ud>")
            has_closing_tag = "</ud>" in after_text

            if not (has_opening_tag and has_closing_tag):
                context_start = max(0, start_pos - 50)
                context_end = min(len(log_content), end_pos + 50)
                context = log_content[context_start:context_end]
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
        password = "password"

        self.mark_test_step("Create bucket and default collection")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway with log redaction enabled")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        if await sg.database_exists(sg_db):
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to channels")
        sg_user = await sg.create_user_client(sg, sg_db, username, password, channels)

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
        all_docs = await sg_user.get_all_documents(
            sg_db, "_default", "_default", use_public_api=True
        )
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
                log_contents = await sg.fetch_log_file_via_caddy(log_type)
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
        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.skip(
        reason="SGCollect zip file discovery via Caddy not yet implemented (requires SSH or directory browsing)"
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgcollect_redacted_files_and_contents(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Test SGCollect REST API for redacted files and log file contents.

        TODO: This test is skipped until we implement a way to discover SGCollect
        zip filenames without SSH (e.g., enable Caddy directory browsing, or have
        SGCollect API return the output filename).
        """
        pass
