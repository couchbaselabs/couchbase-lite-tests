from pathlib import Path
from cbltest import CBLPyTest
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorBasicAuthenticator, ReplicatorType, ReplicatorActivityLevel
import pytest

from cbltest.api.cloud import CouchbaseCloud

class TestReplicationFilter:
    @pytest.mark.asyncio
    async def test_push_document_ids_filter(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : 
            * `travel.airlines`
                * documentIDs : `airline_10`, `airline_20`, `airline_1000`
            * `travel.routes`
                * documentIDs : `route_10`, `route_20`
            * endpoint: `/travel`
            * type: push
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines"], document_ids=["airline_10", "airline_20", "airline_1000"]),
            ReplicatorCollectionEntry(["travel.routes"], document_ids=["route_10", "route_20"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), enable_document_listener=True)
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that only docs specified in the documentIDs filters are replicated except `travel.airline`.`airline_1000`
        expected_ids = {"airline_10", "airline_20", "route_10", "route_20"}
        for update in replicator.document_updates:
            assert update.document_id in expected_ids, f"Unexpected document update not in filter: {update.document_id}"
            expected_ids.remove(update.document_id)

        assert len(expected_ids) == 0, f"Not all document updates were found (e.g. {next(iter(expected_ids))})"
