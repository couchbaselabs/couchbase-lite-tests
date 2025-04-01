from pathlib import Path
from typing import Any, Dict, List

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import DocumentEntry, MaintenanceType
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null


class TestReplicationBlob(CBLTestClass):
    @pytest.mark.cbse(14861)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_non_blob_changes_with_delta_sync_and_compact(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step(
            "Reset SG and load `travel` dataset with delta sync enabled."
        )
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel", ["delta_sync"])

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step(
            """
            Start a replicator:
                * endpoint: `/travel`
                * collections : `travel.hotels`
                * type: push_and_pull
                * continuous: false
                * credentials: user1/pass
        """
        )
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
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
            "travel",
            ["travel.hotels"],
        )

        self.mark_test_step("Update hotel_1 on SG without changing the image key.")
        hotel_1 = assert_not_null(
            await cblpytest.sync_gateways[0].get_document(
                "travel", "hotel_1", "travel", "hotels"
            ),
            "hotel_1 vanished from SGW",
        )
        hotels_updates: List[DocumentUpdateEntry] = []
        hotels_updates.append(
            DocumentUpdateEntry(
                "hotel_1",
                hotel_1.revision,
                body={
                    "_attachments": {
                        "blob_/image": {
                            "content_type": "image/png",
                            "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                            "length": 156627,
                            "revpos": 1,
                            "stub": True,
                        }
                    },
                    "channels": ["United States"],
                    "description": "This boutique hotel offers five unique food and beverage venues.",
                    "image": {
                        "@type": "blob",
                        "content_type": "image/png",
                        "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                        "length": 156627,
                    },
                    "name": "The Padre Hotel",
                },
            )
        )
        await cblpytest.sync_gateways[0].update_documents(
            "travel", hotels_updates, "travel", "hotels"
        )

        self.mark_test_step("Start the replicator with the same config as the step 3.")
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
            "travel",
            ["travel.hotels"],
        )

        self.mark_test_step(
            "Update hotel_1 on SG again without changing the image key."
        )
        hotel_1 = assert_not_null(
            await cblpytest.sync_gateways[0].get_document(
                "travel", "hotel_1", "travel", "hotels"
            ),
            "hotel_1 vanished from SGW",
        )
        hotels_updates = []
        hotels_updates.append(
            DocumentUpdateEntry(
                "hotel_1",
                hotel_1.revision,
                body={
                    "_attachments": {
                        "blob_/image": {
                            "content_type": "image/png",
                            "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                            "length": 156627,
                            "revpos": 1,
                            "stub": True,
                        }
                    },
                    "channels": ["United States"],
                    "image": {
                        "@type": "blob",
                        "content_type": "image/png",
                        "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                        "length": 156627,
                    },
                    "name": "The Padre Hotel",
                },
            )
        )
        await cblpytest.sync_gateways[0].update_documents(
            "travel", hotels_updates, "travel", "hotels"
        )

        self.mark_test_step("Snapshot document hotel_1.")
        snapshot_id = await db.create_snapshot(
            [DocumentEntry("travel.hotels", "hotel_1")]
        )

        self.mark_test_step("Start the replicator with the same config as the step 3.")
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
            "travel",
            ["travel.hotels"],
        )

        self.mark_test_step("Perform compact on the database.")
        await db.perform_maintenance(MaintenanceType.COMPACT)

        self.mark_test_step("Verify updates to the snapshot from the step 11.")
        snapshot_updater = SnapshotUpdater(snapshot_id)
        snapshot_updater.upsert_document(
            "travel.hotels", "hotel_1", removed_properties=["description"]
        )
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, (
            f"The verification failed: {verify_result.description}"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_replication(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `names` dataset.")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step(
            "Create a document with a blob on the property `watermelon` with the contents of s10.jpg"
        )
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default", "fruits", new_blobs={"watermelon": "s10.jpg"}
            )

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
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

        self.mark_test_step(
            "Check that the document with the ID from step 3 contains a valid `watermelon` property"
        )
        remote_doc = await cblpytest.sync_gateways[0].get_document("names", "fruits")
        assert remote_doc is not None, "Document `fruits` not found in SGW"

        def check_blob_prop(d: Dict, prop: str, expected_value: Any):
            assert prop in d, f"Property `{prop}` not found in the blob"
            assert d[prop] == expected_value, (
                f"Property `{prop}` is incorrect (expected: {expected_value}, actual: {d[prop]})"
            )

        assert "watermelon" in remote_doc.body, (
            "Property `watermelon` not found in the document"
        )
        check_blob_prop(remote_doc.body["watermelon"], "@type", "blob")
        check_blob_prop(remote_doc.body["watermelon"], "content_type", "image/jpeg")
        check_blob_prop(
            remote_doc.body["watermelon"], "digest", "sha1-8ArxA/yauDMWJrQsvVSzo8RKhtk="
        )
        check_blob_prop(remote_doc.body["watermelon"], "length", 199095)

        self.mark_test_step(
            "Check that the blob in the `watermelon` property has a corresponding attachment entry in SGW"
        )
        assert "_attachments" in remote_doc.body, (
            "Property `_attachments` not found in the document"
        )
        assert isinstance(remote_doc.body["_attachments"], dict), (
            "Property `_attachments` is not a dictionary"
        )
        assert "blob_/watermelon" in remote_doc.body["_attachments"], (
            "Attachment `blob_/watermelon` not found in the document"
        )
        assert isinstance(remote_doc.body["_attachments"]["blob_/watermelon"], dict), (
            "Attachment `blob_/watermelon` is not a dictionary"
        )
        check_blob_prop(
            remote_doc.body["_attachments"]["blob_/watermelon"],
            "content_type",
            "image/jpeg",
        )
        check_blob_prop(
            remote_doc.body["_attachments"]["blob_/watermelon"],
            "digest",
            "sha1-8ArxA/yauDMWJrQsvVSzo8RKhtk=",
        )
        check_blob_prop(
            remote_doc.body["_attachments"]["blob_/watermelon"], "length", 199095
        )
        check_blob_prop(
            remote_doc.body["_attachments"]["blob_/watermelon"], "revpos", 1
        )
        check_blob_prop(
            remote_doc.body["_attachments"]["blob_/watermelon"], "stub", True
        )
