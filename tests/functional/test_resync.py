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
