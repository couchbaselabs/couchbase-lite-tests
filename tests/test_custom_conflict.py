from pathlib import Path
from typing import Callable

import pytest

from cbltest import CBLPyTest
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorType, \
    ReplicatorBasicAuthenticator, ReplicatorActivityLevel, ReplicatorConflictResolver
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import DocumentEntry
from cbltest.api.syncgateway import DocumentUpdateEntry

class TestCustomConflict(CBLTestClass):
    async def do_custom_conflict_test(self, cblpytest: CBLPyTest, dataset_path: Path, 
                                      conflict_resolver: ReplicatorConflictResolver, setup_snapshot: Callable[[SnapshotUpdater], str]):
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
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
        
        snapshot_id = await db.create_snapshot([DocumentEntry("_default._default", "name_101")])
        snapshot_updater = SnapshotUpdater(snapshot_id)

        self.mark_test_step("Modify the local name_101 document `name.last` = 'Smith'")
        update_coll = "_default._default"
        update_id = "name_101"
        verify_description = setup_snapshot(snapshot_updater)
        async with db.batch_updater() as b:
            b.upsert_document(update_coll, update_id, [{"name.last": "Smith"}])

        self.mark_test_step("Modify the remote name_101 document `name.last` = 'Jones'")
        existing = await cblpytest.sync_gateways[0].get_document("names", "name_101")
        assert existing is not None, "Missing name_101 on remote"
        newBody = existing.body
        newBody["name"]["last"] = "Jones"
        await cblpytest.sync_gateways[0].update_documents("names", [DocumentUpdateEntry("name_101", existing.revid, newBody)])

        resolver_params = f" / {conflict_resolver.parameters}" if conflict_resolver.parameters is not None else ""
        self.mark_test_step(f"""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push/pull
                * continuous: false
                * credentials: user1/pass
                * conflictResolver: '{conflict_resolver.name}'{resolver_params}
        """)
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"),
                                replicator_type=ReplicatorType.PULL, collections=[
                ReplicatorCollectionEntry(["_default._default"], conflict_resolver=conflict_resolver)
            ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"), pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"

        self.mark_test_step(verify_description)
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Conflict resolution resulted in bad data: {verify_result.description}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_conflict_local_wins(self, cblpytest: CBLPyTest, dataset_path: Path):
        def setup_snapshot(updater: SnapshotUpdater):
            updater.upsert_document("_default._default", "name_101", [{"name.last": "Smith"}])
            return "Check that the names_101 document `name.last` == 'Smith'"
        
        await self.do_custom_conflict_test(cblpytest, dataset_path, ReplicatorConflictResolver("local-wins"), setup_snapshot)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_conflict_remote_wins(self, cblpytest: CBLPyTest, dataset_path: Path):
        def setup_snapshot(updater: SnapshotUpdater):
            updater.upsert_document("_default._default", "name_101", [{"name.last": "Jones"}])
            return "Check that the names_101 document `name.last` == 'Jones'"
        
        await self.do_custom_conflict_test(cblpytest, dataset_path, ReplicatorConflictResolver("remote-wins"), setup_snapshot)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_conflict_delete(self, cblpytest: CBLPyTest, dataset_path: Path):
        def setup_snapshot(updater: SnapshotUpdater):
            updater.delete_document("_default._default", "name_101")
            return "Check that the names_101 document is deleted"
        
        await self.do_custom_conflict_test(cblpytest, dataset_path, ReplicatorConflictResolver("delete"), setup_snapshot)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_conflict_merge(self, cblpytest: CBLPyTest, dataset_path: Path):
        def setup_snapshot(updater: SnapshotUpdater):
            updater.upsert_document("_default._default", "name_101", [{"name": [{"first": "Davis", "last": "Smith"}, {"first": "Davis", "last": "Jones"}]}])
            return "Check that the names_101 document `name` property contains `[{'first': 'Davis', 'last': 'Smith'},{'first': 'Davis', 'last': 'Jones'}]`"
        
        await self.do_custom_conflict_test(cblpytest, dataset_path, ReplicatorConflictResolver("merge", {"property": "name"}), setup_snapshot)