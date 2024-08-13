from pathlib import Path

import pytest

from cbltest import CBLPyTest
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorType, \
    ReplicatorBasicAuthenticator, ReplicatorActivityLevel
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.syncgateway import DocumentUpdateEntry


class TestCustomConflict(CBLTestClass):
    @pytest.mark.asyncio
    async def test_custom_conflict_local_wins(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("empty", ["db1"])
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"),
                                replicator_type=ReplicatorType.PULL, collections=[
                ReplicatorCollectionEntry(["_default._default"])
            ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that all docs are replicated correctly.")
        await compare_local_and_remote(db, cblpytest.sync_gateways[0], ReplicatorType.PULL, "names",
                                       ["_default._default"])
        
        snapshot_id = await db.create_snapshot([SnapshotDocumentEntry("_default._default", "name_101")])
        snapshot_updater = SnapshotUpdater(snapshot_id)

        self.mark_test_step("Modify the local name_101 document `name.last` = 'Smith'")
        update_coll = "_default._default"
        update_id = "name_101"
        update_props = [{"name.last": "Smith"}]
        async with db.batch_updater() as b:
            b.upsert_document(update_coll, update_id, update_props)
            snapshot_updater.upsert_document(update_coll, update_id, update_props)

        self.mark_test_step("Modify the remote name_101 document `name.last` = 'Jones'")
        existing = await cblpytest.sync_gateways[0].get_document("names", "name_101")
        assert existing is not None, "Missing name_101 on remote"
        newBody = existing.body
        dict(newBody["name"])["last"] = "Jones"
        await cblpytest.sync_gateways[0].update_documents("names", [DocumentUpdateEntry("name_101", existing.revid, newBody)])

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push/pull
                * continuous: false
                * credentials: user1/pass
                * conflictResolver: 'local-wins'
        """)
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"),
                                replicator_type=ReplicatorType.PULL, collections=[
                ReplicatorCollectionEntry(["_default._default"], conflict_resolver="local-wins")
            ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step("Check that the names_101 document `names.last` == 'Smith'")
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Conflict resolution resulted in bad data: {verify_result.description}"