from datetime import datetime
from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload


import logging

logger = logging.getLogger(__name__)

class TestBlobs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_blobs_create_delete(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting Blobs CRUD test with Server, Sync Gateway, Edge Server and 1 client")

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 3):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            server.add_document(bucket_name, doc["id"], doc)
        logger.info("2 documents created in Couchbase Server.")

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
            "num_index_replicas": 0
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

        self.mark_test_step("Check that Sync Gateway has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        self.mark_test_step("Adding a blob to a document in Couchbase Server.")
        doc_id = "doc_2"
        logger.info(f"Adding a blob to document {doc_id} in Couchbase Server.")
        document = await edge_server.get_document(es_db_name, doc_id)

        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test.png"
        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)
        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Blob added to document {doc_id} in Edge Server.")

        # Validate blob on Sync Gateway and Couchbase Server
        self.mark_test_step("Validating blob on Sync Gateway and Couchbase Server.")
        document = await sync_gateway.get_document(sg_db_name, doc_id)
        print(document)
        
        # Assert that the response contains `_attachments` with expected metadata
        assert "_attachments" in document, "Error: '_attachments' field is missing in the document response"
        assert f"blob_/{attachment_name}" in document["_attachments"], f"Error: Attachment '{attachment_name}' not found in '_attachments'"

        blob_metadata = document["_attachments"][f"blob_/{attachment_name}"]
        assert blob_metadata["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_metadata['content_type']}'"
        assert "digest" in blob_metadata, "Error: 'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "Error: 'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, f"Error: Blob length is invalid ({blob_metadata['length']})"

        # Assert that the blob is also referenced in the document body
        assert attachment_name in document, f"Error: '{attachment_name}' not found in document body"
        blob_info = document[attachment_name]
        assert blob_info["@type"] == "blob", f"Error: Expected '@type'='blob', but got '{blob_info.get('@type')}'"
        assert blob_info["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_info['content_type']}'"
        assert blob_info["digest"] == blob_metadata["digest"], f"Error: Blob digest mismatch, expected '{blob_metadata['digest']}', got '{blob_info['digest']}'"
        assert blob_info["length"] == blob_metadata["length"], f"Error: Blob length mismatch, expected '{blob_metadata['length']}', got '{blob_info['length']}'"

        logger.info("Blob validated successfully on Sync Gateway.")

        self.mark_test_step("Deleting the blob from the document in Edge Server.")
        logger.info(f"Deleting the blob from document {doc_id} in Edge Server.")
        response = await edge_server.delete_sub_document(doc_id, rev_id, attachment_name, es_db_name)

        assert response.get("ok"), f"Failed to delete blob from document {doc_id} in Edge Server."
        logger.info(f"Blob deleted from document {doc_id} in Edge Server.")

        # Validate blob deletion on Sync Gateway and Couchbase Server
        self.mark_test_step("Validating blob deletion on Sync Gateway and Couchbase Server.")
        document = await sync_gateway.get_document(sg_db_name, doc_id)

        assert "_attachments" not in document, "Error: '_attachments' field is present in the document response"
        logger.info("Blob deleted even on Sync Gateway.")

        self.mark_test_step("Blob creation and deletion test passed.")
        logger.info("Blob creation and deletion test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_blob(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to add empty blob to a document in Edge Server")

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        sg_db_name = "db-1"
        es_db_name = "db"

        edge_server = cblpytest.edge_servers[0]

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        self.mark_test_step("Adding an empty blob to a document in Edge Server.")
        logger.info("Adding an empty blob to a document in Edge Server.")

        # Upload an empty blob
        empty_blob = b""
        doc_id = "doc_2"

        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test.png"

        # Add the image as an attachment to the document
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=empty_blob)
        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Empty blob added to document {doc_id} in Edge Server.")

        # Validate empty blob uploaded
        self.mark_test_step("Validating empty blob can be retrieved on Edge Server.")
        blob = await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)
        print(blob)

        assert blob is not None, "Failed to retrieve empty blob from document."
        assert blob.body == empty_blob, "Empty blob data mismatch."

        self.mark_test_step("Empty blob validated successfully on Edge Server.")
        logger.info("Empty blob validated successfully on Edge Server.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to update blob in a document in Edge Server")

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        sg_db_name = "db-1"
        es_db_name = "db"

        edge_server = cblpytest.edge_servers[0]

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        self.mark_test_step("Adding a blob to a document in Edge Server.")
        doc_id = "doc_2"
        logger.info(f"Adding a blob to document {doc_id} in Edge Server.")
        document = await edge_server.get_document(es_db_name, doc_id)

        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test.png"
        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name,  value=image_data)
        assert response is not None, "Failed to update attachment in document."

        logger.info(f"Blob updated in document {doc_id} in Edge Server.")

        self.mark_test_step("Validating updated blob on Sync Gateway.")

        document = await sync_gateway.get_document(sg_db_name, doc_id)
        print(document)
        
        # Assert that the response contains `_attachments` with expected metadata
        assert "_attachments" in document, "Error: '_attachments' field is missing in the document response"
        assert f"blob_/{attachment_name}" in document["_attachments"], f"Error: Attachment '{attachment_name}' not found in '_attachments'"

        blob_metadata = document["_attachments"][f"blob_/{attachment_name}"]
        assert blob_metadata["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_metadata['content_type']}'"
        assert "digest" in blob_metadata, "Error: 'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "Error: 'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, f"Error: Blob length is invalid ({blob_metadata['length']})"

        # Assert that the blob is also referenced in the document body
        assert attachment_name in document, f"Error: '{attachment_name}' not found in document body"
        blob_info = document[attachment_name]
        assert blob_info["@type"] == "blob", f"Error: Expected '@type'='blob', but got '{blob_info.get('@type')}'"
        assert blob_info["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_info['content_type']}'"
        assert blob_info["digest"] == blob_metadata["digest"], f"Error: Blob digest mismatch, expected '{blob_metadata['digest']}', got '{blob_info['digest']}'"
        assert blob_info["length"] == blob_metadata["length"], f"Error: Blob length mismatch, expected '{blob_metadata['length']}', got '{blob_info['length']}'"

        logger.info("Blob update validated successfully on Sync Gateway.")

        self.mark_test_step("Blob update worked as expected.")
        logger.info("Blob update worked as expected.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_get_nonexistent(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to get nonexistent blob from a document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_updation"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat()
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id} via Edge Server."

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Getting nonexistent blob from a document in Edge Server.")
        logger.info("Getting nonexistent blob from a document in Edge Server.")

        attachment_name = "missing_blob.png"

        try:
            blob = await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)
        except CblEdgeServerBadResponseError:
            assert CblEdgeServerBadResponseError, "Able to retrieve nonexistent blob from document."

        logger.info("Nonexistent blob retrieval test passed.")
        self.mark_test_step("Nonexistent blob retrieval test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_delete_nonexistent(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to delete nonexistent blob from a document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_deletion"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat()
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id} via Edge Server."

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Deleting nonexistent blob from a document in Edge Server.")

        logger.info("Try to get the document to get the latest revision.")
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "missing_blob.png"

        try:
            response = await edge_server.delete_sub_document(doc_id, rev_id, attachment_name, es_db_name)
        except CblEdgeServerBadResponseError:
            assert CblEdgeServerBadResponseError, "Able to delete nonexistent blob from document."

        logger.info("Nonexistent blob deletion test passed.")
        self.mark_test_step("Nonexistent blob deletion test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update_incorrect_rev(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to update blob with incorrect revision in a document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_updation"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat()
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id} via Edge Server."

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Add a blob to the document in Edge Server.")
        logger.info(f"Adding a blob to document {doc_id} in Edge Server.")

        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test.png"
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Blob added to document {doc_id} in Edge Server.")

        self.mark_test_step("Try to update the blob with incorrect revision in the document in Edge Server.")

        updated_data = b"updated blob data"

        try:
            response = await edge_server.put_sub_document(doc_id, "incorrect rev", attachment_name, es_db_name, value=updated_data)
        except CblEdgeServerBadResponseError:
            assert CblEdgeServerBadResponseError, "Able to update blob with incorrect revision in document."

        logger.info("Incorrect revision blob update test passed.")
        self.mark_test_step("Incorrect revision blob update test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_put_nonexistent_doc(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to add blob to nonexistent document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_blob"

        self.mark_test_step("Try to add blob to nonexistent document in Edge Server.")
        logger.info("Try to add blob to nonexistent document in Edge Server.")

        attachment_name = "test.png"
        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        try:
            response = await edge_server.put_sub_document(doc_id, "1-abcdef", attachment_name, es_db_name, value=image_data)
        except CblEdgeServerBadResponseError:
            assert CblEdgeServerBadResponseError, "Able to add blob to nonexistent document."

        logger.info("Nonexistent document blob addition test passed.")
        self.mark_test_step("Nonexistent document blob addition test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_blobs_same_doc(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to add multiple blobs to the same document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_blob"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat()
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id} via Edge Server."

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Add multiple blobs to the same document in Edge Server.")
        logger.info(f"Adding multiple blobs to document {doc_id} in Edge Server.")

        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test.png"
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"First blob added to document {doc_id} in Edge Server.")

        # Read test image as binary data
        with open("../resources/images/test2.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "test2.png"

        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)
        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Second blob added to document {doc_id} in Edge Server.")

        self.mark_test_step("Multiple blobs addition test passed.")
        logger.info("Multiple blobs addition test passed.")

        # try:
        #     response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)
        # except CblEdgeServerBadResponseError as e:
        #     assert CblEdgeServerBadResponseError, "Able to add multiple blobs to the same document."

        # assert response is not None, "Failed to add attachment to document."

        # assert "409" in str(e), f"Expected HTTP 409 status code in error message but got '{str(e)}'"

        # logger.info("Multiple blobs addition test passed.")
        # self.mark_test_step("Multiple blobs addition test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_exceeding_maxsize(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to add blob exceeding max size to a document in Edge Server")

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_blob"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat()
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id} via Edge Server."

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Add blob exceeding max size to the document in Edge Server.")
        logger.info(f"Adding blob exceeding max size to document {doc_id} in Edge Server.")

        # Read test image as binary data
        with open("../resources/images/20mb.jpg", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        attachment_name = "20mb.jpg"

        try:
            response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)
        except CblEdgeServerBadResponseError:
            assert CblEdgeServerBadResponseError, "Able to add blob exceeding max size to document."

        assert "413" in str(e), f"Expected HTTP 413 status code in error message but got '{str(e)}'"

        logger.info("Blob exceeding max size addition test passed.")
        self.mark_test_step("Blob exceeding max size addition test passed.")


    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_special_characters(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to add blob with special characters to a document in Edge Server")

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        sg_db_name = "db-1"
        
        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 3):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            server.add_document(bucket_name, doc["id"], doc)
        logger.info("2 documents created in Couchbase Server.")

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
            "num_index_replicas": 0
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

        self.mark_test_step("Check that Sync Gateway has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 2 documents")
        assert len(response.rows) == 2, f"Expected 2 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        self.mark_test_step("Adding a blob with special characters to a document in Edge Server.")

        doc_id = "doc_2"
        logger.info(f"Adding a blob with special characters to document {doc_id} in Edge Server.")

        logger.info("Get the document to get the latest revision.")
        document = await edge_server.get_document(es_db_name, doc_id)

        assert document is not None, f"Document {doc_id} does not exist on the edge server."

        rev_id = document.rev_id

        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        attachment_name = "im@g#e$%&*().png"
        response = await edge_server.put_sub_document(doc_id, rev_id, attachment_name, es_db_name, value=image_data)

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Blob with special characters added to document {doc_id} in Edge Server.")

        self.mark_test_step("Validating blob with special characters on Sync Gateway.")
        # unicoded_attachment_name = "blob_%2Fim%40g%23e%24%25%26%2A%28%29.png"

        document = await sync_gateway.get_document(sg_db_name, doc_id)

        # Assert that the response contains `_attachments` with expected metadata
        assert "_attachments" in document, "Error: '_attachments' field is missing in the document response"
        assert attachment_name in document["_attachments"], f"Error: Attachment '{attachment_name}' not found in '_attachments'"

        blob_metadata = document["_attachments"][attachment_name]
        assert blob_metadata["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_metadata['content_type']}'"
        assert "digest" in blob_metadata, "Error: 'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "Error: 'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, f"Error: Blob length is invalid ({blob_metadata['length']}"

        # Assert that the blob is also referenced in the document body
        assert attachment_name in document, f"Error: '{attachment_name}' not found in document body"

        blob_info = document[attachment_name]
        assert blob_info["@type"] == "blob", f"Error: Expected '@type'='blob', but got '{blob_info.get('@type')}'"
        assert blob_info["content_type"] == "image/png", f"Error: Expected content_type='image/png', but got '{blob_info['content_type']}'"
        assert blob_info["digest"] == blob_metadata["digest"], f"Error: Blob digest mismatch, expected '{blob_metadata['digest']}', got '{blob_info['digest']}'"
        assert blob_info["length"] == blob_metadata["length"], f"Error: Blob length mismatch, expected '{blob_metadata['length']}', got '{blob_info['length']}'"

        logger.info("Blob with special characters validated successfully on Sync Gateway.")

        self.mark_test_step("Blob with special characters addition test passed.")