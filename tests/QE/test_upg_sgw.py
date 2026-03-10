import os
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


@pytest.mark.upg_sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSgwUpgrade(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_and_persistence_after_upgrade(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        """
        This test runs after each SGW upgrade. It performs two key checks:
        1. Ingests a new set of documents to verify that the newly upgraded
           Sync Gateway is functioning correctly.
        2. Verifies that all documents created in *previous* iterations (before
           the upgrade) are still present and correct, ensuring data persistence.
        """
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        current_upgrade_ver = os.environ.get("SGW_VERSION_UNDER_TEST", "0.0.0")
        num_docs_per_iteration = 10
        sg_db = "upg_db"
        bucket = "upg_bucket"
        cbl_db = "upg_sgw_dataset"
        scope = "_default"
        collection = "_default"

        self.mark_test_step(
            f"Running upgrade test version {current_upgrade_ver} "
            f"for SGW DB '{sg_db}' -> CBS '{bucket}.{scope}.{collection}'"
        )
        doc_id_prefix = f"upg_test_{sg_db}_{current_upgrade_ver}"

        self.mark_test_step("Add a bucket on CBS if not there already")
        if bucket not in cbs.get_bucket_names():
            print(f"Bucket '{bucket}' not found on CBS. Creating it for the test...")
            cbs.create_bucket(bucket)

        self.mark_test_step("Load dataset on CBL")
        if not hasattr(self, "db"):
            print(f"Resetting CBL database '{cbl_db}' for the test...")
            self.db = (await cblpytest.test_servers[0].create_and_reset_db([cbl_db]))[0]
        db = self.db

        self.mark_test_step("Configure Sync Gateway database and wait for it to be up")
        stable_upgrade_config = {
            "bucket": bucket,
            "num_index_replicas": 0,
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": """
                                function(doc, oldDoc) {
                                    channel("upgrade");
                                }
                            """
                        }
                    }
                }
            },
            "revs_limit": 1000,
            "import_docs": True,
            "enable_shared_bucket_access": True,
            "delta_sync": {"enabled": True},
        }
        db_payload = PutDatabasePayload(stable_upgrade_config)
        try:
            await sg.put_database(sg_db, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise e
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step("Create user1 for replication")
        collection_access = sg.create_collection_access_dict(
            {"_default._default": ["*"]}
        )
        await sg.add_user(sg_db, "user1", "pass", collection_access)

        self.mark_test_step("Add documents to SGW for this version")
        sg_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs_per_iteration):
            sg_docs.append(
                DocumentUpdateEntry(
                    f"{doc_id_prefix}_{i}",
                    None,
                    body={
                        "type": "upgrade_test_doc",
                        "version": current_upgrade_ver,
                        "index": i,
                        "message": "SGW upgrade test document.",
                    },
                )
            )
        await sg.update_documents(sg_db, sg_docs)

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/upg_sgw_dataset`
                * collections: `_default._default`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify data persistence on CBS and CBL for all docs")
        all_docs_to_verify = await sg.get_all_documents(sg_db, scope, collection)
        for row in all_docs_to_verify.rows:
            doc = cbs.get_document(bucket, row.id, scope, collection)
            print(f"Retrieved doc {row.id} from CBS: {doc}")
            assert doc is not None, f"Doc {row.id} not found on CBS"
            assert "version" in doc, f"Doc {row.id} missing 'version' field!"
            assert doc.get("type") == "upgrade_test_doc", (
                f"Doc {row.id} has wrong type! Expected 'upgrade_test_doc', got {doc.get('type')}"
            )
            cbl_doc = await db.get_document(DocumentEntry("_default._default", row.id))
            print(f"Retrieved doc {row.id} from CBL: {cbl_doc}")
            assert cbl_doc is not None, f"Doc {row.id} not found on CBL"
            assert "version" in cbl_doc.body, (
                f"Doc {row.id} missing 'version' field on CBL!"
            )
            assert cbl_doc.body.get("type") == "upgrade_test_doc", (
                f"Doc {row.id} has wrong type on CBL! Expected 'upgrade_test_doc', got {cbl_doc.body.get('type')}"
            )
