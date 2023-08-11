from pathlib import Path
from typing import List
import pytest
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, WaitForDocumentEventEntry 
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import DocumentUpdateEntry
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
        #   * endpoint: `/names`
        #   * collections : `travel.airlines`
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
            * endpoint: `/travel`
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
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
            * endpoint: `/travel`
            * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
            * type: pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PULL, collections=[
            ReplicatorCollectionEntry(["travel.routes", "travel.landmarks", "travel.hotels"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped.
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
            * endpoint: `/travel`
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
            * type: push-and-pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), replicator_type=ReplicatorType.PUSH_AND_PULL, collections=[
            ReplicatorCollectionEntry(["travel.airlines", "travel.airports", "travel.hotels", "travel.landmarks", "travel.routes"])
        ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel", 
                                 ["travel.airlines", "travel.airports", "travel.hotels", "travel.landmarks", "travel.routes"])
        
    @pytest.mark.asyncio
    async def test_continuous_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * endpoint: `/travel`
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
            * type: push
            * continuous: true
            * enableDocumentListener: true
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.airlines", 
                                                                        "travel.airports", 
                                                                        "travel.hotels"])],
                                replicator_type=ReplicatorType.PUSH, 
                                continuous=True, 
                                enable_document_listener=True,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is idle.
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
                
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "travel", 
                                        ["travel.airlines", "travel.airports", "travel.hotels"])
        
        # 6. Clear current document replication events.
        replicator.clear_document_updates()

        '''
        7. Update documents in the local database.
            * Add 2 airports in travel.airports.
            * Update 2 new airlines in travel.airlines.
            * Remove 2 hotels in travel.hotels.
        '''
        async with db.batch_updater() as b:
            b.upsert_document("travel.airports", "test_airport_1", 
                              [{"name": "Airport 1", "channels": ["United States"]}])
            b.upsert_document("travel.airports", "test_airport_2", 
                              [{"name": "Airport 2", "channels": ["United Kingdom"]}])
            b.upsert_document("travel.airlines", "airline_1", removed_properties=["country"])
            b.upsert_document("travel.airlines", "airline_2", removed_properties=["country"])
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")

        # 8. Wait until receiving all document replication events
        await replicator.wait_for_doc_events({
            WaitForDocumentEventEntry("travel.airports", "test_airport_1"),
            WaitForDocumentEventEntry("travel.airports", "test_airport_2"),
            WaitForDocumentEventEntry("travel.airlines", "airline_1"),
            WaitForDocumentEventEntry("travel.airlines", "airline_2"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_1"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_2")
        })
        
        # 9. Check that all updates are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "travel", 
                                ["travel.airlines", "travel.airports", "travel.hotels"])
        
    @pytest.mark.asyncio
    async def test_continuous_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * endpoint: `/travel`
            * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
            * type: pull
            * continuous: true
            * enableDocumentListener: true
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"),
                                collections=[ReplicatorCollectionEntry(["travel.routes", 
                                                                        "travel.landmarks", 
                                                                        "travel.hotels"])],
                                replicator_type=ReplicatorType.PULL, 
                                continuous=True, 
                                enable_document_listener=True, 
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is idle.
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "travel", 
                                        ["travel.routes", "travel.landmarks", "travel.hotels"])
        
        # 6. Clear current document replication events.
        replicator.clear_document_updates()

        '''
        7. Update documents on SG.
            * Add 2 routes in `travel.routes`.
            * Update 2 landmarks in `travel.landmarks`.
            * Remove 2 hotels in `travel.hotels`.
        '''
        # Add 2 routes in `travel.routes`
        routes_updates: List[DocumentUpdateEntry] = [] 
        routes_updates.append(DocumentUpdateEntry("test_route_1", None, body={
            "airline": "Skyline", 
            "channels": ["United States"], 
            "country": "United States", 
            "sourceairport": "SFO", 
            "destinationairport": "NRT"}))
        routes_updates.append(DocumentUpdateEntry("test_route_2", None, body={
            "airline": "Nimbus", 
            "channels": ["United States"], 
            "country": "United States", 
            "sourceairport": "SFO", 
            "destinationairport": "BKK"}))
        await cblpytest.sync_gateways[0].update_documents("travel", routes_updates, "travel", "routes")
        
        # Update 2 landmarks in `travel.landmarks`
        landmarks_updates: List[DocumentUpdateEntry] = []
        landmarks_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "landmarks")
        for doc in landmarks_all_docs.rows:
            if doc.id == "landmark_100":
                landmarks_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {
                    "name": "Wallace Creek Trail", 
                    "channels": ["United States"],
                    "content": "Wallace Creek is a creek with a twist.",
                    "city": "McKittrick", 
                    "state": "CA", 
                    "country": "United States"}))
            elif doc.id == "landmark_200":
                landmarks_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {
                    "name": "Mission San Jose and Museum", 
                    "channels": ["United States"],
                    "content": "This mission founded in 1797 by Fermin Lasuen.",
                    "city": "Fremont", 
                    "state": "CA", 
                    "country": 
                    "United States"}))
        await cblpytest.sync_gateways[0].update_documents("travel", landmarks_updates, "travel", "landmarks")

        # Remove 2 hotels in `travel.hotels`
        hotels_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "hotels")
        for doc in hotels_all_docs.rows:
            if doc.id == "hotel_400" or doc.id == "hotel_500":
                await cblpytest.sync_gateways[0].delete_document(doc.id, doc.revid, "travel", "travel", "hotels")

        # 8. Wait until receiving all document replication events
        await replicator.wait_for_doc_events({
            WaitForDocumentEventEntry("travel.routes", "test_route_1"),
            WaitForDocumentEventEntry("travel.routes", "test_route_2"),
            WaitForDocumentEventEntry("travel.landmarks", "landmark_100"),
            WaitForDocumentEventEntry("travel.landmarks", "landmark_200"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_400"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_500")
        })

        # 9. Check that all updates are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "travel", 
                                       ["travel.routes", "travel.landmarks", "travel.hotels"])
        
    @pytest.mark.asyncio
    async def test_continuous_push_and_pull(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # 2. Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator: 
            * endpoint: `/travel`
            * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
            * type: push-and-pull
            * continuous: false
            * enableDocumentListener: true
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.airlines", 
                                                                        "travel.airports", 
                                                                        "travel.hotels", 
                                                                        "travel.landmarks", 
                                                                        "travel.routes"])], 
                                replicator_type=ReplicatorType.PUSH_AND_PULL, 
                                continuous=True, 
                                enable_document_listener=True, 
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is idle.
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
                
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel", 
                                       ["travel.airlines", "travel.airports", "travel.hotels", 
                                        "travel.landmarks", "travel.routes"])
        
        # 6. Clear current document replication events.
        replicator.clear_document_updates()

        '''
        7. Update documents in the local database.
            * Add 2 airports in travel.airports.
            * Update 2 new airlines in travel.airlines.
            * Remove 2 hotels in travel.hotels.
        '''
        async with db.batch_updater() as b:
            b.upsert_document("travel.airports", "test_airport_1", [{"name": "AirPort1", "channels": ["United States"]}])
            b.upsert_document("travel.airports", "test_airport_2", [{"name": "AirPort2", "channels": ["United Kingdom"]}])
            b.upsert_document("travel.airlines", "airline_1", removed_properties=["country"])
            b.upsert_document("travel.airlines", "airline_2", removed_properties=["country"])
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")
        
        '''
        8. Update documents on SG.
            * Add 2 routes in `travel.routes`.
            * Update 2 landmarks in `travel.landmarks`.
            * Remove 2 hotels in `travel.hotels`.
        '''
        # Add 2 routes in `travel.routes`
        routes_updates: List[DocumentUpdateEntry] = []
        routes_updates.append(DocumentUpdateEntry("test_route_1", None, body={
            "airline": "Skyline",
            "channels": ["United States"],
            "country": "United States",
            "sourceairport": "SFO",
            "destinationairport": "NRT"
        }))
        routes_updates.append(DocumentUpdateEntry("test_route_2", None, body={
            "airline": "Nimbus", 
            "channels": ["United States"], 
            "country": "United States", 
            "sourceairport": "SFO", 
            "destinationairport": "BKK"}))
        await cblpytest.sync_gateways[0].update_documents("travel", routes_updates, "travel", "routes")
        
        # Update 2 landmarks in `travel.landmarks`
        landmarks_updates: List[DocumentUpdateEntry] = []
        landmarks_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "landmarks")
        for doc in landmarks_all_docs.rows:
            if doc.id == "landmark_100":
                landmarks_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {
                    "name": "Wallace Creek Trail", 
                    "channels": ["United States"],
                    "content": "Wallace Creek is a creek with a twist.",
                    "city": "McKittrick", 
                    "state": "CA", 
                    "country": "United States"}))
            elif doc.id == "landmark_200":
                landmarks_updates.append(DocumentUpdateEntry(doc.id, doc.revid, {
                    "name": "Mission San Jose and Museum", 
                    "channels": ["United States"],
                    "content": "This mission founded in 1797 by Fermin Lasuen.",
                    "city": "Fremont", 
                    "state": "CA", 
                    "country": "United States"}))
        await cblpytest.sync_gateways[0].update_documents("travel", landmarks_updates, "travel", "landmarks")

        # Remove 2 hotels in `travel.hotels`
        hotels_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "hotels")
        for doc in hotels_all_docs.rows:
            if doc.id == "hotel_400" or doc.id == "hotel_500":
                await cblpytest.sync_gateways[0].delete_document(doc.id, doc.revid, "travel", "travel", "hotels")

        # 9. Wait until receiving all document replication events
        await replicator.wait_for_doc_events({
            WaitForDocumentEventEntry("travel.airports", "test_airport_1"),
            WaitForDocumentEventEntry("travel.airports", "test_airport_2"),
            WaitForDocumentEventEntry("travel.airlines", "airline_1"),
            WaitForDocumentEventEntry("travel.airlines", "airline_2"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_1"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_2"),
            WaitForDocumentEventEntry("travel.routes", "test_route_1"),
            WaitForDocumentEventEntry("travel.routes", "test_route_2"),
            WaitForDocumentEventEntry("travel.landmarks", "landmark_100"),
            WaitForDocumentEventEntry("travel.landmarks", "landmark_200"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_400"),
            WaitForDocumentEventEntry("travel.hotels", "hotel_500")
        })

        # 10. Check that all updates are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel", 
                                       ["travel.airlines", "travel.airports", "travel.hotels", 
                                        "travel.landmarks", "travel.routes"])
        
    @pytest.mark.skip(reason="CBL-4805")
    @pytest.mark.asyncio
    async def test_reset_checkpoint_push(self, cblpytest: CBLPyTest, dataset_path: Path):
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator:
            * endpoint: `/travel`
            * collections : `travel.airlines`
            * type: push
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.airlines"])], 
                                replicator_type=ReplicatorType.PUSH, 
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH, "travel", 
                                 ["travel.airlines"])
        
        # 6. Purge an airline doc from `travel.airlines` on SG.
        sg_purged_doc_id = "airline_10"
        await cblpytest.sync_gateways[0].purge_document(sg_purged_doc_id, "travel", "travel", "airlines")

        # 7. Start the replicator with the same config as the step 3.
        await replicator.start()

        # 8. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
          
        # 9. Check that the purged airline doc doesn't exist on SG.
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airlines")
        for doc in sg_all_docs.rows:
            assert doc.id != sg_purged_doc_id, f"Unexpected purged document found in SG: {doc.id}"

        # 10. Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`.
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.airlines"])], 
                                replicator_type=ReplicatorType.PUSH, 
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                reset=True)
        await replicator.start()

        # 11. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 12. Check that the purged airline doc is pushed back to SG
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents("travel", "travel", "airlines")
        found_doc = False
        for doc in sg_all_docs.rows:
            if doc.id == sg_purged_doc_id:
                found_doc = True
                break
        assert found_doc, f"{sg_purged_doc_id} was not pushed back to SG after reset checkpoint"

    @pytest.mark.asyncio
    async def test_reset_checkpoint_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        # 1. Reset SG and load `travel` dataset.
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        # Reset local database, and load `travel` dataset.
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        '''
        3. Start a replicator:
            * endpoint: `/travel`
            * collections : `travel.airports`
            * type: pull
            * continuous: false
            * credentials: user1/pass
        '''
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                    collections=[ReplicatorCollectionEntry(["travel.airports"])], 
                                    replicator_type=ReplicatorType.PULL, 
                                    authenticator=ReplicatorBasicAuthenticator("user1", "pass"))
        await replicator.start()

        # 4. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
            
        
        # 5. Check that all docs are replicated correctly.
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "travel", 
                                       ["travel.airports"])
        
        # 6. Purge an airport doc from `travel.airports` in the local database.
        lite_purged_doc_id = "airport_20"
        async with db.batch_updater() as b:
            b.purge_document("travel.airports", lite_purged_doc_id)

        # 7. Start the replicator with the same config as the step 3.
        await replicator.start()

        # 8. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 9. Check that the purged airport doc doesn't exist in CBL database.
        lite_all_docs = await db.get_all_documents("travel.airports")
        for doc in lite_all_docs["travel.airports"]:
            assert doc.id != lite_purged_doc_id, f"Unexpected purged document found in local database: {doc.id}"
        
        # 10. Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`.
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.airports"])], 
                                replicator_type=ReplicatorType.PULL, 
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                reset=True)
        await replicator.start()

        # 11. Wait until the replicator is stopped.
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        # 12. Check that the purged airport doc is pulled back in CBL database.
        lite_all_docs = await db.get_all_documents("travel.airports")
        found_doc = False
        for doc in lite_all_docs["travel.airports"]:
            if doc.id == lite_purged_doc_id:
                found_doc = True
                break
        assert found_doc, f"{lite_purged_doc_id} was not pulled back to local database after reset checkpoint"
