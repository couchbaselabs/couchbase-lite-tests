import asyncio
import json
from pathlib import Path

import pytest
import requests
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
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote


async def bytes_transferred(cblpytest: CBLPyTest, dataset_name: str) -> tuple[int, int]:
    resp = requests.get(
        cblpytest.sync_gateways[0].get_expvars(),
        verify=False,
        auth=("admin", "password"),
    )
    resp.raise_for_status()
    expvars = resp.json()

    db_stats = expvars["syncgateway"]["per_db"][dataset_name]["database"]
    doc_reads_bytes = db_stats["doc_reads_bytes_blip"]
    doc_writes_bytes = db_stats["doc_writes_bytes_blip"]
    return doc_reads_bytes, doc_writes_bytes


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
            5. Verify number of docs updated using delta sync.
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

        self.mark_test_step("Modify docs in CBL with and without attachment")
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])
            b.upsert_document(
                "travel.hotels",
                "hotel_2",
                [
                    {
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
                    }
                ],
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

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_before, _ = await bytes_transferred(cblpytest, "travel")

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
                    "description": "Its a stupid hotel.",
                    "image": {
                        "@type": "blob",
                        "content_type": "image/png",
                        "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                        "length": 156627,
                    },
                    "name": "The stupid hotel",
                },
            ),
        ]
        await cblpytest.sync_gateways[0].upsert_documents(
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

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_after, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step(
            "Verify delta sync bytes transferred is less than doc size."
        )
        sgw_doc_1 = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        sgw_doc_2 = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_2", "travel", "hotels"
        )
        updated_doc_size = len(json.dumps(sgw_doc_1.body).encode("utf-8")) + len(
            json.dumps(sgw_doc_2.body).encode("utf-8")
        )
        delta_bytes_read = read_pull_bytes_after - read_pull_bytes_before
        assert delta_bytes_read < updated_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes_read} bytes (doc size: {updated_doc_size})"
        )

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
                [{"name": "CBL", "nested": {"name": "I am a nested field"}}],
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

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_before, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Verify the nested document is present in SGW")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("name") == "CBL", "Document should have the correct name"
        assert doc.body.get("nested", {}).get("name") == "I am a nested field", (
            "Nested document should have the correct name"
        )

        self.mark_test_step("Update docs in SGW with nested docs")
        updates = [
            DocumentUpdateEntry(
                "hotel_1",
                None,
                {"name": "SGW", "nested": {"name": "I am a nested field"}},
            )
        ]
        await cblpytest.sync_gateways[0].upsert_documents(
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

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_after, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step(
            "Verify delta sync bytes transferred is less than doc size."
        )
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        updated_doc_size = len(json.dumps(sgw_doc.body).encode("utf-8"))
        delta_bytes_read = read_pull_bytes_after - read_pull_bytes_before
        assert delta_bytes_read < updated_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes_read} bytes (doc size: {updated_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_utf8_strings(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify delta sync works with UTF-8 strings
            1. Have delta sync enabled
            2. Create docs in CBL
            3. Do push replication to SGW
            4. update docs in SGW/CBL with utf8 strings
            5. replicate docs using pull replication
            6. Verify that docs replicated successfully and only delta is replicated
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

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Create docs in CBL")
        utf8_body = "東京🚀🌏Привет世界مرحبا" * 100
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels", "hotel_1", [{"name": "CBL", "utf8": utf8_body}]
            )

        self.mark_test_step("Do push replication to SGW")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        bytes_pull_before, _ = await bytes_transferred(cblpytest, "travel")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        self.mark_test_step("Update docs in SGW/CBL with utf8 strings")
        updates = [
            DocumentUpdateEntry(
                "hotel_1",
                sgw_doc.revid,
                {
                    "name": "SGW",
                    "utf8": utf8_body,
                },
            )
        ]
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel", updates, "travel", "hotels"
        )

        self.mark_test_step("Do pull replication")
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

        self.mark_test_step("Record the bytes transferred")
        bytes_pull_after, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Verify only delta is updated.")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        delta_bytes_transferred = bytes_pull_after - bytes_pull_before
        assert delta_bytes_transferred < updated_doc_size, (
            "Expected delta to be less than the full doc size"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_enabled_disabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify delta sync works with enabled and disabled delta sync
            1. Have delta sync enabled.
            2. Create docs in CBL.
            3. Do PUSH replication to SGW.
            4. Update docs in SGW.
            5. Replicate docs using PULL replication.
            6. Verify stats shows number of docs updated with delta sync.
            7. Reset SG and load `posts` dataset with delta sync disabled.
            8. Reset local database, and load `posts` dataset.
            9. Create docs in CBL.
            10. Start replication.
            11. Verify stats shows number of docs updated.
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

        self.mark_test_step("Verify docs are replicated correctly")
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

        self.mark_test_step("Create docs in CBL")
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels", "hotel_1", [{"name": "CBL", "extra": "a" * 3000}]
            )

        self.mark_test_step("Start replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_before, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Update doc on SGW")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel",
            [
                DocumentUpdateEntry(
                    "hotel_1", sgw_doc.revid, {"name": "SGW", "extra": "a" * 3000}
                )
            ],
            "travel",
            "hotels",
        )

        self.mark_test_step("Do pull replication")
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_after, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Verify delta transferred is less than doc size.")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        delta_bytes_transferred = bytes_read_after - bytes_read_before
        assert delta_bytes_transferred < updated_doc_size, (
            "Expected delta to be less than the full doc size"
        )

        self.mark_test_step(
            "Reset SG and load `posts` dataset with delta sync disabled"
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database, and load `posts` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("Start a replicator")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
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

        self.mark_test_step("Verify docs are replicated correctly")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "posts",
            ["_default.posts"],
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {len(lite_all_docs['_default.posts'])})"
        )

        self.mark_test_step("Create docs in CBL")
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts", "post_1", [{"channels": ["group1"], "name": "CBL"}]
            )

        self.mark_test_step("Start replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_1",
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_before, _ = await bytes_transferred(cblpytest, "posts")

        self.mark_test_step("Update doc on SGW")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1", collection="posts"
        )
        await cblpytest.sync_gateways[0].upsert_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_1", sgw_doc.revid, {"channels": ["group1"], "name": "SGW"}
                )
            ],
            collection="posts",
        )

        self.mark_test_step("Do pull replication")
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_1",
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_after, _ = await bytes_transferred(cblpytest, "posts")

        self.mark_test_step("Verify delta transferred equivalent to doc size.")
        cbl_doc = await db.get_document(DocumentEntry("_default.posts", "post_1"))
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        delta_bytes_transferred = bytes_read_after - bytes_read_before
        assert delta_bytes_transferred >= 0.8 * updated_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_transferred} bytes read (doc size: {updated_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_within_expiry(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify delta sync works within expiry time
            1. Have delta sync enabled.
            2. Update docs in CBL.
            3. Do replication to SGW.
            4. Record the bytes transferred.
            5. Wait for the delta revision to expire.
            6. Update docs in SGW.
            7. Replicate docs back to CBL.
            8. Record the bytes transferred.
            9. Verify the bytes transferred now are more than step 4.
        """
        self.mark_test_step(
            "Reset SG and load `short_expiry` dataset with delta sync enabled"
        )
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(
            dataset_path, "short_expiry", ["delta_sync_with_expiry"]
        )

        self.mark_test_step("Reset local database, and load `short_expiry` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step("Create docs in CBL")
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default", "doc_1", [{"channels": ["group1"], "name": "CBL"}]
            )

        self.mark_test_step("Replicate to SGW")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("short_expiry"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default._default",
                    "doc_1",
                    ReplicatorType.PUSH,
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

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_before, _ = await bytes_transferred(cblpytest, "short_expiry")

        self.mark_test_step("Verify doc body in SGW matches the updates from CBL")
        sgw_doc = await cblpytest.sync_gateways[0].get_document("short_expiry", "doc_1")
        assert sgw_doc.body.get("name") == "CBL", "Expected doc to have `name` as `CBL`"

        self.mark_test_step("Update docs in SGW")
        await cblpytest.sync_gateways[0].upsert_documents(
            "short_expiry",
            [
                DocumentUpdateEntry(
                    "doc_1", sgw_doc.revid, {"channels": ["group1"], "name": "SGW"}
                )
            ],
        )
        self.mark_test_step("Wait for 60 seconds for delta revision to expire")
        await asyncio.sleep(60)

        self.mark_test_step("Replicate back to CBL")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("short_expiry"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
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

        self.mark_test_step("Record the bytes transferred post expiry")
        read_pull_bytes_after, _ = await bytes_transferred(cblpytest, "short_expiry")
        delta_bytes_read = read_pull_bytes_after - read_pull_bytes_before

        self.mark_test_step("Verify the doc in SGW and CBL have same content.")
        sgw_doc = await cblpytest.sync_gateways[0].get_document("short_expiry", "doc_1")
        cbl_doc = await db.get_document(DocumentEntry("_default._default", "doc_1"))
        assert sgw_doc.body.get("name") == cbl_doc.body.get("name") == "SGW", (
            "Expected doc to have same content"
        )

        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        assert delta_bytes_read >= 0.8 * updated_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_read} bytes read (doc size: {updated_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_with_no_deltas(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Testing a specific case where an update to a document doesn't produce any changes at all (i.e. empty delta)
            1. Create new docs in CBL/ SGW
            2. Do push_pull one shot replication to SGW
            3. Update doc on SGW/CBL
            4. Update doc on SGW/CBL again to have same value as rev-1
            5. update same doc in SGW/cbl which still has rev-1
            6. Verify the body of the doc matches with sgw and cbl
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

        self.mark_test_step("Do initial push_pull replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify docs are replicated correctly")
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Update doc on CBL")
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Replicate to SGW")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Update doc on SGW with same body")
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", None, {"name": "CBL"})],
            "travel",
            "hotels",
        )

        self.mark_test_step(
            "Update doc on SGW again to have same value as previous rev"
        )
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", None, {"name": "CBL"})],
            "travel",
            "hotels",
        )

        self.mark_test_step("Replicate docs with continuous replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator idles.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Update doc on CBL again to have same value as previous rev"
        )
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Wait until the replicator idles.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify doc body matches between SGW and CBL")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert sgw_doc.body.get("name") == cbl_doc.body.get("name"), (
            "Expected doc to have same content"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_larger_than_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary: Verify delta sync works when the delta is larger than the doc
            1. Have delta sync enabled
            2. Create docs in CBL
            3. Do push replication to SGW
            4. get delta stats
            5. update docs in SGW, update has to be larger than doc in bytes
            6. replicate docs to CBL
            7. get delta stats
            8. Verify full doc is replicated. Delta size at step 7 shold be same as step 4
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

        self.mark_test_step("Do initial replication")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify docs are replicated correctly")
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Update doc on CBL")
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Replicate to SGW")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Get delta stats")
        bytes_read_before, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Update doc on SGW with larger body")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        current_rev = doc.revid
        large_doc_body = "X" * 2_000_000
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", current_rev, {"name": large_doc_body})],
            "travel",
            "hotels",
        )

        self.mark_test_step("Replicate doc to CBL")
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

        self.mark_test_step("Get delta stats")
        bytes_read_after, _ = await bytes_transferred(cblpytest, "travel")

        self.mark_test_step("Verify full doc is replicated")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert cbl_doc.body.get("name") == large_doc_body, (
            "Expected doc to have same content"
        )

        self.mark_test_step("Verify delta size at step 7 is >= step 4")
        large_doc_size = len(large_doc_body.encode("utf-8"))
        delta_bytes_read = bytes_read_after - bytes_read_before

        assert delta_bytes_read > 0.8 * large_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_read} bytes read (doc size: {large_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")
