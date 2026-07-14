import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import (
    DocumentUpdateEntry,
    PutDatabasePayload,
    ResyncAction,
    ResyncState,
    SyncGateway,
)
from cbltest.api.syncgatewaycluster import SyncGatewayCluster

SCOPE_NAME = "scope1"
COLLECTION_NAME = "col1"
SIMPLE_RESYNC_NUM_DOCS = 10
DEFAULT_NUM_DOCS = 20000
# Batch size to keep bulk requests under client request timeout.
LOAD_BATCH_SIZE = 20000
# Ensure resync is still running when stopped (rate varies widely with machine load).
STOP_RESYNC_NUM_DOCS = 400000


class TestSyncGatewayResync(CBLTestClass):
    async def _initialize_database(
        self,
        cblpytest: CBLPyTest,
        *,
        bucket_name: str,
        db_name: str,
    ) -> SyncGatewayCluster:
        """
        Creates bucket_name with scope1.col1 collection (skipped under rosmar)
        and configures db_name backed by it. Returns the Sync Gateway cluster.
        """
        sg_cluster = SyncGatewayCluster(cblpytest.sync_gateways)
        if not sg_cluster.sync_gateways[0].using_rosmar:
            cbs = cblpytest.couchbase_servers[0]
            cbs.create_bucket(bucket_name)
            cbs.create_collections(bucket_name, SCOPE_NAME, [COLLECTION_NAME])

        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {SCOPE_NAME: {"collections": {COLLECTION_NAME: {}}}},
        }
        await sg_cluster.round_robin_node.put_database(
            db_name, PutDatabasePayload(db_config)
        )
        return sg_cluster

    async def _load_documents(
        self,
        sg: SyncGateway,
        db_name: str,
        num_docs: int,
    ) -> None:
        """Writes documents to scope1.col1 in batches to prevent client timeouts."""
        for batch_start in range(0, num_docs, LOAD_BATCH_SIZE):
            batch_end = min(batch_start + LOAD_BATCH_SIZE, num_docs)
            await sg.update_documents(
                db_name,
                [
                    DocumentUpdateEntry(f"doc_{i}", None, {"foo": "bar"})
                    for i in range(batch_start, batch_end)
                ],
                scope=SCOPE_NAME,
                collection=COLLECTION_NAME,
            )

    async def _load_and_offline_for_resync(
        self,
        cblpytest: CBLPyTest,
        bucket_name: str,
        db_name: str,
        num_docs: int = DEFAULT_NUM_DOCS,
    ) -> SyncGatewayCluster:
        """Loads documents and prepares the database offline for resync."""
        sg_cluster = await self._initialize_database(
            cblpytest, bucket_name=bucket_name, db_name=db_name
        )
        sg = sg_cluster.round_robin_node
        await sg_cluster.wait_for_db_online(db_name)

        await self._load_documents(sg, db_name, num_docs)

        await sg_cluster.take_database_offline(db_name)
        await sg_cluster.update_sync_function(
            db_name,
            'function(doc){channel("ABC");}',
            scope=SCOPE_NAME,
            collection=COLLECTION_NAME,
        )
        return sg_cluster

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.min_sync_gateways(1)
    @pytest.mark.parametrize(
        "change_sync_function",
        [True, False],
        ids=["changed_sync_function", "unchanged_sync_function"],
    )
    async def test_resync_simple(
        self, cblpytest: CBLPyTest, *, change_sync_function: bool
    ) -> None:
        suffix = "changed" if change_sync_function else "unchanged"
        bucket_name = f"resync-simple-bucket-{suffix}"
        db_name = f"resync_simple_db_{suffix}"

        self.mark_test_step(
            f"Create bucket '{bucket_name}' backed database '{db_name}' using a "
            f"{SCOPE_NAME}.{COLLECTION_NAME} collection, and load {SIMPLE_RESYNC_NUM_DOCS} documents."
        )
        sg_cluster = await self._initialize_database(
            cblpytest, bucket_name=bucket_name, db_name=db_name
        )
        await self._load_documents(
            sg_cluster.round_robin_node, db_name, SIMPLE_RESYNC_NUM_DOCS
        )

        if change_sync_function:
            self.mark_test_step(f"Update the sync function for database '{db_name}'.")
            await sg_cluster.round_robin_node.update_sync_function(
                db_name,
                'function(doc){channel("ABC");}',
                scope=SCOPE_NAME,
                collection=COLLECTION_NAME,
            )

        self.mark_test_step(f"Take database '{db_name}' offline.")
        await sg_cluster.take_database_offline(db_name)

        self.mark_test_step(f"Start a resync operation on database '{db_name}'.")
        await sg_cluster.round_robin_node.put_resync(
            db_name, action=ResyncAction.START, reset=True
        )

        self.mark_test_step(
            f"Wait until the resync operation on database '{db_name}' completes."
        )
        final_status = await sg_cluster.round_robin_node.wait_for_resync_completed(
            db_name
        )

        self.mark_test_step(
            f"Check that the resync for database '{db_name}' processed all "
            f"documents with no errors."
        )
        assert final_status.docs_errored == 0
        assert final_status.docs_processed >= SIMPLE_RESYNC_NUM_DOCS

    @pytest.mark.asyncio(loop_scope="session")
    async def test_resync_stop_resume(self, cblpytest: CBLPyTest) -> None:
        bucket_name = "resync-stop-resume-bucket"
        db_name = "resync_stop_resume_db"
        num_docs = STOP_RESYNC_NUM_DOCS

        self.mark_test_step(
            f"Create bucket '{bucket_name}' backed database '{db_name}' using a "
            f"{SCOPE_NAME}.{COLLECTION_NAME} collection, load documents, update the sync function, "
            f"and take the database offline."
        )
        sg_cluster = await self._load_and_offline_for_resync(
            cblpytest, bucket_name, db_name, num_docs
        )

        self.mark_test_step(f"Start a resync operation on database '{db_name}'.")
        await sg_cluster.round_robin_node.put_resync(
            db_name, action=ResyncAction.START, reset=True
        )

        self.mark_test_step(
            f"Check that the resync status is 'running' for database '{db_name}'."
        )
        # Wait for all nodes to converge on 'running' before stopping.
        await sg_cluster.wait_for_resync_state(db_name, ResyncState.RUNNING)

        self.mark_test_step(f"Stop the resync operation on database '{db_name}'.")
        await sg_cluster.round_robin_node.put_resync(db_name, action=ResyncAction.STOP)

        self.mark_test_step(
            f"Check that the resync status is 'stopped' for database '{db_name}', "
            f"and that it stopped before processing every document."
        )
        stopped_status = await sg_cluster.round_robin_node.wait_for_resync_stopped(
            db_name
        )
        assert stopped_status.status == ResyncState.STOPPED
        assert stopped_status.docs_processed < num_docs, (
            f"Expected resync to still be running when stopped, but it already processed "
            f"all {stopped_status.docs_processed}/{num_docs} documents."
        )

        self.mark_test_step(
            f"Resume the resync operation on database '{db_name}', without "
            f"resetting it."
        )
        await sg_cluster.round_robin_node.put_resync(db_name, action=ResyncAction.START)

        self.mark_test_step(
            f"Wait until the resumed resync operation on database '{db_name}' "
            f"completes."
        )
        final_status = await sg_cluster.round_robin_node.wait_for_resync_completed(
            db_name
        )

        self.mark_test_step(
            f"Check that the completed resync for database '{db_name}' actually "
            f"processed every document."
        )
        # docs_processed can exceed num_docs due to DCP feed echoes, but must not be less.
        assert final_status.docs_processed >= num_docs, (
            f"Resync reported 'completed' after processing only "
            f"{final_status.docs_processed}/{num_docs} documents"
        )
