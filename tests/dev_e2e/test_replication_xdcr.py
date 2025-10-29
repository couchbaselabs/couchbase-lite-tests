import time
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_doc_ids, compare_local_and_remote
from cbltest.utils import assert_not_null


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(2)
@pytest.mark.min_load_balancers(1)
class TestReplicationXdcr(CBLTestClass):
    async def setup_xdcr_clusters(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        dataset_name: str,
    ):
        """
        Prepare two Couchbase clusters for XDCR testing:
        - Stop any existing XDCR replications.
        - Reset Sync Gateways and load the dataset on each cluster.
        - Start bidirectional XDCR.
        """
        self.mark_test_step(
            "Stop XDCR between cluster 1 and cluster 2 if they are active."
        )
        cblpytest.couchbase_servers[0].stop_xcdr(
            cblpytest.couchbase_servers[1], dataset_name
        )
        cblpytest.couchbase_servers[1].stop_xcdr(
            cblpytest.couchbase_servers[0], dataset_name
        )

        self.mark_test_step("Reset SGs in cluster 1 and 2, and load dataset.")
        cloud1 = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud1.configure_dataset(dataset_path, dataset_name)
        cloud2 = CouchbaseCloud(
            cblpytest.sync_gateways[1], cblpytest.couchbase_servers[1]
        )
        await cloud2.configure_dataset(dataset_path, dataset_name)

        self.mark_test_step("Start XDCR between cluster 1 and cluster 2.")
        cblpytest.couchbase_servers[0].start_xdcr(
            cblpytest.couchbase_servers[1], dataset_name
        )
        cblpytest.couchbase_servers[1].start_xdcr(
            cblpytest.couchbase_servers[0], dataset_name
        )

        self.mark_test_step("Wait 5 secs to ensure that clusters are ready.")
        time.sleep(5)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_and_pull_with_xdcr(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        await self.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.0.0")

        self.mark_test_step("Prepare clusters and start XDCR.")
        await self.setup_xdcr_clusters(cblpytest, dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator to SG1 via load balancer: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
            """)
        repl_url = cblpytest.sync_gateways[0].replication_url(
            "names", cblpytest.load_balancers[0]
        )
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Wait 5 secs to ensure that the docs are sync between two SGs."
        )
        time.sleep(5)

        self.mark_test_step("Check that all docs are replicated correctly at SG1.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            bucket="names",
            collections=["_default._default"],
        )

        self.mark_test_step("Check that all docs are replicated correctly at SG2.")
        # Local docs from the 3.2 dataset use rev-trees, while SG2 docs replicated
        # via XDCR use version vectors, so their revids are not comparable.
        local_docs = await db.get_all_documents("_default._default")
        remote_docs = await cblpytest.sync_gateways[1].get_all_documents(
            "names", "_default", "_default"
        )
        assert compare_doc_ids(
            local_docs.get("_default._default") or [], remote_docs.rows
        ).success, "Local database and SG2 should have the same docs"

        self.mark_test_step("""
            Update documents in the local database.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default", "name_201", [{"name.last": "Spring"}]
            )
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.delete_document("_default._default", "name_2")

        self.mark_test_step("""
            Update documents on SG2.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)

        # Add 1 docs to SG2
        await cblpytest.sync_gateways[1].update_documents(
            "names",
            [DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"})],
            "_default",
            "_default",
        )

        # Update and delete specific docs in SG2
        names_all_docs = await cblpytest.sync_gateways[1].get_all_documents(
            "names", "_default", "_default"
        )

        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                await cblpytest.sync_gateways[1].update_documents(
                    "names",
                    [DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"})],
                    "_default",
                    "_default",
                )
            elif doc.id == "name_102":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[1].delete_document(
                    doc.id, revid, "names", "_default", "_default"
                )

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Wait 5 secs to ensure that the docs are sync between two SGs."
        )
        time.sleep(5)

        self.mark_test_step(
            "Check that all updated docs are replicated correctly at SG1."
        )
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
            ["name_201", "name_1", "name_2", "name_301", "name_101", "name_102"],
        )

        self.mark_test_step(
            "Check that all updated docs are replicated correctly at SG2."
        )
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[1],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
            ["name_201", "name_1", "name_2", "name_301", "name_101", "name_102"],
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_fail_over(self, cblpytest: CBLPyTest, dataset_path: Path):
        await self.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.0.0")

        self.mark_test_step("Prepare clusters and start XDCR.")
        await self.setup_xdcr_clusters(cblpytest, dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator to SG1 via load balancer: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: false
            """)
        repl_url = cblpytest.sync_gateways[0].replication_url(
            "names", cblpytest.load_balancers[0]
        )
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Wait 5 secs to ensure that the docs are sync between two SGs."
        )
        time.sleep(5)

        self.mark_test_step("Check that all docs are replicated correctly at SG1.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            bucket="names",
            collections=["_default._default"],
        )

        self.mark_test_step("Check that all docs are replicated correctly at SG2.")
        # Local docs from the 3.2 dataset use rev-trees, while SG2 docs replicated
        # via XDCR use version vectors, so their revids are not comparable.
        local_docs = await db.get_all_documents("_default._default")
        remote_docs = await cblpytest.sync_gateways[1].get_all_documents(
            "names", "_default", "_default"
        )
        assert compare_doc_ids(
            local_docs.get("_default._default") or [], remote_docs.rows
        ).success, "Local database and SG2 should have the same docs"

        self.mark_test_step("""
            Update documents in the local database.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default", "name_201", [{"name.last": "Spring"}]
            )
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.delete_document("_default._default", "name_2")

        self.mark_test_step("""
            Update documents on SG2.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        # Add 1 docs to SG2
        await cblpytest.sync_gateways[1].update_documents(
            "names",
            [DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"})],
            "_default",
            "_default",
        )

        # Update and delete specific docs in SG2
        names_all_docs = await cblpytest.sync_gateways[1].get_all_documents(
            "names", "_default", "_default"
        )

        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                await cblpytest.sync_gateways[1].update_documents(
                    "names",
                    [DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"})],
                    "_default",
                    "_default",
                )
            elif doc.id == "name_102":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[1].delete_document(
                    doc.id, revid, "names", "_default", "_default"
                )

        self.mark_test_step(
            "Start the replicator with header X-Backend=sg-1 to tell the load balancer to switch to SG2."
        )
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            headers={"X-Backend": "sg-1"},
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that all updated docs are replicated correctly at SG2."
        )
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[1],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
            ["name_201", "name_1", "name_2", "name_301", "name_101", "name_102"],
        )

        await cblpytest.test_servers[0].cleanup()
