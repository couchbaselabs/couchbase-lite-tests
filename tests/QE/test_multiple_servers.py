import asyncio
from pathlib import Path

import pytest
import requests
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from packaging.version import Version


def _check_node_in_cluster(cbs_hostname: str, cluster_nodes: list) -> tuple[bool, bool]:
    """Check if a CBS node is in cluster and if it needs recovery."""
    for node in cluster_nodes:
        hostname = node.get("hostname", "").split(":")[0]
        alt_hostname = (
            node.get("alternateAddresses", {}).get("external", {}).get("hostname", "")
        )
        if cbs_hostname in [hostname, alt_hostname]:
            return True, node.get("clusterMembership") == "inactiveFailed"
    return False, False


def _recover_or_add_node(cbs_one, cbs_two):
    """Recover or add CBS node based on its cluster state."""
    session = requests.Session()
    session.auth = ("Administrator", "password")
    resp = session.get(f"http://{cbs_one.hostname}:8091/pools/default")
    resp.raise_for_status()
    cluster_data = resp.json()
    node_in_cluster, _ = _check_node_in_cluster(
        cbs_two.hostname, cluster_data.get("nodes", [])
    )
    if node_in_cluster:
        cbs_one.recover(cbs_two)
    else:
        cbs_one.add_node(cbs_two)
    cbs_one.rebalance_in()


async def _cleanup_test_resources(sg, cbs, sg_db: str, bucket_name: str):
    """Clean up test database and bucket."""
    try:
        await sg.delete_database(sg_db)
        await asyncio.sleep(3)
    except Exception:
        pass
    for attempt in range(3):
        try:
            cbs.drop_bucket(bucket_name)
            break
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                break
            if attempt < 2:
                await asyncio.sleep(5)
    await asyncio.sleep(10)


async def _setup_database_and_user(
    sg,
    cbs,
    sg_db: str,
    bucket_name: str,
    user_name: str,
    user_password: str,
    channels: list,
):
    """Setup bucket, database, and user."""
    cbs.create_bucket(bucket_name, num_replicas=1)
    await asyncio.sleep(5)

    db_config = {
        "bucket": bucket_name,
        "index": {"num_replicas": 1},
        "scopes": {"_default": {"collections": {"_default": {}}}},
    }
    await sg.put_database(sg_db, PutDatabasePayload(db_config))
    await asyncio.sleep(3)

    await sg.delete_user(sg_db, user_name)
    await sg.add_user(
        sg_db,
        user_name,
        password=user_password,
        collection_access={"_default": {"_default": {"admin_channels": channels}}},
    )
    return await sg.create_user_client(sg_db, user_name, user_password, channels)


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
        cbs_one.ensure_cluster_healthy(cblpytest.couchbase_servers)

        sg_db, bucket_name = "db-rebalance-sanity", "data-bucket"
        num_docs, num_updates = 50, 10
        sg_user_name, sg_user_password = "vipul", "pass"
        channels = ["ABC", "CBS"]

        self.mark_test_step("Clean up and setup test environment")
        await _cleanup_test_resources(sg, cbs_one, sg_db, bucket_name)
        sg_user = await _setup_database_and_user(
            sg, cbs_one, sg_db, bucket_name, sg_user_name, sg_user_password, channels
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
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        current_docs = await sg_user.get_all_documents(sg_db)
                        rev_map = {row.id: row.revision for row in current_docs.rows}

                        updates = [
                            DocumentUpdateEntry(
                                id=f"test_doc_{i}",
                                revid=rev_map.get(
                                    f"test_doc_{i}"
                                ),  # Use current revision
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
                        break  # Success, exit retry loop
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(
                                f"Update attempt {attempt + 1} failed: {e}, retrying..."
                            )
                            await asyncio.sleep(1)
                        else:
                            print(f"Update failed after {max_retries} attempts: {e}")
                            raise

                # Small delay between update batches to avoid overwhelming SGW
                await asyncio.sleep(0.1)

        update_task = asyncio.create_task(update_docs_continuously())
        await asyncio.sleep(2)

        self.mark_test_step("Rebalance OUT cbs_two from cluster")
        cbs_one.rebalance_out(cbs_two)

        self.mark_test_step("Add cbs_two back to cluster")
        cbs_one.add_node(cbs_two)

        self.mark_test_step("Rebalance IN cbs_two to cluster")
        cbs_one.rebalance_in()
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_server_goes_down_sanity(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs_one = cblpytest.couchbase_servers[0]
        cbs_two = cblpytest.couchbase_servers[1]
        cbs_one.ensure_cluster_healthy(cblpytest.couchbase_servers)

        sg_db, bucket_name = "db", "data-bucket"
        num_docs = 50
        sg_user_name, sg_user_password = "vipul", "pass"
        channels = ["ABC", "CBS"]

        self.mark_test_step("Clean up and setup test environment")
        await _cleanup_test_resources(sg, cbs_one, sg_db, bucket_name)
        sg_user = await _setup_database_and_user(
            sg, cbs_one, sg_db, bucket_name, sg_user_name, sg_user_password, channels
        )

        self.mark_test_step(f"Add {num_docs} docs to Sync Gateway before failover")
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
        initial_docs = await sg_user.get_all_documents(sg_db)
        assert len(initial_docs.rows) == num_docs, (
            f"Expected {num_docs} docs, got {len(initial_docs.rows)}"
        )

        self.mark_test_step("Failover CBS node 2 to simulate server failure")
        cbs_one.failover(cbs_two)
        cbs_one.rebalance(eject_failed_nodes=False)
        await asyncio.sleep(10)

        self.mark_test_step("Verify original docs accessible with node 2 failed over")

        changes_after_failover = await sg.get_changes(sg_db, version_type="cv")
        assert len(changes_after_failover.results) == num_docs

        self.mark_test_step(f"Add {num_docs} NEW docs while node 2 is down")
        new_docs_during_failover = [
            DocumentUpdateEntry(
                id=f"test_doc_during_failover_{i}",
                revid=None,
                body={
                    "type": "test_doc_failover",
                    "index": i,
                    "content": f"Document {i} added during failover",
                    "channels": channels,
                },
            )
            for i in range(num_docs)
        ]
        await sg.update_documents(sg_db, new_docs_during_failover)

        self.mark_test_step("Verify new docs added during failover")
        all_docs_with_new = await sg.get_all_documents(sg_db)
        assert len(all_docs_with_new.rows) == num_docs * 2

        self.mark_test_step("Recover CBS node 2")
        _recover_or_add_node(cbs_one, cbs_two)
        if not cbs_one.wait_for_cluster_healthy(timeout=60):
            pytest.fail("Cluster did not become healthy")
        await asyncio.sleep(10)

        self.mark_test_step("Verify all docs accessible after recovery")
        changes_final = await sg.get_changes(sg_db, version_type="cv")
        assert len(changes_final.results) == num_docs * 2

        await sg.delete_database(sg_db)
        cbs_one.drop_bucket(bucket_name)
        cbs_two.drop_bucket(bucket_name)
