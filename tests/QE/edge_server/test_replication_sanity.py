import json
import time
from datetime import datetime
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


class TestReplicationSanity(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_sanity(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
                    "collections": {
                        "_default": {"sync": "function(doc){channel(doc.channels);}"}
                    }
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

        self.mark_test_step(
            "Creating a database on Edge Server with replication to Sync Gateway."
        )
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
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )

        self.mark_test_step("Waiting for replication to Edge Server to be idle.")
        await edge_server.wait_for_idle(timeout=5)

        self.mark_test_step("Verifying that Edge Server has 10 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )

        # Single replication cycle: SG → ES and ES → SG (create, update, delete both ways)
        doc_id_sg = "doc_11"  # Sync Gateway cycle: create on SG, update/delete via ES
        doc_id_es = "doc_12"  # Edge Server cycle: create on ES, update/delete via SG

        # --- Sync Gateway Cycle ---
        self.mark_test_step(f"Creating document {doc_id_sg} via Sync Gateway.")
        doc = {
            "id": doc_id_sg,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        created_doc = await sync_gateway.create_document(sg_db_name, doc_id_sg, doc)
        assert created_doc is not None, (
            f"Failed to create document {doc_id_sg} via Sync Gateway."
        )
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        self.mark_test_step(f"Validating document {doc_id_sg} on Edge Server.")
        remote_doc = await edge_server.get_document(es_db_name, doc_id_sg)

        assert remote_doc is not None, (
            f"Document {doc_id_sg} does not exist on the edge server."
        )
        assert remote_doc.id == doc_id_sg, (
            f"Document ID mismatch: expected {doc_id_sg}, got {remote_doc.id}"
        )

        rev_id = remote_doc.revid

        self.mark_test_step(f"Updating document {doc_id_sg} via Edge Server.")
        updated_doc_body = {
            "id": doc_id_sg,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
            "changed": "yes",
        }

        updated_doc = await edge_server.put_document_with_id(
            updated_doc_body, doc_id_sg, es_db_name, rev=rev_id
        )

        assert updated_doc is not None, (
            f"Failed to update document {doc_id_sg} via Edge Server"
        )
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        self.mark_test_step(f"Validating update for {doc_id_sg} on Sync Gateway.")
        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id_sg)
        assert sg_doc is not None
        assert rev_id != sg_doc.revid, (
            f"Document {doc_id_sg} update not reflected on Sync Gateway"
        )
        rev_id = sg_doc.revid

        self.mark_test_step(f"Deleting document {doc_id_sg} via Sync Gateway.")
        assert rev_id is not None, "rev_id required for delete"
        await sync_gateway.delete_document(doc_id_sg, rev_id, sg_db_name)

        self.mark_test_step(f"Validating deletion of {doc_id_sg} on Edge Server.")
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, doc_id_sg)

        # --- Edge Server Cycle ---
        self.mark_test_step(f"Creating document {doc_id_es} via Edge Server.")
        doc = {
            "id": doc_id_es,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        created_doc = await edge_server.put_document_with_id(doc, doc_id_es, es_db_name)
        assert created_doc is not None, (
            f"Failed to create document {doc_id_es} via Edge Server."
        )
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        self.mark_test_step(f"Validating document {doc_id_es} on Sync Gateway.")
        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id_es)
        assert sg_doc is not None, (
            f"Document {doc_id_es} does not exist on the sync gateway."
        )
        assert sg_doc.id == doc_id_es, f"Document ID mismatch: {sg_doc.id}"

        rev_id = sg_doc.revid

        self.mark_test_step(f"Updating document {doc_id_es} via Sync Gateway.")
        updated_doc_body = {
            "id": doc_id_es,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
            "changed": "yes",
        }
        updated_doc = await sync_gateway.update_document(
            sg_db_name, doc_id_es, updated_doc_body, rev_id
        )
        assert updated_doc is not None, (
            f"Failed to update document {doc_id_es} via Sync Gateway."
        )
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        self.mark_test_step(f"Validating update for {doc_id_es} on Edge Server.")
        remote_doc = await edge_server.get_document(es_db_name, doc_id_es)

        assert remote_doc is not None, (
            f"Document {doc_id_es} does not exist on the edge server."
        )
        assert remote_doc.id == doc_id_es, f"Document ID mismatch: {remote_doc.id}"

        rev_id = remote_doc.revid

        self.mark_test_step(f"Deleting document {doc_id_es} via Edge Server.")
        delete_resp = await edge_server.delete_document(doc_id_es, rev_id, es_db_name)

        assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
            f"Failed to delete document {doc_id_es} via Edge Server."
        )
        # Allow replication to propagate before validating (eventual consistency).
        time.sleep(5)

        self.mark_test_step(f"Validating deletion of {doc_id_es} on Sync Gateway.")

        with pytest.raises(CblSyncGatewayBadResponseError):
            await sync_gateway.get_document(sg_db_name, doc_id_es)
