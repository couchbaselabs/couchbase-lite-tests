from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentEntry,
    ReplicatorFilter,
    ReplicatorType,
)
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.utils import assert_not_null
from test_replication_filter_data import uk_and_france_doc_ids  # type: ignore


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationFilter(CBLTestClass):
    def validate_replicated_doc_ids(
        self, expected: set[str], actual: list[ReplicatorDocumentEntry]
    ) -> None:
        for update in actual:
            assert update.document_id in expected, (
                f"Unexpected document update not in filter: {update.document_id}"
            )
            expected.remove(update.document_id)

        assert len(expected) == 0, (
            f"Not all document updates were found (e.g. {next(iter(expected))})"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_push_document_ids_filter(
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

        self.mark_test_step(
            """
            Start a replicator: 
                * collections : 
                * `travel.airlines`
                    * documentIDs : `airline_10`, `airline_20`, `airline_1000`
                * `travel.routes`
                    * documentIDs : `route_10`, `route_20`
                * endpoint: `/travel`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PUSH,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.airlines"],
                    document_ids=["airline_10", "airline_20", "airline_1000"],
                ),
                ReplicatorCollectionEntry(
                    ["travel.routes"], document_ids=["route_10", "route_20"]
                ),
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only docs specified in the documentIDs filters are replicated except `travel.airline`.`airline_1000`"
        )
        expected_ids = {"airline_10", "airline_20", "route_10", "route_20"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        self.mark_test_step(
            """
            Update docs in the local database
                * Add `airline_1000` in `travel.airlines`
                * Update `airline_10` in `travel.airlines`
                * Remove `route_10` in `travel.routes`
        """
        )
        async with db.batch_updater() as b:
            b.upsert_document("travel.airlines", "airline_1000", [{"new_doc": True}])
            b.upsert_document("travel.airlines", "airline_10", [{"new_doc": False}])
            b.delete_document("travel.routes", "route_10")

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only changes for docs in the specified documentIDs filters are replicated."
        )
        expected_ids = {"airline_1000", "airline_10", "route_10"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_document_ids_filter(
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

        self.mark_test_step(
            """
            Start a replicator: 
                * collections : 
                * `travel.airports`
                    * documentIDs : `airport_10`, `airport_20`, `airport_1000`
                * `travel.landmarks`
                    * documentIDs : `landmark_10`, `landmark_20`
                * endpoint: `/travel`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.airports"],
                    document_ids=["airport_10", "airport_20", "airport_1000"],
                ),
                ReplicatorCollectionEntry(
                    ["travel.landmarks"], document_ids=["landmark_10", "landmark_20"]
                ),
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only docs specified in the documentIDs filters are replicated except `travel.airline`.`airline_1000`"
        )
        expected_ids = {"airport_10", "airport_20", "landmark_10", "landmark_20"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        self.mark_test_step(
            """
            Update docs on SG
                * Add `airport_1000` in `travel.airports`
                * Update `airport_10` in `travel.airports`
                * Remove `landmark_10`, in `travel.landmarks`
        """
        )
        remote_airport_10 = await cblpytest.sync_gateways[0].get_document(
            "travel", "airport_10", "travel", "airports"
        )
        assert remote_airport_10 is not None, "Missing airport_10 from sync gateway"

        remote_landmark_10 = await cblpytest.sync_gateways[0].get_document(
            "travel", "landmark_10", "travel", "landmarks"
        )
        assert remote_landmark_10 is not None, "Missing landmark_10 from sync gateway"
        landmark_10_revid = assert_not_null(
            remote_landmark_10.revid, "Missing landmark_10 revid"
        )

        updates = [
            DocumentUpdateEntry("airport_1000", None, {"answer": 42}),
            DocumentUpdateEntry("airport_10", remote_airport_10.revid, {"answer": 42}),
        ]
        await cblpytest.sync_gateways[0].update_documents(
            "travel", updates, "travel", "airports"
        )
        await cblpytest.sync_gateways[0].delete_document(
            "landmark_10", landmark_10_revid, "travel", "travel", "landmarks"
        )

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only changes for docs in the specified documentIDs filters are replicated."
        )
        expected_ids = {"airport_1000", "airport_10", "landmark_10"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_channels_filter(
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

        self.mark_test_step(
            """
            Start a replicator: 
                * collections : 
                * `travel.airports`
                    * channels : `United Kingdom`, `France`
                * `travel.landmarks`
                    * channels : `France`
                * endpoint: `/travel
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[
                ReplicatorCollectionEntry(
                    ["travel.airports"], channels=["United Kingdom", "France"]
                ),
                ReplicatorCollectionEntry(["travel.landmarks"], channels=["France"]),
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that only docs in the filtered channels are pulled.")
        expected_ids = uk_and_france_doc_ids
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        self.mark_test_step(
            """
            Update docs on SG
                * Add `airport_1000` with channels = ["United Kingdom"], `airport_2000` with channels = ["France"] 
                    and `airport_3000` with channels = ["United States"] in `travel.airports`
                * Update `airport_11` with channels = ["United States"], `airport_1` with channels = ["France"], 
                    `airport_17` with channels = ["United States"] in `travel.airports`
                * Remove `landmark_1` channels = ["United Kingdom"], `landmark_2001` channels = ["France"] in `travel.landmarks`
        """
        )
        remote_airport_11 = await cblpytest.sync_gateways[0].get_document(
            "travel", "airport_11", "travel", "airports"
        )
        assert remote_airport_11 is not None, "Missing airport_11 from sync gateway"

        remote_airport_1 = await cblpytest.sync_gateways[0].get_document(
            "travel", "airport_1", "travel", "airports"
        )
        assert remote_airport_1 is not None, "Missing airport_1 from sync gateway"

        remote_airport_17 = await cblpytest.sync_gateways[0].get_document(
            "travel", "airport_17", "travel", "airports"
        )
        assert remote_airport_17 is not None, "Missing airport_17 from sync gateway"

        remote_landmark_1 = await cblpytest.sync_gateways[0].get_document(
            "travel", "landmark_1", "travel", "landmarks"
        )
        assert remote_landmark_1 is not None, "Missing landmark_1 from sync gateway"
        landmark_1_revid = assert_not_null(
            remote_landmark_1.revid, "Missing landmark_1 revid"
        )

        remote_landmark_601 = await cblpytest.sync_gateways[0].get_document(
            "travel", "landmark_601", "travel", "landmarks"
        )
        assert remote_landmark_601 is not None, "Missing landmark_601 from sync gateway"
        landmark_601_revid = assert_not_null(
            remote_landmark_601.revid, "Missing landmark_601 revid"
        )

        updates = [
            DocumentUpdateEntry(
                "airport_1000", None, {"answer": 42, "channels": ["United Kingdom"]}
            ),
            DocumentUpdateEntry(
                "airport_2000", None, {"answer": 42, "channels": ["France"]}
            ),
            DocumentUpdateEntry(
                "airport_3000", None, {"answer": 42, "channels": ["United States"]}
            ),
            DocumentUpdateEntry(
                "airport_11",
                remote_airport_11.revid,
                {"answer": 42, "channels": ["United States"]},
            ),
            DocumentUpdateEntry(
                "airport_1",
                remote_airport_1.revid,
                {"answer": 42, "channels": ["France"]},
            ),
            DocumentUpdateEntry(
                "airport_17",
                remote_airport_17.revid,
                {"answer": 42, "channels": ["United Kingdom"]},
            ),
        ]

        await cblpytest.sync_gateways[0].update_documents(
            "travel", updates, "travel", "airports"
        )
        await cblpytest.sync_gateways[0].delete_document(
            "landmark_1", landmark_1_revid, "travel", "travel", "landmarks"
        )
        await cblpytest.sync_gateways[0].delete_document(
            "landmark_601", landmark_601_revid, "travel", "travel", "landmarks"
        )

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        replicator.clear_document_updates()
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only changes in the filtered channels are pulled."
        )
        expected_ids = {
            "airport_1000",
            "airport_2000",
            "airport_1",
            "airport_17",
            "landmark_601",
        }
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_public_channel(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `names` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `empty` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]
        snapshot_id = await db.create_snapshot(
            [DocumentEntry("_default._default", "test_public")]
        )
        snapshot_updater = SnapshotUpdater(snapshot_id)

        self.mark_test_step(
            """
            Add a document to SG
                * id: test_public
                * channels: `!`
                * content: `{"hello": "world"}`
        """
        )
        sgw = cblpytest.sync_gateways[0]
        await sgw.update_documents(
            "names",
            [
                DocumentUpdateEntry(
                    "test_public", None, {"hello": "world", "channels": ["!"]}
                )
            ],
        )
        snapshot_updater.upsert_document(
            "_default._default",
            "test_public",
            [{"hello": "world"}, {"channels": ["!"]}],
        )

        self.mark_test_step(
            """
            Start a replicator: 
                * endpoint: `/names`
                * type: pull
                * continuous: false
                * credentials: user2/pass
        """
        )
        replicator = Replicator(
            db,
            sgw.replication_url("names"),
            ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user2", "pass"),
            pinned_server_cert=sgw.tls_cert(),
        )
        replicator.add_default_collection()
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that only test_public was pulled")
        all_docs = await db.get_all_documents("_default._default")
        assert (
            "_default._default" in all_docs and len(all_docs["_default._default"]) == 1
        ), "Invalid number of documents after pull"

        self.mark_test_step("Verify test_public contents")
        await db.verify_documents(snapshot_updater)

        self.mark_test_step(
            """
            Update test_public locally
                * body: `{"see you later": "world"}`
        """
        )
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default", "test_public", [{"see you later": "world"}]
            )

        self.mark_test_step(
            """
            Start a replicator: 
                * endpoint: `/names`
                * type: push
                * continuous: false
                * credentials: user2/pass
        """
        )
        replicator = Replicator(
            db,
            sgw.replication_url("names"),
            ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user2", "pass"),
            pinned_server_cert=sgw.tls_cert(),
        )
        replicator.add_default_collection()
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify that the document on Sync Gateway was updated")
        sgw_doc = await sgw.get_document("names", "test_public")
        assert sgw_doc is not None, "test_public missing from SGW"
        assert "see you later" in sgw_doc.body, (
            "updated key missing from test_public in SGW"
        )
        assert sgw_doc.body["see you later"] == "world", (
            "incorrect data in updated key from test_public in SGW"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_push_filter(
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

        self.mark_test_step(
            """
            Start a replicator: 
                * collections : 
                * `_default._default`
                    * pushFilter:  
                        * name: `deletedDocumentsOnly`
                        * params: `{}`
                * endpoint: `/names`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PUSH,
            collections=[
                ReplicatorCollectionEntry(
                    ["_default._default"],
                    push_filter=ReplicatorFilter("deletedDocumentsOnly"),
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that no docs are replicated.")
        assert len(replicator.document_updates) == 0, (
            f"{len(replicator.document_updates)} documents replicated even though they should be filtered"
        )

        self.mark_test_step(
            """
            Update docs in the local database
                * Add `name_10000`
                * Remove `name_10` and `name_20`
        """
        )
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_10000", [{"answer": 42}])
            b.delete_document("_default._default", "name_10")
            b.delete_document("_default._default", "name_20")

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only changes passed the push filters are replicated."
        )
        expected_ids = {"name_10", "name_20"}
        self.validate_replicated_doc_ids(expected_ids, replicator.document_updates)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_pull_filter(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        def repl_filter(x):
            return (x.error is None) or (
                (x.error.domain == "CouchbaseLite") and (x.error.code == 10403)
            )

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

        self.mark_test_step(
            """
        Start a replicator:
            * collections :
            * `_default._default`
                * pullFilter:
                    * name: `deletedDocumentsOnly`
                    * params: `{}`
            * endpoint: `/names`
            * type: pull
            * continuous: false
            * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PULL,
            collections=[
                ReplicatorCollectionEntry(
                    ["_default._default"],
                    pull_filter=ReplicatorFilter("deletedDocumentsOnly"),
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Pull replication failed: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that no docs are replicated.")
        successful_replications1 = list(
            filter(repl_filter, replicator.document_updates)
        )
        assert len(successful_replications1) == 0, (
            f"{len(successful_replications1)} documents were replicated even though they should have been filtered"
        )

        self.mark_test_step(
            """
        Update docs on SG
            * Add `name_10000`
            * Remove `name_10` and `name_20`
        """
        )
        updates = [DocumentUpdateEntry("name_1000", None, {"answer": 42})]

        remote_name_10 = await cblpytest.sync_gateways[0].get_document(
            "names", "name_105"
        )
        assert remote_name_10 is not None, "Missing name_105 from sync gateway"
        name_10_revid = assert_not_null(remote_name_10.revid, "Missing name_105 revid")

        remote_name_20 = await cblpytest.sync_gateways[0].get_document(
            "names", "name_193"
        )
        assert remote_name_20 is not None, "Missing name_193 from sync gateway"
        name_20_revid = assert_not_null(remote_name_20.revid, "Missing name_193 revid")

        await cblpytest.sync_gateways[0].update_documents("names", updates)
        await cblpytest.sync_gateways[0].delete_document(
            "name_105", name_10_revid, "names"
        )
        await cblpytest.sync_gateways[0].delete_document(
            "name_193", name_20_revid, "names"
        )

        self.mark_test_step("Start a replicator with the same config as in step 3.")
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Pull replication failed: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Check that only changes passed the push filters are replicated."
        )
        expected_ids = {"name_105", "name_193"}
        successful_replications2 = list(
            filter(repl_filter, replicator.document_updates)
        )
        self.validate_replicated_doc_ids(expected_ids, successful_replications2)

        await cblpytest.test_servers[0].cleanup()
