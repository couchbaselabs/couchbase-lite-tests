from pathlib import Path
from typing import List

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorBasicAuthenticator, ReplicatorType, \
    WaitForDocumentEventEntry, ReplicatorActivityLevel, ReplicatorDocumentFlags, ReplicatorFilter
from cbltest.api.syncgateway import DocumentUpdateEntry


class TestReplicationAutoPurge(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_docs_from_channel_with_auto_purge_enabled(self, cblpytest: CBLPyTest,
                                                                    dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        ''')
        replicator = Replicator(db,
                                cblpytest.sync_gateways[0].replication_url("posts"),
                                collections=[ReplicatorCollectionEntry(["_default.posts"])],
                                replicator_type=ReplicatorType.PULL,
                                continuous=False,
                                enable_auto_purge=True,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Verify that the all the docs to which the user has access were pulled")
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Update docs on SG:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
                * Update `post_2` with channels = ["group1"]
                * Update `post_3` with channels = ["group2"]
                * Delete `post_4`
        ''')
        updates: List[DocumentUpdateEntry] = []
        for doc in lite_all_docs["_default.posts"]:
            if doc.id == "post_1":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": []}))
            elif doc.id == "post_2":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group1"]}))
            elif doc.id == "post_3":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group2"]}))
            elif doc.id == "post_4":
                await cblpytest.sync_gateways[0].delete_document("post_4", doc.rev, "posts", collection="posts")

        await cblpytest.sync_gateways[0].update_documents("posts", updates, collection="posts")

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step('''
            Check the local documents:
                * `post_1` was purged.
                * `post_2` and `post_3` were updated with the new channels.
                * `post_4` was deleted.
        ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, "Incorrect number of documents after second replication"
        expected_docs = {"post_2", "post_3", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Check document replications:
                * `post_1` has access-removed flag set.
                * `post_2` and `post_3` have no flags set.
                * `post_4` has deleted flag set.
        ''')
        for update in replicator.document_updates:
            if update.document_id == "post_1":
                assert update.flags & ReplicatorDocumentFlags.ACCESS_REMOVED, \
                    "Access removed flag missing from post_1"
            elif update.document_id == "post_2" or update.document_id == "post_3":
                assert update.flags == ReplicatorDocumentFlags.NONE, \
                    f"Stray flags on {update.document_id} ({update.flags})"
            elif update.document_id == "post_4":
                assert update.flags & ReplicatorDocumentFlags.DELETED, \
                    "Deleted flag missing from post_4"
            else:
                assert False, f"Stray document update present in list ({update.document_id})"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoke_access_with_auto_purge_enabled(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        ''')
        replicator = Replicator(db,
                                cblpytest.sync_gateways[0].replication_url("posts"),
                                collections=[ReplicatorCollectionEntry(["_default.posts"])],
                                replicator_type=ReplicatorType.PULL,
                                continuous=False,
                                enable_auto_purge=True,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Verify that the docs to which the user has access, are all pulled")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of initial documents replicated"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Update user1's access to channels on SG:
                * Remove access to `group2` channel.
        ''')
        collection_access_dict = cblpytest.sync_gateways[0].create_collection_access_dict(
            {"_default.posts": ["group1"]})
        await cblpytest.sync_gateways[0].add_user("posts", "user1", "pass", collection_access_dict)

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.enable_document_listener = True
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step('''
            Check local documents:
                * `post_4` and `post_5` were purged.
        ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, "Incorrect number of documents after second replication"
        expected_docs = {"post_1", "post_2", "post_3"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Check document replications:
                * `post_4` and `post_5` have access-removed flag set.
        ''')
        assert len(replicator.document_updates) == 2, \
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", \
                f"Unexpected document update found for {update.document_id}"
            assert update.flags == ReplicatorDocumentFlags.ACCESS_REMOVED, \
                f"Invalid flags on document update (expected ACCESS_REMOVED): {update.flags}"

        self.mark_test_step('''
            Restore user1's access to channels on SG:
                * Add user access to `group2` channel back again.
        ''')
        collection_access_dict = cblpytest.sync_gateways[0].create_collection_access_dict(
            {"_default.posts": ["group1", "group2"]})
        await cblpytest.sync_gateways[0].add_user("posts", "user1", "pass", collection_access_dict)

        self.mark_test_step("Start another replicator with the same config as above")
        replicator.clear_document_updates()
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step('''
            Check local documents:
                * `post_4` and `post_5` are back.
        ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of documents after third replication"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Check document replications:
                * `post_4` and `post_5` have events with no flags set.
        ''')
        assert len(replicator.document_updates) == 2, \
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", \
                f"Unexpected document update found for {update.document_id}"
            assert update.flags == ReplicatorDocumentFlags.NONE, \
                f"Invalid flags on document update (expected NONE): {update.flags}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_docs_from_channel_with_auto_purge_disabled(self, cblpytest: CBLPyTest,
                                                                     dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: false
                * credentials: user1/pass
        ''')
        repl1 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(["_default.posts"])],
                           replicator_type=ReplicatorType.PULL,
                           continuous=False,
                           enable_auto_purge=False,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Verify that the all the docs to which the user has access were pulled.")
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step("Snapshot the database")
        snap = await db.create_snapshot([
            SnapshotDocumentEntry("_default.posts", "post_1"),
            SnapshotDocumentEntry("_default.posts", "post_2"),
            SnapshotDocumentEntry("_default.posts", "post_3"),
            SnapshotDocumentEntry("_default.posts", "post_4"),
            SnapshotDocumentEntry("_default.posts", "post_5")
        ])

        self.mark_test_step('''
            Update docs on SG:
                * Update `post_1` with channels = [] (ACCESS-REMOVED)
                * Update `post_2` with channels = ["group1"]
                * Update `post_3` with channels = ["group2"]
        ''')
        updates: List[DocumentUpdateEntry] = []
        for doc in lite_all_docs["_default.posts"]:
            if doc.id == "post_1":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": []}))
            elif doc.id == "post_2":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group1"]}))
            elif doc.id == "post_3":
                updates.append(DocumentUpdateEntry(doc.id, doc.rev, {"channels": ["group2"]}))
        await cblpytest.sync_gateways[0].update_documents("posts", updates, collection="posts")

        self.mark_test_step("Start a continuous replicator with a config similar to the one above")
        repl2 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(["_default.posts"])],
                           replicator_type=ReplicatorType.PULL,
                           continuous=True,
                           enable_auto_purge=False,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           enable_document_listener=True,
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl2.start()

        self.mark_test_step('''
            Check document replications:
               * `post_1` has access-removed flag set.
               * `post_2` and `post_3` have no flags set.
        ''')
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.posts", "post_1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED),
            WaitForDocumentEventEntry("_default.posts", "post_2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.posts", "post_3", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step('''
            Check the local docs
               * there are 5 documents in the database
               * `post_1`, `post_2` and `post_3` are updated with new channels.
               * `post_4` and `post_5` are unchanged
        ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 5, f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"

        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.upsert_document("_default.posts", "post_2",
                                         new_properties=[{"channels": ["group1"]}],
                                         removed_properties=["collection", "content", "owner", "scope", "title"])
        snapshot_updater.upsert_document("_default.posts", "post_3",
                                         new_properties=[{"channels": ["group2"]}],
                                         removed_properties=["collection", "content", "owner", "scope", "title"])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Local docs are not as expected: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoke_access_with_auto_purge_disabled(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: false
                * credentials: user1/pass
        ''')
        repl1 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(["_default.posts"])],
                           replicator_type=ReplicatorType.PULL,
                           continuous=False,
                           enable_auto_purge=False,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Verify that the all the docs to which the user has access were pulled.")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of initial documents replicated"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        self.mark_test_step('''
            Update user1's access to channels on SG:
                * Remove access to `group2` channel.
        ''')
        collection_access_dict = cblpytest.sync_gateways[0].create_collection_access_dict(
            {"_default.posts": ["group1"]})
        await cblpytest.sync_gateways[0].add_user("posts", "user1", "pass", collection_access_dict)

        self.mark_test_step('''
             Start another replicator:
                 * endpoint: `/posts`
                 * collections:
                     * `_default_.posts`
                 * type: pull
                 * continuous: true
                 * autoPurge: false
                 * credentials: user1/pass
         ''')
        repl2 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(["_default.posts"])],
                           replicator_type=ReplicatorType.PULL,
                           continuous=True,
                           enable_auto_purge=False,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           enable_document_listener=True,
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl2.start()

        self.mark_test_step('''
            Check document replications
                * `post_4` and `post_5` have access-removed flag set
        ''')
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.posts", "post_4", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED),
            WaitForDocumentEventEntry("_default.posts", "post_5", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED)})

        self.mark_test_step('''
            Check local documents:
                * `post_4` and `post_5` were purged.
        ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        n = len(lite_all_docs["_default.posts"])
        assert n == 5, f"Incorrect number of documents after second replication: {n}"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_filter_removed_access_documents(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/posts`
                * collections:
                    * `_default_.posts`
                * type: pull
                * continuous: false
                * autoPurge: true
                * credentials: user1/pass
        ''')
        repl1 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(["_default.posts"])],
                           replicator_type=ReplicatorType.PULL,
                           continuous=False,
                           enable_auto_purge=True,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl1.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Verify that the all the docs to which the user has access were pulled")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of initial documents replicated"
        expected_docs = {"post_1", "post_2", "post_3", "post_4", "post_5"}
        rev_ids = {}
        for doc in lite_all_docs["_default.posts"]:
            doc_id = doc.id
            assert doc_id in expected_docs, f"Unexpected document found after initial replication: {doc_id}"
            rev_ids[doc_id] = doc.rev

        self.mark_test_step("Snapshot the database")
        snap = await db.create_snapshot([
            SnapshotDocumentEntry("_default.posts", "post_1"),
            SnapshotDocumentEntry("_default.posts", "post_2"),
            SnapshotDocumentEntry("_default.posts", "post_3"),
            SnapshotDocumentEntry("_default.posts", "post_4"),
            SnapshotDocumentEntry("_default.posts", "post_5")
        ])

        self.mark_test_step('''
            Update docs on SG: 
                * Update post_1 with channels = [] (ACCESS-REMOVED)
                * Update post_2 with channels = [] (ACCESS-REMOVED)
        ''')
        channel_access_dict: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry("post_1", rev_ids["post_1"], body={"channels": []}),
            DocumentUpdateEntry("post_2", rev_ids["post_2"], body={"channels": []})]
        await cblpytest.sync_gateways[0].update_documents("posts", channel_access_dict, "_default", "posts")

        self.mark_test_step('''
             Start another replicator:
                 * endpoint: `/posts`
                 * collections:
                     * `_default_.posts`
                     * pullFilter: name: documentIDs params: {"documentIDs": {"_default.posts": ["post_1"]}} }
                 * type: pull
                 * continuous: true
                 * autoPurge: true
                 * credentials: user1/pass
         ''')
        repl2 = Replicator(db,
                           cblpytest.sync_gateways[0].replication_url("posts"),
                           collections=[ReplicatorCollectionEntry(
                               ["_default.posts"],
                               pull_filter=ReplicatorFilter(
                                   "documentIDs",
                                   {"documentIDs": {"_default.posts": ["post_1"]}})
                           )],
                           replicator_type=ReplicatorType.PULL,
                           continuous=True,
                           enable_auto_purge=True,
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           enable_document_listener=True,
                           pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await repl2.start()

        self.mark_test_step('''
            Check document replications
               * `post_1` has access-removed flag set with no error.
               * `post_2` has access-removed flag set with WebSocket/403 ("CBL, 10403) error.
        ''')
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.posts", "post_1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED),
            WaitForDocumentEventEntry("_default.posts", "post_2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED, "CBL", 10403)})

        self.mark_test_step('''
            Check the local docs
               * there are 4 documents in the database
               * `post_1` was purged.
               * `post_2`, `post_3`, `post_4` and `post_5` still exists.
       ''')
        lite_all_docs = await db.get_all_documents("_default.posts")
        n_docs = len(lite_all_docs["_default.posts"])
        assert n_docs == 4, f"Incorrect number of initial documents replicated (expected 5; got {n_docs}"

        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.delete_document("_default.posts", "post_1")
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Local docs are not as expected: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()
