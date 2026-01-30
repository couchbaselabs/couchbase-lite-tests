import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblSyncGatewayBadResponseError,
)
from cbltest.api.syncgateway import PutDatabasePayload

logger = logging.getLogger(__name__)
SCRIPT_DIR = str(Path(__file__).parent)


class TestEndtoEnd(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_end_to_end_sgw(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting E2E test with Server, Sync Gateway, Edge Server and 1 client"
        )
        # Calculate end time for 30 minutes from now
        end_time = datetime.now() + timedelta(minutes=30)

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 11):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)
        logger.info("10 documents created in Couchbase Server.")

        self.mark_test_step(
            "Creating a database in Sync Gateway and adding a user and role."
        )
        sg_db_name = "db-1"
        config = {
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
        payload = PutDatabasePayload(config)
        await sync_gateway.put_database(sg_db_name, payload)
        logger.info(f"Database created in Sync Gateway and linked to {bucket_name}.")

        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        logger.info("User and role added to Sync Gateway.")

        self.mark_test_step("Configure Edge Server with replication to Sync Gateway.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_empty_database.json"
        with open(config_path) as file:
            config = cast(dict[str, Any], json.load(file))
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        logger.info("Edge Server configured with replication to Sync Gateway.")

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step(
            "Verifying initial synchronization from Couchbase Server to Edge Server."
        )

        logger.info(
            "Checking initial document sync from Couchbase Server to Sync Gateway..."
        )
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )

        self.mark_test_step("Check that Sync Gateway has 10 documents")
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Sync Gateway initially."
        )

        time.sleep(15)

        logger.info(
            "Checking initial document sync from Sync Gateway to Edge Server..."
        )
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 10 documents")
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Edge Server initially."
        )

        doc_counter = 11  # Initialize the document counter

        # Run until 30 minutes have passed
        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # --- Sync Gateway Cycle ---
            self.mark_test_step(f"Starting Sync Gateway cycle for {doc_id}")
            logger.info(f"Starting Sync Gateway cycle for {doc_id}")

            # Step 1: Create Document via Sync Gateway
            self.mark_test_step(
                "Checking documents created at Sync Gateway get synced down to Edge Server"
            )
            logger.info(f"Step 1: Creating document {doc_id} via Sync Gateway.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
            assert created_doc is not None, (
                f"Failed to create document {doc_id} via Sync Gateway."
            )
            logger.info(f"Document {doc_id} created via Sync Gateway.")

            time.sleep(5)

            # Step 2: Validate Document on Edge Server
            logger.info(f"Step 2: Validating document {doc_id} on Edge Server.")
            remote_doc = await edge_server.get_document(es_db_name, doc_id)

            assert remote_doc is not None, (
                f"Document {doc_id} does not exist on the edge server."
            )
            assert remote_doc.id == doc_id, (
                f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
            )
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            logger.info(
                f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
            )

            # Storing the revision ID
            rev_id = remote_doc.revid

            # Step 3: Update Document via Edge Server
            self.mark_test_step(
                "Checking documents updated Edge Server get synced up to Sync Gateway"
            )
            logger.info(
                f"Step 3: Updating document by adding a 'changed' sub document in {doc_id} via Edge Server."
            )

            updated_doc_body = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes",
            }

            updated_doc = await edge_server.put_document_with_id(
                updated_doc_body, doc_id, es_db_name, rev=rev_id
            )

            assert updated_doc is not None, (
                f"Failed to update document {doc_id} via Edge Server"
            )

            logger.info(f"Document {doc_id} updated via Edge Server")

            time.sleep(5)

            # Step 4: Validate Update on Sync Gateway
            logger.info(f"Validating update for {doc_id} on Sync Gateway")
            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
            assert sg_doc is not None
            assert rev_id != sg_doc.revid, (
                f"Document {doc_id} update not reflected on Sync Gateway"
            )

            logger.info(f"Document {doc_id} update reflected on Sync Gateway")

            # Storing the revision ID
            rev_id = sg_doc.revid

            # Step 5: Delete Document via Sync Gateway
            self.mark_test_step(
                "Checking documents deleted at Sync Gateway get synced down to Edge Server"
            )
            logger.info(f"Step 5: Deleting document {doc_id} via Sync Gateway.")
            assert rev_id is not None, "rev_id required for delete"
            del_result = await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
            assert del_result is None, (
                f"Failed to delete document {doc_id} via Sync Gateway."
            )

            logger.info(f"Document {doc_id} deleted via Sync Gateway.")

            time.sleep(5)

            # Step 6: Validate Deletion on Edge Server
            logger.info(f"Step 6: Validating deletion of {doc_id} on Edge Server.")
            time.sleep(2)  # Allow time for sync

            try:
                await edge_server.get_document(es_db_name, doc_id)
            except CblEdgeServerBadResponseError:
                pass  # expected, document not found (deleted)

            logger.info(f"Document {doc_id} deleted from Edge Server.")

            # --- Edge Server Cycle ---
            self.mark_test_step(f"Starting Edge Server cycle for {doc_id}")
            logger.info(f"Starting Edge Server cycle for {doc_id}")

            # Step 7: Create Document via Edge Server
            self.mark_test_step(
                "Checking documents created at Edge Server get synced up to Sync Gateway"
            )
            logger.info(f"Step 7: Creating document {doc_id} via Edge Server.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            created_doc = await edge_server.put_document_with_id(
                doc, doc_id, es_db_name
            )
            assert created_doc is not None, (
                f"Failed to create document {doc_id} via Edge Server."
            )

            logger.info(f"Document {doc_id} created via Edge Server.")

            time.sleep(5)

            # Step 8: Validate Document on Sync Gateway
            logger.info(f"Step 8: Validating document {doc_id} on Sync Gateway.")
            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
            assert sg_doc is not None, (
                f"Document {doc_id} does not exist on the sync gateway."
            )
            assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
            # assert "rev" in response, "Revision ID (_rev) missing in the document"

            logger.info(
                f"Document {doc_id} fetched successfully from edge server with data: {sg_doc}"
            )

            # Storing the revision ID
            rev_id = sg_doc.revid

            # Step 9: Update Document via Sync Gateway
            self.mark_test_step(
                "Checking documents updated at Sync Gateway get synced down to Edge Server"
            )
            logger.info(f"Step 9: Updating document {doc_id} via Sync Gateway.")
            updated_doc_body = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes",
            }
            updated_doc = await sync_gateway.update_document(
                sg_db_name, doc_id, updated_doc_body, rev_id
            )
            assert updated_doc is not None, (
                f"Failed to update document {doc_id} via Sync Gateway."
            )

            logger.info(f"Document {doc_id} updated via Sync Gateway.")

            time.sleep(5)

            # Step 10: Validate Update on Edge Server
            logger.info(f"Step 10: Validating update for {doc_id} on Edge Server.")

            remote_doc = await edge_server.get_document(es_db_name, doc_id)

            assert remote_doc is not None, (
                f"Document {doc_id} does not exist on the edge server."
            )
            assert remote_doc.id == doc_id, f"Document ID mismatch: {remote_doc.id}"
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            logger.info(
                f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
            )

            # Storing the revision ID
            rev_id = remote_doc.revid

            # Step 11: Delete Document via Edge Server
            self.mark_test_step(
                "Checking documents deleted at Edge Server get synced up to Sync Gateway"
            )
            logger.info(f"Step 11: Deleting document {doc_id} via Edge Server.")

            delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)

            assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
                f"Failed to delete document {doc_id} via Edge Server."
            )

            logger.info(f"Document {doc_id} deleted via Edge Server.")

            time.sleep(5)

            # Step 12: Validate Deletion on Sync Gateway
            logger.info(f"Step 12: Validating deletion of {doc_id} on Sync Gateway.")
            time.sleep(2)  # Allow time for sync

            try:
                await sync_gateway.get_document(sg_db_name, doc_id)
            except CblSyncGatewayBadResponseError:
                pass  # expected, document not found (deleted)

            logger.info(f"Document {doc_id} deleted from Sync Gateway.")

            doc_counter += 1  # Increment the document counter for the next cycle

        self.mark_test_step("Test completed after 30 minutes.")
        logger.info("Test successfully ran for 30 minutes.")
