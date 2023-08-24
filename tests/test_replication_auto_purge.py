from pathlib import Path
from typing import List
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorBasicAuthenticator, ReplicatorType, ReplicatorActivityLevel, ReplicatorDocumentFlags
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.cbltestclass import CBLTestClass
import pytest

class TestReplicationFilter(CBLTestClass):
    @pytest.mark.asyncio
    async def test_remove_docs_from_channel_with_auto_purge_enabled(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `posts` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        # 2. Reset local database, and load `posts` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : 
                * `_default_.posts`
            * endpoint: `/posts`
            * type: pull
            * continuous: false
            * autoPurge: true
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("posts"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["_default.posts"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start() 

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that the docs that the user has access to are all pulled.
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of initial documents replicated"
        expected_docs = { "post_1", "post_2", "post_3", "post_4", "post_5" }
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        '''
        6. Update docs on SG:
            * Update `post_1` with channels = [] (ACCESS-REMOVED)
            * Update `post_2` with channels = ["group1"]
            * Update `post_3` with channels = ["group2"]
            * Delete `post_4`
        '''
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

        # 7. Start the replicator with the same config as the step 3.
        replicator.enable_document_listener = True
        await replicator.start()

        # 8. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        '''
        9. Check local documents:
            * `post_1` was purged.
            * `post_2` and `post_3` were updated with the new channels.
            * `post_4` was deleted.
        '''
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, "Incorrect number of documents after second replication"
        expected_docs = { "post_2", "post_3", "post_5" }
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        '''
        10. Check document replications:
            * `post_1` has access-removed flag set.
            * `post_2` and `post_3` have no flags set.
            * `post_4` has deleted flag set.
        '''
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

    @pytest.mark.asyncio
    async def test_revoke_access_with_auto_purge_enabled(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `posts` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "posts")

        # 2. Reset local database, and load `posts` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("posts", ["db1"])
        db = dbs[0]


        '''
        3. Start a replicator: 
            * collections : 
            * `_default_.posts`
            * endpoint: `/posts`
            * type: pull
            * continuous: false
            * autoPurge: true
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("posts"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["_default.posts"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start() 

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that the docs that the user has access to are all pulled.
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of initial documents replicated"
        expected_docs = { "post_1", "post_2", "post_3", "post_4", "post_5" }
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        '''
        6. Update user access to channels on SG:
            * Remove access to `group2` channel.
        '''
        collection_access_dict = cblpytest.sync_gateways[0].create_collection_access_dict({
            "_default.posts": ["group1"]
        })
        await cblpytest.sync_gateways[0].add_user("posts", "user1", "pass", collection_access_dict)

        # 7. Start the replicator with the same config as the step 3.
        replicator.enable_document_listener = True
        await replicator.start()

        # 8. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        '''
        9. Check local documents:
            * `post_4` and `post_5` were purged.
        '''
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 3, "Incorrect number of documents after second replication"
        expected_docs = { "post_1", "post_2", "post_3" }
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        '''
        10. Check document replications:
            * `post_4` and `post_5` have access-removed flag set.
        '''
        assert len(replicator.document_updates) == 2, \
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", \
                f"Unexpected document update found for {update.document_id}"
            assert update.flags == ReplicatorDocumentFlags.ACCESS_REMOVED, \
                f"Invalid flags on document update (expected ACCESS_REMOVED): {update.flags}"
            
        '''
        11. Update user access to channels on SG:
            * Add user access to `group2` channel back again.
        '''
        collection_access_dict = cblpytest.sync_gateways[0].create_collection_access_dict({
            "_default.posts": ["group1", "group2"]
        })
        await cblpytest.sync_gateways[0].add_user("posts", "user1", "pass", collection_access_dict)

        # 12. Start the replicator with the same config as the step 3.
        replicator.clear_document_updates()
        await replicator.start()

        # 13. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        '''
        14. Check local documents:
            * `post_4` and `post_5` are back.
        '''
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, "Incorrect number of documents after third replication"
        expected_docs = { "post_1", "post_2", "post_3", "post_4", "post_5" }
        for doc in lite_all_docs["_default.posts"]:
            assert doc.id in expected_docs, f"Unexpected document found after initial replication: {doc.id}"

        '''
        15. Check document replications:
            * `post_4` and `post_5` have events with no flags set.
        '''
        assert len(replicator.document_updates) == 2, \
            f"Expected 2 replicator document updates but found {len(replicator.document_updates)}"
        for update in replicator.document_updates:
            assert update.document_id == "post_4" or update.document_id == "post_5", \
                f"Unexpected document update found for {update.document_id}"
            assert update.flags == ReplicatorDocumentFlags.NONE, \
                f"Invalid flags on document update (expected NONE): {update.flags}"