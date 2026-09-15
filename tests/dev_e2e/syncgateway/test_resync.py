import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    IndexConfig,
    ScopeConfig,
    SyncGateway,
)
from cbltest.api.syncgatewaycluster import SyncGatewayCluster

SCOPE_NAME = "scope1"
COLLECTION_NAME = "col1"

SYNC_FUNCTION = 'function(doc){channel("ABC");}'

# otto has no sleep, so the delay spins on Date.now(), timed in ms to hold on a faster machine.
SLOW_SYNC_FUNCTION_MS = 100
SLOW_SYNC_FUNCTION = (
    f'function(doc){{var end=Date.now()+{SLOW_SYNC_FUNCTION_MS}; while (Date.now()<end){{}} channel("ABC"); }}'
)


@pytest.mark.min_sync_gateways(1)
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
        and configures db_name backed by it, across every configured Sync Gateway
        node. Returns the Sync Gateway cluster.
        """
        cluster = cblpytest.clusters[0]
        db_config = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={SCOPE_NAME: ScopeConfig(collections={COLLECTION_NAME: {}})},
        )
        await cluster.create_database(db_name, db_config)
        return cluster.sync_gateway_cluster

    async def _load_documents(
        self,
        sg: SyncGateway,
        db_name: str,
        num_docs: int,
    ) -> None:
        """Writes documents to scope1.col1."""
        await sg.update_documents(
            db_name,
            [DocumentUpdateEntry(f"doc_{i}", None, {"foo": "bar"}) for i in range(num_docs)],
            scope=SCOPE_NAME,
            collection=COLLECTION_NAME,
        )

    async def _load_and_offline_for_resync(
        self,
        cblpytest: CBLPyTest,
        bucket_name: str,
        db_name: str,
        num_docs: int,
    ) -> SyncGatewayCluster:
        """Loads documents and prepares the database offline for resync."""
        sg_cluster = await self._initialize_database(cblpytest, bucket_name=bucket_name, db_name=db_name)

        await self._load_documents(sg_cluster.round_robin_node, db_name, num_docs)

        await sg_cluster.take_database_offline(
            db_name,
            sync_function=SLOW_SYNC_FUNCTION,
            scope=SCOPE_NAME,
            collection=COLLECTION_NAME,
        )
        return sg_cluster

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "change_sync_function",
        [True, False],
        ids=["changed_sync_function", "unchanged_sync_function"],
    )
    async def test_resync_simple(self, cblpytest: CBLPyTest, *, change_sync_function: bool) -> None:
        SIMPLE_RESYNC_NUM_DOCS = 10
        suffix = "changed" if change_sync_function else "unchanged"
        bucket_name = f"resync-simple-bucket-{suffix}"
        db_name = f"resync_simple_db_{suffix}"

        self.mark_test_step(
            f"Create bucket '{bucket_name}' backed database '{db_name}' using a "
            f"{SCOPE_NAME}.{COLLECTION_NAME} collection, and load {SIMPLE_RESYNC_NUM_DOCS} documents."
        )
        sg_cluster = await self._initialize_database(cblpytest, bucket_name=bucket_name, db_name=db_name)
        await self._load_documents(sg_cluster.round_robin_node, db_name, SIMPLE_RESYNC_NUM_DOCS)

        sync_function = SYNC_FUNCTION if change_sync_function else None

        self.mark_test_step(
            f"Take database '{db_name}' offline"
            + (", updating its sync function in the same write." if change_sync_function else ".")
        )
        await sg_cluster.take_database_offline(
            db_name,
            sync_function=sync_function,
            scope=SCOPE_NAME,
            collection=COLLECTION_NAME,
        )

        # Resync status is node-local until CBG-5817, so every call goes to the same node.
        resync_node = sg_cluster.round_robin_node

        self.mark_test_step(f"Start a resync operation on database '{db_name}', discarding previous progress.")
        await resync_node.start_resync(db_name, reset=True)

        self.mark_test_step(f"Wait until the resync operation on database '{db_name}' completes.")
        final_status = await resync_node.wait_for_resync_completed(db_name)

        self.mark_test_step(f"Check that the resync for database '{db_name}' processed all documents with no errors.")
        assert final_status.docs_errored == 0
        assert final_status.docs_processed >= SIMPLE_RESYNC_NUM_DOCS

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.min_sync_gateways(1)
    async def test_resync_stop_resume(self, cblpytest: CBLPyTest) -> None:
        # Enough to outlast the ~20s before a stop takes effect, while still fitting in one
        # _bulk_docs within the client timeout.
        num_docs = 5000
        bucket_name = "resync-stop-resume-bucket"
        db_name = "resync_stop_resume_db"

        self.mark_test_step(
            f"Create bucket '{bucket_name}' backed database '{db_name}' using a "
            f"{SCOPE_NAME}.{COLLECTION_NAME} collection, load documents, update the sync function, "
            f"and take the database offline."
        )
        sg_cluster = await self._load_and_offline_for_resync(cblpytest, bucket_name, db_name, num_docs)

        # Resync status is node-local until CBG-5817, so every call goes to the same node.
        resync_node = sg_cluster.round_robin_node

        self.mark_test_step(f"Start a resync operation on database '{db_name}', discarding previous progress.")
        await resync_node.start_resync(db_name, reset=True)

        self.mark_test_step(f"Check that the resync status is 'running' for database '{db_name}'.")
        try:
            await resync_node.wait_for_resync_running(db_name)
        except TimeoutError:
            status = await resync_node.get_resync_status(db_name)
            if status.status.value == "completed":
                pytest.skip(f"Resync on '{db_name}' finished before it was seen running, so there is nothing to stop")
            raise

        self.mark_test_step(f"Stop the resync operation on database '{db_name}'.")
        await resync_node.stop_resync(db_name)

        self.mark_test_step(f"Check that the resync status is 'stopped' for database '{db_name}'.")
        stopped_status = await resync_node.wait_for_resync_stopped(db_name)

        self.mark_test_step(f"Check that the resync for database '{db_name}' has work left to resume.")
        # A stop only takes effect once the resync feed is up, by which point a small resync
        # has finished.  That leaves nothing to resume, which is a setup miss, not a failure.
        if stopped_status.docs_processed >= num_docs:
            pytest.skip(
                f"Resync processed all {stopped_status.docs_processed}/{num_docs} documents before the "
                f"stop took effect, so there is no partial resync to resume"
            )

        self.mark_test_step(f"Resume the resync operation on database '{db_name}', without resetting it.")
        await resync_node.start_resync(db_name)

        self.mark_test_step(f"Wait until the resumed resync operation on database '{db_name}' completes.")
        final_status = await resync_node.wait_for_resync_completed(db_name)

        self.mark_test_step(
            f"Check that the completed resync for database '{db_name}' actually processed every document."
        )
        # docs_processed can exceed num_docs due to DCP feed echoes, but must not be less.
        assert final_status.docs_processed >= num_docs, (
            f"Resync reported 'completed' after processing only {final_status.docs_processed}/{num_docs} documents"
        )
