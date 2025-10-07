import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from cbltest.api.syncgateway import DocumentUpdateEntry


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationFunctional(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_roles_replication(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `posts` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset.")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]

        self.mark_test_step("Create test user 'testuser' with no initial roles.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "testuser",
            password="testpass",
            collection_access={
                "_default": {
                    "posts": {
                        "admin_channels": []  # No direct channel access
                    }
                }
            },
        )

        self.mark_test_step("Create role1 with access to group1 channel.")
        await cblpytest.sync_gateways[0].add_role(
            "posts", "role1", {"_default": {"posts": {"admin_channels": ["group1"]}}}
        )

        self.mark_test_step("Create role2 with access to group2 channel.")
        await cblpytest.sync_gateways[0].add_role(
            "posts", "role2", {"_default": {"posts": {"admin_channels": ["group2"]}}}
        )

        self.mark_test_step("Assign only role1 to testuser initially.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "testuser",
            password="testpass",
            admin_roles=["role1"],
            collection_access={
                "_default": {
                    "posts": {
                        "admin_channels": []  # Access comes from roles only
                    }
                }
            },
        )

        self.mark_test_step("Create initial documents in both channels on SGW.")
        # Documents in group1 channel (should be accessible)
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "initial_group1_doc1",
                    None,
                    {
                        "title": "Initial Group1 Doc 1",
                        "content": "Content for initial group1 document 1",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "initial_group1_doc2",
                    None,
                    {
                        "title": "Initial Group1 Doc 2",
                        "content": "Content for initial group1 document 2",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )
        # Documents in group2 channel (should NOT be accessible initially)
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "initial_group2_doc1",
                    None,
                    {
                        "title": "Initial Group2 Doc 1",
                        "content": "Content for initial group2 document 1",
                        "channels": ["group2"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "initial_group2_doc2",
                    None,
                    {
                        "title": "Initial Group2 Doc 2",
                        "content": "Content for initial group2 document 2",
                        "channels": ["group2"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step("""
            Start initial pull replication:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: pull
                * continuous: false
                * credentials: testuser/testpass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("testuser", "testpass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the initial replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify docs got replicated from only group1 channel:
                * Should have: post_1, post_2, post_3 (from dataset), initial_group1_doc1, initial_group1_doc2
                * Should NOT have: post_4, post_5 (group2 from dataset), initial_group2_doc1, initial_group2_doc2
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        replicated_doc_ids = {doc.id for doc in lite_all_docs["_default.posts"]}
        expected_group1_docs = {
            "post_1",
            "post_2",
            "post_3",
            "initial_group1_doc1",
            "initial_group1_doc2",
        }
        for doc_id in expected_group1_docs:
            assert doc_id in replicated_doc_ids, (
                f"Expected group1 document {doc_id} not found in CBL"
            )
        unexpected_group2_docs = {
            "post_4",
            "post_5",
            "initial_group2_doc1",
            "initial_group2_doc2",
        }
        for doc_id in unexpected_group2_docs:
            assert doc_id not in replicated_doc_ids, (
                f"Unexpected group2 document {doc_id} found in CBL"
            )
        assert len(replicated_doc_ids) == 5, (
            f"Expected exactly 5 documents (group1 only), got {len(replicated_doc_ids)}: {replicated_doc_ids}"
        )

        self.mark_test_step("Add role2 to testuser to grant access to group2 channel.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "testuser",
            password="testpass",
            admin_roles=["role1", "role2"],  # Now has both roles
            collection_access={
                "_default": {
                    "posts": {
                        "admin_channels": []  # Access comes from roles only
                    }
                }
            },
        )

        self.mark_test_step("Add new documents to SGW in both channels.")
        # New documents in group1 channel
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "new_group1_doc1",
                    None,
                    {
                        "title": "New Group1 Doc 1",
                        "content": "Content for new group1 document 1",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "new_group1_doc2",
                    None,
                    {
                        "title": "New Group1 Doc 2",
                        "content": "Content for new group1 document 2",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )
        # New documents in group2 channel
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "new_group2_doc1",
                    None,
                    {
                        "title": "New Group2 Doc 1",
                        "content": "Content for new group2 document 1",
                        "channels": ["group2"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "new_group2_doc2",
                    None,
                    {
                        "title": "New Group2 Doc 2",
                        "content": "Content for new group2 document 2",
                        "channels": ["group2"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step("Start the replicator again.")
        await replicator.start()

        self.mark_test_step("Wait until the second replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify all docs got replicated from both channels:
                * Should now have ALL documents from both group1 and group2.
                * From dataset: post_1, post_2, post_3, post_4, post_5.
                * Initial docs: initial_group1_doc1, initial_group1_doc2, initial_group2_doc1, initial_group2_doc2.
                * New docs: new_group1_doc1, new_group1_doc2, new_group2_doc1, new_group2_doc2.
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        final_replicated_doc_ids = {doc.id for doc in lite_all_docs["_default.posts"]}
        expected_all_docs = {
            "post_1",
            "post_2",
            "post_3",
            "post_4",
            "post_5",
            "initial_group1_doc1",
            "initial_group1_doc2",
            "initial_group2_doc1",
            "initial_group2_doc2",
            "new_group1_doc1",
            "new_group1_doc2",
            "new_group2_doc1",
            "new_group2_doc2",
        }
        for doc_id in expected_all_docs:
            assert doc_id in final_replicated_doc_ids, (
                f"Expected document {doc_id} not found in CBL after role addition"
            )
        assert len(final_replicated_doc_ids) == 13, (
            f"Expected exactly 13 documents (all channels), got {len(final_replicated_doc_ids)}: {final_replicated_doc_ids}"
        )

        self.mark_test_step(
            "Verify specific documents from group2 that were previously inaccessible."
        )
        for doc_id in [
            "post_4",
            "post_5",
            "initial_group2_doc1",
            "initial_group2_doc2",
        ]:
            doc = await db.get_document(DocumentEntry("_default.posts", doc_id))
            assert doc is not None, (
                f"Document {doc_id} should be accessible after adding role2"
            )
            assert "group2" in doc.body.get("channels", []), (
                f"Document {doc_id} should have group2 channel"
            )
        for doc_id in [
            "new_group1_doc1",
            "new_group1_doc2",
            "new_group2_doc1",
            "new_group2_doc2",
        ]:
            doc = await db.get_document(DocumentEntry("_default.posts", doc_id))
            assert doc is not None, f"New document {doc_id} should be accessible"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_CBL_SG_replication_with_rev_messages(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `short_expiry` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "short_expiry")

        self.mark_test_step("Reset local database")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("Create initial document in CBL.")
        async with db.batch_updater() as updater:
            updater.upsert_document(
                "_default._default",
                "doc_1",
                [
                    {
                        "type": "test_doc",
                        "content": "This is the first document that will be purged",
                        "channels": ["*"],
                        "created_in": "CBL",
                    }
                ],
            )

        self.mark_test_step("""
            Start continuous push replication to sync doc_1 to SGW:
                * endpoint: `/short_expiry`
                * collections: `_default._default`
                * type: push
                * continuous: true
                * credentials: user1/pass
        """)
        push_replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("short_expiry"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await push_replicator.start()

        self.mark_test_step("Wait for initial push replication to complete.")
        status = await push_replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for push replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify doc_1 exists in SGW.")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "short_expiry", "doc_1", "_default", "_default"
        )
        assert sgw_doc is not None, "doc_1 should exist in SGW after push replication"
        assert sgw_doc.body["type"] == "test_doc", "doc_1 should have correct content"

        self.mark_test_step("Purge doc_1 from SGW.")
        await cblpytest.sync_gateways[0].purge_document(
            "doc_1", "short_expiry", "_default", "_default"
        )

        self.mark_test_step("Verify doc_1 is purged from SGW")
        all_docs = await cblpytest.sync_gateways[0].get_all_documents("short_expiry")
        sgw_doc_ids = {row.id for row in all_docs.rows}
        assert "doc_1" not in sgw_doc_ids, (
            f"doc_1 should be purged from SGW, but found in: {sgw_doc_ids}"
        )

        self.mark_test_step("""
            Create 2 new documents in CBL to flush doc_1's revision from SGW's rev_cache:
            (rev_cache size = 1, so creating 2 docs will definitely flush doc_1's revision)
        """)
        async with db.batch_updater() as updater:
            updater.upsert_document(
                "_default._default",
                "doc_2",
                [
                    {
                        "type": "flush_doc",
                        "content": "This document will help flush doc_1 from rev cache",
                        "channels": ["*"],
                        "created_in": "CBL",
                    }
                ],
            )
            updater.upsert_document(
                "_default._default",
                "doc_3",
                [
                    {
                        "type": "flush_doc",
                        "content": "This document will also help flush doc_1 from rev cache",
                        "channels": ["*"],
                        "created_in": "CBL",
                    }
                ],
            )

        self.mark_test_step("Verify documents were created in local database.")
        doc2 = await db.get_document(DocumentEntry("_default._default", "doc_2"))
        doc3 = await db.get_document(DocumentEntry("_default._default", "doc_3"))
        assert doc2 is not None, "doc_2 should exist in local database"
        assert doc3 is not None, "doc_3 should exist in local database"

        self.mark_test_step("Wait for new documents to be pushed to SGW.")
        push_replicator.clear_document_updates()  # Clear previous updates to track new ones
        status = await push_replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for push replicator after new docs: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify documents exist in SGW.")
        all_docs_after = await cblpytest.sync_gateways[0].get_all_documents(
            "short_expiry"
        )
        sgw_doc_ids_after = {row.id for row in all_docs_after.rows}
        assert "doc_2" in sgw_doc_ids_after, (
            f"doc_2 should exist in SGW, found: {sgw_doc_ids_after}"
        )
        assert "doc_3" in sgw_doc_ids_after, (
            f"doc_3 should exist in SGW, found: {sgw_doc_ids_after}"
        )

        self.mark_test_step("Reset the database.")
        db_recreated = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("Verify the recreated database is empty.")
        lite_all_docs = await db_recreated.get_all_documents("_default._default")
        assert len(lite_all_docs["_default._default"]) == 0, (
            "Recreated database should be empty"
        )

        self.mark_test_step("""
            Start pull replication from SGW to recreated database:
                * endpoint: `/short_expiry`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        pull_replicator = Replicator(
            db_recreated,
            cblpytest.sync_gateways[0].replication_url("short_expiry"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await pull_replicator.start()

        self.mark_test_step("Wait for pull replication to finish.")
        status = await pull_replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for pull replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify replication completed successfully")
        assert status.progress.completed is True, (
            f"Replication status should be `completed`, but got ={status.progress.completed}"
        )

        self.mark_test_step("""
            Verify all docs from SGW replicated successfully:
            * Should have: doc1 (from dataset), doc_2, doc_3 (created docs).
            * Should NOT have: doc_1 (purged document).
        """)
        lite_all_docs = await db_recreated.get_all_documents("_default._default")
        replicated_doc_ids = {doc.id for doc in lite_all_docs["_default._default"]}
        expected_docs = {"doc1", "doc_2", "doc_3"}
        for doc_id in expected_docs:
            assert doc_id in replicated_doc_ids, (
                f"Expected document {doc_id} not found in CBL"
            )
        assert "doc_1" not in replicated_doc_ids, (
            "Purged document doc_1 should not be replicated"
        )
        assert len(replicated_doc_ids) == 3, (
            f"Expected exactly 3 documents, got {len(replicated_doc_ids)}: {replicated_doc_ids}"
        )

        self.mark_test_step("Verify specific document contents")
        dataset_doc = await db_recreated.get_document(
            DocumentEntry("_default._default", "doc1")
        )
        assert dataset_doc is not None, "Dataset document should be accessible"
        doc2 = await db_recreated.get_document(
            DocumentEntry("_default._default", "doc_2")
        )
        assert doc2 is not None, "doc_2 should be accessible"
        assert doc2.body["type"] == "flush_doc", "doc_2 should have correct content"
        doc3 = await db_recreated.get_document(
            DocumentEntry("_default._default", "doc_3")
        )
        assert doc3 is not None, "doc_3 should be accessible"
        assert doc3.body["type"] == "flush_doc", "doc_3 should have correct content"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_behavior_with_channelRole_modification(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset.")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]

        self.mark_test_step("Create test user 'testuser' with no initial access.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "testuser",
            password="testpass",
            collection_access={"_default": {"posts": {"admin_channels": []}}},
        )

        self.mark_test_step("Create role 'testrole' with access to group1 channel.")
        await cblpytest.sync_gateways[0].add_role(
            "posts", "testrole", {"_default": {"posts": {"admin_channels": ["group1"]}}}
        )

        self.mark_test_step("Assign testrole to testuser.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "testuser",
            password="testpass",
            admin_roles=["testrole"],
            collection_access={"_default": {"posts": {"admin_channels": []}}},
        )

        self.mark_test_step("Create initial documents in group1 channel on SGW")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "initial_doc1",
                    None,
                    {
                        "title": "Initial Document 1",
                        "content": "Content for initial document 1",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "initial_doc2",
                    None,
                    {
                        "title": "Initial Document 2",
                        "content": "Content for initial document 2",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step("""
            Start continuous pull replication from SGW:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: pull
                * continuous: true
                * credentials: testuser/testpass
        """)
        pull_replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("testuser", "testpass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await pull_replicator.start()

        self.mark_test_step("Wait for initial pull replication to complete")
        status = await pull_replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for pull replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify initial docs got replicated to CBL:
            * Should have: post_1, post_2, post_3 (from dataset), initial_doc1, initial_doc2 (created).
            * Should NOT have: post_4, post_5 (group2 from dataset).
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        initial_replicated_doc_ids = {doc.id for doc in lite_all_docs["_default.posts"]}
        expected_initial_docs = {
            "post_1",
            "post_2",
            "post_3",
            "initial_doc1",
            "initial_doc2",
        }
        for doc_id in expected_initial_docs:
            assert doc_id in initial_replicated_doc_ids, (
                f"Expected initial document {doc_id} not found in CBL"
            )
        unexpected_docs = {"post_4", "post_5"}
        for doc_id in unexpected_docs:
            assert doc_id not in initial_replicated_doc_ids, (
                f"Unexpected document {doc_id} found in CBL"
            )
        assert len(initial_replicated_doc_ids) == 5, (
            f"Expected exactly 5 documents initially, got {len(initial_replicated_doc_ids)}: {initial_replicated_doc_ids}"
        )

        self.mark_test_step("Change testrole's channel access from group1 to group2.")
        await cblpytest.sync_gateways[0].add_role(
            "posts", "testrole", {"_default": {"posts": {"admin_channels": ["group2"]}}}
        )

        self.mark_test_step(
            "Add new documents to SGW in group1 channel (should NOT be accessible)."
        )
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "new_group1_doc1",
                    None,
                    {
                        "title": "New Group1 Doc 1",
                        "content": "This document should NOT be replicated after role change",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
                DocumentUpdateEntry(
                    "new_group1_doc2",
                    None,
                    {
                        "title": "New Group1 Doc 2",
                        "content": "This document should also NOT be replicated after role change",
                        "channels": ["group1"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step(
            "Add new documents to SGW in group2 channel (should be accessible)."
        )
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "new_group2_doc1",
                    None,
                    {
                        "title": "New Group2 Doc 1",
                        "content": "This document should be replicated after role change",
                        "channels": ["group2"],
                        "owner": "testuser",
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step("Wait for replicator to detect new group2 document.")
        await asyncio.sleep(5)  # Give SG time to process the change

        self.mark_test_step("Wait for replicator to finish pulling.")
        status = await pull_replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator to become idle: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify CBL did NOT get new docs from group1 channel after role change:
            * Should have: post_1, post_2, post_3, post_4, post_5 (from dataset) + new_group2_doc1 (new doc in group2).
            * Should NOT have: initial_doc1, initial_doc2 (group1 no longer accessible), new_group1_doc1, new_group1_doc2 (group1 no longer accessible).
        """)
        lite_all_docs_final = await db.get_all_documents("_default.posts")
        final_replicated_doc_ids = {
            doc.id for doc in lite_all_docs_final["_default.posts"]
        }
        expected_final_docs = {
            "post_1",
            "post_2",
            "post_3",
            "post_4",
            "post_5",
            "new_group2_doc1",
        }

        for doc_id in expected_final_docs:
            assert doc_id in final_replicated_doc_ids, (
                f"Expected final document {doc_id} not found in CBL"
            )
        group1_docs = {
            "initial_doc1",
            "initial_doc2",
            "new_group1_doc1",
            "new_group1_doc2",
        }
        for doc_id in group1_docs:
            assert doc_id not in final_replicated_doc_ids, (
                f"Document {doc_id} from group1 should not be present in CBL after role change"
            )
        assert len(final_replicated_doc_ids) == len(expected_final_docs), (
            f"Expected exactly {len(expected_final_docs)} documents after role change, got {len(final_replicated_doc_ids)}: {final_replicated_doc_ids}"
        )

        self.mark_test_step("Verify specific document contents.")
        new_group2_doc = await db.get_document(
            DocumentEntry("_default.posts", "new_group2_doc1")
        )
        assert new_group2_doc is not None, "new_group2_doc1 should be accessible"
        assert new_group2_doc.body["title"] == "New Group2 Doc 1", (
            "new_group2_doc1 should have correct content"
        )
        post4_doc = await db.get_document(DocumentEntry("_default.posts", "post_4"))
        assert post4_doc is not None, "post_4 should be accessible after role change"
        post5_doc = await db.get_document(DocumentEntry("_default.posts", "post_5"))
        assert post5_doc is not None, "post_5 should be accessible after role change"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_conflict_withConflicts_withChannels(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Create two users with access to different channels.")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "user1",
            password="pass1",
            collection_access={"_default": {"posts": {"admin_channels": ["channel1"]}}},
        )
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "user2",
            password="pass2",
            collection_access={"_default": {"posts": {"admin_channels": ["channel2"]}}},
        )

        self.mark_test_step("Create initial documents in both channels.")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "shared_doc1",
                    None,
                    {
                        "title": "Shared Document 1",
                        "content": "Initial content for shared document 1",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "admin",
                        "version": 1,
                    },
                ),
                DocumentUpdateEntry(
                    "shared_doc2",
                    None,
                    {
                        "title": "Shared Document 2",
                        "content": "Initial content for shared document 2",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "admin",
                        "version": 1,
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step(
            "Create conflicts by having both users update the same documents."
        )
        doc1 = await cblpytest.sync_gateways[0].get_document(
            "posts", "shared_doc1", "_default", "posts"
        )
        doc2 = await cblpytest.sync_gateways[0].get_document(
            "posts", "shared_doc2", "_default", "posts"
        )
        assert doc1 is not None, "Document shared_doc1 not found in SGW"
        assert doc2 is not None, "Document shared_doc2 not found in SGW"
        assert doc1.revid is not None, "Document shared_doc1 has no revision ID"
        assert doc2.revid is not None, "Document shared_doc2 has no revision ID"

        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "shared_doc1",
                    doc1.revid,
                    {
                        "title": "Shared Document 1 - User1's version",
                        "content": "Content modified by user1",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "user1",
                        "version": 2,
                    },
                ),
                DocumentUpdateEntry(
                    "shared_doc2",
                    doc2.revid,
                    {
                        "title": "Shared Document 2 - User1's version",
                        "content": "Content modified by user1",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "user1",
                        "version": 2,
                    },
                ),
            ],
            collection="posts",
        )

        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "shared_doc1",
                    doc1.revid,  # Using same base revision as user1 to create conflict
                    {
                        "title": "Shared Document 1 - User2's version",
                        "content": "Content modified by user2",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "user2",
                        "version": 2,
                    },
                ),
                DocumentUpdateEntry(
                    "shared_doc2",
                    doc2.revid,  # Using same base revision as user1 to create conflict
                    {
                        "title": "Shared Document 2 - User2's version",
                        "content": "Content modified by user2",
                        "channels": ["channel1", "channel2"],
                        "type": "shared",
                        "owner": "user2",
                        "version": 2,
                    },
                ),
            ],
            collection="posts",
        )

        self.mark_test_step("Create a CBL database.")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]

        self.mark_test_step("Start push-pull replication for both users.")
        replicator1 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass1"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator1.start()

        replicator2 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user2", "pass2"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator2.start()

        self.mark_test_step("Wait for initial replications to be idle.")
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error waiting for replicator1: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )

        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator2: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        # Verify that conflicts exist in the database
        doc1_result = await db.get_document(
            DocumentEntry("_default.posts", "shared_doc1")
        )
        doc2_result = await db.get_document(
            DocumentEntry("_default.posts", "shared_doc2")
        )
        assert doc1_result is not None, "Document shared_doc1 not found"
        assert doc2_result is not None, "Document shared_doc2 not found"
        assert "," in doc1_result.revs, "No conflicts found in shared_doc1"
        assert "," in doc2_result.revs, "No conflicts found in shared_doc2"

        self.mark_test_step("Update documents in CBL database with different users.")
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "shared_doc1",
                new_properties=[
                    {"title": "Shared Document 1 - Updated by CBL User1"},
                    {"content": "Content updated in CBL by user1"},
                    {"channels": ["channel1", "channel2"]},
                    {"type": "shared"},
                    {"owner": "user1"},
                    {"version": 3},
                ],
            )
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error waiting for replicator1 after doc1 update: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "shared_doc2",
                new_properties=[
                    {"title": "Shared Document 2 - Updated by CBL User2"},
                    {"content": "Content updated in CBL by user2"},
                    {"channels": ["channel1", "channel2"]},
                    {"type": "shared"},
                    {"owner": "user2"},
                    {"version": 3},
                ],
            )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator2 after doc2 update: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("Verify documents in Sync Gateway have the latest updates.")
        sgw_doc1 = await cblpytest.sync_gateways[0].get_document(
            "posts", "shared_doc1", "_default", "posts"
        )
        sgw_doc2 = await cblpytest.sync_gateways[0].get_document(
            "posts", "shared_doc2", "_default", "posts"
        )
        assert sgw_doc1 is not None, "Document shared_doc1 not found in SGW"
        assert sgw_doc2 is not None, "Document shared_doc2 not found in SGW"
        assert sgw_doc1.body["title"] == "Shared Document 1 - Updated by CBL User1", (
            f"Document 1 in SG does not have user1's CBL update. Found: {sgw_doc1.body['title']}"
        )
        assert sgw_doc1.body["version"] == 3, (
            "Document 1 version should be 3 after conflict resolution"
        )
        assert sgw_doc2.body["title"] == "Shared Document 2 - Updated by CBL User2", (
            f"Document 2 in SG does not have user2's CBL update. Found: {sgw_doc2.body['title']}"
        )
        assert sgw_doc2.body["version"] == 3, (
            "Document 2 version should be 3 after conflict resolution"
        )

        await cblpytest.test_servers[0].cleanup()
