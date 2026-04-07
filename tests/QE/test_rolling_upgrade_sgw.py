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

SGW_BUCKET = "rolling_upg_bucket"
SGW_CONFIG = {
    "bucket": SGW_BUCKET,
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


@pytest.mark.upg_sgw
@pytest.mark.min_sync_gateways(3)
@pytest.mark.min_couchbase_servers(1)
class TestSgwRollingUpgrade(CBLTestClass):
    """
    Rolling upgrade test for a 3-node Sync Gateway cluster.

    Each invocation (initial, rolling_node_N, complete) follows the same
    pattern from test_upg_sgw.py:
      1. Reset CBL, configure SGW DB + user on relevant nodes
      2. Start continuous push-pull replicator (pulls old docs from CBS via SGW)
      3. Add new docs tagged with current version
      4. Update ALL existing docs to progress revisions
      5. Verify revision progression on SGW
      6. Verify persistence on CBS and CBL
    """

    @pytest.mark.asyncio(loop_scope="session")
    async def test_rolling_upgrade_sgw_cluster(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg_nodes = cblpytest.sync_gateways[:3]
        cbs = cblpytest.couchbase_servers[0]
        upgrade_phase = os.environ.get("SGW_UPGRADE_PHASE", "initial")
        current_version = os.environ.get("SGW_VERSION_UNDER_TEST", "0.0.0")
        num_docs_per_iteration = 10
        sg_db = "rolling_upg_db"
        bucket: str = SGW_BUCKET
        cbl_db = "rolling_upg_cbl"
        scope = "_default"
        collection = "_default"

        self.mark_test_step(f"Phase: {upgrade_phase} | SGW version: {current_version}")
        doc_id_prefix = f"rolling_{upgrade_phase}_{current_version}"

        self.mark_test_step("Ensure bucket exists on CBS")
        if bucket not in cbs.get_bucket_names():
            cbs.create_bucket(bucket)

        self.mark_test_step("Reset CBL database")
        db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]

        self.mark_test_step("Configure SGW database on all nodes")
        db_payload = PutDatabasePayload(SGW_CONFIG)
        for sg in sg_nodes:
            try:
                await sg.put_database(sg_db, db_payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code != 412:
                    raise e
        for sg in sg_nodes:
            await sg.wait_for_db_up(sg_db)

        self.mark_test_step("Ensure user exists on all SGW nodes")
        for sg in sg_nodes:
            collection_access = sg.create_collection_access_dict(
                {"_default._default": ["*"]}
            )
            try:
                await sg.add_user(sg_db, "user1", "pass", collection_access)
            except Exception as e:
                print(f"User may already exist: {e}")

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
        assert status.error is None, f"Error waiting for replicator: {status.error}"

        self.mark_test_step(f"Add {num_docs_per_iteration} new docs for this phase")
        new_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs_per_iteration):
            new_docs.append(
                DocumentUpdateEntry(
                    f"{doc_id_prefix}_{i}",
                    None,
                    body={
                        "type": "rolling_upgrade_doc",
                        "version": current_version,
                        "phase": upgrade_phase,
                        "index": i,
                        "message": "SGW rolling upgrade test document.",
                    },
                )
            )
        await sg_nodes[0].update_documents(sg_db, new_docs)

        self.mark_test_step("Wait for replicator to sync new docs")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: "
            f"({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Save current revisions before update")
        docs_before = await sg_nodes[0].get_all_documents(
            sg_db, scope, collection, True
        )
        revs_before = {row.id: row.revid for row in docs_before.rows}
        print(f"Total docs before update: {len(revs_before)}")

        self.mark_test_step("Update all docs on SGW to progress revisions")
        updated_docs: list[DocumentUpdateEntry] = []
        for row in docs_before.rows:
            if row is None or row.doc is None:
                continue
            updated_docs.append(
                DocumentUpdateEntry(
                    row.id,
                    revs_before[row.id],
                    body={
                        **row.doc,
                        "message": f"updated in {upgrade_phase}",
                    },
                )
            )
        await sg_nodes[0].update_documents(sg_db, updated_docs)

        self.mark_test_step("Wait for replicator to sync updates")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: "
            f"({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify revisions have progressed on SGW via changes feed")
        changes = await sg_nodes[0].get_changes(sg_db, scope, collection)
        revs_after: dict[str, str] = {}
        for entry in changes.results:
            if not entry.deleted and entry.changes:
                revs_after[entry.id] = entry.changes[-1]
        for doc_id in revs_before:
            before_rev = revs_before[doc_id]
            after_rev = revs_after.get(doc_id)
            assert before_rev is not None, f"Doc {doc_id} missing before update"
            assert after_rev is not None, f"Doc {doc_id} missing after update"
            before_num = int(before_rev.split("-")[0])
            after_num = int(after_rev.split("-")[0])
            assert after_num > before_num, (
                f"Doc {doc_id}: Revision didn't progress. "
                f"Before={before_rev}, After={after_rev}"
            )
            print(f"  {doc_id}: {before_num} -> {after_num}")

        self.mark_test_step("Verify revision consistency across all SGW nodes")
        for node_idx, sg in enumerate(sg_nodes):
            node_changes = await sg.get_changes(sg_db, scope, collection)
            node_revs: dict[str, str] = {}
            for entry in node_changes.results:
                if not entry.deleted and entry.changes:
                    node_revs[entry.id] = entry.changes[-1]
            assert len(node_revs) == len(revs_after), (
                f"Node {node_idx} has {len(node_revs)} docs, expected {len(revs_after)}"
            )
            for doc_id, rev in revs_after.items():
                assert node_revs.get(doc_id) == rev, (
                    f"Node {node_idx} doc {doc_id}: expected {rev}, got {node_revs.get(doc_id)}"
                )

        self.mark_test_step("Verify data persistence on CBS and CBL")
        for row in docs_before.rows:
            cbs_doc = cbs.get_document(bucket, row.id)
            assert cbs_doc is not None, f"Doc {row.id} not found on CBS"
            assert "version" in cbs_doc, f"Doc {row.id} missing 'version' on CBS"
            assert cbs_doc["type"] == "rolling_upgrade_doc", (
                f"Doc {row.id} wrong type on CBS: {cbs_doc['type']}"
            )

            cbl_doc = await db.get_document(DocumentEntry("_default._default", row.id))
            assert cbl_doc is not None, f"Doc {row.id} not found on CBL"
            assert "version" in cbl_doc.body, f"Doc {row.id} missing 'version' on CBL"
            assert cbl_doc.body.get("type") == "rolling_upgrade_doc", (
                f"Doc {row.id} wrong type on CBL: {cbl_doc.body.get('type')}"
            )
