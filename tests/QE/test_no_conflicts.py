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


@pytest.mark.min_test_servers(3)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestNoConflicts(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sg_cbl_updates_concurrently_with_push_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary:
            1. Create docs in SG.
            2. Pull replication to CBL
            3. update docs in SG and CBL.
            4. Push_pull replication to CBL.
            5. Verify docs can resolve conflicts and should be able to replicate docs to CBL
            6. Update docs through in CBL
            7. Verify docs got replicated to sg with CBL updates
            8. Add verification of sync-gateway
        """
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

        self.mark_test_step("Pull replication to CBL")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        print("Starting PULL replicator...")
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {len(lite_all_docs['_default.posts'])}"
        )

        self.mark_test_step("Create docs in SG and replicate to CBL")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [DocumentUpdateEntry("post_1000", None, {"channels": ["group1"]})],
            collection="posts",
        )
        await replicator.start()

        self.mark_test_step("Wait until replication is complete")
        status2 = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status2.error is None, (
            f"Error waiting for replicator: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("Verify updated doc count in CBL")
        lite_all_docs = await db.get_all_documents("_default.posts")
        doc_count = len(lite_all_docs["_default.posts"])
        assert doc_count == 6, (
            f"Incorrect number of documents replicated (expected 6; got {doc_count})"
        )

        self.mark_test_step("Update docs in SGW and CBL")
        await asyncio.gather(
            cblpytest.sync_gateways[0].update_documents(
                "posts",
                [
                    DocumentUpdateEntry(
                        "post_2000", None, {"channels": "group1", "title": "SGW Update"}
                    )
                ],
                collection="posts",
            ),
            update_cbl(
                db, "post_2000", [{"channels": "group1", "title": "CBL Update"}]
            ),
        )

        self.mark_test_step("Start Push Pull replication between SGW and CBL")
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        stat = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert stat.error is None, (
            f"Error waiting for replicator: ({stat.error.domain} / {stat.error.code}) {stat.error.message}"
        )

        self.mark_test_step("Verify updated doc count in CBL")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 7, (
            f"Incorrect number of documents replicated (expected 7; got {len(lite_all_docs['_default.posts'])}"
        )

        self.mark_test_step("Verify updated doc body in SGW and CBL")
        cbl_doc = await db.get_document(DocumentEntry("_default.posts", "post_2000"))
        assert cbl_doc.id == "post_2000", (
            f"Incorrect document ID (expected post_2000; got {cbl_doc.id}"
        )
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_2000", collection="posts"
        )
        assert sg_doc.id == "post_2000", (
            f"Incorrect document ID (expected post_2000; got {sg_doc.id}"
        )
        assert sg_doc.body.get("title") == cbl_doc.body.get("title"), (
            f"Mismatch in document title, SG: {sg_doc.body.get('title')}, CBL: {cbl_doc.body.get('title')}"
        )

        self.mark_test_step("Update docs through CBL")
        await update_cbl(
            db, "post_2000", [{"channels": "group1", "title": "CBL Update 2"}]
        )

        self.mark_test_step("Wait until the replicator is idle")
        stat2 = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert stat2.error is None, (
            f"Error waiting for replicator: ({stat2.error.domain} / {stat2.error.code}) {stat2.error.message}"
        )

        self.mark_test_step("Verify docs got replicated to sg with CBL updates")
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_2000", collection="posts"
        )
        assert sg_doc.body.get("title") == "CBL Update 2", (
            f"Wrong title in SG doc (expected 'CBL Update 2'; got {sg_doc.body.get('title')}"
        )

        await cblpytest.test_servers[0].cleanup()
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_cbls_updates_concurrently_with_push(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary:
            1. Create docs in CBL DB1, DB2, DB3 associated with its own channel.
            2. Replicate docs from CBL DB1 to DB2 with push pull and continous.
            3. Wait until replication is done.
            4. Replicate docs from CBL DB1 to DB3.
            5. Wait until replication is done with push pull and continous.
            6. update docs on CBL DB1, DB2, DB3.
            7. Now update docs concurrently on all 3 CBL DBs.
            8. Wait until replication is done.
            9. Replicate docs from CBL DB3 to sg with push pull and continous.
            10. Verify all docs replicated to sync-gateway.
        """
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

        self.mark_test_step(
            "Create docs in CBL DB1, DB2, DB3 associated with its own channel"
        )
        await asyncio.gather(
            update_cbl(db1, "post_1000", [{"channels": "group1"}]),
            update_cbl(db2, "post_1000", [{"channels": "group1"}]),
            update_cbl(db3, "post_1000", [{"channels": "group2"}]),
        )

        listener2 = Listener(db2, ["_default.posts"], 59840)
        await listener2.start()
        listener3 = Listener(db3, ["_default.posts"], 59841)
        await listener3.start()
        self.mark_test_step(
            "Replicate docs from CBL DB1 to DB2 with push pull and continous"
        )
        repl1 = Replicator(
            db1,
            cblpytest.test_servers[1].replication_url("db2", 59840),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.test_servers[1].tls_cert(),
        )
        await repl1.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await repl1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Replicate docs from CBL DB1 to DB3")
        repl2 = Replicator(
            db1,
            cblpytest.test_servers[2].replication_url("db3", 59841),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.test_servers[2].tls_cert(),
        )
        await repl2.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await repl2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Update docs on CBL DB1, DB2, DB3")
        await asyncio.gather(
            update_cbl(
                db1, "post_1000", [{"channels": "group1", "title": "CBL1 Update 1"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": "group1", "title": "CBL2 Update 1"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": "group2", "title": "CBL3 Update 1"}]
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

        self.mark_test_step(
            "Replicate docs from CBL DB3 to SGW with push pull and continous"
        )
        replicator = Replicator(
            db3,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
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

        self.mark_test_step("Verify all docs replicated to sync-gateway")
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
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
        self.mark_test_step("...COMPLETED...")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_cbls_updates_concurrently_with_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        @summary:
            1. Create docs in SG.
            2. Do Pull replication to 3 CBLs
            3. update docs in SG and all 3 CBL.
            4. PUSH and PULL replication to CBLs
            5. Verify docs can resolve conflicts and should able to replicate docs to CBL
            6. Update docs through all 3 CBLs
            7. Verify docs can be updated
            8. Add verification of sync-gateway
        """
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

        self.mark_test_step("Create docs in SG")
        await cblpytest.sync_gateways[0].update_documents(
            "posts",
            [DocumentUpdateEntry("post_1000", None, {"channels": "group1"})],
            collection="posts",
        )

        self.mark_test_step("Do Pull replication to 3 CBLs")
        repl1 = Replicator(
            db1,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl1.start()
        repl2 = Replicator(
            db2,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl2.start()
        repl3 = Replicator(
            db3,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await repl3.start()

        self.mark_test_step("Wait until the replicators stop")
        status = await repl1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await repl3.wait_for(ReplicatorActivityLevel.STOPPED)
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

        self.mark_test_step("Update docs in SGW and all 3 CBLs")
        await asyncio.gather(
            cblpytest.sync_gateways[0].update_documents(
                "posts",
                [
                    DocumentUpdateEntry(
                        "post_1000",
                        None,
                        {"channels": "group1", "title": "SGW Update 1"},
                    )
                ],
                collection="posts",
            ),
            update_cbl(
                db1, "post_1000", [{"channels": "group1", "title": "CBL1 Update 1"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": "group1", "title": "CBL2 Update 1"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": "group1", "title": "CBL3 Update 1"}]
            ),
        )

        self.mark_test_step("Do PUSH and PULL replication to 3 CBLs")
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
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
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

        self.mark_test_step("Update docs through all 3 CBLs")
        await asyncio.gather(
            update_cbl(
                db1, "post_1000", [{"channels": "group1", "title": "CBL1 Update 2"}]
            ),
            update_cbl(
                db2, "post_1000", [{"channels": "group1", "title": "CBL2 Update 2"}]
            ),
            update_cbl(
                db3, "post_1000", [{"channels": "group1", "title": "CBL3 Update 2"}]
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

        self.mark_test_step("Verify docs updated through all 3 CBLs")
        cbl1_doc = await db1.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl2_doc = await db2.get_document(DocumentEntry("_default.posts", "post_1000"))
        cbl3_doc = await db3.get_document(DocumentEntry("_default.posts", "post_1000"))
        sg_doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
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
        self.mark_test_step("...COMPLETED...")
