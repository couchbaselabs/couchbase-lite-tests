from datetime import timedelta
from pathlib import Path
from typing import List

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.replicator_types import (
    ReplicatorBasicAuthenticator,
    ReplicatorDocumentFlags,
)
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null


class TestBasicReplication(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_non_existing_sg_collections(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator
            * endpoint: `/names`
            * collections : `travel.airlines`
            * type: push
            * continuous: false
            * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PUSH,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)

        self.mark_test_step("Check that the replicator's error is CBL/10404")
        assert (
            status.error is not None
            and status.error.code == 10404
            and ErrorDomain.equal(status.error.domain, ErrorDomain.CBL)
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PUSH,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.airlines", "travel.airports", "travel.hotels"]
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH,
            "travel",
            ["travel.airlines", "travel.airports", "travel.hotels"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.routes", "travel.landmarks", "travel.hotels"]
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.routes", "travel.landmarks", "travel.hotels"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_and_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections: `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
                * type: push-and-pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            collections=[
                ReplicatorCollectionEntry(
                    [
                        "travel.airlines",
                        "travel.airports",
                        "travel.hotels",
                        "travel.landmarks",
                        "travel.routes",
                    ]
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(
            ReplicatorActivityLevel.STOPPED, timeout=timedelta(seconds=300)
        )
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "travel",
            [
                "travel.airlines",
                "travel.airports",
                "travel.hotels",
                "travel.landmarks",
                "travel.routes",
            ],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_continuous_push(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
                * type: push
                * continuous: true
                * enableDocumentListener: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.airlines", "travel.airports", "travel.hotels"]
                )
            ],
            replicator_type=ReplicatorType.PUSH,
            continuous=True,
            enable_document_listener=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH,
            "travel",
            ["travel.airlines", "travel.airports", "travel.hotels"],
        )

        self.mark_test_step("Clear current document replication events.")
        replicator.clear_document_updates()

        self.mark_test_step("""
            Update documents in the local database.
                * Add 2 airports in travel.airports.
                * Update 2 new airlines in travel.airlines.
                * Remove 2 hotels in travel.hotels.
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.airports",
                "test_airport_1",
                [{"name": "Airport 1", "channels": ["United States"]}],
            )
            b.upsert_document(
                "travel.airports",
                "test_airport_2",
                [{"name": "Airport 2", "channels": ["United Kingdom"]}],
            )
            b.upsert_document(
                "travel.airlines", "airline_1", removed_properties=["country"]
            )
            b.upsert_document(
                "travel.airlines", "airline_2", removed_properties=["country"]
            )
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")

        self.mark_test_step("Wait until receiving all document replication events")
        await replicator.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.airports",
                    "test_airport_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airports",
                    "test_airport_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airlines",
                    "airline_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airlines",
                    "airline_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
            }
        )

        self.mark_test_step("Check that all updates are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH,
            "travel",
            ["travel.airlines", "travel.airports", "travel.hotels"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_continuous_pull(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
                * type: pull
                * continuous: true
                * enableDocumentListener: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.routes", "travel.landmarks", "travel.hotels"]
                )
            ],
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            enable_document_listener=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.routes", "travel.landmarks", "travel.hotels"],
        )

        self.mark_test_step("Clear current document replication events.")
        replicator.clear_document_updates()

        self.mark_test_step("""
            Update documents on SG.
                * Add 2 routes in `travel.routes`.
                * Update 2 landmarks in `travel.landmarks`.
                * Remove 2 hotels in `travel.hotels`.
        """)
        # Add 2 routes in `travel.routes`
        routes_updates: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry(
                "test_route_1",
                None,
                body={
                    "airline": "Skyline",
                    "channels": ["United States"],
                    "country": "United States",
                    "sourceairport": "SFO",
                    "destinationairport": "NRT",
                },
            ),
            DocumentUpdateEntry(
                "test_route_2",
                None,
                body={
                    "airline": "Nimbus",
                    "channels": ["United States"],
                    "country": "United States",
                    "sourceairport": "SFO",
                    "destinationairport": "BKK",
                },
            ),
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "travel", routes_updates, "travel", "routes"
        )

        # Update 2 landmarks in `travel.landmarks`
        landmarks_updates: List[DocumentUpdateEntry] = []
        landmarks_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "landmarks"
        )
        for doc in landmarks_all_docs.rows:
            if doc.id == "landmark_100":
                landmarks_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Wallace Creek Trail",
                            "channels": ["United States"],
                            "content": "Wallace Creek is a creek with a twist.",
                            "city": "McKittrick",
                            "state": "CA",
                            "country": "United States",
                        },
                    )
                )
            elif doc.id == "landmark_200":
                landmarks_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Mission San Jose and Museum",
                            "channels": ["United States"],
                            "content": "This mission founded in 1797 by Fermin Lasuen.",
                            "city": "Fremont",
                            "state": "CA",
                            "country": "United States",
                        },
                    )
                )
        await cblpytest.sync_gateways[0].update_documents(
            "travel", landmarks_updates, "travel", "landmarks"
        )

        # Remove 2 hotels in `travel.hotels`
        hotels_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "hotels"
        )
        for doc in hotels_all_docs.rows:
            if doc.id == "hotel_400" or doc.id == "hotel_500":
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[0].delete_document(
                    doc.id, revid, "travel", "travel", "hotels"
                )

        self.mark_test_step("Wait until receiving all document replication events")
        await replicator.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.routes",
                    "test_route_1",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.routes",
                    "test_route_2",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.landmarks",
                    "landmark_100",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.landmarks",
                    "landmark_200",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_400",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_500",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
            }
        )

        self.mark_test_step("Check that all updates are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.routes", "travel.landmarks", "travel.hotels"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_continuous_push_and_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/travel`
                * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
                * type: push-and-pull
                * continuous: true
                * enableDocumentListener: true
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[
                ReplicatorCollectionEntry(
                    [
                        "travel.airlines",
                        "travel.airports",
                        "travel.hotels",
                        "travel.landmarks",
                        "travel.routes",
                    ]
                )
            ],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            enable_document_listener=True,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle.")
        status = await replicator.wait_for(
            ReplicatorActivityLevel.IDLE, timeout=timedelta(seconds=300)
        )
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "travel",
            [
                "travel.airlines",
                "travel.airports",
                "travel.hotels",
                "travel.landmarks",
                "travel.routes",
            ],
        )

        self.mark_test_step("Clear current document replication events.")
        replicator.clear_document_updates()

        self.mark_test_step("""
            Update documents in the local database.
                * Add 2 airports in travel.airports.
                * Update 2 CBL airlines in travel.airlines.
                * Update 2 SG hotels in travel.hotels.
                * Remove 2 CBL hotels in travel.hotels.
                * Remove 2 SG hotels in travel.hotels.
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "travel.airports",
                "test_airport_1",
                [{"name": "AirPort1", "channels": ["United States"]}],
            )
            b.upsert_document(
                "travel.airports",
                "test_airport_2",
                [{"name": "AirPort2", "channels": ["United Kingdom"]}],
            )
            b.upsert_document(
                "travel.airlines", "airline_1", removed_properties=["country"]
            )
            b.upsert_document(
                "travel.airlines", "airline_2", removed_properties=["country"]
            )
            b.upsert_document("travel.hotels", "hotel_361", [{"non_smoking": True}])
            b.upsert_document("travel.hotels", "hotel_362", [{"non_smoking": True}])
            b.delete_document("travel.hotels", "hotel_1")
            b.delete_document("travel.hotels", "hotel_2")
            b.delete_document("travel.hotels", "hotel_371")
            b.delete_document("travel.hotels", "hotel_372")

        self.mark_test_step("""
            Update documents on SG.
                * Add 2 routes in `travel.routes`.
                * Update 2 SG landmarks in `travel.landmarks`.
                * Update 2 CBL hotels in `travel.hotels`.
                * Remove 2 SG hotels in `travel.hotels`.
                * Remove 2 CBL hotels in `travel.hotels`.
        """)
        # Add 2 routes in `travel.routes`
        routes_updates: List[DocumentUpdateEntry] = [
            DocumentUpdateEntry(
                "test_route_1",
                None,
                body={
                    "airline": "Skyline",
                    "channels": ["United States"],
                    "country": "United States",
                    "sourceairport": "SFO",
                    "destinationairport": "NRT",
                },
            ),
            DocumentUpdateEntry(
                "test_route_2",
                None,
                body={
                    "airline": "Nimbus",
                    "channels": ["United States"],
                    "country": "United States",
                    "sourceairport": "SFO",
                    "destinationairport": "BKK",
                },
            ),
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "travel", routes_updates, "travel", "routes"
        )

        # Update 2 SG landmarks in `travel.landmarks`
        landmarks_updates: List[DocumentUpdateEntry] = []
        landmarks_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "landmarks"
        )
        for doc in landmarks_all_docs.rows:
            if doc.id == "landmark_100":
                landmarks_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Wallace Creek Trail",
                            "channels": ["United States"],
                            "content": "Wallace Creek is a creek with a twist.",
                            "city": "McKittrick",
                            "state": "CA",
                            "country": "United States",
                        },
                    )
                )
            elif doc.id == "landmark_200":
                landmarks_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Mission San Jose and Museum",
                            "channels": ["United States"],
                            "content": "This mission founded in 1797 by Fermin Lasuen.",
                            "city": "Fremont",
                            "state": "CA",
                            "country": "United States",
                        },
                    )
                )
        await cblpytest.sync_gateways[0].update_documents(
            "travel", landmarks_updates, "travel", "landmarks"
        )

        # Update 2 CBL hotels in `travel.landmarks`
        hotels_updates: List[DocumentUpdateEntry] = []
        hotels_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "hotels"
        )
        for doc in hotels_all_docs.rows:
            if doc.id == "hotel_51":
                hotels_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Mountain Hotel 51",
                            "channels": ["United States"],
                            "address": "1 Snow st",
                            "city": "Tahoe City",
                            "state": "CA",
                            "country": "United States",
                            "non_smoking": True,
                            "free_breakfast": True,
                            "free_internet": True,
                            "free_parking": True,
                            "collection": "hotels",
                            "scope": "travel",
                        },
                    )
                )
            elif doc.id == "hotel_52":
                hotels_updates.append(
                    DocumentUpdateEntry(
                        doc.id,
                        doc.revid,
                        {
                            "name": "Mountain Hotel 52",
                            "channels": ["United States"],
                            "address": "2 Snow st",
                            "city": "Tahoe City",
                            "state": "CA",
                            "country": "United States",
                            "non_smoking": True,
                            "free_breakfast": True,
                            "free_internet": True,
                            "free_parking": True,
                            "collection": "hotels",
                            "scope": "travel",
                        },
                    )
                )
        await cblpytest.sync_gateways[0].update_documents(
            "travel", hotels_updates, "travel", "hotels"
        )

        # Remove 2 SG and 2 CBL hotels in `travel.hotels`
        hotels_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "hotels"
        )
        for doc in hotels_all_docs.rows:
            if (
                doc.id == "hotel_61"
                or doc.id == "hotel_62"
                or doc.id == "hotel_400"
                or doc.id == "hotel_500"
            ):
                revid = assert_not_null(doc.revid, f"Missing revid on {doc.id}")
                await cblpytest.sync_gateways[0].delete_document(
                    doc.id, revid, "travel", "travel", "hotels"
                )

        self.mark_test_step("Wait until receiving all document replication events")
        await replicator.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    "travel.airports",
                    "test_airport_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airports",
                    "test_airport_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airlines",
                    "airline_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.airlines",
                    "airline_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_361",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_362",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_1",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_2",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_371",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_372",
                    ReplicatorType.PUSH,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.routes",
                    "test_route_1",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.routes",
                    "test_route_2",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.landmarks",
                    "landmark_100",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.landmarks",
                    "landmark_200",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_51",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_52",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.NONE,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_61",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_62",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_400",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
                WaitForDocumentEventEntry(
                    "travel.hotels",
                    "hotel_500",
                    ReplicatorType.PULL,
                    ReplicatorDocumentFlags.DELETED,
                ),
            },
            max_retries=100,
        )

        self.mark_test_step("Check that all updates are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "travel",
            [
                "travel.airlines",
                "travel.airports",
                "travel.hotels",
                "travel.landmarks",
                "travel.routes",
            ],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_collection_push(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `names` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push
                * continuous: false
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PUSH,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH,
            "names",
            ["_default._default"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_collection_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `names` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: pull
                * continuous: false
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "names",
            ["_default._default"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_collection_push_and_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `names` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push-and-pull
                * continuous: false
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_checkpoint_push(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections : `travel.airlines`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH,
            "travel",
            ["travel.airlines"],
        )

        self.mark_test_step("Purge an airline doc from `travel.airlines` on SG.")
        sg_purged_doc_id = "airline_10"
        await cblpytest.sync_gateways[0].purge_document(
            sg_purged_doc_id, "travel", "travel", "airlines"
        )

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that the purged airline doc doesn't exist on SG.")
        sg_all_docs = await cblpytest.sync_gateways[0].get_all_documents(
            "travel", "travel", "airlines"
        )
        for doc in sg_all_docs.rows:
            assert doc.id != sg_purged_doc_id, (
                f"Unexpected purged document found in SG: {doc.id}"
            )

        self.mark_test_step(
            "Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`."
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            reset=True,
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that there were no docs pushed.")
        assert len(replicator.document_updates) == 0, (
            f"Should be no docs pushed, but {len(replicator.document_updates)} docs were pushed"
        )

        self.mark_test_step(
            "Check that the purged airline doc was not pushed back to SG"
        )
        for doc in sg_all_docs.rows:
            assert doc.id != sg_purged_doc_id, (
                f"Unexpected purged document found in SG: {doc.id}"
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_checkpoint_pull(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `travel` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections : `travel.airports`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.airports"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.airports"],
        )

        self.mark_test_step(
            "Purge an airport doc from `travel.airports` in the local database."
        )
        lite_purged_doc_id = "airport_20"
        async with db.batch_updater() as b:
            b.purge_document("travel.airports", lite_purged_doc_id)

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that the purged airport doc doesn't exist in CBL database."
        )
        lite_all_docs = await db.get_all_documents("travel.airports")
        for doc in lite_all_docs["travel.airports"]:
            assert doc.id != lite_purged_doc_id, (
                f"Unexpected purged document found in local database: {doc.id}"
            )

        self.mark_test_step(
            "Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`."
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.airports"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            reset=True,
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that there was only one doc pulled.")
        assert len(replicator.document_updates) == 1, (
            f"Should be one doc pulled, but {len(replicator.document_updates)} docs were pulled"
        )
        assert replicator.document_updates[0].document_id == lite_purged_doc_id, (
            f"Unexpected doc '{replicator.document_updates[0].document_id}' was pulled"
        )

        self.mark_test_step(
            "Check that the purged airport doc is pulled back in CBL database."
        )
        lite_all_docs = await db.get_all_documents("travel.airports")
        found_doc = False
        for doc in lite_all_docs["travel.airports"]:
            if doc.id == lite_purged_doc_id:
                found_doc = True
                break
        assert found_doc, (
            f"{lite_purged_doc_id} was not pulled back to local database after reset checkpoint"
        )

        await cblpytest.test_servers[0].cleanup()
