from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorFilter,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import DocumentUpdateEntry


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationAutoPurge(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_docs_from_channel_with_auto_purge_enabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Update docs on SG:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
                * Update `post_2` with channels = ["group1"]
                * Update `post_3` with channels = ["group2"]
                * Delete `post_4`
        """)
        updates: list[DocumentUpdateEntry] = []
        for doc in lite_all_docs["_default.posts"]:
            if doc.id == "post_1":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": []}))
            elif doc.id == "post_2":
                updates.append(
                    DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group1"]})
                )
            elif doc.id == "post_3":
                updates.append(
                    DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group2"]})
                )
            elif doc.id == "post_4":
                await cblpytest.sync_gateways[0].delete_document(
                    "post_4", doc.rev, "posts", collection="posts"
                )

        await cblpytest.sync_gateways[0].update_documents(
            "posts", updates, collection="posts"
        )

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Check the local documents:
                * `post_1` was purged.
                * `post_2` and `post_3` were updated with the new channels.
                * `post_4` was deleted.
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, (
            "Incorrect number of documents after second replication"
        )
        expected_docs = {"post_2", "post_3", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Check document replications:
                * `post_1` has access-removed flag set.
                * `post_2` and `post_3` have no flags set.
                * `post_4` has deleted flag set.
        """)
        for update in replicator.document_updates:
            if update.document_id == "post_1":
                assert update.flags & ReplicatorDocumentFlags.ACCESS_REMOVED, (
                    "Access removed flag missing from post_1"
                )
            elif update.document_id == "post_2" or update.document_id == "post_3":
                assert update.flags == ReplicatorDocumentFlags.NONE, (
                    f"Stray flags on {update.document_id} ({update.flags})"
                )
            elif update.document_id == "post_4":
                assert update.flags & ReplicatorDocumentFlags.DELETED, (
                    "Deleted flag missing from post_4"
                )
            else:
                assert False, (
                    f"Stray document update present in list ({update.document_id})"
                )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoke_access_with_auto_purge_enabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the docs to which the user has access, are all pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Update user1's access to channels on SG:
                * Remove access to `group2` channel.
        """)
        collection_access_dict = cblpytest.sync_gateways[
            0
        ].create_collection_access_dict({"_default.posts": ["group1"]})
        await cblpytest.sync_gateways[0].add_user(
            "posts", "user1", "pass", collection_access_dict
        )

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Check local documents:
                * `post_4` and `post_5` were purged.
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, (
            "Incorrect number of documents after second replication"
        )
        expected_docs = {"post_1", "post_2", "post_3"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Check document replications:
                * `post_4` and `post_5` have access-removed flag set.
        """)
        assert len(replicator.document_updates) == 2, (
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        )
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", (
                f"Unexpected document update found for {update.document_id}"
            )
            assert update.flags == ReplicatorDocumentFlags.ACCESS_REMOVED, (
                f"Invalid flags on document update (expected ACCESS_REMOVED): {update.flags}"
            )

        self.mark_test_step("""
            Restore user1's access to channels on SG:
                * Add user access to `group2` channel back again.
        """)
        collection_access_dict = cblpytest.sync_gateways[
            0
        ].create_collection_access_dict({"_default.posts": ["group1", "group2"]})
        await cblpytest.sync_gateways[0].add_user(
            "posts", "user1", "pass", collection_access_dict
        )

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.clear_document_updates()
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Check local documents:
                * `post_4` and `post_5` are back.
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of documents after third replication"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Check document replications:
                * `post_4` and `post_5` have events with no flags set.
        """)
        assert len(replicator.document_updates) == 2, (
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        )
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", (
                f"Unexpected document update found for {update.document_id}"
            )
            assert update.flags == ReplicatorDocumentFlags.NONE, (
                f"Invalid flags on document update (expected NONE): {update.flags}"
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_docs_from_channel_with_auto_purge_disabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: false
                * credentials: user1/pass
        """)
        repl1 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=False,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled."
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("Snapshot the database")
        snap = await db.create_snapshot(
            [
                DocumentEntry("_default.posts", "post_1"),
                DocumentEntry("_default.posts", "post_2"),
                DocumentEntry("_default.posts", "post_3"),
                DocumentEntry("_default.posts", "post_4"),
                DocumentEntry("_default.posts", "post_5"),
            ]
        )

        self.mark_test_step("""
            Update docs on SG:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
                * Update `post_2` with channels = ["group1"]
                * Update `post_3` with channels = ["group2"]
        """)
        updates: list[DocumentUpdateEntry] = []
        for doc in lite_all_docs["_default.posts"]:
            if doc.id == "post_1":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": []}))
            elif doc.id == "post_2":
                updates.append(
                    DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group1"]})
                )
            elif doc.id == "post_3":
                updates.append(
                    DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group2"]})
                )
        await cblpytest.sync_gateways[0].update_documents(
            "posts", updates, collection="posts"
        )

        self.mark_test_step(
            "Start a continuous replicator with a config similar to the one above"
        )
        repl2 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            enable_auto_purge=False,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl2.start()

        self.mark_test_step("""
            Check document replications:
               * `post_1` has access-removed flag set.
               * `post_2` and `post_3` have no flags set.
        """)
        await repl2.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_1",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.ACCESS_REMOVED,
                ),
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_2",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_3",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
            }
        )

        self.mark_test_step("""
            Check the local docs
               * there are 5 documents in the database
               * `post_1`, `post_2` and `post_3` are updated with new channels.
               * `post_4` and `post_5` are unchanged
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )

        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.upsert_document(
            "_default.posts",
            "post_2",
            new_properties=[{"channels": ["group1"]}],
            removed_properties=["collection", "content", "owner", "scope", "title"],
        )
        snapshot_updater.upsert_document(
            "_default.posts",
            "post_3",
            new_properties=[{"channels": ["group2"]}],
            removed_properties=["collection", "content", "owner", "scope", "title"],
        )
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, (
            f"Local docs are not as expected: {verify_result.description}"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoke_access_with_auto_purge_disabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: false
                * credentials: user1/pass
        """)
        repl1 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=False,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled."
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Update user1's access to channels on SG:
                * Remove access to `group2` channel.
        """)
        collection_access_dict = cblpytest.sync_gateways[
            0
        ].create_collection_access_dict({"_default.posts": ["group1"]})
        await cblpytest.sync_gateways[0].add_user(
            "posts", "user1", "pass", collection_access_dict
        )

        self.mark_test_step("""
             Start another replicator:
                 * endpoint: `/posts`
                 * collections:
                     * `_default_.posts`
                 * type: pull
                 * continuous: true
                 * autoPurge: false
                 * credentials: user1/pass
         """)
        repl2 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            enable_auto_purge=False,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl2.start()

        self.mark_test_step("""
            Check document replications
                * `post_4` and `post_5` have access-removed flag set
        """)
        await repl2.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_4",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.ACCESS_REMOVED,
                ),
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_5",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.ACCESS_REMOVED,
                ),
            }
        )

        self.mark_test_step("""
            Check local documents:
                * `post_4` and `post_5` were purged.
        """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        n = len(lite_all_docs["_default.posts"])
        assert n == 5, f"Incorrect number of documents after second replication: {n}"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_filter_removed_access_documents(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        repl1 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        rev_ids = {}
        for doc in lite_all_docs["_default.posts"]:
            doc_id = doc.id
            assert doc_id in expected_docs, (
                f"Unexpected document found after initial replication: {doc_id}"
            )
            rev_ids[doc_id] = doc.rev

        self.mark_test_step("Snapshot the database")
        snap = await db.create_snapshot(
            [
                DocumentEntry("_default.posts", "post_1"),
                DocumentEntry("_default.posts", "post_2"),
                DocumentEntry("_default.posts", "post_3"),
                DocumentEntry("_default.posts", "post_4"),
                DocumentEntry("_default.posts", "post_5"),
            ]
        )

        self.mark_test_step("""
            Update docs on SG: 
                * Update post_1 with channels = [] (ACCESS-REMOVED)
                * Update post_2 with channels = [] (ACCESS-REMOVED)
        """)
        channel_access_dict: list[DocumentUpdateEntry] = [
            DocumentUpdateEntry("post_1", rev_ids["post_1"], body={"channels": []}),
            DocumentUpdateEntry("post_2", rev_ids["post_2"], body={"channels": []}),
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "posts", channel_access_dict, "_default", "posts"
        )

        self.mark_test_step("""
             Start another replicator:
                 * endpoint: `/posts`
                 * collections:
                     * `_default_.posts`
                     * pullFilter: name: documentIDs params: {"documentIDs": {"_default.posts": ["post_1"]}} }
                 * type: pull
                 * continuous: true
                 * autoPurge: true
                 * credentials: user1/pass
         """)
        repl2 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[
                ReplicatorCollectionEntry(
                    ["_default.posts"],
                    pull_filter=ReplicatorFilter(
                        "documentIDs", {"documentIDs": {"_default.posts": ["post_1"]}}
                    ),
                )
            ],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl2.start()

        self.mark_test_step("""
            Check document replications
               * `post_1` has access-removed flag set with no error.
               * Note: JS doesn't notify document ended error notifications when documents 
                 are rejected by pull replication filters. The other platforms plan to align 
                 this behavior. So we are not checking the error from the filtered removed 
                 revision here. See CBL-7246 and CBL-7645 for more details. 
        """)
        await repl2.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_1",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.ACCESS_REMOVED,
                )
            }
        )

        self.mark_test_step("""
            Check the local docs
               * there are 4 documents in the database
               * `post_1` was purged.
               * `post_2`, `post_3`, `post_4` and `post_5` still exists.
       """)
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 4, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )

        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.delete_document("_default.posts", "post_1")
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, (
            f"Local docs are not as expected: {verify_result.description}"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("auto_purge_enabled", [True, False])
    async def test_remove_user_from_role(
        self, cblpytest: CBLPyTest, dataset_path: Path, auto_purge_enabled: bool
    ) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step(f"""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: {auto_purge_enabled}
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=auto_purge_enabled,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step(
            "Update user by removing `group2` from the `admin_channels` property."
        )
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "user1",
            "pass",
            {"_default": {"posts": {"admin_channels": ["group1"]}}},
        )

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Check the local documents:
                * `post_1`, `post_2` and `post_3` are still present.
                * `post_4` and `post_5` were purged if `auto_purge_enabled` 
                   is true, still present otherwise.
        """)

        expected_doc_count = 3 if auto_purge_enabled else 5
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == expected_doc_count, (
            "Incorrect number of documents after second replication"
        )
        expected_docs = {"post_1", "post_2", "post_3"}
        if not auto_purge_enabled:
            expected_docs.add("post_4")
            expected_docs.add("post_5")

        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Check document replications:
                * `post_4` and `post_5` have access-remove flag set
        """)
        assert len(replicator.document_updates) == 2, (
            "Incorrect document replication count"
        )
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", (
                f"Unexpected document update found -> '{update.document_id}'"
            )

            assert update.flags & ReplicatorDocumentFlags.ACCESS_REMOVED, (
                f"Access removed flag missing from {update.document_id} ({update.flags})"
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("auto_purge_enabled", [True, False])
    async def test_remove_role_from_channel(
        self, cblpytest: CBLPyTest, dataset_path: Path, auto_purge_enabled: bool
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step(
            "Add a role on Sync Gateway `role1` with access to channel `group3` in `_default.posts`"
        )
        await cblpytest.sync_gateways[0].add_role(
            "posts", "role1", {"_default": {"posts": {"admin_channels": ["group3"]}}}
        )

        self.mark_test_step("Update `user1` to be in `role1`")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "user1",
            "pass",
            {"_default": {"posts": {"admin_channels": ["group1", "group2"]}}},
            ["role1"],
        )

        self.mark_test_step("""
            Add a document `post_6` on Sync Gateway to `posts`
                * title: Post 6
                * content: This is the content of my post 6
                * channels: ["group3"]
                * owner: user2
        """)
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_6",
                    None,
                    {
                        "title": "Post 6",
                        "content": "This is the content of my post 6",
                        "channels": ["group3"],
                        "owner": "user2",
                    },
                )
            ],
            collection="posts",
        )

        self.mark_test_step(f"""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: {auto_purge_enabled}
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=auto_purge_enabled,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 6, (
            f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5", "post_6"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step(
            "Update `role1` by removing `group3` from the `admin_channels` property."
        )
        await cblpytest.sync_gateways[0].add_role(
            "posts", "role1", {"_default": {"posts": {"collection_access": {}}}}
        )

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Check the local documents:
                * `post_1`, `post_2`, `post_3`, `post_4` and `post_5` are still present.
                * `post_6` was purged if `auto_purge_enabled` is true, still present otherwise.
        """)

        expected_doc_count = 5 if auto_purge_enabled else 6
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == expected_doc_count, (
            "Incorrect number of documents after second replication"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        if not auto_purge_enabled:
            expected_docs.add("post_6")

        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, (
                f"Unexpected document found after initial replication: {doc.id}"
            )

        self.mark_test_step("""
            Check document replications:
                * `post_6` has access-remove flag set
        """)
        assert len(replicator.document_updates) == 1, (
            "Incorrect document replication count"
        )

        for update in replicator.document_updates:
            assert update.document_id == "post_6", (
                f"Unexpected document update found -> '{update.document_id}'"
            )

            assert update.flags & ReplicatorDocumentFlags.ACCESS_REMOVED, (
                f"Access removed flag missing from {update.document_id} ({update.flags})"
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_after_restore_access(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        repl = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        rev_ids = {}
        for doc in lite_all_docs["_default.posts"]:
            doc_id = doc.id
            assert doc_id in expected_docs, (
                f"Unexpected document found after initial replication: {doc_id}"
            )
            rev_ids[doc_id] = doc.rev

        self.mark_test_step(""""
            Start another replicator:
                * endpoint: `/posts`
                * collections :
                    * `_default_.posts`
                * type: pull
                * continuous: true
                * credentials: user1/pass
                * enable_document_listener: True
        """)
        repl = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            enable_document_listener=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl.start()

        self.mark_test_step("Snapshot the database for post_1")
        snapshot = await db.create_snapshot([DocumentEntry("_default.posts", "post_1")])

        self.mark_test_step(""""
            Update doc in SGW:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
        """)
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [DocumentUpdateEntry("post_1", rev_ids["post_1"], {"channels": []})],
            collection="posts",
        )

        self.mark_test_step("""
            Wait for a document event regarding `post_1`
                * flags: access-removed
        """)
        await repl.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts",
                    "post_1",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.ACCESS_REMOVED,
                )
            }
        )

        self.mark_test_step("Check that `post_1` no longer exists locally")
        snapshot_updater = SnapshotUpdater(snapshot)
        snapshot_updater.purge_document("_default.posts", "post_1")
        await db.verify_documents(snapshot_updater)

        self.mark_test_step(""""
            Update doc in SGW:
                * Update `post_1` with channels = ["group1"]
        """)
        remote_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1", collection="posts"
        )
        assert remote_doc is not None, "post_1 vanished from SGW"
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_1", remote_doc.revision, {"channels": ["group1"]}
                )
            ],
            collection="posts",
        )

        self.mark_test_step(
            "Wait for a document event regarding `post_1` with no error"
        )
        repl.clear_document_updates()
        await repl.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts", "post_1", ReplicatorType.PULL, None
                )
            }
        )

        self.mark_test_step("Check that `post_1` exists locally")
        local_doc = await db.get_document(DocumentEntry("_default.posts", "post_1"))
        assert local_doc.body["channels"] == ["group1"], (
            "post_1 incorrect locally at end"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_after_remove_access(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        repl = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        rev_ids = {}
        for doc in lite_all_docs["_default.posts"]:
            doc_id = doc.id
            assert doc_id in expected_docs, (
                f"Unexpected document found after initial replication: {doc_id}"
            )
            rev_ids[doc_id] = doc.rev

        self.mark_test_step(""""
            Start another replicator:
                * endpoint: `/posts`
                * collections :
                    * `_default_.posts`
                * type: push
                * continuous: true
                * credentials: user1/pass
                * enable_document_listener: True
        """)
        repl = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            enable_document_listener=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl.start()

        self.mark_test_step(""""
            Update doc in CBL:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "post_1",
                new_properties=[{"channels": []}],
            )

        self.mark_test_step(
            "Wait for a document event regarding `post_1` with no error"
        )
        await repl.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts", "post_1", ReplicatorType.PUSH, None
                )
            }
        )

        self.mark_test_step(""""
            Update doc in CBL:
                * Update `post_1` with channels = ["fake"]
        """)
        repl.clear_document_updates()
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "post_1",
                new_properties=[{"channels": ["fake"]}],
            )

        self.mark_test_step(
            "Wait for a document event regarding `post_1` with no error"
        )
        await repl.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "_default.posts", "post_1", ReplicatorType.PUSH, None
                )
            }
        )

        self.mark_test_step(
            "Check that `post_1` on Sync Gateway has channels = ['fake']"
        )
        remote_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1", collection="posts"
        )

        assert remote_doc is not None, "post_1 not found on Sync Gateway"
        assert remote_doc.body["channels"] == ["fake"], (
            f"Unexpected channels value found on remote document -> '{remote_doc.body['channels']}'"
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("remove_type", ["delete", "purge"])
    async def test_auto_purge_after_resurrection(
        self, cblpytest: CBLPyTest, dataset_path: Path, remove_type: str
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        """)
        repl = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=False,
            enable_auto_purge=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify that the all the docs to which the user has access were pulled"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            "Incorrect number of initial documents replicated"
        )
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        rev_ids = {}
        for doc in lite_all_docs["_default.posts"]:
            doc_id = doc.id
            assert doc_id in expected_docs, (
                f"Unexpected document found after initial replication: {doc_id}"
            )
            rev_ids[doc_id] = doc.rev

        self.mark_test_step(
            f"Perform a {remove_type} operation to remove post_1 on SGW"
        )
        if remove_type == "delete":
            await cblpytest.sync_gateways[0].delete_document(
                "post_1", rev_ids["post_1"], "posts", collection="posts"
            )
        else:
            await cblpytest.sync_gateways[0].purge_document(
                "post_1", "posts", collection="posts"
            )

        self.mark_test_step("Recreate post_1 on SGW with channels [group1]")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [
                DocumentUpdateEntry(
                    "post_1",
                    revid=None,
                    body={"title": "Post 1", "channels": ["group1"]},
                )
            ],
            collection="posts",
        )

        self.mark_test_step("Remove user1 from group1")
        await cblpytest.sync_gateways[0].add_user(
            "posts",
            "user1",
            "pass",
            collection_access={"_default": {"posts": {"admin_channels": ["group2"]}}},
        )

        self.mark_test_step("Snapshot the local db for post_1")
        snapshot = await db.create_snapshot([DocumentEntry("_default.posts", "post_1")])

        self.mark_test_step("Start a replicator identical to the previous")
        await repl.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that `post_1` no longer exists")
        snapshot_updater = SnapshotUpdater(snapshot)
        snapshot_updater.purge_document("_default.posts", "post_1")
        await db.verify_documents(snapshot_updater)
