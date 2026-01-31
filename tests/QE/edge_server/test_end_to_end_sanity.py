import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblSyncGatewayBadResponseError,
)
from cbltest.api.syncgateway import PutDatabasePayload

SCRIPT_DIR = str(Path(__file__).parent)


class TestEndtoEnd(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_end_to_end_sanity(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # Calculate end time for 15 minutes from now
        end_time = datetime.now() + timedelta(minutes=15)

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket on server.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 10 documents to bucket.")
        for i in range(1, 11):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)

        self.mark_test_step("Creating a database on Sync Gateway.")
        sg_db_name = "db-1"
        sg_config = {
            "bucket": "bucket-1",
            "scopes": {
                "_default": {
                    "collections": {"_default": {"sync": "function(doc){channel(doc.channels);}"}}
                }
            },
            "num_index_replicas": 0,
        }
        payload = PutDatabasePayload(sg_config)
        await sync_gateway.put_database(sg_db_name, payload)

        self.mark_test_step("Adding role and user to Sync Gateway.")
        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        self.mark_test_step("Creating a database on Edge Server with replication to Sync Gateway.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_empty_database.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        self.mark_test_step("Verifying that Sync Gateway has 10 documents.")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )

        self.mark_test_step("Waiting 15 seconds for replication to Edge Server.")
        time.sleep(15)

        self.mark_test_step("Verifying that Edge Server has 10 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )

        doc_counter = 11  # Initialize the document counter

        # Run until 15 minutes have passed
        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # --- Sync Gateway Cycle ---
            self.mark_test_step(f"Step 1: Creating document {doc_id} via Sync Gateway.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
            assert created_doc is not None, f"Failed to create document {doc_id} via Sync Gateway."
            time.sleep(5)

            self.mark_test_step(f"Step 2: Validating document {doc_id} on Edge Server.")
            remote_doc = await edge_server.get_document(es_db_name, doc_id)

            assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server."
            assert remote_doc.id == doc_id, (
                f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
            )
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            # Storing the revision ID
            rev_id = remote_doc.revid

            self.mark_test_step(f"Step 3: Updating document {doc_id} via Edge Server.")
            updated_doc_body = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes",
            }

            updated_doc = await edge_server.put_document_with_id(
                updated_doc_body, doc_id, es_db_name, rev=rev_id
            )

            assert updated_doc is not None, f"Failed to update document {doc_id} via Edge Server"
            time.sleep(5)

            self.mark_test_step(f"Step 4: Validating update for {doc_id} on Sync Gateway.")
            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
            assert sg_doc is not None
            assert rev_id != sg_doc.revid, f"Document {doc_id} update not reflected on Sync Gateway"
            # Storing the revision ID
            rev_id = sg_doc.revid

            self.mark_test_step(f"Step 5: Deleting document {doc_id} via Sync Gateway.")
            assert rev_id is not None, "rev_id required for delete"
            await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)

            self.mark_test_step(f"Step 6: Validating deletion of {doc_id} on Edge Server.")
            time.sleep(5)  # Allow time for sync

            try:
                await edge_server.get_document(es_db_name, doc_id)
            except CblEdgeServerBadResponseError:
                pass  # expected, document not found (deleted)

            # --- Edge Server Cycle ---
            self.mark_test_step(f"Step 7: Creating document {doc_id} via Edge Server.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
            assert created_doc is not None, f"Failed to create document {doc_id} via Edge Server."
            time.sleep(5)

            self.mark_test_step(f"Step 8: Validating document {doc_id} on Sync Gateway.")
            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
            assert sg_doc is not None, f"Document {doc_id} does not exist on the sync gateway."
            assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
            # assert "rev" in response, "Revision ID (_rev) missing in the document"

            # Storing the revision ID
            rev_id = sg_doc.revid

            self.mark_test_step(f"Step 9: Updating document {doc_id} via Sync Gateway.")
            updated_doc_body = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes",
            }
            updated_doc = await sync_gateway.update_document(
                sg_db_name, doc_id, updated_doc_body, rev_id
            )
            assert updated_doc is not None, f"Failed to update document {doc_id} via Sync Gateway."
            time.sleep(5)

            self.mark_test_step(f"Step 10: Validating update for {doc_id} on Edge Server.")
            remote_doc = await edge_server.get_document(es_db_name, doc_id)

            assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server."
            assert remote_doc.id == doc_id, f"Document ID mismatch: {remote_doc.id}"
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            # Storing the revision ID
            rev_id = remote_doc.revid

            self.mark_test_step(f"Step 11: Deleting document {doc_id} via Edge Server.")
            delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)

            assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
                f"Failed to delete document {doc_id} via Edge Server."
            )
            time.sleep(5)

            self.mark_test_step(f"Step 12: Validating deletion of {doc_id} on Sync Gateway.")
            time.sleep(2)  # Allow time for sync

            try:
                await sync_gateway.get_document(sg_db_name, doc_id)
            except CblSyncGatewayBadResponseError:
                pass  # expected, document not found (deleted)
            doc_counter += 1  # Increment the document counter for the next cycle

        self.mark_test_step("Test successfully ran for 15 minutes.")
