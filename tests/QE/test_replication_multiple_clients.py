from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from packaging.version import Version


@pytest.mark.cbl
@pytest.mark.min_test_servers(2)
@pytest.mark.min_sync_gateways(1)
class TestReplicationMultipleClients(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_with_multiple_client_dbs_and_single_sync_gateway_db(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        sg = cblpytest.sync_gateways[0]
        sg_db = "names"

        self.mark_test_step("Create client database on test server 1")
        db1 = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("Create client database on test server 2")
        db2 = (await cblpytest.test_servers[1].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("""
            Setup continuous push-pull replication from db1 (test server 1) to Sync Gateway:
                * endpoint: `/names`
                * collections: `_default._default`
                * type: push-and-pull
                * continuous: true
                * credentials: user1/pass
        """)
        replicator1 = Replicator(
            db1,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg.tls_cert(),
        )
        await replicator1.start()

        self.mark_test_step("""
            Setup continuous push-pull replication from db2 (test server 2) to Sync Gateway:
                * endpoint: `/names`
                * collections: `_default._default`
                * type: push-and-pull
                * continuous: true
                * credentials: user1/pass
        """)
        replicator2 = Replicator(
            db2,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg.tls_cert(),
        )
        await replicator2.start()

        self.mark_test_step("Wait for both replicators to reach idle state")
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error waiting for replicator1: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator2: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step(
            "Add 100 documents to db1 (test server 1) with prefix 'ls_db1'"
        )
        async with db1.batch_updater() as updater:
            for i in range(100):
                doc_id = f"ls_db1_{i}"
                updater.upsert_document(
                    "_default._default",
                    doc_id,
                    [
                        {
                            "type": "client_doc",
                            "source": "db1",
                            "index": i,
                            "channels": ["*"],
                        }
                    ],
                )

        self.mark_test_step(
            "Add 100 documents to db2 (test server 2) with prefix 'ls_db2'"
        )
        async with db2.batch_updater() as updater:
            for i in range(100):
                doc_id = f"ls_db2_{i}"
                updater.upsert_document(
                    "_default._default",
                    doc_id,
                    [
                        {
                            "type": "client_doc",
                            "source": "db2",
                            "index": i,
                            "channels": ["*"],
                        }
                    ],
                )

        self.mark_test_step("Wait for replicators to sync all documents")
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error during replication from db1: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error during replication from db2: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("""
            Verify all documents are present in Sync Gateway:
                * Should have: 100 docs from db1 + 100 docs from db2 = 200 total
        """)
        sg_all_docs = await sg.get_all_documents(sg_db)
        sg_doc_ids = {row.id for row in sg_all_docs.rows}
        for i in range(100):
            assert f"ls_db1_{i}" in sg_doc_ids, (
                f"SG missing document from db1: ls_db1_{i}"
            )
        for i in range(100):
            assert f"ls_db2_{i}" in sg_doc_ids, (
                f"SG missing document from db2: ls_db2_{i}"
            )
        assert len(sg_doc_ids) == 200, (
            f"Sync Gateway should have 200 documents, got {len(sg_doc_ids)}"
        )

        self.mark_test_step("Verify all documents have correct revision format")
        for row in sg_all_docs.rows:
            assert len(row.revision) > 0, f"Document {row.id} has no revision"
            assert "-" in row.revision, (
                f"Invalid revision format for {row.id}: {row.revision}"
            )

        sgw_version_obj = await sg.get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")
        if supports_version_vectors:
            self.mark_test_step(
                "Verify all documents have correct version vector format (SGW 4.0+)"
            )
            for row in sg_all_docs.rows:
                assert row.cv is not None and len(row.cv) > 0, (
                    f"Document {row.id} has no version vector"
                )
                assert "@" in row.cv, (
                    f"Invalid version vector format for {row.id}: {row.cv}"
                )

        self.mark_test_step("Verify documents in changes feed for Sync Gateway")
        sg_changes = await sg.get_changes(sg_db)
        sg_changes_ids = {row.id for row in sg_changes.results}
        assert len(sg_changes_ids) == 200, (
            f"SG changes feed should have 200 documents, got {len(sg_changes_ids)}"
        )

        await sg.delete_database(sg_db)
        await cblpytest.test_servers[0].cleanup()
        await cblpytest.test_servers[1].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_with_10_attachments(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        sg = cblpytest.sync_gateways[0]
        sg_db = "names"

        self.mark_test_step("Create client database on test server 1")
        db1 = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("Create client database on test server 2")
        db2 = (await cblpytest.test_servers[1].create_and_reset_db(["db1"]))[0]

        self.mark_test_step("""
            Start continuous push replication from db1 (test server 1) to Sync Gateway:
                * endpoint: `/names`
                * collections: `_default._default`
                * type: push
                * continuous: true
                * credentials: user1/pass
        """)
        replicator1 = Replicator(
            db1,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg.tls_cert(),
        )
        await replicator1.start()

        self.mark_test_step("""
            Start continuous push replication from db2 (test server 2) to Sync Gateway:
                * endpoint: `/names`
                * collections: `_default._default`
                * type: push
                * continuous: true
                * credentials: user1/pass
        """)
        replicator2 = Replicator(
            db2,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg.tls_cert(),
        )
        await replicator2.start()

        self.mark_test_step("Wait for both replicators to reach idle state")
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error waiting for replicator1: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error waiting for replicator2: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("""
            Create 5 documents with multiple 2MB attachments in db1 (test server 1):
                * Each document has 20 attachments
                * Use small blobs (s1-s10)
        """)
        db1_doc_ids = []
        async with db1.batch_updater() as updater:
            for i in range(5):
                doc_id = f"db1_attachment_{i}"
                db1_doc_ids.append(doc_id)
                blobs = {f"attachment_{j}": f"s{(j % 10) + 1}.jpg" for j in range(20)}
                updater.upsert_document(
                    "_default._default",
                    doc_id,
                    new_properties=[
                        {"type": "attachment_test_doc"},
                        {"source": "db1"},
                        {"index": i},
                        {"channels": ["ABC"]},
                        {"attachment_count": 20},
                    ],
                    new_blobs=blobs,
                )

        self.mark_test_step("""
            Create 5 documents with multiple 2MB attachments in db2 (test server 2):
                * Each document has 20 attachments
                * Use large blobs (l1-l10)
        """)
        db2_doc_ids = []
        async with db2.batch_updater() as updater:
            for i in range(5):
                doc_id = f"db2_attachment_{i}"
                db2_doc_ids.append(doc_id)
                blobs = {f"attachment_{j}": f"l{(j % 10) + 1}.jpg" for j in range(20)}
                updater.upsert_document(
                    "_default._default",
                    doc_id,
                    new_properties=[
                        {"type": "attachment_test_doc"},
                        {"source": "db2"},
                        {"index": i},
                        {"channels": ["ABC"]},
                        {"attachment_count": 20},
                    ],
                    new_blobs=blobs,
                )

        all_doc_ids = db1_doc_ids + db2_doc_ids

        self.mark_test_step("Verify documents were created in db1 (test server 1)")
        for doc_id in db1_doc_ids:
            doc = await db1.get_document(DocumentEntry("_default._default", doc_id))
            assert doc is not None, f"Document {doc_id} not found in db1"
            attachment_count = sum(
                1 for key in doc.body.keys() if key.startswith("attachment_")
            )
            assert attachment_count == 20, (
                f"Document {doc_id} should have 20 attachments, got {attachment_count}"
            )

        self.mark_test_step("Verify documents were created in db2 (test server 2)")
        for doc_id in db2_doc_ids:
            doc = await db2.get_document(DocumentEntry("_default._default", doc_id))
            assert doc is not None, f"Document {doc_id} not found in db2"
            attachment_count = sum(
                1 for key in doc.body.keys() if key.startswith("attachment_")
            )
            assert attachment_count == 20, (
                f"Document {doc_id} should have 20 attachments, got {attachment_count}"
            )

        self.mark_test_step(
            "Wait for replication to push all documents to Sync Gateway"
        )
        status1 = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status1.error is None, (
            f"Error during replication from db1: ({status1.error.domain} / {status1.error.code}) {status1.error.message}"
        )
        status2 = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status2.error is None, (
            f"Error during replication from db2: ({status2.error.domain} / {status2.error.code}) {status2.error.message}"
        )

        self.mark_test_step("""
            Verify all documents are present in Sync Gateway:
                * Should have: 5 docs from db1 + 5 docs from db2 = 10 total
        """)
        sg_all_docs = await sg.get_all_documents(sg_db)
        sg_doc_ids = {row.id for row in sg_all_docs.rows}
        for doc_id in all_doc_ids:
            assert doc_id in sg_doc_ids, f"Document {doc_id} not found in Sync Gateway"
        assert len(sg_doc_ids) == 10, (
            f"Sync Gateway should have 10 documents, got {len(sg_doc_ids)}"
        )

        self.mark_test_step("Verify all documents have correct revision format")
        for row in sg_all_docs.rows:
            assert len(row.revision) > 0, f"Document {row.id} has no revision"
            assert "-" in row.revision, (
                f"Invalid revision format for {row.id}: {row.revision}"
            )

        sgw_version_obj = await sg.get_version()
        sgw_version = Version(sgw_version_obj.version)
        if sgw_version >= Version("4.0.0"):
            self.mark_test_step(
                "Verify all documents have correct version vector format (SGW 4.0+)"
            )
            for row in sg_all_docs.rows:
                assert row.cv is not None and len(row.cv) > 0, (
                    f"Document {row.id} has no version vector"
                )
                assert "@" in row.cv, (
                    f"Invalid version vector format for {row.id}: {row.cv}"
                )

        self.mark_test_step("Verify documents in Sync Gateway changes feed")
        sg_changes = await sg.get_changes(sg_db)
        sg_changes_ids = {row.id for row in sg_changes.results}
        assert len(sg_changes_ids) == 10, (
            f"SG changes feed should have 10 documents, got {len(sg_changes_ids)}"
        )
        assert all(doc_id in sg_changes_ids for doc_id in all_doc_ids), (
            "All documents should be in SG changes feed"
        )

        self.mark_test_step("Verify document content in Sync Gateway")
        for doc_id in all_doc_ids:
            sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            assert sg_doc is not None, f"Document {doc_id} not found in SG"
            assert sg_doc.body.get("type") == "attachment_test_doc", (
                f"Document {doc_id} has incorrect type"
            )
            assert sg_doc.body.get("attachment_count") == 20, (
                f"Document {doc_id} should have attachment_count=20"
            )
            expected_source = "db1" if doc_id.startswith("db1_") else "db2"
            assert sg_doc.body.get("source") == expected_source, (
                f"Document {doc_id} should have source={expected_source}"
            )

        await sg.delete_database(sg_db)
        await cblpytest.test_servers[0].cleanup()
        await cblpytest.test_servers[1].cleanup()
