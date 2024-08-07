from pathlib import Path
from typing import List
import pytest
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import MaintenanceType, SnapshotDocumentEntry
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.api.cbltestclass import CBLTestClass

class TestReplicationBlob(CBLTestClass):
    @pytest.mark.cbse(14681)
    @pytest.mark.skip(reason="CBL-4839 / CBSE-14861")
    @pytest.mark.asyncio
    async def test_pull_non_blob_changes_with_delta_sync_and_compact(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `travel` dataset with delta sync enabled.")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel", ["delta_sync"])

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/travel`
                * collections : `travel.hotels`
                * type: push_and_pull
                * continuous: false
                * credentials: user1/pass
        ''')
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("travel"), 
                                collections=[ReplicatorCollectionEntry(["travel.hotels"])],
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel",
                                 ["travel.hotels"])
        
        self.mark_test_step("Update hotel_1 on SG without changing the image key.")
        hotels_updates: List[DocumentUpdateEntry] = []
        hotels_updates.append(DocumentUpdateEntry("hotel_1", "1-2888d379591e42370912510ae8e8a976e1bf6436", body={
            "_attachments": {
                "blob_/image": {
                    "content_type": "image/png",
                    "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                    "length": 156627,
                    "revpos": 1,
                    "stub": True
                }
            },
            "channels": ["United States"],
            "description": "This boutique hotel offers five unique food and beverage venues.",
            "image": {
                "@type": "blob",
                "content_type": "image/png",
                "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                "length": 156627
            },
            "name": "The Padre Hotel"
        }))
        await cblpytest.sync_gateways[0].update_documents("travel", hotels_updates, "travel", "hotels")

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel",
                                       ["travel.hotels"])
        
        self.mark_test_step("Update hotel_1 on SG again without changing the image key.")
        hotels_updates = []
        hotels_updates.append(DocumentUpdateEntry("hotel_1", "2-9a718e02f5e5aa1aa90bdbb25072d258", body={
            "_attachments": {
                "blob_/image": {
                    "content_type": "image/png",
                    "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                    "length": 156627,
                    "revpos": 1,
                    "stub": True
                }
            },
            "channels": ["United States"],
            "image": {
                "@type": "blob",
                "content_type": "image/png",
                "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
                "length": 156627
            },
            "name": "The Padre Hotel"
        }))
        await cblpytest.sync_gateways[0].update_documents("travel", hotels_updates, "travel", "hotels")

        self.mark_test_step("Snapshot document hotel_1.")
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("travel.hotels", "hotel_1")
        ])

        self.mark_test_step("Start the replicator with the same config as the step 3.")
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PUSH_AND_PULL, "travel",
                                       ["travel.hotels"])

        self.mark_test_step("Perform compact on the database.")
        await db.perform_maintenance(MaintenanceType.COMPACT)

        self.mark_test_step("Verify updates to the snapshot from the step 11.")
        snapshot_updater = SnapshotUpdater(snapshot_id)
        snapshot_updater.upsert_document("travel.hotels", "hotel_1", removed_properties=["description"])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == True, f"The verification failed: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()
