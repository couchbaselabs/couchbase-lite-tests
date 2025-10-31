from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
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
@pytest.mark.min_couchbase_servers(1)
class TestReplicationBehavior(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_pull_empty_database_active_only(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Delete name_101 through name_150 on sync gateway")
        all_docs = await cblpytest.sync_gateways[0].get_all_documents("names")
        for row in all_docs.rows:
            name_number = int(row.id[-3:])
            if name_number <= 150:
                revid = assert_not_null(row.revid, f"Missing revid on {row.id}")
                await cblpytest.sync_gateways[0].delete_document(row.id, revid, "names")

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
            cblpytest.sync_gateways[0].replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
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
            "Check that only the 50 non deleted documents were replicated"
        )
        assert len(replicator.document_updates) == 50
        for entry in replicator.document_updates:
            name_number = int(entry.document_id[-3:])
            assert name_number > 150 and name_number <= 200, (
                f"Unexpected document found in replication: {entry.document_id}"
            )
