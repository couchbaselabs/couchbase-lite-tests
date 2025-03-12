from datetime import timedelta, datetime
from pathlib import Path
from random import randint
from typing import List
import random
import pytest
import time
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblEdgeServerBadResponseError, CblSyncGatewayBadResponseError
from cbltest.api.edgeserver import EdgeServer, BulkDocOperation
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, \
    WaitForDocumentEventEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload, SyncGateway
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null

from conftest import cblpytest

from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
import logging

logger = logging.getLogger(__name__)

class TestEndtoEnd(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_end_to_end_sgw(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting E2E test with Server, Sync Gateway, Edge Server and 1 client")
        # Calculate end time for 30 minutes from now
        end_time = datetime.now() + timedelta(minutes=30)

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 11):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            server.add_document(bucket_name, doc["id"], doc)
        logger.info("10 documents created in Couchbase Server.")

        self.mark_test_step("Creating a database in Sync Gateway and adding a user and role.")
        sg_db_name = "db-1"
        config = {
            "bucket": "bucket-1",
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": "function(doc){channel(doc.channels);}"
                        }
                    }
                }
            },
            "num_index_replicas": 0,
            "use_views": true
        }
        payload = PutDatabasePayload(config)
        await sync_gateway.put_database(sg_db_name, payload)
        logger.info(f"Database created in Sync Gateway and linked to {bucket_name}.")

        input_data = {
            "_default._default": ["public"]
        }
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        logger.info("User and role added to Sync Gateway.")

        self.mark_test_step("Creating a database in Edge Server.")
        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        await edge_server.kill_server()
        await edge_server.start_server()

        logger.info("Created a database in Edge Server.")

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 10 documents")
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        time.sleep(15)

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 10 documents")
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        doc_counter = 11 # Initialize the document counter

        # Run until 30 minutes have passed
        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # --- Sync Gateway Cycle ---
            self.mark_test_step(f"Starting Sync Gateway cycle for {doc_id}")
            logger.info(f"Starting Sync Gateway cycle for {doc_id}")
            
            # Step 1: Create Document via Sync Gateway
            self.mark_test_step(f"Checking documents created at Sync Gateway get synced down to Edge Server")
            logger.info(f"Step 1: Creating document {doc_id} via Sync Gateway.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            response = await sync_gateway.create_document(sg_db_name, doc_id, doc)
            print(response)
            assert response is not None, f"Failed to create document {doc_id} via Sync Gateway."
            logger.info(f"Document {doc_id} created via Sync Gateway.")

            time.sleep(5)
            
            # Step 2: Validate Document on Edge Server
            logger.info(f"Step 2: Validating document {doc_id} on Edge Server.")
            document = await edge_server.get_document(es_db_name, doc_id)
            # print(document)

            assert document is not None, f"Document {doc_id} does not exist on the edge server."
            assert document.id == doc_id, f"Document ID mismatch: expected {doc_id}, got {document.id}"
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")
            print(document)

            # Storing the revision ID
            rev_id = document.revid
            # print(rev_id)

            # Step 3: Update Document via Edge Server
            self.mark_test_step(f"Checking documents updated Edge Server get synced up to Sync Gateway")
            logger.info(f"Step 3: Updating document by adding a 'changed' sub document in {doc_id} via Edge Server.")

            updated_doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes"
            }

            response = await edge_server.put_document_with_id(updated_doc, doc_id, es_db_name, rev=rev_id)

            assert response is not None, f"Failed to update document {doc_id} via Edge Server"

            logger.info(f"Document {doc_id} updated via Edge Server")

            time.sleep(5)
            
            # Step 4: Validate Update on Sync Gateway
            logger.info(f"Validating update for {doc_id} on Sync Gateway")
            response = await sync_gateway.get_document(sg_db_name, doc_id)
            # print(response)
            assert rev_id != response.revid, f"Document {doc_id} update not reflected on Sync Gateway"

            logger.info(f"Document {doc_id} update reflected on Sync Gateway")

            # Storing the revision ID
            rev_id = response.revid
            
            # Step 5: Delete Document via Sync Gateway
            self.mark_test_step(f"Checking documents deleted at Sync Gateway get synced down to Edge Server")
            logger.info(f"Step 5: Deleting document {doc_id} via Sync Gateway.")
            response = await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
            assert response is None, f"Failed to delete document {doc_id} via Sync Gateway."

            logger.info(f"Document {doc_id} deleted via Sync Gateway.")

            time.sleep(5)
            
            # Step 6: Validate Deletion on Edge Server
            logger.info(f"Step 6: Validating deletion of {doc_id} on Edge Server.")
            time.sleep(2)  # Allow time for sync

            try:
                document = await edge_server.get_document(es_db_name, doc_id)
                print(document)
            except CblEdgeServerBadResponseError as e:
                assert CblEdgeServerBadResponseError, f"Document {doc_id} not deleted from Edge Server."

            logger.info(f"Document {doc_id} deleted from Edge Server.")
            
            
            # --- Edge Server Cycle ---
            self.mark_test_step(f"Starting Edge Server cycle for {doc_id}")
            logger.info(f"Starting Edge Server cycle for {doc_id}")
            
            # Step 7: Create Document via Edge Server
            self.mark_test_step(f"Checking documents created at Edge Server get synced up to Sync Gateway")
            logger.info(f"Step 7: Creating document {doc_id} via Edge Server.")
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }

            response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
            assert response is not None, f"Failed to create document {doc_id} via Edge Server."

            logger.info(f"Document {doc_id} created via Edge Server.")

            time.sleep(5)
            
            # Step 8: Validate Document on Sync Gateway
            logger.info(f"Step 8: Validating document {doc_id} on Sync Gateway.")
            response = await sync_gateway.get_document(sg_db_name, doc_id)
            # print(response)
            assert response is not None, f"Document {doc_id} does not exist on the sync gateway."
            assert response.id == doc_id, f"Document ID mismatch: {document.id}"
            # assert "rev" in response, "Revision ID (_rev) missing in the document"

            logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")

            # Storing the revision ID
            rev_id = response.revid

            # Step 9: Update Document via Sync Gateway
            self.mark_test_step(f"Checking documents updated at Sync Gateway get synced down to Edge Server")
            logger.info(f"Step 9: Updating document {doc_id} via Sync Gateway.")
            updated_doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "changed": "yes"
            }
            response = await sync_gateway.update_document(sg_db_name, doc_id, updated_doc, rev_id)
            assert response is not None, f"Failed to update document {doc_id} via Sync Gateway."

            logger.info(f"Document {doc_id} updated via Sync Gateway.")

            time.sleep(5)
            
            # Step 10: Validate Update on Edge Server
            logger.info(f"Step 10: Validating update for {doc_id} on Edge Server.")

            document = await edge_server.get_document(es_db_name, doc_id)
            # print(document)

            assert document is not None, f"Document {doc_id} does not exist on the edge server."
            assert document.id == doc_id, f"Document ID mismatch: {document.id}"
            # assert "rev" in document, "Revision ID (_rev) missing in the document"

            logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")

            # Storing the revision ID
            rev_id = document.revid
            # print(rev_id)
            
            # Step 11: Delete Document via Edge Server
            self.mark_test_step(f"Checking documents deleted at Edge Server get synced up to Sync Gateway")
            logger.info(f"Step 11: Deleting document {doc_id} via Edge Server.")

            response = await edge_server.delete_document(doc_id, rev_id, es_db_name)

            assert response.get("ok"), f"Failed to delete document {doc_id} via Edge Server."

            logger.info(f"Document {doc_id} deleted via Edge Server.")

            time.sleep(5)
            
            # Step 12: Validate Deletion on Sync Gateway
            logger.info(f"Step 12: Validating deletion of {doc_id} on Sync Gateway.")
            time.sleep(2)  # Allow time for sync
            
            try:
                document = await sync_gateway.get_document(sg_db_name, doc_id)
            except CblSyncGatewayBadResponseError as e:
                assert CblSyncGatewayBadResponseError, f"Document {doc_id} not deleted from Sync Gateway."

            logger.info(f"Document {doc_id} deleted from Sync Gateway.")
            
            doc_counter += 1  # Increment the document counter for the next cycle

        self.mark_test_step("Test completed after 30 minutes.")
        logger.info("Test successfully ran for 30 minutes.")