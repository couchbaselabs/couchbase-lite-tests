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
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Record baseline bytes before update")
        read_pull_bytes_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get existing document size for comparison")
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document hotel_400 should exist"
        original_doc_size = len(json.dumps(original_doc.body).encode("utf-8"))

        self.mark_test_step("""
            Update existing document in SGW:
                * Modify hotel_400 with new name to test delta sync
        """)
        updates = [
            DocumentUpdateEntry(
                "hotel_400",
                original_doc.revid,
                {"name": "Updated Hotel"},
            )
        ]
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel", updates, "travel", "hotels"
        )

        self.mark_test_step("Start the same replicator again to pull the update")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_400",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                )
            }
        )
        assert events, "Expected documents to be processed"

        self.mark_test_step("Record bytes transferred after delta sync")
        read_pull_bytes_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify the document was updated correctly in CBL")
        updated_cbl_doc = await db.get_document(
            DocumentEntry("travel.hotels", "hotel_400")
        )
        assert updated_cbl_doc is not None, "Hotel_400 should exist in CBL"
        assert updated_cbl_doc.body.get("name") == "Updated Hotel", (
            f"Expected updated name, got: {updated_cbl_doc.body.get('name')}"
        )

        self.mark_test_step(
            "Verify delta sync worked - bytes transferred should be much smaller than full document"
        )
        delta_bytes = read_pull_bytes_after - read_pull_bytes_before
        assert delta_bytes < original_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes} bytes (original doc size: {original_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_nested_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Get baseline bytes before update")
        read_pull_bytes_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get existing document size for comparison")
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document hotel_400 should exist"
        original_doc_size = len(json.dumps(original_doc.body).encode("utf-8"))

        self.mark_test_step("""
            Update docs in SGW:
                * Update nested fields in existing document
        """)
        updates = [
            DocumentUpdateEntry(
                "hotel_400",
                original_doc.revid,
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
                    "hotel_400",
                    ReplicatorType.PULL,
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

        self.mark_test_step("Verify the document was updated correctly in CBL")
        updated_cbl_doc = await db.get_document(
            DocumentEntry("travel.hotels", "hotel_400")
        )
        assert updated_cbl_doc is not None, "Hotel_400 should exist in CBL"
        assert updated_cbl_doc.body.get("name") == "SGW", (
            f"Expected updated name, got: {updated_cbl_doc.body.get('name')}"
        )
        assert (
            updated_cbl_doc.body.get("nested").get("name") == "I am a nested field"
        ), (
            f"Expected updated nested field, got: {updated_cbl_doc.body.get('nested').get('name')}"
        )

        self.mark_test_step("Record the bytes transferred")
        read_pull_bytes_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step(
            "Verify delta sync bytes transferred is less than doc size."
        )
        delta_bytes = read_pull_bytes_after - read_pull_bytes_before
        assert delta_bytes < original_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes} bytes (original doc size: {original_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_utf8_strings(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("Get baseline bytes before update")
        bytes_pull_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get existing document size for comparison")
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document hotel_400 should exist"
        original_doc_size = len(json.dumps(original_doc.body).encode("utf-8"))

        self.mark_test_step("""
            Update docs in SGW:
                * Add UTF-8 content (Chinese, Japanese characters, emoji-rich descriptions)
        """)
        utf8_body = "東京🚀🌏Привет世界مرحبا"
        updates = [
            DocumentUpdateEntry(
                "hotel_400",
                original_doc.revid,
                {"utf8": utf8_body},
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
                    "hotel_400",
                    ReplicatorType.PULL,
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

        self.mark_test_step("Verify the document was updated correctly in CBL")
        updated_cbl_doc = await db.get_document(
            DocumentEntry("travel.hotels", "hotel_400")
        )
        assert updated_cbl_doc is not None, "Hotel_400 should exist in CBL"
        assert updated_cbl_doc.body.get("utf8") == utf8_body, (
            f"Expected updated UTF-8 content, got: {updated_cbl_doc.body.get('utf8')}"
        )

        self.mark_test_step("Record the bytes transferred again this time.")
        bytes_pull_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step(
            "Verify only delta is updated while replicating UTF-8 content."
        )
        delta_bytes_transferred = bytes_pull_after - bytes_pull_before
        assert delta_bytes_transferred < original_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes_transferred} bytes (original doc size: {original_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_enabled_disabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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
            enable_document_listener=True,
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get existing document size for comparison")
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document hotel_400 should exist"
        original_doc_size = len(json.dumps(original_doc.body).encode("utf-8"))

        self.mark_test_step("""
            Update docs in SGW:
                * Modify only the key `name`: `SGW`.
        """)
        updates = [
            DocumentUpdateEntry("hotel_400", original_doc.revid, {"name": "SGW"})
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
                    "hotel_400",
                    ReplicatorType.PULL,
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

        self.mark_test_step("Verify the document was updated correctly in CBL")
        updated_cbl_doc = await db.get_document(
            DocumentEntry("travel.hotels", "hotel_400")
        )
        assert updated_cbl_doc is not None, "Hotel_400 should exist in CBL"
        assert updated_cbl_doc.body.get("name") == "SGW", (
            f"Expected updated name, got: {updated_cbl_doc.body.get('name')}"
        )

        self.mark_test_step("Record the bytes transferred")
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify delta transferred is less than doc size.")
        delta_bytes_transferred = bytes_read_after - bytes_read_before
        assert delta_bytes_transferred < original_doc_size, (
            f"Expected delta to be less than the full doc size, but got {delta_bytes_transferred} bytes (original doc size: {original_doc_size})"
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
                * collections: `_default.posts`
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
            enable_document_listener=True,
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "posts"
        )

        self.mark_test_step("Get existing document for comparison")
        existing_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1", collection="posts"
        )
        assert existing_doc is not None, "Document should exist in SGW"
        original_doc_size = len(json.dumps(existing_doc.body).encode("utf-8"))

        self.mark_test_step("""
            Update docs in SGW:
                * Modify the `name` field of the doc (small change).
        """)
        await cblpytest.sync_gateways[0].upsert_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_1",
                    existing_doc.revid,
                    {"channels": ["group1"], "name": "SGW"},
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
                    ReplicatorType.PULL,
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

        self.mark_test_step("Verify the document was updated correctly in CBL")
        updated_cbl_doc = await db.get_document(
            DocumentEntry("_default.posts", "post_1")
        )
        assert updated_cbl_doc is not None, "post_1 should exist in CBL"
        assert updated_cbl_doc.body.get("name") == "SGW", (
            f"Expected updated name, got: {updated_cbl_doc.body.get('name')}"
        )

        self.mark_test_step("Record the bytes transferred")
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "posts"
        )

        self.mark_test_step(
            "Verify delta transferred equivalent to doc size (full doc transfer)."
        )
        delta_bytes_transferred = bytes_read_after - bytes_read_before
        assert delta_bytes_transferred >= 0.8 * original_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_transferred} bytes read (doc size: {original_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_within_expiry(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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
        db_config = await cblpytest.sync_gateways[0].get_database_config("short_expiry")

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

        self.mark_test_step("Reset local database.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
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
            enable_document_listener=True,
        )
        await replicator.start()
        events = await replicator.wait_for_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default._default",
                    "doc1",
                    ReplicatorType.PULL,
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
            "short_expiry", "doc1"
        )
        assert sgw_doc_before_update is not None, "Document should exist in SGW"
        assert sgw_doc_before_update.body.get("type") == "test", (
            "Expected doc to have `type` as `test`"
        )
        old_revision = sgw_doc_before_update.revision
        assert old_revision is not None, "Document should have a revision"

        self.mark_test_step(
            "Verify old revision body is accessible before expiry through public API."
        )
        sg = cblpytest.sync_gateways[0]
        old_rev_doc = await sg.get_document_revision_public(
            "short_expiry", "doc1", old_revision, BasicAuth("user1", "pass", "ascii")
        )

        assert old_rev_doc is not None, (
            "Should be able to fetch old revision before expiry"
        )
        assert old_rev_doc.get("type") == "test", (
            "Old revision should have correct content"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Modify content in document "doc1": `"name": "SGW"` (small change)
        """)
        await cblpytest.sync_gateways[0].upsert_documents(
            "short_expiry",
            [
                DocumentUpdateEntry(
                    "doc1",
                    old_revision,
                    {"name": "SGW"},
                )
            ],
        )

        self.mark_test_step("Wait for 10 seconds to ensure delta rev expires.")
        await asyncio.sleep(10)

        self.mark_test_step("Verify old revision is not accessible through public API.")
        try:
            expired_rev_doc = await sg.get_document_revision_public(
                "short_expiry",
                "doc1",
                old_revision,
                BasicAuth("user1", "pass", "ascii"),
            )
            assert "stub" in expired_rev_doc or "_attachments" in expired_rev_doc, (
                f"Expected old revision to be a stub, but got full document: {expired_rev_doc}"
            )
        except Exception as e:
            assert "404" in str(e) or "not found" in str(e).lower(), (
                f"Expected 404 error, got: {e}"
            )

        self.mark_test_step("Start the same replicator again.")
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
        cbl_doc = await db.get_document(DocumentEntry("_default._default", "doc1"))
        assert cbl_doc is not None, "Document should exist in CBL"
        updated_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        assert delta_bytes_read >= 0.8 * updated_doc_size, (
            f"Expected a full doc transfer since old revision expired, but only {delta_bytes_read} bytes read (doc size: {updated_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_with_no_deltas(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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

        self.mark_test_step("Record the bytes transferred")
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify docs are replicated correctly.")
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])})"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Update the same hotel document with identical content (no real change)
        """)
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel",
            [DocumentUpdateEntry("hotel_400", original_doc.revid, {})],
            "travel",
            "hotels",
        )

        self.mark_test_step("Start the same replicator again.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Record the bytes transferred")
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get the original document size.")
        original_doc_size = len(json.dumps(original_doc.body).encode("utf-8"))

        self.mark_test_step("Verify no bytes transferred (except some metadata).")
        delta_bytes_read = bytes_read_after - bytes_read_before
        assert delta_bytes_read <= 0.1 * original_doc_size, (
            f"Expected no bytes transferred, but got {delta_bytes_read} bytes"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_larger_than_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
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
            enable_document_listener=True,
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
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document should exist in SGW"

        self.mark_test_step("Get delta stats.")
        bytes_read_before, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("""
            Update docs in SGW:
                * Update the same hotel document with much larger content (>2x original size)
        """)
        large_doc_body = "X" * 2_000_000
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel",
            [
                DocumentUpdateEntry(
                    "hotel_400", original_doc.revid, {"name": large_doc_body}
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
                    "hotel_400",
                    ReplicatorType.PULL,
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

        self.mark_test_step("Get delta stats.")
        bytes_read_after, _ = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify document is replicated correctly.")
        cbl_doc = await db.get_document(DocumentEntry("travel.hotels", "hotel_400"))
        assert cbl_doc is not None, "Document should exist in CBL"
        assert cbl_doc.body.get("name") == large_doc_body, (
            "Expected doc to have same content"
        )

        self.mark_test_step("Verify full doc is transferred.")
        large_doc_size = len(json.dumps(cbl_doc.body).encode("utf-8"))
        delta_bytes_read = bytes_read_after - bytes_read_before

        assert delta_bytes_read > 0.8 * large_doc_size, (
            f"Expected a full doc transfer, but only {delta_bytes_read} bytes read (doc size: {large_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
