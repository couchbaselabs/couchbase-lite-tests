from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import wait_for_converging_cvs, wait_for_matching_cvs
from cbltest.api.testserver import CouchbaseLiteFeature


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(2)
@pytest.mark.min_clusters(2)
@pytest.mark.min_load_balancers(1)
class TestReplicationXdcr(CBLTestClass):
    async def setup_xdcr_clusters(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        dataset_name: str,
    ) -> None:
        """
        Prepare two Couchbase clusters for XDCR testing:
        - Stop any existing XDCR replications.
        - Reset Sync Gateways and load the dataset on each cluster.
        - Start bidirectional XDCR.
        """
        self.mark_test_step("If XDCR between cluster 1 and cluster 2 is active, stop it.")
        await (
            cblpytest.clusters[0]
            .couchbase_servers[0]
            .stop_xcdr(cblpytest.clusters[1].couchbase_servers[0], dataset_name)
        )
        await (
            cblpytest.clusters[1]
            .couchbase_servers[0]
            .stop_xcdr(cblpytest.clusters[0].couchbase_servers[0], dataset_name)
        )

        self.mark_test_step("Reset SGs in cluster 1 and 2, and load dataset.")

        await cblpytest.clusters[0].configure_dataset(dataset_path, dataset_name)
        await cblpytest.clusters[1].configure_dataset(dataset_path, dataset_name)

        self.mark_test_step("Start XDCR between cluster 1 and cluster 2.")
        await (
            cblpytest.clusters[0]
            .couchbase_servers[0]
            .start_xdcr(cblpytest.clusters[1].couchbase_servers[0], dataset_name)
        )
        await (
            cblpytest.clusters[1]
            .couchbase_servers[0]
            .start_xdcr(cblpytest.clusters[0].couchbase_servers[0], dataset_name)
        )

        self.mark_test_step("Wait until both SGs have the same CV for every doc, through XDCR.")
        await wait_for_converging_cvs(
            cblpytest.clusters[0].sync_gateways[0], cblpytest.clusters[1].sync_gateways[0], dataset_name
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_and_pull_with_xdcr(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_supports(
            cblpytest.test_servers[0],
            CouchbaseLiteFeature.VERSION_VECTORS,
            CouchbaseLiteFeature.CUSTOM_REPLICATOR_HEADERS,
        )

        self.mark_test_step("Prepare clusters and start XDCR.")
        await self.setup_xdcr_clusters(cblpytest, dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("""
            Put SG1 and SG2 behind the load balancer, and start a replicator pinned to SG1:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: true
            """)
        lb = cblpytest.load_balancers[0]
        sg1, sg2 = cblpytest.clusters[0].sync_gateways[0], cblpytest.clusters[1].sync_gateways[0]
        await lb.configure([sg1, sg2])
        repl_url = lb.replication_url("names")
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            headers=lb.pin(sg1),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Wait until both SGs have the same CV for every doc, through XDCR.")
        await wait_for_converging_cvs(sg1, sg2, "names")

        self.mark_test_step("Check that the local database has the same CV as SG1 for every doc.")
        await wait_for_matching_cvs(db, sg1, "names")

        self.mark_test_step("""
            Update documents in the local database.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_201", [{"name.last": "Spring"}])
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.delete_document("_default._default", "name_2")

        self.mark_test_step("""
            Update documents on SG2.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)

        # Add 1 docs to SG2
        await (
            cblpytest.clusters[1]
            .sync_gateways[0]
            .update_documents(
                "names",
                [DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"})],
                "_default",
                "_default",
            )
        )

        # Update and delete specific docs in SG2
        names_all_docs = await cblpytest.clusters[1].sync_gateways[0].get_all_documents("names", "_default", "_default")

        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                await (
                    cblpytest.clusters[1]
                    .sync_gateways[0]
                    .update_documents(
                        "names",
                        [DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"})],
                        "_default",
                        "_default",
                    )
                )
            elif doc.id == "name_102":
                await (
                    cblpytest.clusters[1]
                    .sync_gateways[0]
                    .delete_document(doc.id, doc.revid, "names", "_default", "_default")
                )

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Wait until both SGs have the same CV for every doc, through XDCR.")
        await wait_for_converging_cvs(sg1, sg2, "names")

        self.mark_test_step(
            "Check that the local database has the same CV as SG1 for every doc, including the updates."
        )
        await wait_for_matching_cvs(db, sg1, "names")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_fail_over(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_supports(
            cblpytest.test_servers[0],
            CouchbaseLiteFeature.VERSION_VECTORS,
            CouchbaseLiteFeature.CUSTOM_REPLICATOR_HEADERS,
        )

        self.mark_test_step("Prepare clusters and start XDCR.")
        await self.setup_xdcr_clusters(cblpytest, dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("""
            Put SG1 and SG2 behind the load balancer, and start a replicator pinned to SG1:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push_and_pull
                * continuous: false
            """)
        lb = cblpytest.load_balancers[0]
        sg1, sg2 = cblpytest.clusters[0].sync_gateways[0], cblpytest.clusters[1].sync_gateways[0]
        await lb.configure([sg1, sg2])
        repl_url = lb.replication_url("names")
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            headers=lb.pin(sg1),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Wait until both SGs have the same CV for every doc, through XDCR.")
        await wait_for_converging_cvs(sg1, sg2, "names")

        self.mark_test_step("Check that the local database has the same CV as SG1 for every doc.")
        await wait_for_matching_cvs(db, sg1, "names")

        self.mark_test_step("""
            Update documents in the local database.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_201", [{"name.last": "Spring"}])
            b.upsert_document("_default._default", "name_1", [{"name.last": "Winter"}])
            b.delete_document("_default._default", "name_2")

        self.mark_test_step("""
            Update documents on SG2.
                * Add 1 docs in default collection.
                * Update 1 docs in default collection.
                * Remove 1 docs in default collection.
            """)
        # Add 1 docs to SG2
        await (
            cblpytest.clusters[1]
            .sync_gateways[0]
            .update_documents(
                "names",
                [DocumentUpdateEntry("name_301", None, body={"name.last": "Snow"})],
                "_default",
                "_default",
            )
        )

        # Update and delete specific docs in SG2
        names_all_docs = await cblpytest.clusters[1].sync_gateways[0].get_all_documents("names", "_default", "_default")

        for doc in names_all_docs.rows:
            if doc.id == "name_101":
                await (
                    cblpytest.clusters[1]
                    .sync_gateways[0]
                    .update_documents(
                        "names",
                        [DocumentUpdateEntry(doc.id, doc.revid, {"name.last": "Cloud"})],
                        "_default",
                        "_default",
                    )
                )
            elif doc.id == "name_102":
                await (
                    cblpytest.clusters[1]
                    .sync_gateways[0]
                    .delete_document(doc.id, doc.revid, "names", "_default", "_default")
                )

        self.mark_test_step("Start the replicator pinned to SG2, to switch the load balancer to SG2.")
        replicator = Replicator(
            db,
            repl_url,
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=False,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            headers=lb.pin(sg2),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that the local database has the same CV as SG2 for every doc, including the updates."
        )
        await wait_for_matching_cvs(db, sg2, "names")

        await cblpytest.test_servers[0].cleanup()
