import os
import tempfile
import zipfile
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import (
    DocumentUpdateEntry,
    PutDatabasePayload,
    scan_logs_for_untagged_sensitive_data,
)


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
        ssh_key_path = os.environ.get(
            "SSH_KEY_PATH", os.path.expanduser("~/.ssh/jborden.pem")
        )

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

        self.mark_test_step("Fetch and scan SG logs for redaction violations")
        try:
            log_contents = await sg.fetch_log_file("debug", ssh_key_path)
        except Exception as e:
            raise Exception(f"Could not fetch log file: {e}")
        sensitive_patterns = sg_doc_ids + [username]
        violations = scan_logs_for_untagged_sensitive_data(
            log_contents, sensitive_patterns
        )
        assert len(violations) == 0, (
            f"Found {len(violations)} log redaction violations: Showing first 10:\n"
            + "\n".join(violations[:10])
        )

        await sg_user.close()
        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_redacted_files_via_command_line(
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
        ssh_key_path = os.environ.get(
            "SSH_KEY_PATH", os.path.expanduser("~/.ssh/jborden.pem")
        )

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

        self.mark_test_step(f"Create user '{username}' with access to {channels}")
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

        self.mark_test_step("Verify docs were created via public API")
        all_docs = await sg_user.get_all_documents(
            sg_db, "_default", "_default", use_public_api=True
        )
        assert len(all_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(all_docs.rows)}"
        )

        self.mark_test_step("Run SGCollect to generate diagnostic zip")
        zip_path = await sg.run_sgcollect_info(ssh_key_path, "sgcollect_test")

        self.mark_test_step("Verify redacted zip marks sensitive data with <ud> tags")
        if zip_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                local_zip = os.path.join(temp_dir, "redacted.zip")
                sg.download_file(zip_path, local_zip, ssh_key_path)

                extract_dir = os.path.join(temp_dir, "extracted_redacted")
                os.makedirs(extract_dir)
                with zipfile.ZipFile(local_zip, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)

                sg_log_names = [
                    "sg_debug.log",
                    "sg_info.log",
                    "sg_error.log",
                    "sg_warn.log",
                ]
                log_files = [
                    os.path.join(root, f)
                    for root, dirs, files in os.walk(extract_dir)
                    for f in files
                    if f in sg_log_names
                ]
                assert len(log_files) > 0, "No SG log files found in redacted zip"

                sensitive_patterns = sg_doc_ids + [username]
                all_violations = []

                for log_file in log_files:
                    with open(log_file, encoding="utf-8", errors="ignore") as f:
                        log_content = f.read()
                        violations = scan_logs_for_untagged_sensitive_data(
                            log_content, sensitive_patterns
                        )
                        if violations:
                            all_violations.extend(
                                [
                                    f"{os.path.basename(log_file)}: {v}"
                                    for v in violations
                                ]
                            )
                assert len(all_violations) == 0, (
                    f"Found {len(all_violations)} log redaction violations: \n"
                    + "\n".join(all_violations)
                )
        else:
            pytest.fail("No redacted zip created when redaction_level is 'partial'")

        await sg_user.close()
        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgcollect_via_rest_api(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["logging"]
        username = "vipul"
        password = "password"
        ssh_key_path = os.environ.get(
            "SSH_KEY_PATH", os.path.expanduser("~/.ssh/jborden.pem")
        )

        self.mark_test_step("Create bucket and default collection")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        if await sg.database_exists(sg_db):
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to {channels}")
        sg_user = await sg.create_user_client(sg, sg_db, username, password, channels)

        self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs):
            sg_docs.append(
                DocumentUpdateEntry(
                    f"sg_doc_{i}",
                    None,
                    body={"type": "test_doc", "index": i, "channels": channels},
                )
            )
        await sg.update_documents(sg_db, sg_docs, "_default", "_default")

        self.mark_test_step("Start SGCollect via REST API and wait for it to complete")
        resp = await sg.start_sgcollect_via_api(redact_level="partial")
        assert resp.get("status") == "started", f"SGCollect failed to start: {resp}"
        await sg.wait_for_sgcollect_to_complete()

        self.mark_test_step("Verify all expected log files exist in SGCollect zip")
        server_config = await sg._send_request("GET", "/_config")
        log_dir = server_config.get("logging", {}).get(
            "log_file_path", "/home/ec2-user/log"
        )
        latest_zip = sg.ssh_exec_command(
            f"ls -t {log_dir}/sgcollectinfo-*-redacted.zip | head -1", ssh_key_path
        )
        assert latest_zip, "No sgcollect zip found"

        with tempfile.TemporaryDirectory() as temp_dir:
            local_zip = os.path.join(temp_dir, "sgcollect.zip")
            sg.download_file(latest_zip, local_zip, ssh_key_path)

            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir)
            with zipfile.ZipFile(local_zip, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
            expected_logs = [
                "sg_debug.log",
                "sg_info.log",
                "sg_error.log",
                "sg_warn.log",
                "sg_trace.log",
                "sg_stats.log",
            ]
            found_logs = []
            for root, dirs, files in os.walk(extract_dir):
                found_logs.extend([f for f in files if f.endswith(".log")])
            missing_logs = [log for log in expected_logs if log not in found_logs]
            assert len(missing_logs) == 0, f"Missing log files: {missing_logs}"

            self.mark_test_step("Verify content of sync_gateway.log")
            sg_log_path = None
            for root, dirs, files in os.walk(extract_dir):
                if "sync_gateway.log" in files:
                    sg_log_path = os.path.join(root, "sync_gateway.log")
                    break
            assert sg_log_path is not None, (
                "sync_gateway.log not found in SGCollect zip"
            )
            actual_hostname = sg.ssh_exec_command("hostname", ssh_key_path)
            with open(sg_log_path, encoding="utf-8", errors="ignore") as f:
                sg_log_content = f.read()

            hostname_found = (
                f"hostname: {actual_hostname}" in sg_log_content
                or f"hostname = {actual_hostname}" in sg_log_content
                or f"kernel.hostname = {actual_hostname}" in sg_log_content
                or actual_hostname in sg_log_content
            )
            assert hostname_found, (
                f"Hostname '{actual_hostname}' not found in sync_gateway.log. "
                f"Log may not contain system information."
            )

        await sg_user.close()
        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
