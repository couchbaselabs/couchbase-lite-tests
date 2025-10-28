from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestXattrs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_offline_processing_of_external_updates(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs_per_client = 1000
        sg_db = "db"
        bucket_name = "data-bucket"

        self.mark_test_step("Create bucket and default collection")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_config = {
            "bucket": bucket_name,
            "num_index_replicas": 0,
            "enable_shared_bucket_access": True,
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step("Create user 'vipul' with access to SG and SDK channels")
        await sg.add_user(
            sg_db,
            "vipul",
            password="pass",
            collection_access={
                "_default": {"_default": {"admin_channels": ["SG", "SDK", "*"]}}
            },
        )

        self.mark_test_step(f"Write {num_docs_per_client} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        sg_doc_ids: list[str] = []
        for i in range(num_docs_per_client):
            doc_id = f"sg_{i}"
            sg_doc_ids.append(doc_id)
            sg_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    None,  # No revision for new docs
                    body={
                        "type": "sg_doc",
                        "index": i,
                        "channels": ["SG"],
                        "created_by": "sync_gateway",
                    },
                )
            )

        batch_size = 500
        for batch_start in range(0, num_docs_per_client, batch_size):
            batch_end = min(batch_start + batch_size, num_docs_per_client)
            await sg.update_documents(
                sg_db,
                sg_docs[batch_start:batch_end],
                scope="_default",
                collection="_default",
            )

        self.mark_test_step("Verify all SG docs were created successfully")
        sg_all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        sg_created_count = len(
            [doc for doc in sg_all_docs.rows if doc.id.startswith("sg_")]
        )
        assert sg_created_count == num_docs_per_client, (
            f"Expected {num_docs_per_client} SG docs, but found {sg_created_count}"
        )

        self.mark_test_step("Stop Sync Gateway")
        await sg.delete_database(sg_db)

        self.mark_test_step(f"Update {num_docs_per_client} SG docs via SDK")
        for doc_id in sg_doc_ids:
            doc_body: dict[str, Any] = {
                "type": "sg_doc",
                "index": int(doc_id.split("_")[1]),
                "channels": ["SG"],
                "created_by": "sync_gateway",
                "updated_by_sdk": True,
            }
            cbs.upsert_document(
                bucket_name, doc_id, doc_body, scope="_default", collection="_default"
            )

        self.mark_test_step(f"Write {num_docs_per_client} new docs via SDK")
        sdk_doc_ids: list[str] = []
        for i in range(num_docs_per_client):
            doc_id = f"sdk_{i}"
            sdk_doc_ids.append(doc_id)
            doc_body = {
                "type": "sdk_doc",
                "index": i,
                "channels": ["SDK"],
                "created_by": "sdk",
            }
            cbs.upsert_document(
                bucket_name, doc_id, doc_body, scope="_default", collection="_default"
            )

        self.mark_test_step("Restart Sync Gateway (recreate database endpoint)")
        await sg.put_database(sg_db, db_payload)
        await sg.add_user(
            sg_db,
            "seth",
            password="pass",
            collection_access={
                "_default": {"_default": {"admin_channels": ["SG", "SDK", "*"]}}
            },
        )

        self.mark_test_step("Verify all docs are accessible via Sync Gateway")
        all_doc_ids = sg_doc_ids + sdk_doc_ids
        assert len(all_doc_ids) == num_docs_per_client * 2, (
            f"Expected {num_docs_per_client * 2} total docs, but have {len(all_doc_ids)} doc IDs"
        )

        sg_all_docs_after_restart = await sg.get_all_documents(
            sg_db, "_default", "_default"
        )
        doc_revisions: dict[str, str] = {}
        for row in sg_all_docs_after_restart.rows:
            doc_revisions[row.id] = row.revision

        self.mark_test_step("Verify all expected documents are present")
        for doc_id in all_doc_ids:
            assert doc_id in doc_revisions, (
                f"Document '{doc_id}' not found in Sync Gateway after restart"
            )

        self.mark_test_step("Verify document revisions are correct")
        sg_docs_with_wrong_rev = []
        sdk_docs_with_wrong_rev = []
        for doc_id in all_doc_ids:
            rev = doc_revisions[doc_id]
            if doc_id.startswith("sg_"):
                if not rev.startswith("2-"):
                    sg_docs_with_wrong_rev.append(f"{doc_id} has rev {rev}")
            else:
                if not rev.startswith("1-"):
                    sdk_docs_with_wrong_rev.append(f"{doc_id} has rev {rev}")

        assert len(sg_docs_with_wrong_rev) == 0, (
            f"SG documents have incorrect revisions (expected 2-*): {sg_docs_with_wrong_rev[:10]}"
        )
        assert len(sdk_docs_with_wrong_rev) == 0, (
            f"SDK documents have incorrect revisions (expected 1-*): {sdk_docs_with_wrong_rev[:10]}"
        )

        self.mark_test_step("Verify document contents for sample documents")
        sample_sg_docs = sg_doc_ids[:5]
        for doc_id in sample_sg_docs:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            assert doc is not None, f"Document {doc_id} not found"
            assert doc.body.get("updated_by_sdk") is True, (
                f"Document {doc_id} doesn't have 'updated_by_sdk' flag"
            )
            assert doc.revid and doc.revid.startswith("2-"), (
                f"Document {doc_id} has incorrect revision: {doc.revid}"
            )

        sample_sdk_docs = sdk_doc_ids[:5]
        for doc_id in sample_sdk_docs:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            assert doc is not None, f"Document {doc_id} not found"
            assert doc.body.get("created_by") == "sdk", (
                f"Document {doc_id} doesn't have correct 'created_by' value"
            )
            assert doc.revid and doc.revid.startswith("1-"), (
                f"Document {doc_id} has incorrect revision: {doc.revid}"
            )

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
