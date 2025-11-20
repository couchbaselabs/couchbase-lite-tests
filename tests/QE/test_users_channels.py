import time
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from packaging.version import Version


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(3)
@pytest.mark.min_couchbase_servers(1)
class TestUsersChannels(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_single_user_multiple_channels(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sgs = cblpytest.sync_gateways
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["ABC", "CBS", "NBC", "FOX"]
        username = "vipul"
        password = "pass"
        num_batches = 50
        batch_size = 100
        total_docs = num_batches * batch_size
        num_sgs = len(sgs)

        self.mark_test_step("Create single shared bucket for all SGW nodes")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step(
            f"Configure database '{sg_db}' on all {num_sgs} SGW nodes (pointing to shared bucket)"
        )
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)

        for sg in sgs:
            db_status = await sg.get_database_status(sg_db)
            if db_status is not None:
                await sg.delete_database(sg_db)
            await sg.put_database(sg_db, db_payload)

        self.mark_test_step(
            f"Create user '{username}' with access to {channels} (stored in shared bucket)"
        )
        sg_user = await sgs[0].create_user_client(sg_db, username, password, channels)

        self.mark_test_step(
            f"Bulk create {total_docs} documents in {num_batches} batches of {batch_size} docs "
            f"using round-robin across {num_sgs} SGW nodes"
        )
        doc_ids: list[str] = []
        for batch_num in range(num_batches):
            target_sg = sgs[batch_num % num_sgs]
            docs: list[DocumentUpdateEntry] = []
            for i in range(batch_size):
                doc_id = f"doc_{batch_num}_{i}"
                doc_ids.append(doc_id)
                channel = channels[i % len(channels)]
                docs.append(
                    DocumentUpdateEntry(
                        doc_id,
                        None,
                        body={
                            "type": "test_doc",
                            "batch": batch_num,
                            "index": i,
                            "channels": [channel],
                            "updates": 0,
                            "created_via_sgw": batch_num % num_sgs,
                        },
                    )
                )
            await target_sg.update_documents(sg_db, docs, "_default", "_default")

        self.mark_test_step("Wait for documents to propagate across all SGW nodes")
        time.sleep(10)

        self.mark_test_step(
            f"Verify user sees all {total_docs} docs via changes feed from first SGW"
        )
        changes = await sg_user.get_changes(sg_db)
        user_doc_changes = [entry for entry in changes.results if entry.id in doc_ids]
        assert len(user_doc_changes) == total_docs, (
            f"Expected {total_docs} docs in changes feed, got {len(user_doc_changes)}"
        )

        self.mark_test_step("Verify no duplicate documents in changes feed")
        unique_ids = {entry.id for entry in user_doc_changes}
        assert len(unique_ids) == total_docs, (
            f"Duplicate documents found in changes feed. "
            f"Expected: {total_docs}, Got: {len(unique_ids)}"
        )

        self.mark_test_step("Verify all expected document IDs are present")
        expected_ids = set(doc_ids)
        actual_ids = unique_ids
        missing_ids = expected_ids - actual_ids
        unexpected_ids = actual_ids - expected_ids
        assert len(missing_ids) == 0, f"Missing document IDs: {missing_ids}"
        assert len(unexpected_ids) == 0, f"Unexpected document IDs: {unexpected_ids}"

        self.mark_test_step(
            "Verify user can retrieve all documents via _all_docs from one SGW node"
        )
        all_docs = await sg_user.get_all_documents(sg_db)
        all_docs_ids = [row.id for row in all_docs.rows if row.id in doc_ids]
        assert len(all_docs_ids) == total_docs, (
            f"Expected {total_docs} docs via _all_docs, got {len(all_docs_ids)}"
        )

        self.mark_test_step("Verify all documents have correct revision format")
        for row in all_docs.rows:
            if row.id in doc_ids:
                assert len(row.revision) > 0, f"Document {row.id} has no revision"
                assert "-" in row.revision, (
                    f"Invalid revision format for {row.id}: {row.revision}"
                )

        sgw_version_obj = await sgs[0].get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")
        if supports_version_vectors:
            self.mark_test_step(
                "Verify all documents have correct version vector format (SGW 4.0+)"
            )
            for row in all_docs.rows:
                if row.id in doc_ids:
                    assert row.cv is not None and len(row.cv) > 0, (
                        f"Document {row.id} has no version vector"
                    )
                    assert "@" in row.cv, (
                        f"Invalid version vector format for {row.id}: {row.cv}"
                    )

        self.mark_test_step(
            "Verify all documents are accessible from each SGW node independently"
        )
        for i, sg in enumerate(sgs):
            test_user = await sg.create_user_client(sg_db, username, password, channels)
            node_all_docs = await test_user.get_all_documents(sg_db)
            node_doc_ids = [row.id for row in node_all_docs.rows if row.id in doc_ids]
            assert len(node_doc_ids) == total_docs, (
                f"SGW node {i}: Expected {total_docs} docs, got {len(node_doc_ids)}"
            )
            await test_user.close()

        await sg_user.close()
        await sgs[0].delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
