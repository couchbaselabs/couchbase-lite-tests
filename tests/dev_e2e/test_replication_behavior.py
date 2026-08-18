from pathlib import Path

import pytest
import tenacity
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
from cbltest.utils import assert_not_null, retry_assert


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestReplicationBehavior(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_empty_database_active_only(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Delete name_101 through name_150 on sync gateway")
        all_docs = await sync_gateway.get_all_documents("names")
        for row in all_docs.rows:
            name_number = int(row.id[-3:])
            if name_number <= 150:
                revid = assert_not_null(row.revid, f"Missing revid on {row.id}")
                await sync_gateway.delete_document(row.id, revid, "names")

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

        self.mark_test_step(f"Wait until Sync Gateway has imported the resurrected `{loc_deleted}`")

        async def _confirm_resurrected_on_sg() -> None:
            remote_doc = await sync_gateway.get_document("names", loc_deleted)
            assert remote_doc is not None, f"{loc_deleted} not yet visible on Sync Gateway"
            assert remote_doc.body.get("name") == resurrected_body["name"], (
                f"{loc_deleted} on Sync Gateway does not reflect the resurrected content yet"
            )

        await retry_assert(_confirm_resurrected_on_sg, tenacity.wait_fixed(1), tenacity.stop_after_attempt(15))

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
