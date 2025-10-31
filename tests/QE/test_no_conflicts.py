import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import DocumentEntry
from cbltest.api.listener import Listener
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.syncgateway import DocumentUpdateEntry


async def update_cbl(cbl_db, doc_id, data):
    async with cbl_db.batch_updater() as b:
        b.upsert_document("_default.posts", doc_id, data)


@pytest.mark.cbl
@pytest.mark.min_test_servers(3)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestNoConflicts(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sg_cbl_updates_concurrently_with_push_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database and load `posts` dataset")
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: pull
                * continuous: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {len(lite_all_docs['_default.posts'])}"
        )

        self.mark_test_step("Create docs in SG")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [DocumentUpdateEntry("post_1000", None, {"channels": ["group1"]})],
            collection="posts",
        )

        self.mark_test_step("""
            Update docs concurrently:
                * In SGW: `"title"`: `"SGW Update"`
                * In CBL: `"title"`: `"CBL Update"`
        """)
        await asyncio.gather(
            cblpytest.sync_gateways[0].update_documents(
                "posts",
                [
                    DocumentUpdateEntry(
                        "post_1000",
                        None,
                        {"channels": ["group1"], "title": "SGW Update"},
                    )
                ],
                collection="posts",
            ),
            update_cbl(
                db, "post_1000", [{"channels": ["group1"], "title": "CBL Update"}]
            ),
        )

        self.mark_test_step("""
            Start another replicator:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: push
                * continuous: true
                * credentials: user1/pass""")
        replicator2 = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator2.start()

        self.mark_test_step("Wait until the replicators are idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("Verify updated doc count in CBL")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 6, (
            f"Incorrect number of documents replicated (expected 6; got {len(lite_all_docs['_default.posts'])}"
        )

        self.mark_test_step("Verify updated doc body in SGW and CBL.")
        cbl_doc = await db.get_document(DocumentEntry("_default.posts", "post_1000"))
        assert cbl_doc is not None, "Document not found"
        assert cbl_doc.id == "post_1000", (
            f"Incorrect document ID (expected post_1000; got {cbl_doc.id})"
        )
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert sg_doc is not None, "Document not found"
        assert sg_doc.id == "post_1000", (
            f"Incorrect document ID (expected post_1000; got {sg_doc.id})"
        )
        assert sg_doc.body.get("title") == cbl_doc.body.get("title"), (
            f"Mismatch in document title, SG: {sg_doc.body.get('title')}, CBL: {cbl_doc.body.get('title')}"
        )

        self.mark_test_step("""
            Update docs through CBL:
                * `"title"`: `"CBL Update 2"`
        """)
        await update_cbl(
            db, "post_1000", [{"channels": ["group1"], "title": "CBL Update 2"}]
        )

        self.mark_test_step("Wait until the replicators are idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("Verify docs got replicated to SGW with CBL updates.")
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert sg_doc is not None, "Document not found"
        assert sg_doc.body.get("title") == "CBL Update 2", (
            f"Wrong title in SG doc (expected 'CBL Update 2'; got {sg_doc.body.get('title')}"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_cbls_updates_concurrently_with_push(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step(
            "Reset local database and load `posts` dataset on all 3 CBLs"
        )
        db1 = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]
        db2 = (
            await cblpytest.test_servers[1].create_and_reset_db(
                ["db2"], dataset="posts"
            )
        )[0]
        db3 = (
            await cblpytest.test_servers[2].create_and_reset_db(
                ["db3"], dataset="posts"
            )
        )[0]

        self.mark_test_step("""
            Create docs in CBL DB1, DB2, DB3:
                * In DB1:
                    * Add doc in "group1"
                * In DB2:
                    * Add doc in "group1"
                * In DB3:
                    * Add doc in "group2"
        """)
        await asyncio.gather(
            update_cbl(db1, "post_1000", [{"channels": ["group1"]}]),
            update_cbl(db2, "post_1000", [{"channels": ["group1"]}]),
            update_cbl(db3, "post_1000", [{"channels": ["group2"]}]),
        )

        listener2 = Listener(db2, ["_default.posts"], 59840)
        await listener2.start()
        listener3 = Listener(db3, ["_default.posts"], 59841)
        await listener3.start()
        self.mark_test_step("""
            Start a replicator between DB1 and DB2:
                * endpoint: DB2 URL
                * collections: `_default.posts`
                * type: push-and-pull
                * continuous: true
        """)
        repl1 = Replicator(
            db1,
            cblpytest.test_servers[1].replication_url("db2", 8080),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        )
        await repl1.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Start a replicator between DB1 and DB3:
                * endpoint: DB3 URL
                * collections: `_default.posts`
                * type: push-and-pull
                * continuous: false
        """)
        repl2 = Replicator(
            db1,
            cblpytest.test_servers[2].replication_url("db3", 59841),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        )
        await repl2.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Update docs concurrently:
                * In DB1: `"CBL1 Update 1"`
                * In DB2: `"CBL2 Update 1"`
                * In DB3: `"CBL3 Update 1"`
        """)
        await asyncio.gather(
            update_cbl(
                db1, "post_1000", [{"channels": ["group1"], "title": "CBL1 Update 1"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": ["group1"], "title": "CBL2 Update 1"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": ["group2"], "title": "CBL3 Update 1"}]
            ),
        )

        self.mark_test_step("Wait until the replicators are idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Start a replicator between DB3 and SGW:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: push-and-pull
                * continuous: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db3,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verify replication was successful and document content in SGW."
        )
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert sg_doc is not None, "Document should exist in SGW"
        cbl1_doc = await db1.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl2_doc = await db2.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl3_doc = await db3.get_document(DocumentEntry("_default.posts", "post_1000"))
        assert (
            sg_doc.body.get("title")
            == cbl1_doc.body.get("title")
            == cbl2_doc.body.get("title")
            == cbl3_doc.body.get("title")
        ), (
            f"Title mismatch in replicated docs (SGW: {sg_doc.body.get('title')}; \
                    CBL1: {cbl1_doc.body.get('title')}, CBL2: {cbl2_doc.body.get('title')}, \
                    CBL3: {cbl3_doc.body.get('title')}"
        )

        await cblpytest.test_servers[0].cleanup()
        await cblpytest.test_servers[1].cleanup()
        await cblpytest.test_servers[2].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_cbls_updates_concurrently_with_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step(
            "Reset local database and load `posts` dataset on all 3 CBLs"
        )
        db1 = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="posts"
            )
        )[0]
        db2 = (
            await cblpytest.test_servers[1].create_and_reset_db(
                ["db2"], dataset="posts"
            )
        )[0]
        db3 = (
            await cblpytest.test_servers[2].create_and_reset_db(
                ["db3"], dataset="posts"
            )
        )[0]

        self.mark_test_step("Create a new doc in SG: `post_1000`.")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [DocumentUpdateEntry("post_1000", None, {"channels": ["group1"]})],
            collection="posts",
        )

        self.mark_test_step("""
            Start replicators for all 3 CBLs:
                * For each CBL (DB1, DB2, DB3):
                    * endpoint: `/posts`
                    * collections: `_default.posts`
                    * type: pull
                    * continuous: false
                    * credentials: user1/pass
        """)
        repl1 = Replicator(
            db1,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl1.start()
        repl2 = Replicator(
            db2,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl2.start()
        repl3 = Replicator(
            db3,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl3.start()

        self.mark_test_step("Wait until the replicators are idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl3.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify docs replicated to all 3 CBLs")
        cbl1_doc = await db1.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl2_doc = await db2.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl3_doc = await db3.get_document(DocumentEntry("_default.posts", "post_1000"))
        assert cbl1_doc.id == cbl2_doc.id == cbl3_doc.id, (
            f"Wrong document ID in CBL docs (expected 'post_1000'; \
                got CBL1: {cbl1_doc.id}, CBL2: {cbl2_doc.id}, CBL3: {cbl3_doc.id}"
        )

        self.mark_test_step("""
            Update docs concurrently:
                * In SGW: `"title": "SGW Update 1"`
                * In DB1: `"title": "CBL1 Update 1"`
                * In DB2: `"title": "CBL2 Update 1"`
                * In DB3: `"title": "CBL3 Update 1"`
        """)
        await asyncio.gather(
            cblpytest.sync_gateways[0].update_documents(
                "posts",
                [
                    DocumentUpdateEntry(
                        "post_1000",
                        None,
                        {"channels": ["group1"], "title": "SGW Update 1"},
                    )
                ],
                collection="posts",
            ),
            update_cbl(
                db1, "post_1000", [{"channels": ["group1"], "title": "CBL1 Update 1"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": ["group1"], "title": "CBL2 Update 1"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": ["group1"], "title": "CBL3 Update 1"}]
            ),
        )

        self.mark_test_step("Wait until the replicators are idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl3.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify docs replicated to all 3 CBLs:
                * Check doc bodies are consistent across all 3 CBLs and SGW
        """)
        cbl1_doc = await db1.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl2_doc = await db2.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl3_doc = await db3.get_document(DocumentEntry("_default.posts", "post_1000"))
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert sg_doc is not None, "Document should exist in SGW"
        assert (
            cbl1_doc.body.get("title")
            == cbl2_doc.body.get("title")
            == cbl3_doc.body.get("title")
            == sg_doc.body.get("title")
        ), (
            f"Document title mismatch (SGW: {sg_doc.body.get('title')}; \
                    CBL1: {cbl1_doc.body.get('title')}, CBL2: {cbl2_doc.body.get('title')}, \
                    CBL3: {cbl3_doc.body.get('title')}"
        )

        self.mark_test_step("""
            Update docs concurrently through all 3 CBLs:
                * In DB1: `"title": "CBL1 Update 2"`
                * In DB2: `"title": "CBL2 Update 2"`
                * In DB3: `"title": "CBL3 Update 2"`
        """)
        await asyncio.gather(
            update_cbl(
                db1, "post_1000", [{"channels": ["group1"], "title": "CBL1 Update 2"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": ["group1"], "title": "CBL2 Update 2"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": ["group1"], "title": "CBL3 Update 2"}]
            ),
        )

        self.mark_test_step("Wait until the replicators are idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl3.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("""
            Verify docs updated through all 3 CBLs:
                * Check doc bodies are consistent across all 3 CBLs and SGW
        """)
        cbl1_doc = await db1.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl2_doc = await db2.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl3_doc = await db3.get_document(DocumentEntry("_default.posts", "post_1000"))
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert sg_doc is not None, "Document should exist in SGW"
        assert (
            cbl1_doc.body.get("title")
            == cbl2_doc.body.get("title")
            == cbl3_doc.body.get("title")
            == sg_doc.body.get("title")
        ), (
            f"Document title mismatch (SGW: {sg_doc.body.get('title')}; \
                    CBL1: {cbl1_doc.body.get('title')}, CBL2: {cbl2_doc.body.get('title')}, \
                    CBL3: {cbl3_doc.body.get('title')}"
        )

        await cblpytest.test_servers[0].cleanup()
        await cblpytest.test_servers[1].cleanup()
        await cblpytest.test_servers[2].cleanup()
