from pathlib import Path
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry, ReplicatorType, \
    ReplicatorBasicAuthenticator, ReplicatorActivityLevel
from cbltest.api.cbltestclass import CBLTestClass
import pytest

class TestReplicationBehavior(CBLTestClass):
    @pytest.mark.asyncio
    async def test_pull_empty_database_active_only(self, cblpytest: CBLPyTest, dataset_path: Path):
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Delete name_101 through name_150 on sync gateway")
        all_docs = await cblpytest.sync_gateways[0].get_all_documents("names")
        for i in range(101, 151):
            doc_id = f"name_{i}"
            revid = next(x.revid for x in all_docs.rows if x.id == doc_id)
            await cblpytest.sync_gateways[0].delete_document(doc_id, revid, "names")

        self.mark_test_step("Reset local database, and load `empty` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db("empty", ["db1"])
        db = dbs[0]

        self.mark_test_step('''
            Start a replicator:
                * endpoint: `/names`
                * collections : `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
                * enable_document_listener: true
        ''')
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"),
                                collections=[ReplicatorCollectionEntry(["_default._default"])],
                                replicator_type=ReplicatorType.PULL,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                enable_document_listener=True,
                                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        
        self.mark_test_step("Check that only the 50 non deleted documents were replicated")
        assert len(replicator.document_updates) == 50
        for entry in replicator.document_updates:
            name_number = int(entry.document_id[-3:])
            assert name_number > 150 and name_number <= 200, f"Unexpected document found in replication: {entry.document_id}"