import os
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
        await sg.add_user(
            sg_db,
            username,
            password=password,
            collection_access={"_default": {"_default": {"admin_channels": channels}}},
        )

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

        self.mark_test_step("Verify docs were created")
        all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        assert len(all_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(all_docs.rows)}"
        )

        self.mark_test_step("Fetch and scan SG logs for redaction violations")
        server_config = await sg.get_server_config()
        log_dir = server_config.get("logging", {}).get(
            "log_file_path", "/home/ec2-user/log"
        )
        remote_log_path = f"{log_dir}/sg_debug.log"
        try:
            log_contents = sg.fetch_log_file(remote_log_path, ssh_key_path)
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

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
