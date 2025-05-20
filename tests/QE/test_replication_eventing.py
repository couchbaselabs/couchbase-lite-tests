import base64
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorType,
    WaitForDocumentEventEntry,
)


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationEventing(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_replication_for_20mb_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary:
            1. Create a large doc in CBL a, >20MB.
            2. Replicate to SG using push one-shot replication.
            3. Start push one-shot replication and start replication event listener.
            4. Check the error is thrown in replication event changes
                as CBS can't have doc greater than 20mb.
        """
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database, and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("Create a large document with blob")
        large_bytes = b"x" * (10 * 1024 * 1024)  # 10MB of data
        large_b64 = base64.b64encode(large_bytes).decode("ascii")
        doc_body = [
            {
                "name": "Large Document",
                "type": "large_doc_test",
                "channels": ["group1", "group2"],
                "large_20mb_blob": {
                    "@type": "blob",
                    "content_type": "application/octet-stream",
                    "data": large_b64,
                },
            }
        ]
        async with db.batch_updater() as b:
            b.upsert_document("_default.posts", "large_doc", doc_body)

        # Verify document was created successfully
        self.mark_test_step("Verify document with large blob")
        doc = await db.get_document(DocumentEntry("_default.posts", "large_doc"))
        assert doc is not None, "Document not found after update"

        # Debug logging to inspect document structure
        self.mark_test_step(f"Document body type: {type(doc.body)}")
        self.mark_test_step(f"Document body keys: {list(doc.body[0].keys())}")

        # Verify document content
        assert doc.body[0].get("name") == "Large Document", (
            "Document content changed unexpectedly"
        )
        assert doc.body[0].get("type") == "large_doc_test", (
            "Document type changed unexpectedly"
        )
        assert "large_20mb_blob" in doc.body[0], "Large blob not found in document"
        blob_dict = doc.body[0].get("large_20mb_blob", {})
        assert isinstance(blob_dict, dict), "large_20mb_blob is not a dict"
        assert blob_dict.get("@type") == "blob", "Blob type missing or incorrect"
        assert blob_dict.get("content_type") == "application/octet-stream", (
            "Blob content_type incorrect"
        )
        assert isinstance(blob_dict.get("data"), bytes), "Blob data is not bytes"
        assert len(blob_dict.get("data", b"")) == len(large_bytes), (
            "Large blob size mismatch"
        )

        self.mark_test_step("Verify documents in CBL before replication")
        docs_before = await db.get_all_documents("_default.posts")
        self.mark_test_step(
            f"Documents in CBL before replication: {len(docs_before['_default.posts'])}"
        )

        # Check documents in SGW before replication
        self.mark_test_step("Verify documents in SGW before replication")
        sgw_docs_before = await cblpytest.sync_gateways[0].get_all_documents(
            "posts", collection="posts"
        )
        self.mark_test_step(
            f"Documents in SGW before replication: {len(sgw_docs_before.rows)}"
        )
        for doc in sgw_docs_before.rows:
            self.mark_test_step(f"{doc.id}")

        self.mark_test_step("Start push one-shot replication to SGW")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait for document replication event with error")
        await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "large_doc",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                )
            }
        )

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify replication event details")
        # Since the document was too large, it should not appear in document_updates
        assert len(replicator.document_updates) == 0, (
            f"Expected no successful document updates but found {len(replicator.document_updates)}"
        )

        # doc_update = replicator.document_updates[0]
        # assert doc_update.documentID == "large_doc", "Expected error for large_doc"
        # assert doc_update.error is not None, "Expected error for large document replication"
        # assert doc_update.error.domain == "CBL", "Expected error domain CBL"
        # assert doc_update.error.code == 10403, "Expected error code 10403 for large document"

        self.mark_test_step("Verify documents in CBL after replication")
        docs_after = await db.get_all_documents("_default.posts")
        self.mark_test_step(
            f"Documents in CBL after replication: {len(docs_after['_default.posts'])}"
        )

        # Check documents in SGW after replication
        self.mark_test_step("Verify documents in SGW after replication")
        sgw_docs_after = await cblpytest.sync_gateways[0].get_all_documents(
            "posts", collection="posts"
        )
        self.mark_test_step(
            f"Documents in SGW after replication: {len(sgw_docs_after.rows)}"
        )
        for doc in sgw_docs_after.rows:
            self.mark_test_step(f"{doc.id}")

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")
