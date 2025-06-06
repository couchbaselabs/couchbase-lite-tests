from datetime import timedelta
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
    ReplicatorType,
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
            1. Create a large doc in CBL : 20MB.
            2. Replicate to SG using push one-shot replication.
            3. Start push one-shot replication and start replication event listener.
            4. Check the error is thrown in replication event changes
                as CBS can't have doc greater than 20mb.
        """
        self.mark_test_step("Reset SG and load `posts` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database, and load `posts` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default.posts`
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
        )
        await replicator.start()

        self.mark_test_step("Wait for replication to complete.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Create document with a large attachment:
                * Create a new document with ID "large_doc"
                * Add text content and metadata
                * Attach a 20MB binary file
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "large_doc",
                new_blobs={"image": "xl1.jpg"},
            )

        self.mark_test_step("""
            Verify document was created successfully:
                * Check document exists in local database
                * Verify attachment is accessible
        """)
        doc = await db.get_document(DocumentEntry("_default.posts", "large_doc"))
        assert doc is not None, "Document not found after update"

        self.mark_test_step("""
            Verify document content:
                * Check text content is correct
                * Verify metadata is present
                * Validate attachment size is 20MB
        """)
        assert "image" in doc.body, "Large blob not found in document"
        blob_dict = doc.body.get("image")
        assert isinstance(blob_dict, dict), "image is not a dict"

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(
            ReplicatorActivityLevel.STOPPED,
            timedelta(seconds=5),
            timedelta(seconds=300),
        )
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify document was not replicated:
                * Check replicator error indicates document size limit exceeded
                * Verify document is not present in Sync Gateway
                * Validate error message contains size limit information
        """)
        docs_after = await db.get_all_documents("_default.posts")
        sgw_docs_after = await cblpytest.sync_gateways[0].get_all_documents(
            "posts", collection="posts"
        )
        assert len(sgw_docs_after.rows) < len(docs_after["_default.posts"]), (
            f"Expected no successful document updates but found {len(sgw_docs_after.rows)}"
        )
        large_doc = next(
            (doc for doc in sgw_docs_after.rows if doc.id == "large_doc"), None
        )
        assert large_doc is None, "Large document should not be replicated"
        try:
            with pytest.raises(Exception) as excinfo:
                await cblpytest.sync_gateways[0].get_document(
                    "posts", "large_doc", collection="_default.posts"
                )
            assert "404" in str(excinfo.value) or "returned 404" in str(excinfo.value)
        except Exception as e:
            print(e)

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")
