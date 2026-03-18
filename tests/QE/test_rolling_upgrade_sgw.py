import asyncio
import os
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
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


@pytest.mark.upg_sgw
@pytest.mark.min_sync_gateways(3)
@pytest.mark.min_couchbase_servers(1)
class TestSgwRollingUpgrade(CBLTestClass):
    """
    Rolling upgrade test for Sync Gateway clusters.

    Tests that a 3-node SGW cluster can be upgraded one node at a time while
    maintaining data consistency, replication, and cross-version read/write capability.
    """

    @pytest.mark.asyncio(loop_scope="session")
    async def test_rolling_upgrade_sgw_cluster(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Rolling upgrade test that upgrades SGW nodes one at a time.

        The test adapts based on SGW_UPGRADE_PHASE env var:
        - 'initial': Setup phase (all nodes same version)
        - 'rolling_node_N': Mixed-version state (node N upgraded, others old)
        - 'complete': All nodes upgraded
        """
        sg_nodes = cblpytest.sync_gateways[:3]
        cbs = cblpytest.couchbase_servers[0]
        load_balancer = (
            cblpytest.load_balancers[0] if cblpytest.load_balancers else None
        )

        upgrade_phase = os.environ.get("SGW_UPGRADE_PHASE", "initial")
        upgraded_node_index = os.environ.get("SGW_UPGRADED_NODE_INDEX", None)
        current_version = os.environ.get("SGW_VERSION_UNDER_TEST", "0.0.0")
        previous_version = os.environ.get("SGW_PREVIOUS_VERSION", "0.0.0")

        sg_db = "rolling_upg_db"
        bucket = "rolling_upg_bucket"
        cbl_db = "rolling_upg_cbl"
        scope = "_default"
        collection = "_default"

        if upgrade_phase == "initial":
            await self._phase_initial(
                cblpytest,
                sg_nodes,
                cbs,
                sg_db,
                bucket,
                cbl_db,
                scope,
                collection,
                current_version,
            )
        elif upgrade_phase.startswith("rolling_node_"):
            await self._phase_rolling_node(
                cblpytest,
                sg_nodes,
                cbs,
                load_balancer,
                sg_db,
                bucket,
                cbl_db,
                scope,
                collection,
                upgraded_node_index,
                current_version,
                previous_version,
            )
        elif upgrade_phase == "complete":
            await self._phase_complete(
                cblpytest,
                sg_nodes,
                cbs,
                sg_db,
                bucket,
                cbl_db,
                scope,
                collection,
                current_version,
            )
        else:
            raise ValueError(f"Unknown SGW_UPGRADE_PHASE: {upgrade_phase}")

    async def _phase_initial(
        self,
        cblpytest: CBLPyTest,
        sg_nodes,
        cbs,
        sg_db,
        bucket,
        cbl_db,
        scope,
        collection,
        version,
    ) -> None:
        """
        Initial setup phase: provision bucket, SGW DB, users, and initial data.
        """
        self.mark_test_step(f"PHASE: INITIAL SETUP (v{version})")
        self.mark_test_step("Create bucket on CBS")
        if bucket not in cbs.get_bucket_names():
            cbs.create_bucket(bucket)

        self.mark_test_step("Load CBL database")
        if not hasattr(self, "db"):
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
        db = self.db

        self.mark_test_step("Configure SGW database on all 3 nodes")
        sgw_config = {
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
        db_payload = PutDatabasePayload(sgw_config)
        for i, sg in enumerate(sg_nodes):
            try:
                await sg.put_database(sg_db, db_payload)
            except Exception as e:
                if "412" not in str(e):
                    raise e
            await sg.wait_for_db_up(sg_db)
            self.mark_test_step(f"SGW node {i} database configured and ready")

        self.mark_test_step("Create users on all SGW nodes")
        for sg in sg_nodes:
            collection_access = sg.create_collection_access_dict(
                {"_default._default": ["*"]}
            )
            try:
                await sg.add_user(sg_db, "user1", "pass", collection_access)
            except Exception as e:
                print(f"User may already exist on node: {e}")

        self.mark_test_step("Ingest initial 30 documents (10 per node)")
        all_docs = []
        for node_idx, sg in enumerate(sg_nodes):
            docs: list[DocumentUpdateEntry] = []
            for i in range(10):
                doc_id = f"initial_node{node_idx}_{i}"
                docs.append(
                    DocumentUpdateEntry(
                        doc_id,
                        None,
                        body={
                            "type": "rolling_upgrade_doc",
                            "created_by_node": node_idx,
                            "version": version,
                            "index": i,
                            "content": f"Initial doc created via node {node_idx}",
                        },
                    )
                )
            await sg.update_documents(sg_db, docs)
            all_docs.extend(docs)

        self.mark_test_step("Start continuous push-pull replicator")
        replicator = Replicator(
            db,
            sg_nodes[0].replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg_nodes[0].tls_cert(),
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, f"Replication error: {status.error}"

        self.mark_test_step("Verify all 30 documents replicated to CBL")
        for doc_entry in all_docs:
            cbl_doc = await db.get_document(
                DocumentEntry(f"{scope}.{collection}", doc_entry.id)
            )
            assert cbl_doc is not None, f"Doc {doc_entry.id} not found in CBL"

        self.mark_test_step("Verify revision consistency across all 3 SGW nodes")
        rev_node0 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        rev_node1 = await sg_nodes[1].get_all_documents(sg_db, scope, collection)
        rev_node2 = await sg_nodes[2].get_all_documents(sg_db, scope, collection)

        revs_0 = {row.id: row.revid for row in rev_node0.rows}
        revs_1 = {row.id: row.revid for row in rev_node1.rows}
        revs_2 = {row.id: row.revid for row in rev_node2.rows}

        for doc_id in revs_0:
            assert revs_0[doc_id] == revs_1[doc_id], (
                f"Doc {doc_id}: revision mismatch node0 vs node1"
            )
            assert revs_0[doc_id] == revs_2[doc_id], (
                f"Doc {doc_id}: revision mismatch node0 vs node2"
            )
            print(f"✓ Doc {doc_id}: revisions consistent across all 3 nodes")

    async def _phase_rolling_node(
        self,
        cblpytest: CBLPyTest,
        sg_nodes,
        cbs,
        load_balancer,
        sg_db,
        bucket,
        cbl_db,
        scope,
        collection,
        upgraded_node_index,
        current_version,
        previous_version,
    ) -> None:
        """
        Rolling upgrade phase: one node upgraded, others old version (mixed-version state).
        """
        upgraded_idx = int(upgraded_node_index)
        self.mark_test_step(
            f"PHASE: ROLLING UPGRADE node {upgraded_idx} ({previous_version} → {current_version})"
        )

        db = self.db if hasattr(self, "db") else None
        if db is None:
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
            db = self.db

        self.mark_test_step(
            f"Wait for upgraded node {upgraded_idx} database to come online"
        )
        await sg_nodes[upgraded_idx].wait_for_db_up(sg_db)

        self.mark_test_step(
            "Verify cross-version read: all docs readable from upgraded node"
        )
        all_docs_upgraded = await sg_nodes[upgraded_idx].get_all_documents(
            sg_db, scope, collection
        )
        doc_count_upgraded = len(all_docs_upgraded.rows)
        assert doc_count_upgraded > 0, "No documents found on upgraded node!"
        print(f"✓ Upgraded node {upgraded_idx}: found {doc_count_upgraded} documents")

        self.mark_test_step(
            "Verify cross-version read: all docs readable from old-version nodes"
        )
        for old_idx, sg in enumerate(sg_nodes):
            if old_idx == upgraded_idx:
                continue
            all_docs_old = await sg.get_all_documents(sg_db, scope, collection)
            doc_count_old = len(all_docs_old.rows)
            assert doc_count_old == doc_count_upgraded, (
                f"Doc count mismatch: old node {old_idx} has {doc_count_old}, "
                f"upgraded node has {doc_count_upgraded}"
            )
            print(
                f"✓ Old-version node {old_idx}: found {doc_count_old} documents (matches upgraded)"
            )

        self.mark_test_step(
            "Write 5 new docs via upgraded node, verify readable from old nodes"
        )
        upgraded_node_docs: list[DocumentUpdateEntry] = []
        for i in range(5):
            doc_id = f"rolling_upgrade_by_node{upgraded_idx}_{i}"
            upgraded_node_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    None,
                    body={
                        "type": "rolling_upgrade_doc",
                        "created_by_node": upgraded_idx,
                        "version": current_version,
                        "content": f"Rolled doc from upgraded node {upgraded_idx}",
                    },
                )
            )
        await sg_nodes[upgraded_idx].update_documents(sg_db, upgraded_node_docs)

        for old_idx, sg in enumerate(sg_nodes):
            if old_idx == upgraded_idx:
                continue
            await asyncio.sleep(1)
            old_docs = await sg.get_all_documents(sg_db, scope, collection)
            for upg_doc in upgraded_node_docs:
                found = any(row.id == upg_doc.id for row in old_docs.rows)
                assert found, (
                    f"Doc {upg_doc.id} (from upgraded node) not readable on old node {old_idx}"
                )
            print(f"✓ All docs from upgraded node readable on old node {old_idx}")

        self.mark_test_step(
            "Write 5 new docs via old node, verify readable from upgraded node"
        )
        old_node_idx = (upgraded_idx + 1) % 3
        old_node_docs: list[DocumentUpdateEntry] = []
        for i in range(5):
            doc_id = f"rolling_upgrade_by_oldnode_{old_node_idx}_{i}"
            old_node_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    None,
                    body={
                        "type": "rolling_upgrade_doc",
                        "created_by_node": old_node_idx,
                        "version": previous_version,
                        "content": f"Old-version doc from node {old_node_idx}",
                    },
                )
            )
        await sg_nodes[old_node_idx].update_documents(sg_db, old_node_docs)

        await asyncio.sleep(1)
        upg_docs = await sg_nodes[upgraded_idx].get_all_documents(
            sg_db, scope, collection
        )
        for old_doc in old_node_docs:
            found = any(row.id == old_doc.id for row in upg_docs.rows)
            assert found, (
                f"Doc {old_doc.id} (from old node) not readable on upgraded node"
            )
        print(
            f"✓ All docs from old node {old_node_idx} readable on upgraded node {upgraded_idx}"
        )

        self.mark_test_step("Test replicator connectivity to each node individually")
        for node_idx, sg in enumerate(sg_nodes):
            replicator = Replicator(
                db,
                sg.replication_url(sg_db),
                collections=[ReplicatorCollectionEntry(["_default._default"])],
                replicator_type=ReplicatorType.PUSH_AND_PULL,
                continuous=False,
                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                pinned_server_cert=sg.tls_cert(),
            )
            await replicator.start()
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, (
                f"Replication to node {node_idx} failed: {status.error}"
            )
            print(f"✓ Replicator successfully synced with node {node_idx}")

        self.mark_test_step(
            "Test replicator connectivity through load balancer if available"
        )
        if load_balancer:
            replicator_lb = Replicator(
                db,
                load_balancer.replication_url(sg_db),
                collections=[ReplicatorCollectionEntry(["_default._default"])],
                replicator_type=ReplicatorType.PUSH_AND_PULL,
                continuous=False,
                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                pinned_server_cert=None,
            )
            await replicator_lb.start()
            status = await replicator_lb.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, (
                f"Replication through load balancer failed: {status.error}"
            )
            print("✓ Replicator successfully synced through load balancer")
        else:
            print(
                "⊘ Load balancer not available in topology, skipping LB replication test"
            )

        self.mark_test_step(
            "Verify revision consistency across cluster (mixed-version)"
        )
        rev_node0 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        rev_node1 = await sg_nodes[1].get_all_documents(sg_db, scope, collection)
        rev_node2 = await sg_nodes[2].get_all_documents(sg_db, scope, collection)

        revs_0 = {row.id: row.revid for row in rev_node0.rows}
        revs_1 = {row.id: row.revid for row in rev_node1.rows}
        revs_2 = {row.id: row.revid for row in rev_node2.rows}

        for doc_id in revs_0:
            assert revs_0[doc_id] == revs_1[doc_id], (
                f"Doc {doc_id}: mixed-version revision mismatch node0 vs node1"
            )
            assert revs_0[doc_id] == revs_2[doc_id], (
                f"Doc {doc_id}: mixed-version revision mismatch node0 vs node2"
            )
        print("✓ Revision consistency maintained in mixed-version state")

        self.mark_test_step("Spot-check documents exist on CBS with correct fields")
        all_docs = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        for i, row in enumerate(all_docs.rows[:5]):
            cbs_doc = cbs.get_document(bucket, row.id)
            assert cbs_doc is not None, f"Doc {row.id} not found on CBS"
            assert "type" in cbs_doc, f"Doc {row.id} missing 'type' field on CBS"
            print(f"✓ Doc {row.id} verified on CBS")

    async def _phase_complete(
        self,
        cblpytest: CBLPyTest,
        sg_nodes,
        cbs,
        sg_db,
        bucket,
        cbl_db,
        scope,
        collection,
        version,
    ) -> None:
        """
        Complete phase: all nodes upgraded to final version.
        """
        self.mark_test_step(f"PHASE: COMPLETE (All nodes on v{version})")

        db = self.db if hasattr(self, "db") else None
        if db is None:
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
            db = self.db

        self.mark_test_step("Verify all documents present from all upgrade phases")
        all_docs_node0 = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        total_docs = len(all_docs_node0.rows)
        print(f"Total documents across all phases: {total_docs}")

        self.mark_test_step("Full 3-way verification: SGW (all nodes) == CBS == CBL")
        for node_idx, sg in enumerate(sg_nodes):
            all_docs_this_node = await sg.get_all_documents(sg_db, scope, collection)
            assert len(all_docs_this_node.rows) == total_docs, (
                f"Node {node_idx} has {len(all_docs_this_node.rows)} docs, expected {total_docs}"
            )

        for row in all_docs_node0.rows:
            cbs_doc = cbs.get_document(bucket, row.id)
            assert cbs_doc is not None, f"Doc {row.id} missing from CBS"

            cbl_doc = await db.get_document(
                DocumentEntry(f"{scope}.{collection}", row.id)
            )
            assert cbl_doc is not None, f"Doc {row.id} missing from CBL"

        print(f"✓ All {total_docs} documents verified across SGW cluster, CBS, and CBL")

        self.mark_test_step(
            "Final replicator round-trip: push from CBL, pull back, verify no data loss"
        )
        replicator = Replicator(
            db,
            sg_nodes[0].replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=sg_nodes[0].tls_cert(),
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Final replication failed: {status.error}"

        final_docs = await sg_nodes[0].get_all_documents(sg_db, scope, collection)
        assert len(final_docs.rows) == total_docs, (
            f"Final doc count {len(final_docs.rows)} != expected {total_docs}"
        )
        print(f"✓ Final round-trip verified: {total_docs} documents intact")
