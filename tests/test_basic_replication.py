from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.syncgateway import PutDatabasePayload
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator

class TestBasicReplication:
    @pytest.mark.asyncio
    async def test_replicate_non_existing_sg_collections(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is not None and status.error.code == 10404
        return None

    @pytest.mark.asyncio
    async def test_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airlines")
        lite_all_docs = await db.get_all_documents("travel.airlines")
        assert len(sg_all_docs) == len(lite_all_docs.collections[0].documents)
        sg_ids = set(lite_all_docs.collections[0].documents)
        lite_ids = set(lite_all_docs.collections[0].documents)
        for id in sg_ids:
            assert id in lite_ids

        # TODO: Need document listener API for steps 6-8

        async with db.batch_updater() as b:
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")
            b.upsert_document("travel.airports", "test_airport_1", [{"name": "Bob"}])
            b.upsert_document("travel.airports", "test_airport_2", [{"name": "Bill"}])
            b.upsert_document("travel.airlines", "airline_1", removed_properties=["country"])
            b.upsert_document("travel.airlines", "airline_2", removed_properties=["country"])

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines", "travel.hotels", "travel.airports"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        return None

    @pytest.mark.asyncio
    async def test_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["travel.airports"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airports")
        lite_all_docs = await db.get_all_documents("travel.airports")
        assert len(lite_all_docs.collections[0].documents) > 0
        assert len(sg_all_docs) == len(lite_all_docs.collections[0].documents)
        sg_ids = set(lite_all_docs.collections[0].documents)
        lite_ids = set(lite_all_docs.collections[0].documents)
        for id in sg_ids:
            assert id in lite_ids