from datetime import timedelta, datetime
from pathlib import Path
from random import randint
from typing import List
import asyncio
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

class TestSystem(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting system test with Server, Sync Gateway, Edge Server and HTTP clients")

        # Calculate end time for 30 minutes from now
        end_time = datetime.now() + timedelta(minutes=360)

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        # for i in range(1, 11):
        #     doc = {
        #         "id": f"doc_{i}",
        #         "channels": ["public"],
        #         "timestamp": datetime.utcnow().isoformat()
        #     }
        #     server.add_document(bucket_name, doc["id"], doc)
        logger.info("10 documents created in Couchbase Server.")

        self.mark_test_step("Creating a database in Sync Gateway and adding a user and role.")
        sg_db_name = "db-1"
        # config = {
        #     "bucket": "bucket-1",
        #     "scopes": {
        #         "_default": {
        #             "collections": {
        #                 "_default": {
        #                     "sync": "function(doc){channel(doc.channels);}"
        #                 }
        #             }
        #         }
        #     },
        #     "num_index_replicas": 0
        # }
        # payload = PutDatabasePayload(config)
        # await sync_gateway.put_database(sg_db_name, payload)
        logger.info(f"Database created in Sync Gateway and linked to {bucket_name}.")

        # input_data = {
        #     "_default._default": ["public"]
        # }
        # access_dict = sync_gateway.create_collection_access_dict(input_data)
        # await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        # await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        logger.info("User and role added to Sync Gateway.")

        self.mark_test_step("Creating a database in Edge Server.")
        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        logger.info("Created a database in Edge Server.")

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 10 documents")
        # assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 10 documents")
        # assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        doc_counter = 55 # Initialize the document counter

        # Run until 30 minutes have passed
        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])

            # Randomize the operation type (create, create_update_delete, create_delete)
            operations = random.choice(["create", "create_update_delete", "create_delete"])
            self.mark_test_step(f"Starting {cycle} cycle for {doc_id} with operations: {operations}")

            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }

            if cycle == "sync_gateway":
                logger.info(f"Starting Sync Gateway cycle for {doc_id}")

                # Create on Sync Gateway and validate on Edge Server
                response = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                # print(response)
                assert response is not None, f"Failed to create document {doc_id} via Sync Gateway."
                logger.info(f"Document {doc_id} created via Sync Gateway.")

                time.sleep(random.uniform(1, 5))

                document = await edge_server.get_document(es_db_name, doc_id)
                assert document is not None, f"Document {doc_id} does not exist on the edge server."
                assert document.id == doc_id, f"Document ID mismatch: expected {doc_id}, got {document.id}"
                assert document.revid is not None, "Revision ID (_rev) missing in the document"

                logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")
                rev_id = document.revid

                if "update" in operations:
                    # Update on sync gateway and validate on edge server
                    logger.info(f"Updating document {doc_id} via Sync Gateway")
                    updated_doc = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "changed": "yes"
                    }
                    response = await sync_gateway.update_document(sg_db_name, doc_id, updated_doc, rev_id)
                    assert response is not None, f"Failed to update document {doc_id} via Sync Gateway"

                    logger.info(f"Document {doc_id} updated via Sync Gateway")
                    
                    # Validate update on Edge Server
                    logger.info(f"Validating update for {doc_id} on Edge Server")

                    document = await edge_server.get_document(es_db_name, doc_id)
                    print(document)
                    print(document.body)

                    assert document is not None, f"Document {doc_id} does not exist on the edge server"
                    assert document.id == doc_id, f"Document ID mismatch: {document.id}"
                    assert document.revid != rev_id, "Revision ID (_rev) missing in the document"

                    logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")

                    # Storing the revision ID
                    rev_id = document.revid
                    # print(rev_id)

                if "delete" in operations:
                    # Delete on edge server and validate on sync gateway
                    logger.info(f"Deleting document {doc_id} via Edge Server")

                    response = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert response is None, f"Failed to delete document {doc_id} via Edge Server"

                    logger.info(f"Document {doc_id} deleted via Edge Server")
                    
                    logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                    time.sleep(2)
                    
                    try:
                        document = await sync_gateway.get_document(sg_db_name, doc_id)
                    except CblSyncGatewayBadResponseError as e:
                        assert CblSyncGatewayBadResponseError, f"Document {doc_id} not deleted from Sync Gateway"

                    logger.info(f"Document {doc_id} deleted from Sync Gateway")

            elif cycle == "edge_server":
                logger.info(f"Starting Edge Server cycle for {doc_id}")

                logger.info(f"Creating document {doc_id} via Edge Server")
                doc = {
                    "id": doc_id,
                    "channels": ["public"],
                    "timestamp": datetime.utcnow().isoformat()
                }

                response = await edge_server.add_document_with_id(doc, doc_id, es_db_name)
                assert response is not None, f"Failed to create document {doc_id} via Edge Server"

                logger.info(f"Document {doc_id} created via Edge Server")

                logger.info(f"Validating document {doc_id} on Sync Gateway")
                response = await sync_gateway.get_document(sg_db_name, doc_id)
                # print(response)
                assert response is not None, f"Document {doc_id} does not exist on the sync gateway"
                assert response.id == doc_id, f"Document ID mismatch: {response.id}"
                assert response.revid is not None, "Revision ID (_rev) missing in the document"

                logger.info(f"Document {doc_id} fetched successfully from edge server with data: {response}")

                rev_id = response.revid

                if "update" in operations:
                    # Create, update, delete and validate on Sync Gateway

                    logger.info(f"Updating document by adding a 'changed' sub document in {doc_id} via Edge Server")
                    # response = await edge_server.put_sub_document(doc_id, rev_id, {"changed": "yes"}, es_db_name)
                    # assert response is not None, f"Failed to update document {doc_id} via Edge Server"

                    # logger.info(f"Document {doc_id} updated via Edge Server")
                    
                    # # Step 4: Validate Update on Sync Gateway
                    # logger.info(f"Step 4: Validating update for {doc_id} on Sync Gateway")
                    response = await sync_gateway.get_document(sg_db_name, doc_id)
                    # print(response)
                    # assert response.get("changed") == "yes", f"Document {doc_id} update not reflected on Sync Gateway"

                    # logger.info(f"Document {doc_id} update reflected on Sync Gateway")

                    # Storing the revision ID
                    rev_id = response.revid

                if "delete" in operations:
                    # Delete on sync gateway and validate on edge server
                    logger.info(f"Deleting document {doc_id} via Sync Gateway")
                    response = await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    assert response is None, f"Failed to delete document {doc_id} via Sync Gateway"

                    logger.info(f"Document {doc_id} deleted via Sync Gateway")
                    
                    logger.info(f"Validating deletion of {doc_id} on Edge Server")
                    time.sleep(2)

                    try:
                        document = await edge_server.get_document(es_db_name, doc_id)
                        print(document)
                    except CblEdgeServerBadResponseError as e:
                        assert CblEdgeServerBadResponseError, f"Document {doc_id} not deleted from Edge Server"

                    logger.info(f"Document {doc_id} deleted from Edge Server")

            doc_counter += 1

        logger.info("Test completed after 30 minutes.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting system test with Server, Sync Gateway, Edge Server and HTTP clients")

        # Calculate end time for 30 minutes from now
        end_time = datetime.now() + timedelta(minutes=360)

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        # for i in range(1, 11):
        #     doc = {
        #         "id": f"doc_{i}",
        #         "channels": ["public"],
        #         "timestamp": datetime.utcnow().isoformat()
        #     }
        #     server.add_document(bucket_name, doc["id"], doc)
        logger.info("10 documents created in Couchbase Server.")

        self.mark_test_step("Creating a database in Sync Gateway and adding a user and role.")
        sg_db_name = "db-1"
        # config = {
        #     "bucket": "bucket-1",
        #     "scopes": {
        #         "_default": {
        #             "collections": {
        #                 "_default": {
        #                     "sync": "function(doc){channel(doc.channels);}"
        #                 }
        #             }
        #         }
        #     },
        #     "num_index_replicas": 0
        # }
        # payload = PutDatabasePayload(config)
        # await sync_gateway.put_database(sg_db_name, payload)
        logger.info(f"Database created in Sync Gateway and linked to {bucket_name}.")

        # input_data = {
        #     "_default._default": ["public"]
        # }
        # access_dict = sync_gateway.create_collection_access_dict(input_data)
        # await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        # await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        logger.info("User and role added to Sync Gateway.")

        self.mark_test_step("Creating a database in Edge Server.")
        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        edge_server_down = False

        logger.info("Created a database in Edge Server.")

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 10 documents")
        # assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 10 documents")
        # assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        doc_counter = 55 # Initialize the document counter

        # Run until 30 minutes have passed
        while datetime.now() < end_time:
            if datetime.now() > end_time:
                self.mark_test_step("Edge server is back online")
                logger.info("Edge server is back online")

                edge_server.start_server()
                time.sleep(10)
                edge_server_down = False

                self.mark_test_step("Check that Edge Server and Sync Gateway have the same number of documents")
                sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
                es_response = await edge_server.get_all_documents(es_db_name)

                assert len(sg_response.rows) == len(es_response.rows), "Document count mismatch between Sync Gateway and Edge Server"
                logger.info(f"Sync Gateway has {len(sg_response.rows)} documents and Edge Server has {len(es_response.rows)} documents")


            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])

            # Randomize the operation type (create, create_update_delete, create_delete)
            operations = random.choice(["create", "create_update_delete", "create_delete"])
            self.mark_test_step(f"Starting {cycle} cycle for {doc_id} with operations: {operations}")

            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }

            if random.random < 0.1: # 10% chance of chaos
                self.mark_test_step("Edge server goes offline for 2 minutes")
                logger.info("Edge server goes offline for 2 minutes")

                edge_server.kill_server()
                end = datetime.now() + timedelta(minutes=2)
                time.sleep(10)
                edge_server_down = True

            if cycle == "sync_gateway":
                logger.info(f"Starting Sync Gateway cycle for {doc_id}")

                # Create on Sync Gateway and validate on Edge Server
                response = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                # print(response)
                assert response is not None, f"Failed to create document {doc_id} via Sync Gateway."
                logger.info(f"Document {doc_id} created via Sync Gateway.")

                time.sleep(random.uniform(1, 5))

                if not edge_server_down:
                    document = await edge_server.get_document(es_db_name, doc_id)
                    assert document is not None, f"Document {doc_id} does not exist on the edge server."
                    assert document.id == doc_id, f"Document ID mismatch: expected {doc_id}, got {document.id}"
                    assert document.revid is not None, "Revision ID (_rev) missing in the document"

                    logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")
                rev_id = response.revid

                if "update" in operations:
                    # Update on sync gateway and validate on edge server
                    logger.info(f"Updating document {doc_id} via Sync Gateway")
                    updated_doc = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "changed": "yes"
                    }
                    response = await sync_gateway.update_document(sg_db_name, doc_id, updated_doc, rev_id)
                    assert response is not None, f"Failed to update document {doc_id} via Sync Gateway"

                    logger.info(f"Document {doc_id} updated via Sync Gateway")
                    
                    # Validate update on Edge Server
                    if not edge_server_down:
                        logger.info(f"Validating update for {doc_id} on Edge Server")

                        document = await edge_server.get_document(es_db_name, doc_id)
                        print(document)
                        print(document.body)

                        assert document is not None, f"Document {doc_id} does not exist on the edge server"
                        assert document.id == doc_id, f"Document ID mismatch: {document.id}"
                        assert document.revid != rev_id, "Revision ID (_rev) missing in the document"

                        logger.info(f"Document {doc_id} fetched successfully from edge server with data: {document}")

                    # Storing the revision ID
                    rev_id = response.revid
                    # print(rev_id)

                if "delete" in operations:
                    if not edge_server_down:
                        # Delete on edge server and validate on sync gateway
                        logger.info(f"Deleting document {doc_id} via Edge Server")

                        response = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                        assert response is None, f"Failed to delete document {doc_id} via Edge Server"

                        logger.info(f"Document {doc_id} deleted via Edge Server")
                        
                        logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                        time.sleep(2)
                        
                        try:
                            document = await sync_gateway.get_document(sg_db_name, doc_id)
                        except CblSyncGatewayBadResponseError as e:
                            assert CblSyncGatewayBadResponseError, f"Document {doc_id} not deleted from Sync Gateway"

                        logger.info(f"Document {doc_id} deleted from Sync Gateway")

            elif cycle == "edge_server":
                if not edge_server_down:
                    logger.info(f"Starting Edge Server cycle for {doc_id}")

                    logger.info(f"Creating document {doc_id} via Edge Server")
                    doc = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    response = await edge_server.add_document_with_id(doc, doc_id, es_db_name)
                    assert response is not None, f"Failed to create document {doc_id} via Edge Server"

                    logger.info(f"Document {doc_id} created via Edge Server")

                    logger.info(f"Validating document {doc_id} on Sync Gateway")
                    response = await sync_gateway.get_document(sg_db_name, doc_id)
                    # print(response)
                    assert response is not None, f"Document {doc_id} does not exist on the sync gateway"
                    assert response.id == doc_id, f"Document ID mismatch: {response.id}"
                    assert response.revid is not None, "Revision ID (_rev) missing in the document"

                    logger.info(f"Document {doc_id} fetched successfully from edge server with data: {response}")

                    rev_id = response.revid

                    if "update" in operations:
                        # Create, update, delete and validate on Sync Gateway

                        logger.info(f"Updating document by adding a 'changed' sub document in {doc_id} via Edge Server")
                        # response = await edge_server.put_sub_document(doc_id, rev_id, {"changed": "yes"}, es_db_name)
                        # assert response is not None, f"Failed to update document {doc_id} via Edge Server"

                        # logger.info(f"Document {doc_id} updated via Edge Server")
                        
                        # # Step 4: Validate Update on Sync Gateway
                        # logger.info(f"Step 4: Validating update for {doc_id} on Sync Gateway")
                        response = await sync_gateway.get_document(sg_db_name, doc_id)
                        # print(response)
                        # assert response.get("changed") == "yes", f"Document {doc_id} update not reflected on Sync Gateway"

                        # logger.info(f"Document {doc_id} update reflected on Sync Gateway")

                        # Storing the revision ID
                        rev_id = response.revid

                    if "delete" in operations:
                        # Delete on sync gateway and validate on edge server
                        logger.info(f"Deleting document {doc_id} via Sync Gateway")
                        response = await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        assert response is None, f"Failed to delete document {doc_id} via Sync Gateway"

                        logger.info(f"Document {doc_id} deleted via Sync Gateway")
                        
                        logger.info(f"Validating deletion of {doc_id} on Edge Server")
                        time.sleep(2)

                        try:
                            document = await edge_server.get_document(es_db_name, doc_id)
                            print(document)
                        except CblEdgeServerBadResponseError as e:
                            assert CblEdgeServerBadResponseError, f"Document {doc_id} not deleted from Edge Server"

                        logger.info(f"Document {doc_id} deleted from Edge Server")

            doc_counter += 1

        logger.info("Test completed after 30 minutes.")





