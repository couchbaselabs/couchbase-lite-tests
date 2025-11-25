import asyncio
from pathlib import Path

import pytest
import requests
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from packaging.version import Version


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(2)
class TestMultipleServers(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_rebalance_sanity(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs_one = cblpytest.couchbase_servers[0]
        cbs_two = cblpytest.couchbase_servers[1]
        cluster_servers = [cbs_one, cbs_two]

        sg_db = "db"
        bucket_name = "data-bucket"
        num_docs = 100
        num_updates = 100
        sg_user_name = "vipul"
        sg_user_password = "pass"
        channels = ["ABC", "CBS"]

        self.mark_test_step("Ensure both CBS nodes are in the cluster")
        # Check if cbs_two is in the cluster by checking the cluster node count
        session = requests.Session()
        session.auth = ("Administrator", "password")
        resp = session.get(f"http://{cbs_one.hostname}:8091/pools/default")
        cluster_data = resp.json()
        node_count = len(cluster_data.get("nodes", []))

        if node_count < 2:
            # cbs_two is not in the cluster, add it
            try:
                cbs_one.add_node(cbs_two)
                cbs_one.rebalance_in(cluster_servers, cbs_two)
                print("Successfully added cbs_two to cluster")
                # Verify node was added
                resp = session.get(f"http://{cbs_one.hostname}:8091/pools/default")
                cluster_data = resp.json()
                node_count = len(cluster_data.get("nodes", []))
            except Exception as e:
                pytest.fail(f"Warning: Failed to add cbs_two to cluster: {e}")

        self.mark_test_step("Clean up any existing test data")
        await sg.delete_database(sg_db)
        cbs_one.drop_bucket(bucket_name)
        cbs_two.drop_bucket(bucket_name)

        self.mark_test_step("Create bucket on CBS cluster")
        cbs_one.create_bucket(bucket_name)

        self.mark_test_step(f"Configure database '{sg_db}' on SGW")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 1},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg.put_database(sg_db, db_payload)
        await asyncio.sleep(3)

        self.mark_test_step(f"Create user '{sg_user_name}' with channels {channels}")
        await sg.delete_user(sg_db, sg_user_name)
        await sg.add_user(
            sg_db,
            sg_user_name,
            password=sg_user_password,
            collection_access={"_default": {"_default": {"admin_channels": channels}}},
        )

        self.mark_test_step("Create user client for SGW access")
        sg_user = await sg.create_user_client(
            sg_db, sg_user_name, sg_user_password, channels
        )

        self.mark_test_step(f"Add {num_docs} docs to Sync Gateway")
        docs_to_add = [
            DocumentUpdateEntry(
                id=f"test_doc_{i}",
                revid=None,
                body={
                    "type": "test_doc",
                    "index": i,
                    "content": f"Document {i}",
                    "channels": channels,
                },
            )
            for i in range(num_docs)
        ]
        await sg_user.update_documents(sg_db, docs_to_add)
        await asyncio.sleep(2)

        self.mark_test_step(
            "Verify all docs were created and store original revisions and version vectors"
        )
        all_docs = await sg_user.get_all_documents(sg_db)
        assert len(all_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(all_docs.rows)}"
        )
        original_revs = {row.id: row.revision for row in all_docs.rows}

        sgw_version_obj = await sg.get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")

        original_vvs = {}
        if supports_version_vectors:
            changes_initial = await sg_user.get_changes(sg_db, version_type="cv")
            original_vvs = {
                entry.id: entry.changes[0] if entry.changes else None
                for entry in changes_initial.results
            }

        self.mark_test_step(
            f"Start concurrent updates ({num_updates} updates per doc) and rebalance CBS cluster"
        )

        async def update_docs_continuously() -> None:
            """Continuously update all documents num_updates times"""
            for update_num in range(num_updates):
                # Get current revisions for all docs
                current_docs = await sg_user.get_all_documents(sg_db)
                rev_map = {row.id: row.revision for row in current_docs.rows}

                updates = [
                    DocumentUpdateEntry(
                        id=f"test_doc_{i}",
                        revid=rev_map.get(f"test_doc_{i}"),  # Use current revision
                        body={
                            "type": "test_doc",
                            "index": i,
                            "content": f"Document {i} - update {update_num + 1}",
                            "channels": channels,
                        },
                    )
                    for i in range(num_docs)
                ]
                await sg_user.update_documents(sg_db, updates)

        update_task = asyncio.create_task(update_docs_continuously())
        await asyncio.sleep(2)

        self.mark_test_step("Rebalance OUT cbs_two from cluster")
        cbs_one.rebalance_out(cluster_servers, cbs_two)

        self.mark_test_step("Add cbs_two back to cluster")
        cbs_one.add_node(cbs_two)

        self.mark_test_step("Rebalance IN cbs_two to cluster")
        cbs_one.rebalance_in(cluster_servers, cbs_two)
        await asyncio.sleep(5)

        self.mark_test_step("Wait for all updates to complete")
        await update_task

        self.mark_test_step(
            "Verify all docs are present and revisions/version vectors changed"
        )
        all_docs_final = await sg_user.get_all_documents(sg_db)
        assert len(all_docs_final.rows) == num_docs, (
            f"Expected {num_docs} docs after rebalance, got {len(all_docs_final.rows)}"
        )

        for row in all_docs_final.rows:
            original_rev = original_revs.get(row.id)
            assert original_rev is not None, (
                f"Document {row.id} not found in original revisions"
            )
            assert row.revision != original_rev, (
                f"Document {row.id} revision should have changed after {num_updates} "
                f"updates. Original: {original_rev}, Current: {row.revision}"
            )
            if supports_version_vectors:
                original_vv = original_vvs.get(row.id)
                assert original_vv is not None, (
                    f"Document {row.id} not found in original version vectors"
                )
                assert row.cv != original_vv, (
                    f"Document {row.id} version vector should have changed after "
                    f"{num_updates} updates. Original: {original_vv}, Current: {row.cv}"
                )

        await sg_user.close()
        await sg.delete_database(sg_db)
        cbs_one.drop_bucket(bucket_name)
        cbs_two.drop_bucket(bucket_name)
