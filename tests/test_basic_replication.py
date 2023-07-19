from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.syncgateway import PutDatabasePayload
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator

class TestBasicReplication:
    @pytest.mark.asyncio
    async def test_replicate_non_existing_sg_collections(self, cblpytest: CBLPyTest, dataset_path: Path):
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        sg_payload = PutDatabasePayload("names")
        sg_payload.add_collection()
        await cloud.put_empty_database("names", sg_payload, "names")
        await cblpytest.sync_gateways[0].load_dataset("names", dataset_path / "names-sg.json")
        await cblpytest.sync_gateways[0].add_user("names", "user1", "pass", {
            "_default._default": ["*"]
        })

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry("travel.airlines")
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error.code == 404

    @pytest.mark.asyncio
    async def test_push(self, cblpytest: CBLPyTest):
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        sg_payload = PutDatabasePayload("travel")
        sg_payload.add_collection("travel", "airlines")
        sg_payload.add_collection("travel", "airports")
        sg_payload.add_collection("travel", "hotels")
        await cloud.put_empty_database("travel", sg_payload, "travel")
        await cblpytest.sync_gateways[0].add_user("travel", "user1", "pass", {
            "travel.airlines": ["*"],
            "travel.airports": ["*"],
            "travel.hotels": ["*"]
        })

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry("travel.airlines")
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airlines")
        lite_all_docs = await db.get_all_documents("travel.airlines")
        assert len(sg_all_docs) == len(lite_all_docs.collections[0].document_ids)
        sg_ids = set(lite_all_docs.collections[0].document_ids)
        lite_ids = set(lite_all_docs.collections[0].document_ids)
        for id in sg_ids:
            assert id in lite_ids

        # TODO: Need document listener API for steps 6-8

        async with db.batch_updater() as b:
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")
            b.upsert_document("travel.airports", "test_airport_1", {"name": "Bob"})
            b.upsert_document("travel.airports", "test_airport_2", {"name": "Bill"})
            b.upsert_document("travel.airlines", "airline_1", removed_properties=["country"])
            b.upsert_document("travel.airlines", "airline_2", removed_properties=["country"])

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry("travel.airlines"),
            ReplicatorCollectionEntry("travel.hotels"),
            ReplicatorCollectionEntry("travel.airports")
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

    @pytest.mark.asyncio
    async def test_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        sg_payload = PutDatabasePayload("travel")
        sg_payload.add_collection("travel", "landmarks")
        sg_payload.add_collection("travel", "airports")
        sg_payload.add_collection("travel", "hotels")
        await cloud.put_empty_database("travel", sg_payload, "travel")
        await cblpytest.sync_gateways[0].add_user("travel", "user1", "pass", {
            "travel.airports": ["*"]
        })
        await cblpytest.sync_gateways[0].load_dataset("travel", dataset_path / "travel-sg.json")

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry("travel.airports")
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airports")
        lite_all_docs = await db.get_all_documents("travel.airports")
        assert len(lite_all_docs.collections[0].document_ids) > 0
        assert len(sg_all_docs) == len(lite_all_docs.collections[0].document_ids)
        sg_ids = set(lite_all_docs.collections[0].document_ids)
        lite_ids = set(lite_all_docs.collections[0].document_ids)
        for id in sg_ids:
            assert id in lite_ids