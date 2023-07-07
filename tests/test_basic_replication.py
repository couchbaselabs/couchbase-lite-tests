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