from pathlib import Path
from typing import List, Set
from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (ReplicatorCollectionEntry, ReplicatorBasicAuthenticator, ReplicatorType, 
                                          ReplicatorActivityLevel, ReplicatorDocumentEntry, ReplicatorFilter)
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.cloud import CouchbaseCloud

from test_replication_filter_data import *
import pytest



class TestReplicationFilter:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    def validate_replicated_doc_ids(self, expected: Set[str], actual: List[ReplicatorDocumentEntry]) -> None:
        for update in actual:
            assert update.document_id in expected, f"Unexpected document update not in filter: {update.document_id}"
            expected.remove(update.document_id)

        assert len(expected) == 0, f"Not all document updates were found (e.g. {next(iter(expected))})"

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
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)
        
        '''
        6.
        Update docs in the local database
            * Add `airline_1000` in `travel.airlines`
            * Update `airline_10` in `travel.airlines`
            * Remove `route_10` in `travel.routes`
        '''
        async with db.batch_updater() as b:
            b.upsert_document("travel.airlines", "airline_1000", [{"new_doc": True}])
            b.upsert_document("travel.airlines", "airline_10", [{"new_doc": False}])
            b.delete_document("travel.routes", "route_10")

        # 7. Start the replicator with the same config as the step 3.
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        # 8. Check that only changes for docs in the specified documentIDs filters are replicated.
        expected_ids = { "airline_1000", "airline_10", "route_10"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)


    @pytest.mark.asyncio
    async def test_pull_document_ids_filter(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : 
            * `travel.airports`
                * documentIDs : `airport_10`, `airport_20`, `airport_1000`
            * `travel.landmarks`
                * documentIDs : `landmark_10`, `landmark_20`
            * endpoint: `/travel`
            * type: pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["travel.airports"], document_ids=["airport_10", "airport_20", "airport_1000"]),
            ReplicatorCollectionEntry(["travel.landmarks"], document_ids=["landmark_10", "landmark_20"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), enable_document_listener=True)
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that only docs specified in the documentIDs filters are replicated except `travel.airline`.`airline_1000`
        expected_ids = {"airport_10", "airport_20", "landmark_10", "landmark_20"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        '''
        6. Update docs on SG
            * Add `airport_1000` in `travel.airports`
            * Update `airport_10` in `travel.airports`
            * Remove `landmark_10`, in `travel.landmarks`
        '''
        remote_airport_10 = await cblpytest.sync_gateways[0].get_document("travel", "airport_10", "travel", "airports")
        assert remote_airport_10 is not None, "Missing airport_10 from sync gateway"

        remote_landmark_10 = await cblpytest.sync_gateways[0].get_document("travel", "landmark_10", "travel", "landmarks")
        assert remote_landmark_10 is not None, "Missing landmark_10 from sync gateway"
        
        updates = [
            DocumentUpdateEntry("airport_1000", None, {"answer": 42}),
            DocumentUpdateEntry("airport_10", remote_airport_10.revid, {"answer": 42})
        ]
        await cblpytest.sync_gateways[0].update_documents("travel", updates, "travel", "airports")
        await cblpytest.sync_gateways[0].delete_document("landmark_10", remote_landmark_10.revid, "travel", "travel", "landmarks")

        # 7. Start the replicator with the same config as the step 3.
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        # 8. Check that only changes for docs in the specified documentIDs filters are replicated.
        expected_ids = { "airport_1000", "airport_10", "landmark_10"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

    @pytest.mark.asyncio
    async def test_pull_channels_filter(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : 
            * `travel.airports`
                * channels : `United Kingdom`, `France`
            * `travel.landmarks`
                * channels : `France`
            * endpoint: `/travel
            * type: pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["travel.airports"], channels=["United Kingdom", "France"]),
            ReplicatorCollectionEntry(["travel.landmarks"], channels=["France"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), enable_document_listener=True)
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that only docs in the filtered channels are pulled.
        expected_ids = uk_and_france_doc_ids
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        '''
        6. Update docs on SG
            * Add `airport_1000` with channels = ["United Kingdom"], `airport_2000` with channels = ["France"] 
                and `airport_3000` with channels = ["United States"] in `travel.airports`
            * Update `airport_11` with channels = ["United States"], `airport_1` with channels = ["France"], 
                `airport_17` with channels = ["United States"] in `travel.airports`
            * Remove `landmark_1` channels = ["United Kingdom"], `landmark_2001` channels = ["France"] in `travel.landmarks`
        '''
        remote_airport_11 = await cblpytest.sync_gateways[0].get_document("travel", "airport_11", "travel", "airports")
        assert remote_airport_11 is not None, "Missing airport_11 from sync gateway"

        remote_airport_1 = await cblpytest.sync_gateways[0].get_document("travel", "airport_1", "travel", "airports")
        assert remote_airport_1 is not None, "Missing airport_1 from sync gateway"

        remote_airport_17 = await cblpytest.sync_gateways[0].get_document("travel", "airport_17", "travel", "airports")
        assert remote_airport_17 is not None, "Missing airport_17 from sync gateway"

        remote_landmark_1 = await cblpytest.sync_gateways[0].get_document("travel", "landmark_1", "travel", "landmarks")
        assert remote_landmark_1 is not None, "Missing landmark_1 from sync gateway"

        remote_landmark_2001 = await cblpytest.sync_gateways[0].get_document("travel", "landmark_2001", "travel", "landmarks")
        assert remote_landmark_2001 is not None, "Missing landmark_2001 from sync gateway"

        updates = [
            DocumentUpdateEntry("airport_1000", None, {"answer": 42, "channels": ["United Kingdom"]}),
            DocumentUpdateEntry("airport_2000", None, {"answer": 42, "channels": ["France"]}),
            DocumentUpdateEntry("airport_3000", None, {"answer": 42, "channels": ["United States"]}),
            DocumentUpdateEntry("airport_11", remote_airport_11.revid, {"answer": 42, "channels": ["United States"]}),
            DocumentUpdateEntry("airport_1", remote_airport_1.revid, {"answer": 42, "channels": ["France"]}),
            DocumentUpdateEntry("airport_17", remote_airport_17.revid, {"answer": 42, "channels": ["United Kingdom"]}),
        ]

        await cblpytest.sync_gateways[0].update_documents("travel", updates, "travel", "airports")
        await cblpytest.sync_gateways[0].delete_document("landmark_1", remote_landmark_1.revid, "travel", "travel", "landmarks")
        await cblpytest.sync_gateways[0].delete_document("landmark_2001", remote_landmark_2001.revid, "travel", "travel", "landmarks")

        # 7. Start the replicator with the same config as the step 3.
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 8. Check that only changes in the filtered channels are pulled.
        expected_ids = { "airport_1000", "airport_2000", "airport_1", "airport_17", "landmark_2001" }
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

    @pytest.mark.asyncio
    async def test_custom_push_filter(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `names` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * collections : 
            * `_default._default`
                * pushFilter:  
                    * name: `deletedDocumentsOnly`
                    * params: `{}`
            * endpoint: `/names`
            * type: push
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), replicator_type=ReplicatorType.PUSH, collections=[
            ReplicatorCollectionEntry(["_default._default"], push_filter=ReplicatorFilter("deletedDocumentsOnly"))
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), enable_document_listener=True)
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that no docs are replicated.
        assert len(replicator.document_updates) == 0, \
            f"{len(replicator.document_updates)} documents replicated even though they should be filtered"
        
        '''
        6. Update docs in the local database
            * Add `name_10000`
            * Remove `name_10` and `name_20`
        '''
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_10000", [{"answer": 42}])
            b.delete_document("_default._default", "name_10")
            b.delete_document("_default._default", "name_20")

        # 7. Start the replicator with the same config as the step 3.
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 8. Check that only changes passed the push filters are replicated.
        expected_ids = { "name_10", "name_20" }
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)