from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.utils import assert_not_null


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestReplicationBehavior(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_empty_database_active_only(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Delete name_001 through name_150 on sync gateway")
        all_docs = await sync_gateway.get_all_documents("names")
        to_delete = [row for row in all_docs.rows if int(row.id[-3:]) <= 150]
        assert to_delete, "The names dataset carries no documents to delete"
        for row in to_delete[:-1]:
            revid = assert_not_null(row.revid, f"Missing revid on {row.id}")
            await sync_gateway.delete_document(row.id, revid, "names")

        # Only the last tombstone is read back from the changes feed: a `request_plus` feed waits
        # for the cache to catch up to every sequence allocated before the request, so the sequence
        # of the newest delete covers the ones before it.
        last = to_delete[-1]
        tombstone = await sync_gateway.delete_document(
            last.id,
            assert_not_null(last.revid, f"Missing revid on {last.id}"),
            "names",
            wait_for_caching_feed=True,
        )

        self.mark_test_step("Wait until every Sync Gateway node serves the deletes")
        await cloud.sync_gateway_cluster.wait_for_sequence("names", tombstone.seq)

        self.mark_test_step("Reset local database, and load `empty` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: true
        """)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that only the 50 non deleted documents were replicated")
        assert len(replicator.document_updates) == 50
        for entry in replicator.document_updates:
            name_number = int(entry.document_id[-3:])
            assert name_number > 150 and name_number <= 200, (
                f"Unexpected document found in replication: {entry.document_id}"
            )

    @pytest.mark.min_couchbase_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_resurrected_doc(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.2.0")

        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database and load `names` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: true
        """)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        loc_deleted = "name_50"
        self.mark_test_step(f"Delete `{loc_deleted}` in the local database.")
        snapshot = await db.create_snapshot([DocumentEntry("_default._default", loc_deleted)])
        async with db.batch_updater() as b:
            b.delete_document("_default._default", loc_deleted)

        self.mark_test_step(f"Assert `{loc_deleted}`,  is `deleted`")
        snapshot_updater = SnapshotUpdater(snapshot)
        snapshot_updater.delete_document("_default._default", loc_deleted)
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result, f"{loc_deleted} was not deleted locally: {verify_result.description}"

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: true
        """)
        replicator.clear_document_updates()
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #2: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(f"Resurrect `{loc_deleted}` in CBS")
        resurrected_body = {
            "name": {"first": "Resurrected", "last": "Fifty"},
            "collection": "_default",
            "scope": "_default",
        }
        cloud.couchbase_servers[0].upsert_document("names", loc_deleted, resurrected_body)

        self.mark_test_step(
            f"Read `{loc_deleted}` on Sync Gateway, which imports the resurrected document on demand, "
            "and wait for that import to reach the changes feed"
        )

        # The admin read performs the on-demand import itself, so the resurrected body comes back
        # from this call; wait_for_caching_feed then holds until a replicator would see it too.
        remote_doc = await sync_gateway.get_document("names", loc_deleted, wait_for_caching_feed=True)
        assert remote_doc.body.get("name") == resurrected_body["name"], (
            f"{loc_deleted} on Sync Gateway does not reflect the resurrected content: {remote_doc.body}"
        )

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: true
        """)
        pull_replicator = Replicator(
            db,
            sync_gateway.replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await pull_replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await pull_replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator #3: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(f"Check `{loc_deleted}` is not `deleted`")
        # Before the fix for CBL-7841, pulling the resurrected revision over a local tombstone was
        # inappropriately treated as a conflict, and the default conflict resolver kept the local (deleted)
        # revision -- silently discarding the resurrection. The assertion below would have failed in
        # that case; its passing confirms the resurrected revision is applied directly, with no conflict
        # resolver involved.
        local_doc = await db.get_document(DocumentEntry("_default._default", loc_deleted))
        assert local_doc.body.get("name") == resurrected_body["name"], (
            f"{loc_deleted} was not resurrected locally as expected: {local_doc.body}"
        )
