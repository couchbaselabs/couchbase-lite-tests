import asyncio
import os
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


@pytest.mark.upg_sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSgwUpgrade(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_and_persistence_after_upgrade(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        This test runs after each SGW upgrade. It performs two key checks:
        1. Ingests a new set of documents to verify that the newly upgraded
           Sync Gateway is functioning correctly.
        2. Verifies that all documents created in *previous* iterations (before
           the upgrade) are still present and correct, ensuring data persistence.
        """
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        current_upgrade_ver = os.environ.get("SGW_VERSION_UNDER_TEST", "0.0.0")
        num_docs_per_iteration = 10
        sg_db = "upg_db"
        bucket = "upg_bucket"
        cbl_db = "upg_sgw_dataset"
        scope = "_default"
        collection = "_default"

        self.mark_test_step(
            f"Running upgrade test version {current_upgrade_ver} "
            f"for SGW DB '{sg_db}' -> CBS '{bucket}.{scope}.{collection}'"
        )
        doc_id_prefix = f"upg_test_{sg_db}_{current_upgrade_ver}"

        self.mark_test_step("Add a bucket on CBS if not there already")
        if bucket not in cbs.get_bucket_names():
            print(f"Bucket '{bucket}' not found on CBS. Creating it for the test...")
            cbs.create_bucket(bucket)

        self.mark_test_step("Load dataset on CBL")
        if not hasattr(self, "db"):
            print(f"Resetting CBL database '{cbl_db}' for the test...")
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
        db = self.db

        self.mark_test_step("Configure Sync Gateway database and wait for it to be up")
        stable_upgrade_config = {
            "bucket": bucket,
            "num_index_replicas": 0,
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": """
                                function(doc, oldDoc) {
                                    channel("upgrade");
                                }
                            """
                        }
                    }
                }
            },
            "revs_limit": 1000,
            "import_docs": True,
            "enable_shared_bucket_access": True,
            "delta_sync": {"enabled": True},
        }
        db_payload = PutDatabasePayload(stable_upgrade_config)
        try:
            await sg.put_database(sg_db, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise e
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step("Create user1 for replication")
        collection_access = sg.create_collection_access_dict(
            {"_default._default": ["*"]}
        )
        await sg.add_user(sg_db, "user1", "pass", collection_access)

        self.mark_test_step("Add documents to SGW for this version")
        sg_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs_per_iteration):
            sg_docs.append(
                DocumentUpdateEntry(
                    f"{doc_id_prefix}_{i}",
                    None,
                    body={
                        "type": "upgrade_test_doc",
                        "version": current_upgrade_ver,
                        "index": i,
                        "message": "SGW upgrade test document.",
                    },
                )
            )
        await sg.update_documents(sg_db, sg_docs)

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/upg_sgw_dataset`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify data persistence on CBS and CBL for all docs")
        all_docs_to_verify = await sg.get_all_documents(sg_db, scope, collection)
        for row in all_docs_to_verify.rows:
            doc = cbs.get_document(bucket, row.id, scope, collection)
            print(f"Retrieved doc {row.id} from CBS: {doc}")
            assert doc is not None, f"Doc {row.id} not found on CBS"
            assert "version" in doc, f"Doc {row.id} missing 'version' field!"
            assert doc.get("type") == "upgrade_test_doc", (
                f"Doc {row.id} has wrong type! Expected 'upgrade_test_doc', got {doc.get('type')}"
            )
            cbl_doc = await db.get_document(DocumentEntry("_default._default", row.id))
            print(f"Retrieved doc {row.id} from CBL: {cbl_doc}")
            assert cbl_doc is not None, f"Doc {row.id} not found on CBL"
            assert "version" in cbl_doc.body, (
                f"Doc {row.id} missing 'version' field on CBL!"
            )
            assert cbl_doc.body.get("type") == "upgrade_test_doc", (
                f"Doc {row.id} has wrong type on CBL! Expected 'upgrade_test_doc', got {cbl_doc.body.get('type')}"
            )


@pytest.mark.upg_sgw
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(1)
class TestSgwUpgradeMultiNode(CBLTestClass):
    """Enhanced upgrade test with multiple SGW nodes and revision history tracking."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_upgrade_multi_sgw_with_revision_history(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Advanced upgrade test validating:
        1. Multi-node SGW cluster consistency during upgrades
        2. Revision history progression across generations (Gen 1 → Gen 2 → Gen 3)
        3. Multi-directional replication (SGW → CBL → SGW → CBL)
        4. Delta sync with multi-revision documents
        5. Round-robin updates across both SGW nodes
        """
        sg_nodes = cblpytest.sync_gateways[:2]
        cbs = cblpytest.couchbase_servers[0]
        current_upgrade_ver = os.environ.get("SGW_VERSION_UNDER_TEST", "0.0.0")
        num_docs = 20
        sg_db = "upg_multi_db"
        bucket = "upg_multi_bucket"
        cbl_db = "upg_multi_sgw"
        scope = "_default"
        collection = "_default"

        self.mark_test_step(
            f"Multi-node upgrade test v{current_upgrade_ver} with {len(sg_nodes)} SGW nodes"
        )
        doc_id_prefix = f"upg_rev_{current_upgrade_ver}"

        self.mark_test_step("Load bucket on CBS")
        if bucket not in cbs.get_bucket_names():
            cbs.create_bucket(bucket)

        self.mark_test_step("Load CBL database")
        if not hasattr(self, "db"):
            print(f"Resetting CBL database '{cbl_db}' for the test...")
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
        db = self.db

        self.mark_test_step("Configure SGW database on both nodes")
        sgw_config = {
            "bucket": bucket,
            "num_index_replicas": 0,
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": """
                                function(doc, oldDoc) {
                                    if (oldDoc) {
                                        doc.update_count = (oldDoc.update_count || 0) + 1;
                                    } else {
                                        doc.update_count = 0;
                                    }
                                    channel("upgrade");
                                }
                            """
                        }
                    }
                }
            },
            "revs_limit": 1000,
            "import_docs": True,
            "enable_shared_bucket_access": True,
            "delta_sync": {"enabled": True},
        }
        db_payload = PutDatabasePayload(sgw_config)
        for _, sg in enumerate(sg_nodes):
            try:
                await sg.put_database(sg_db, db_payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code != 412:
                    raise e
            await sg.wait_for_db_up(sg_db)

        self.mark_test_step("Create users on all SGW nodes")
        for sg in sg_nodes:
            collection_access = sg.create_collection_access_dict(
                {"_default._default": ["*"]}
            )
            try:
                await sg.add_user(sg_db, "user1", "pass", collection_access)
            except Exception as e:
                print(f"User may already exist: {e}")

        self.mark_test_step("GENERATION 1: Create initial documents via SGW node 1")
        gen1_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs):
            gen1_docs.append(
                DocumentUpdateEntry(
                    f"{doc_id_prefix}_{i}",
                    None,
                    body={
                        "generation": 1,
                        "content": f"Gen 1 - doc {i}",
                        "created_via": "sgw_node_1",
                        "upgrade_version": current_upgrade_ver,
                    },
                )
            )
        await sg_nodes[0].update_documents(sg_db, gen1_docs)
        await asyncio.sleep(1)

        self.mark_test_step("Store Generation 1 revisions from both SGW nodes")
        gen1_revisions_n1: dict[str, str] = {}
        all_docs_n1 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        for row in all_docs_n1.rows:
            if row.revid is not None:
                gen1_revisions_n1[row.id] = row.revid
        gen1_revisions_n2: dict[str, str] = {}
        all_docs_n2 = await sg_nodes[1].get_all_documents(sg_db, scope, collection)
        for row in all_docs_n2.rows:
            if row.revid is not None:
                gen1_revisions_n2[row.id] = row.revid

        self.mark_test_step(
            "Verify cluster consistency: Gen 1 revisions match on both nodes"
        )
        for doc_id in gen1_revisions_n1:
            assert gen1_revisions_n1[doc_id] == gen1_revisions_n2[doc_id], (
                f"Doc {doc_id} Gen 1 revisions differ: "
                f"node1={gen1_revisions_n1[doc_id]}, node2={gen1_revisions_n2[doc_id]}"
            )

        # === PULL GENERATION 1 TO CBL ===
        self.mark_test_step("""
            PULL Gen 1: Start replicator to pull Gen 1 docs to CBL
                * endpoint: `/upg_multi_db`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator_gen1 = Replicator(
            db,
            sg_nodes[0].replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg_nodes[0].tls_cert(),
        )
        await replicator_gen1.start()
        status = await replicator_gen1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Gen 1 pull failed: {status.error}"

        # === GENERATION 2: Update via CBL ===
        self.mark_test_step(
            "GENERATION 2: Update documents via CBL (conflict scenario)"
        )
        async with db.batch_updater() as batch:
            for i in range(num_docs):
                doc_id = f"{doc_id_prefix}_{i}"
                existing = await db.get_document(
                    DocumentEntry("_default._default", doc_id)
                )
                if existing:
                    body = existing.body.copy()
                    body["generation"] = 2
                    body["content"] = f"Gen 2 (updated via CBL) - doc {i}"
                    body["last_updated_via"] = "cbl"
                    batch.upsert_document("_default._default", doc_id, [body])

        # === PUSH GENERATION 2 TO SGW ===
        self.mark_test_step("""
            PUSH Gen 2: Push CBL updates back to SGW node 1
                * type: push
                * continuous: false
        """)
        replicator_gen2 = Replicator(
            db,
            sg_nodes[0].replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg_nodes[0].tls_cert(),
        )
        await replicator_gen2.start()
        status = await replicator_gen2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Gen 2 push failed: {status.error}"

        self.mark_test_step("Store Generation 2 revisions after CBL push")
        gen2_revisions: dict[str, str] = {}
        all_docs_gen2 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        for row in all_docs_gen2.rows:
            if row.revid is not None:
                gen2_revisions[row.id] = row.revid

        # === GENERATION 3: Update via both SGW nodes (round-robin) ===
        self.mark_test_step(
            "GENERATION 3: Update documents via both SGW nodes (round-robin)"
        )
        gen3_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs):
            doc_id = f"{doc_id_prefix}_{i}"
            gen3_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    gen2_revisions.get(doc_id),
                    body={
                        "generation": 3,
                        "content": f"Gen 3 (updated via SGW multi-node) - doc {i}",
                        "created_via": "sgw_multi_node",
                        "upgrade_version": current_upgrade_ver,
                    },
                )
            )

        # Split updates across nodes: even → node 1, odd → node 2
        for i, doc in enumerate(gen3_docs):
            target_node = sg_nodes[i % 2]
            await target_node.update_documents(sg_db, [doc])

        await asyncio.sleep(1)

        self.mark_test_step("Store Generation 3 revisions from both SGW nodes")
        gen3_revisions_n1: dict[str, str] = {}
        gen3_revisions_n2: dict[str, str] = {}

        all_docs_n1_gen3 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        for row in all_docs_n1_gen3.rows:
            if row.revid is not None:
                gen3_revisions_n1[row.id] = row.revid

        all_docs_n2_gen3 = await sg_nodes[1].get_all_documents(sg_db, scope, collection)
        for row in all_docs_n2_gen3.rows:
            if row.revid is not None:
                gen3_revisions_n2[row.id] = row.revid

        # === VERIFY REVISION PROGRESSION ===
        self.mark_test_step("Verify revision progression: Gen 1 → Gen 3")
        for doc_id in gen1_revisions_n1:
            gen1_rev = gen1_revisions_n1[doc_id]
            gen3_rev = gen3_revisions_n1[doc_id]

            gen1_num = int(gen1_rev.split("-")[0]) if gen1_rev else 0
            gen3_num = int(gen3_rev.split("-")[0]) if gen3_rev else 0

            assert gen3_num > gen1_num, (
                f"Doc {doc_id}: Revision didn't progress. "
                f"Gen1={gen1_rev}, Gen3={gen3_rev}"
            )

        # === VERIFY CLUSTER CONSISTENCY (Gen 3) ===
        self.mark_test_step(
            "Verify cluster consistency: Gen 3 revisions match on both nodes"
        )
        for doc_id in gen3_revisions_n1:
            assert gen3_revisions_n1[doc_id] == gen3_revisions_n2[doc_id], (
                f"Doc {doc_id} Gen 3 revisions differ: "
                f"node1={gen3_revisions_n1[doc_id]}, node2={gen3_revisions_n2[doc_id]}"
            )

        # === PULL GENERATION 3 TO CBL ===
        self.mark_test_step("""
            PULL Gen 3: Pull final updates to CBL from SGW node 2
                * type: pull
                * continuous: false
        """)
        replicator_gen3 = Replicator(
            db,
            sg_nodes[1].replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg_nodes[1].tls_cert(),
        )
        await replicator_gen3.start()
        status = await replicator_gen3.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Gen 3 pull failed: {status.error}"

        # === FINAL VERIFICATION: 3-WAY DATA CONSISTENCY ===
        self.mark_test_step("FINAL: Verify 3-way data consistency (CBS ↔ SGW ↔ CBL)")
        all_final_docs = await sg_nodes[0].get_all_documents(
            sg_db, scope, collection, True
        )

        for row in all_final_docs.rows:
            doc_id = row.id
            assert row.doc is not None, f"Doc {doc_id} missing on SGW"
            sg_content = row.doc.get("content")

            cbs_doc = cbs.get_document(bucket, doc_id, scope, collection)
            assert cbs_doc is not None, f"Doc {doc_id} missing on CBS"
            assert cbs_doc.get("generation") == 3, (
                f"Doc {doc_id} on CBS: expected gen 3, got {cbs_doc.get('generation')}"
            )

            cbl_doc = await db.get_document(DocumentEntry("_default._default", doc_id))
            assert cbl_doc is not None, f"Doc {doc_id} missing on CBL"
            assert cbl_doc.body.get("generation") == 3, (
                f"Doc {doc_id} on CBL: expected gen 3, got {cbl_doc.body.get('generation')}"
            )
            assert cbl_doc.body.get("content") == sg_content, (
                f"Doc {doc_id}: content mismatch between SGW and CBL"
            )

        self.mark_test_step(
            "✅ Multi-node upgrade test with revision history tracking PASSED"
        )
