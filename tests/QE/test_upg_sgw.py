import os
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
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
            # cbs.create_collections(bucket, "_sync", ["_default"])

        self.mark_test_step("Configure Sync Gateway database and wait for it to be up")
        # db_config_map = {
        #     "3.2.7": {
        #         "bucket": bucket,
        #         # "enable_shared_bucket_access": True,
        #         "scopes": {"_default": {"collections": {"_default": {}}}},
        #     },
        #     "3.3.3": {
        #         "bucket": bucket,
        #         # "enable_shared_bucket_access": True,
        #         "scopes": {"_default": {"collections": {"_default": {}}}},
        #     },
        #     "4.0.0": {
        #         "bucket": bucket,
        #         "index": {"num_replicas": 0},
        #         "scopes": {"_default": {"collections": {"_default": {}}}},
        #     },
        # }
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

        self.mark_test_step("Verify data persistence on CBS for all docs")
        all_docs_to_verify = await sg.get_all_documents(sg_db, scope, collection)
        for row in all_docs_to_verify.rows:
            print(f"Verifying doc {row.id} on CBS...")  # Debug print
            doc = cbs.get_document(bucket, row.id, scope, collection)
            print(f"Retrieved doc {row.id} from CBS: {doc}")  # Debug print
            assert doc is not None, f"Doc {row.id} not found on CBS"
            assert "version" in doc, f"Doc {row.id} missing 'version' field!"
            assert doc.get("type") == "upgrade_test_doc", (
                f"Doc {row.id} has wrong type! Expected 'upgrade_test_doc', got {doc.get('type')}"
            )
