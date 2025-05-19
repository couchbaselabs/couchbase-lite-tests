from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote


class TestDeltaSync(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify push/pull replication works with large data
            1. Create docs in CBL
            2. Do push_pull replication
            3. update docs in SGW  with/without attachment
            4. Do push/pull replication
            5. Verify delta sync stats shows bandwidth saving, replication count, number of docs updated using delta sync.
        """
        self.mark_test_step(
            "Reset SG and load `travel` dataset with delta sync enabled"
        )
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel", ["delta_sync"])

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("Start a replicator")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])}"
        )

        self.mark_test_step("Modify docs in CBL")
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Do push_pull replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify the new document is present in SGW")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("name") == "CBL", "Document should have the correct name"

        self.mark_test_step("Update docs in SGW  with and without attachment")
        updates = [
            DocumentUpdateEntry("hotel_1", None, {"name": "SGW"}),
            DocumentUpdateEntry(
                "hotel_2",
                None,
                body={
                    "_attachments": {
                        "blob_/image": {
                            "content_type": "image/png",
                            "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                            "length": 156627,
                            "revpos": 1,
                            "stub": True,
                        }
                    },
                    "description": "This boutique hotel offers five unique food and beverage venues.",
                    "image": {
                        "@type": "blob",
                        "content_type": "image/png",
                        "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                        "length": 156627,
                    },
                    "name": "The Padre Hotel",
                },
            ),
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "travel", updates, "travel", "hotels"
        )

        self.mark_test_step("Do push_pull replication")
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_1",
                    ReplicatorType.PUSH_AND_PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_2",
                    ReplicatorType.PUSH_AND_PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
            }
        )
        assert events, "Expected documents to be processed"

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify delta sync stats shows number of docs updated using delta sync."
        )
        repl_status = await replicator.get_status()
        assert repl_status.progress.completed, "Expected replication to be completed"
        processed_docs = len(replicator.document_updates)
        updated_doc_ids = {"hotel_1", "hotel_2"}
        processed_updated_docs = [
            doc
            for doc in replicator.document_updates
            if doc.document_id in updated_doc_ids
        ]
        assert len(processed_updated_docs) == 2, (
            f"Expected only 2 updated documents to be processed due to delta sync, "
            f"but got {len(processed_updated_docs)} (total processed: {processed_docs})"
        )
        updated_doc_ids = {doc.document_id for doc in replicator.document_updates}
        assert "hotel_1" in updated_doc_ids, "hotel_1 should be in updated documents"
        assert "hotel_2" in updated_doc_ids, "hotel_2 should be in updated documents"

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_nested_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify delta sync works with nested documents
            1. Create docs in CBL with nested docs.
            2. Do push_pull replication.
            3. Update docs in SGW with nested docs.
            4. Do push/pull replication
            5. Verify delta sync stats shows number of docs updated using delta sync.
        """
        self.mark_test_step(
            "Reset SG and load `travel` dataset with delta sync enabled"
        )
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel", ["delta_sync"])

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("Start a replicator")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])}"
        )

        self.mark_test_step("Modify docs in CBL with nested docs")
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels",
                "hotel_1",
                [{"name": "CBL", "nested": {"name": "Nested CBL"}}],
            )

        self.mark_test_step("Do push_pull replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify the nested document is present in SGW")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("name") == "CBL", "Document should have the correct name"
        assert doc.body.get("nested", {}).get("name") == "Nested CBL", (
            "Nested document should have the correct name"
        )

        self.mark_test_step("Update docs in SGW with nested docs")
        updates = [
            DocumentUpdateEntry(
                "hotel_1", None, {"name": "SGW", "nested": {"name": "Nested SGW"}}
            )
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "travel", updates, "travel", "hotels"
        )

        self.mark_test_step("Do push_pull replication")
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_1",
                    ReplicatorType.PUSH_AND_PULL,
                    ReplicatorDocumentFlags.NONE,
                )
            }
        )
        assert events, "Expected documents to be processed"

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify delta sync stats shows number of docs updated using delta sync."
        )
        repl_status = await replicator.get_status()
        assert repl_status.progress.completed, "Expected replication to be completed"
        processed_docs = len(replicator.document_updates)
        updated_doc_ids = {"hotel_1"}
        processed_updated_docs = [
            doc
            for doc in replicator.document_updates
            if doc.document_id in updated_doc_ids
        ]
        assert len(processed_updated_docs) == 1, (
            f"Expected only 1 updated document to be processed due to delta sync, "
            f"but got {len(processed_updated_docs)} (total processed: {processed_docs})"
        )
        updated_doc_ids = {doc.document_id for doc in replicator.document_updates}
        assert "hotel_1" in updated_doc_ids, "hotel_1 should be in updated documents"

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")
