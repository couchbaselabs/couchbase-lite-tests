from datetime import timedelta, datetime
from pathlib import Path
from random import randint
from typing import List
import random
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, \
    WaitForDocumentEventEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload, SyncGateway
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null

from cbltest.api.edgeserver import EdgeServer, BulkDocOperation
from conftest import cblpytest

class TestEndtoEnd(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_end_to_end_sgw(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting E2E test with Server, Sync Gateway, Edge Server and 1 client")
        # Calculate end time for 30 minutes from now
        end_time = datetime.now() + timedelta(minutes=30)

        doc_counter = 1  # Initialize the document counter

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cloud.__couchbase_server
        sync_gateway = cloud.__sync_gateway

        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 11):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            server.add_document(bucket_name, doc["id"], doc)

        config = {
            "bucket": "bucket-1",
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": True
                        }
                    }
                }
            }
        }
        payload = PutDatabasePayload(config)
        await sync_gateway.put_database("db-1", payload)

        input_data = {
            "_default._default": ["public"]
        }
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role("db-1", "stdrole", access_dict)
        await sync_gateway.add_user("db-1", "sync_gateway", "password", access_dict)

        # Add 10 docs server side
        # Have sync gateway user and role created
        # Have edge server database created

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        # Run until 30 minutes have passed
        # while datetime.now() < end_time:
        #     # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        #     self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")
        #     logger.info("Checking initial document sync from Couchbase Server to Edge Server...")
            
        #     initial_docs = requests.get(f"{BASE_URL}/docs").json()
        #     assert len(initial_docs) == 10, "Initial documents not synced correctly from Couchbase Server to Edge Server."
        #     logger.info(f"Found {len(initial_docs)} documents synced to Edge Server initially.")

        #     # Step 1: Create Document via Sync Gateway
        #     self.mark_test_step(f"Creating document doc_{doc_counter} via Sync Gateway.")
        #     logger.info(f"Creating a new document (doc_{doc_counter}) via Sync Gateway...")
        #     doc = {
        #         "id": f"doc_{doc_counter}",
        #         "channels": ["public"],
        #         "timestamp": datetime.utcnow().isoformat()
        #     }
        #     response = create_doc_sync_gateway(doc)
        #     assert response.status_code == 201, f"Failed to create document doc_{doc_counter} via Sync Gateway."
            
        #     # Wait for the document to sync to Edge Server
        #     logger.info("Waiting for document sync to Edge Server...")
        #     time.sleep(2)
        #     edge_docs = requests.get(f"{BASE_URL}/docs").json()
        #     assert any(doc['id'] == f"doc_{doc_counter}" for doc in edge_docs), f"Document doc_{doc_counter} created via Sync Gateway not synced to Edge Server."
        #     logger.info(f"Document doc_{doc_counter} created via Sync Gateway synced to Edge Server successfully.")

        #     # Step 2: Update Document via HTTP Client (Edge Server)
        #     self.mark_test_step(f"Updating document doc_{doc_counter} via HTTP Client (Edge Server).")
        #     logger.info(f"Updating document (doc_{doc_counter}) via HTTP Client (Edge Server)...")
        #     updated_doc = {
        #         "id": f"doc_{doc_counter}",
        #         "channels": ["public"],
        #         "timestamp": datetime.utcnow().isoformat()
        #     }
        #     response = update_doc_edge_server(f"doc_{doc_counter}", updated_doc)
        #     assert response.status_code == 200, f"Failed to update document doc_{doc_counter} via Edge Server."
            
        #     # Wait for the update to reflect on Sync Gateway and Couchbase Server
        #     logger.info("Waiting for document update to reflect on Sync Gateway and Couchbase Server...")
        #     time.sleep(2)
        #     edge_docs = requests.get(f"{BASE_URL}/docs").json()
        #     assert any(doc['id'] == f"doc_{doc_counter}" and doc['timestamp'] == updated_doc['timestamp'] for doc in edge_docs), f"Updated document doc_{doc_counter} via Edge Server not reflected on Edge Server."
        #     logger.info(f"Document doc_{doc_counter} updated via Edge Server synced successfully.")

        #     # Step 3: Delete Document via Sync Gateway
        #     self.mark_test_step(f"Deleting document doc_{doc_counter} via Sync Gateway.")
        #     logger.info(f"Deleting document (doc_{doc_counter}) via Sync Gateway...")
        #     response = delete_doc_sync_gateway(f"doc_{doc_counter}")
        #     assert response.status_code == 200, f"Failed to delete document doc_{doc_counter} via Sync Gateway."
            
        #     # Wait for the document to be deleted on Edge Server
        #     logger.info("Waiting for document deletion to reflect on Edge Server...")
        #     time.sleep(2)
        #     edge_docs = requests.get(f"{BASE_URL}/docs").json()
        #     assert not any(doc['id'] == f"doc_{doc_counter}" for doc in edge_docs), f"Document doc_{doc_counter} deleted via Sync Gateway not removed from Edge Server."
        #     logger.info(f"Document doc_{doc_counter} deleted via Sync Gateway removed from Edge Server successfully.")

        #     # Step 4: Delete Document via HTTP Client (Edge Server)
        #     self.mark_test_step(f"Deleting document doc_{doc_counter} via HTTP Client (Edge Server).")
        #     logger.info(f"Deleting document (doc_{doc_counter}) via HTTP Client (Edge Server)...")
        #     response = delete_doc_edge_server(f"doc_{doc_counter}")
        #     assert response.status_code == 200, f"Failed to delete document doc_{doc_counter} via Edge Server."
            
        #     # Wait for the document to be deleted on Sync Gateway and Couchbase Server
        #     logger.info("Waiting for document deletion to reflect on Sync Gateway and Couchbase Server...")
        #     time.sleep(2)
        #     edge_docs = requests.get(f"{BASE_URL}/docs").json()
        #     assert not any(doc['id'] == f"doc_{doc_counter}" for doc in edge_docs), f"Document doc_{doc_counter} deleted via Edge Server not removed from Edge Server."
        #     logger.info(f"Document doc_{doc_counter} deleted via Edge Server removed from Sync Gateway and Couchbase Server successfully.")

        #     doc_counter += 1  # Increment the document counter for the next cycle

        # logger.info("Test ran for 30 minutes successfully.")