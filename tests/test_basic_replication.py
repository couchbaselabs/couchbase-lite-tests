from pathlib import Path
from typing import List
import pytest
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.error_types import ErrorDomain
from cbltest.api.test_functions import compare_local_and_remote

class TestBasicReplication:
    @pytest.mark.asyncio
    async def test_replicate_non_existing_sg_collections(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `names` dataset
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        # 2. Reset local database, and load `travel` dataset
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        # 3. Start a replicator
        #   * collections : `travel.airlines`
        #   * endpoint: `/names`
        #   * type: push
        #   * continuous: false
        #   * credentials: user1/pass
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        
        # 5. Check that the replicator's error is CBL/10404
        assert status.error is not None \
            and status.error.code == 10404 \
            and ErrorDomain.equal(status.error.domain, ErrorDomain.CBL)

    @pytest.mark.asyncio
    async def test_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
            * endpoint: `/travel`
            * type: push
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["travel.airlines", "travel.airports", "travel.hotels"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "travel", 
                                 ["travel.airlines", "travel.airports", "travel.hotels"])

    @pytest.mark.asyncio
    async def test_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
            * endpoint: `/travel`
            * type: pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["travel.routes", "travel.landmarks", "travel.hotels"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        # 4. Wait until the replicator is stopped.
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "travel", 
                                 ["travel.routes", "travel.landmarks", "travel.hotels"])

    @pytest.mark.asyncio
    async def test_push_and_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
            * endpoint: `/travel`
            * type: push-and-pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH_AND_PULL, collections=[
            ReplicatorCollectionEntry(["travel.airlines", "travel.airports", "travel.hotels", "travel.landmarks", "travel.routes"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

        # 4. Wait until the replicator is stopped.
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel", 
                                 ["travel.airlines", "travel.airports", "travel.hotels", "travel.landmarks", "travel.routes"])