import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import BasicAuth
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

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.airlines`, `travel.airports`, `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Modify docs in CBL:
                * Update a doc in `travel.airlines` with text content
                * Add attachments to another doc in `travel.airports`
        """)
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

        self.mark_test_step("""
            Start another replicator:
                * endpoint: `/travel`
                * collections: `travel.airlines`, `travel.airports`, `travel.hotels`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: True
        """)
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
        read_pull_bytes_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify the new document is present in SGW")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("name") == "CBL", "Document should have the correct name"

        self.mark_test_step("""
            Update docs in SGW:
                * Update 2 airlines in `travel.airlines` with different text content
                * Modify attachments in 2 airports in `travel.airports`
        """)
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

        self.mark_test_step("Start the same replicator again.")
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
        read_pull_bytes_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step(
            "Verify delta sync bytes transferred is less than doc size."
        )
        sgw_doc_1 = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        sgw_doc_2 = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_2", "travel", "hotels"
        )
        assert sgw_doc_1 is not None and sgw_doc_2 is not None, (
            "Documents should exist in SGW"
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

        self.mark_test_step("""
            Start a pull replicator:
                * endpoint: `/travel`
                * collections: `travel.airlines`, `travel.routes`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Modify docs in CBL:
                * Update nested schedule in `travel.routes`
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels",
                "hotel_1",
                [{"name": "CBL", "nested": {"name": "I am a nested field"}}],
            )

        self.mark_test_step("""
            Start another replicator:
                * endpoint: `/travel`
                * collections: `travel.airlines`, `travel.routes`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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
        read_pull_bytes_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify the nested document is present in SGW")
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("name") == "CBL", "Document should have the correct name"
        assert doc.body.get("nested", {}).get("name") == "I am a nested field", (
            "Nested document should have the correct name"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Update nested fields in `travel.routes`
        """)
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

        self.mark_test_step("Start the same replicator again:")
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
        read_pull_bytes_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step(
            "Verify delta sync bytes transferred is less than doc size."
        )
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
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

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Create docs in CBL:
                * A `name` field : `CBL` and a `body` with large UTF-8 description
                    (Chinese, Japanese characters, emoji-rich descriptions)
        """)
        utf8_body = "東京🚀🌏Привет世界مرحبا"
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels", "hotel_1", [{"name": "CBL", "utf8": utf8_body}]
            )

        self.mark_test_step("Start the same replicator again.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        bytes_pull_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
        self.mark_test_step("""
            Update docs in SGW :
                * Keeping the body same but the `name` field changed to `SGW`.
        """)
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

        self.mark_test_step("Start the same replicator again.")
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

        self.mark_test_step("Record the bytes transferred again this time.")
        bytes_pull_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("""
            Verify only delta is updated while replicating and updating that document to CBL,
                with a new name and same body.
        """)
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert cbl_doc is not None, "Document should exist in CBL"
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

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Create docs in CBL:
                * `name`: `CBL` and a big value for a key: `extra`.
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.hotels", "hotel_1", [{"name": "CBL", "extra": "a" * 3000}]
            )

        self.mark_test_step("""
            Start another replicator this time:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Modify only the key `name`: `SGW`.
        """)
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
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

        self.mark_test_step("Start the same replicator again.")
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
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify delta transferred is less than doc size.")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert cbl_doc is not None, "Document should exist in CBL"
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        delta_bytes_transferred = bytes_read_after - bytes_read_before
        assert delta_bytes_transferred < updated_doc_size, (
            "Expected delta to be less than the full doc size"
        )

        self.mark_test_step(
            "Reset SG and load `posts` dataset with delta sync disabled"
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step(
            "Reset local database, and load `posts` dataset without delta sync."
        )
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Create docs in CBL:
                * Add a new doc.
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "post_1",
                [{"channels": ["group1"], "name": "CBL", "extra": "a" * 3000}],
            )

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default._default`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "posts"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Modify the `name` field of the new doc.
        """)
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1", collection="posts"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
        await cblpytest.sync_gateways[0].upsert_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_1",
                    sgw_doc.revid,
                    {"channels": ["group1"], "name": "SGW", "extra": "a" * 3000},
                )
            ],
            collection="posts",
        )

        self.mark_test_step("Start the same replicator again.")
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
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "posts"
        )

        self.mark_test_step("Verify delta transferred equivalent to doc size.")
        cbl_doc = await db.get_document(DocumentEntry("_default.posts", "post_1"))
        assert cbl_doc is not None, "Document should exist in CBL"
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
            4. Record the bytes transferred and the current revision.
            5. Wait for the delta revision to expire.
            6. Update docs in SGW.
            7. Replicate docs back to CBL.
            8. Record the bytes transferred.
            9. Verify the bytes transferred now are more than step 4.
            10. Verify old revision is expired by attempting to fetch it through public API.
        """
        self.mark_test_step("""
            Reset SG and load `short_expiry` dataset with delta sync enabled.
                * has a `old_rev_expiry_seconds` of 10 seconds.
                * has a rev_cache size of 1.
        """)
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "short_expiry", ["delta_sync"])

        self.mark_test_step("Verify SGW config has correct revision expiry settings")
        db_config = await cblpytest.sync_gateways[0]._send_request(
            "GET",
            "/short_expiry/_config",
        )
        print("Database config:", db_config)

        assert db_config.get("old_rev_expiry_seconds") == 10, (
            f"Expected old_rev_expiry_seconds to be 10, got {db_config.get('old_rev_expiry_seconds')}"
        )
        delta_sync_config = db_config.get("delta_sync", {})
        assert delta_sync_config.get("enabled") is True, (
            f"Expected delta sync to be enabled, got {delta_sync_config.get('enabled')}"
        )
        assert delta_sync_config.get("rev_max_age_seconds") == 10, (
            f"Expected rev_max_age_seconds to be 10, got {delta_sync_config.get('rev_max_age_seconds')}"
        )

        self.mark_test_step("Reset local database, and load `short_expiry` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step("""
            Create doc in CBL:
                * Add a new document with large text content:
                    * `"name": "CBL"`
                    * `"extra": "a" * 3000` (large content)
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default",
                "doc_1",
                [{"channels": ["group1"], "name": "CBL", "extra": "a" * 3000}],
            )

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/short_expiry`
                * collections: `_default._default`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("Record the bytes transferred.")
        read_pull_bytes_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "short_expiry"
        )

        self.mark_test_step(
            "Get the current document state and revision before update."
        )
        sgw_doc_before_update = await cblpytest.sync_gateways[0].get_document(
            "short_expiry", "doc_1"
        )
        assert sgw_doc_before_update is not None, "Document should exist in SGW"
        assert sgw_doc_before_update.body.get("name") == "CBL", (
            "Expected doc to have `name` as `CBL`"
        )
        old_revision = sgw_doc_before_update.revision
        assert old_revision is not None, "Document should have a revision"

        self.mark_test_step(
            "Verify old revision body is accessible before expiry through public API."
        )
        sg = cblpytest.sync_gateways[0]
        public_session = await sg.create_public_session(
            BasicAuth("user1", "pass", "ascii")
        )
        try:
            old_rev_doc = await sg._send_request(
                "GET",
                "/short_expiry/doc_1",
                params={"rev": old_revision},
                session=public_session,
            )
        finally:
            await public_session.close()

        assert old_rev_doc is not None, (
            "Should be able to fetch old revision before expiry"
        )
        assert old_rev_doc.get("name") == "CBL", (
            "Old revision should have correct content"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Modify content in document "doc_1": `"name": "SGW"` (small change)
        """)
        await cblpytest.sync_gateways[0].upsert_documents(
            "short_expiry",
            [
                DocumentUpdateEntry(
                    "doc_1",
                    sgw_doc_before_update.revid,
                    {"channels": ["group1"], "name": "SGW", "extra": "a" * 3000},
                )
            ],
        )

        self.mark_test_step("Wait for 10 seconds to ensure delta rev expires.")
        await asyncio.sleep(10)

        self.mark_test_step("Verify old revision is not accessible through public API.")
        try:
            public_session = await sg.create_public_session(
                BasicAuth("user1", "pass", "ascii")
            )
            try:
                expired_rev_doc = await sg._send_request(
                    "GET",
                    "/short_expiry/doc_1",
                    params={"rev": old_revision},
                    session=public_session,
                )
                assert "stub" in expired_rev_doc or "_attachments" in expired_rev_doc, (
                    f"Expected old revision to be a stub, but got full document: {expired_rev_doc}"
                )
            finally:
                await public_session.close()
        except Exception as e:
            assert "404" in str(e) or "not found" in str(e).lower(), (
                f"Expected 404 error, got: {e}"
            )

        self.mark_test_step("""
            Pull replicate back to CBL:
                * endpoint: `/short_expiry`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("Record the bytes transferred post expiry.")
        read_pull_bytes_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "short_expiry"
        )
        delta_bytes_read = read_pull_bytes_after - read_pull_bytes_before

        self.mark_test_step("""
            Verify:
                * The transferred bytes are approximately equal to the full document size (>3000 bytes)
                * This indicates SGW correctly sent the full document after revision expiry
                * The small change forced a full document transfer due to expired revision
        """)
        cbl_doc = await db.get_document(DocumentEntry("_default._default", "doc_1"))
        assert cbl_doc is not None, "Document should exist in CBL"
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        assert delta_bytes_read >= 0.8 * updated_doc_size, (
            f"Expected a full doc transfer since old revision expired, but only {delta_bytes_read} bytes read (doc size: {updated_doc_size})"
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
            "Reset SG and load `travel` dataset with delta sync enabled."
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

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("Verify docs are replicated correctly.")
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("""
            Update doc in CBL:
                * Add a new doc with body: `"name": "CBL"`.
        """)
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Start the same replicator again.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Update the same hotel document with identical content
        """)
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", None, {"name": "CBL"})],
            "travel",
            "hotels",
        )

        self.mark_test_step("""
            Update docs in SGW again:
                * Update the same hotel document with same content as previous revision
        """)
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", sgw_doc.revid, {"name": "CBL"})],
            "travel",
            "hotels",
        )

        self.mark_test_step("Start a continuous replicator.")
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

        self.mark_test_step("""
            Update docs in CBL:
                * Update the same hotel document with identical content again
        """)
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("Wait until the replicator idles.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify doc body matches between SGW and CBL.")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert sgw_doc is not None and cbl_doc is not None, (
            "Documents should exist in SGW and CBL"
        )
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
            1. Have delta sync enabled.
            2. Create docs in CBL.
            3. Do push replication to SGW.
            4. Get delta stats.
            5. Update docs in SGW, update has to be larger than doc in bytes.
            6. Replicate docs to CBL.
            7. Get delta stats.
            8. Verify full doc is replicated. Delta size at step 7 should be same as step 4.
        """
        self.mark_test_step(
            "Reset SG and load `travel` dataset with delta sync enabled."
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

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("""
            Update doc in CBL:
                * Modify a hotel document with small changes
        """)
        async with db.batch_updater() as b:
            b.upsert_document("travel.hotels", "hotel_1", [{"name": "CBL"}])

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("Get delta stats.")
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Update the same hotel document with much larger content (>2x original size)
        """)
        doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_1", "travel", "hotels"
        )
        assert doc is not None, "Document should exist in SGW"
        current_rev = doc.revid
        large_doc_body = "X" * 2_000_000
        await cblpytest.sync_gateways[0].update_documents(
            "travel",
            [DocumentUpdateEntry("hotel_1", current_rev, {"name": large_doc_body})],
            "travel",
            "hotels",
        )

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
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

        self.mark_test_step("Get delta stats.")
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify full doc is replicated.")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_1"))
        assert cbl_doc is not None, "Document should exist in CBL"
        assert cbl_doc.body.get("name") == large_doc_body, (
            "Expected doc to have same content"
        )

        self.mark_test_step("Verify delta size at step 7 is >= step 4.")
        large_doc_size = len(large_doc_body.encode("utf-8"))
        delta_bytes_read = bytes_read_after - bytes_read_before

        assert delta_bytes_read > 0.8 * large_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_read} bytes read (doc size: {large_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")
