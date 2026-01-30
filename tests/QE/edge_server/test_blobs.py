import json
import logging
from datetime import datetime
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload

logger = logging.getLogger(__name__)
SCRIPT_DIR = str(Path(__file__).parent)


class TestBlobs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_blobs_create_delete(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting Blobs CRUD test with Server, Sync Gateway, Edge Server and 1 client"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)
        logger.info("2 documents created in Couchbase Server.")

        self.mark_test_step(
            "Creating a database in Sync Gateway and adding a user and role."
        )
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
            config = json.load(file)
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

        self.mark_test_step("Check that Sync Gateway has 2 documents")
        assert len(response.rows) == 2, (
            f"Expected 2 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Sync Gateway initially."
        )

        logger.info(
            "Checking initial document sync from Sync Gateway to Edge Server..."
        )
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 2 documents")
        assert len(response.rows) == 2, (
            f"Expected 2 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Edge Server initially."
        )

        self.mark_test_step("Adding a blob to a document in Couchbase Server.")
        doc_id = "doc_2"
        logger.info(f"Adding a blob to document {doc_id} in Couchbase Server.")
        document = await edge_server.get_document(es_db_name, doc_id)

        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "test.png"
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )
        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Blob added to document {doc_id} in Edge Server.")

        # Validate blob on Sync Gateway and Couchbase Server
        self.mark_test_step("Validating blob on Sync Gateway and Couchbase Server.")
        document = await sync_gateway.get_document(sg_db_name, doc_id)
        assert document is not None
        doc_body = document.body

        assert "_attachments" in doc_body, (
            "'_attachments' field is missing in the document response"
        )
        assert f"blob_/{attachment_name}" in doc_body["_attachments"], (
            f"Attachment '{attachment_name}' not found in '_attachments'"
        )
        blob_metadata = doc_body["_attachments"][f"blob_/{attachment_name}"]
        assert blob_metadata["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_metadata['content_type']}'"
        )
        assert "digest" in blob_metadata, "'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, (
            f"Blob length is invalid ({blob_metadata['length']})"
        )
        assert attachment_name in doc_body, (
            f"'{attachment_name}' not found in document body"
        )
        blob_info = doc_body[attachment_name]
        assert blob_info["@type"] == "blob", (
            f"Expected '@type'='blob', got '{blob_info.get('@type')}'"
        )
        assert blob_info["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_info['content_type']}'"
        )
        assert blob_info["digest"] == blob_metadata["digest"], (
            f"Blob digest mismatch, expected '{blob_metadata['digest']}', got '{blob_info['digest']}'"
        )
        assert blob_info["length"] == blob_metadata["length"], (
            f"Blob length mismatch, expected '{blob_metadata['length']}', got '{blob_info['length']}'"
        )
        logger.info("Blob validated successfully on Sync Gateway.")

        self.mark_test_step("Deleting the blob from the document in Edge Server.")
        logger.info(f"Deleting the blob from document {doc_id} in Edge Server.")
        delete_resp = await edge_server.delete_sub_document(
            doc_id, rev_id, attachment_name, es_db_name
        )

        assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
            f"Failed to delete blob from document {doc_id} in Edge Server."
        )
        logger.info(f"Blob deleted from document {doc_id} in Edge Server.")

        # Validate blob deletion on Sync Gateway and Couchbase Server
        self.mark_test_step(
            "Validating blob deletion on Sync Gateway and Couchbase Server."
        )
        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
        assert sg_doc is not None

        assert "_attachments" not in sg_doc.body, (
            "'_attachments' field is present in the document response"
        )
        logger.info("Blob deleted even on Sync Gateway.")

        self.mark_test_step("Blob creation and deletion test passed.")
        logger.info("Blob creation and deletion test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_blob(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step(
            "Starting test to add empty blob to a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Creating a document on Edge Server.")
        doc_id = "doc_empty_blob"
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id}."
        logger.info(f"Document {doc_id} created on Edge Server.")

        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )
        rev_id = document.revid

        self.mark_test_step("Adding an empty blob to the document.")
        empty_blob = b""
        attachment_name = "test.png"
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=empty_blob
        )
        assert response is not None, "Failed to add empty blob to document."
        logger.info(f"Empty blob added to document {doc_id}.")

        self.mark_test_step("Validating empty blob can be retrieved.")
        blob = await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)
        assert blob is not None, "Failed to retrieve empty blob from document."
        assert blob.body == empty_blob, "Empty blob data mismatch."

        self.mark_test_step("Empty blob validated successfully on Edge Server.")
        logger.info("Empty blob validated successfully on Edge Server.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to update blob in a document in Edge Server")

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]
        sg_db_name = "db-1"
        es_db_name = "db"

        self.mark_test_step("Creating bucket and documents in Couchbase Server.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)
        logger.info("2 documents created in Couchbase Server.")

        self.mark_test_step("Creating database and user in Sync Gateway.")
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
        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)
        logger.info("Database and user added to Sync Gateway.")

        self.mark_test_step("Configure Edge Server with replication to Sync Gateway.")
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

        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Sync Gateway, got {len(response.rows)}."
        )
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Edge Server, got {len(response.rows)}."
        )
        logger.info("2 documents synced to Edge Server.")

        self.mark_test_step("Adding a blob to a document on Edge Server.")
        doc_id = "doc_2"
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )
        rev_id = document.revid
        attachment_name = "test.png"
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )
        assert response is not None, "Failed to add blob to document."
        logger.info(f"Blob added to document {doc_id} in Edge Server.")

        self.mark_test_step("Validating updated blob replicated to Sync Gateway.")
        document = await sync_gateway.get_document(sg_db_name, doc_id)
        assert document is not None
        doc_body = document.body

        assert "_attachments" in doc_body, (
            "'_attachments' field is missing in the document response"
        )
        assert f"blob_/{attachment_name}" in doc_body["_attachments"], (
            f"Attachment '{attachment_name}' not found in '_attachments'"
        )
        blob_metadata = doc_body["_attachments"][f"blob_/{attachment_name}"]
        assert blob_metadata["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_metadata.get('content_type')}'"
        )
        assert "digest" in blob_metadata, "'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, (
            f"Blob length is invalid ({blob_metadata['length']})"
        )
        assert attachment_name in doc_body, (
            f"'{attachment_name}' not found in document body"
        )
        blob_info = doc_body[attachment_name]
        assert blob_info["@type"] == "blob", (
            f"Expected '@type'='blob', got '{blob_info.get('@type')}'"
        )
        assert blob_info["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_info.get('content_type')}'"
        )
        assert blob_info["digest"] == blob_metadata["digest"], "Blob digest mismatch"
        assert blob_info["length"] == blob_metadata["length"], "Blob length mismatch"
        logger.info("Blob update validated on Sync Gateway.")

        self.mark_test_step("Blob update worked as expected.")
        logger.info("Blob update worked as expected.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_get_nonexistent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to get nonexistent blob from a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_updation"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Getting nonexistent blob from a document in Edge Server.")
        logger.info("Getting nonexistent blob from a document in Edge Server.")

        attachment_name = "missing_blob.png"

        try:
            await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)
            assert False, (
                "Should not be able to retrieve nonexistent blob from document."
            )
        except CblEdgeServerBadResponseError as e:
            logger.info(f"Got expected error for nonexistent blob: {e}")

        logger.info("Nonexistent blob retrieval test passed.")
        self.mark_test_step("Nonexistent blob retrieval test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_delete_nonexistent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to delete nonexistent blob from a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_deletion"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Deleting nonexistent blob from a document in Edge Server.")

        logger.info("Try to get the document to get the latest revision.")
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "missing_blob.png"

        try:
            response = await edge_server.delete_sub_document(
                doc_id, rev_id, attachment_name, es_db_name
            )
            assert False, "Should not be able to delete nonexistent blob from document."
        except CblEdgeServerBadResponseError as e:
            logger.info(f"Got expected error for nonexistent blob deletion: {e}")

        logger.info("Nonexistent blob deletion test passed.")
        self.mark_test_step("Nonexistent blob deletion test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update_incorrect_rev(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to update blob with incorrect revision in a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_updation"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Add a blob to the document in Edge Server.")
        logger.info(f"Adding a blob to document {doc_id} in Edge Server.")

        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "test.png"
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Blob added to document {doc_id} in Edge Server.")

        self.mark_test_step(
            "Try to update the blob with incorrect revision in the document in Edge Server."
        )

        updated_data = b"updated blob data"

        try:
            response = await edge_server.put_sub_document(
                doc_id, "incorrect rev", attachment_name, es_db_name, value=updated_data
            )
            assert False, "Should not be able to update blob with incorrect revision."
        except CblEdgeServerBadResponseError as e:
            logger.info(f"Got expected error for incorrect revision: {e}")

        logger.info("Incorrect revision blob update test passed.")
        self.mark_test_step("Incorrect revision blob update test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_put_nonexistent_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to add blob to nonexistent document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_blob"

        self.mark_test_step("Try to add blob to nonexistent document in Edge Server.")
        logger.info("Try to add blob to nonexistent document in Edge Server.")

        attachment_name = "test.png"
        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        try:
            await edge_server.put_sub_document(
                doc_id, "1-abcdef", attachment_name, es_db_name, value=image_data
            )
            assert False, "Should not be able to add blob to nonexistent document."
        except CblEdgeServerBadResponseError as e:
            logger.info(f"Got expected error for nonexistent document: {e}")

        logger.info("Nonexistent document blob addition test passed.")
        self.mark_test_step("Nonexistent document blob addition test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_blobs_same_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to add multiple blobs to the same document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_blob"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step("Add multiple blobs to the same document in Edge Server.")
        logger.info(f"Adding multiple blobs to document {doc_id} in Edge Server.")

        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "test.png"
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"First blob added to document {doc_id} in Edge Server.")

        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test2.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "test2.png"

        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )
        assert response is not None, "Failed to add attachment to document."

        logger.info(f"Second blob added to document {doc_id} in Edge Server.")

        self.mark_test_step("Multiple blobs addition test passed.")
        logger.info("Multiple blobs addition test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_exceeding_maxsize(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to add blob exceeding max size to a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_blob"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server.")

        self.mark_test_step(
            "Add blob exceeding max size to the document in Edge Server."
        )
        logger.info(
            f"Adding blob exceeding max size to document {doc_id} in Edge Server."
        )

        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "20mb.jpg"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        attachment_name = "20mb.jpg"

        try:
            response = await edge_server.put_sub_document(
                doc_id, rev_id, attachment_name, es_db_name, value=image_data
            )
            assert False, "Should not be able to add blob exceeding max size."
        except CblEdgeServerBadResponseError as e:
            assert "413" in str(e), (
                f"Expected HTTP 413 status code in error message but got '{str(e)}'"
            )
            logger.info(f"Got expected 413 error for blob exceeding max size: {e}")

        logger.info("Blob exceeding max size addition test passed.")
        self.mark_test_step("Blob exceeding max size addition test passed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_special_characters(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to add blob with special characters to a document in Edge Server"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        sg_db_name = "db-1"

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)
        logger.info("2 documents created in Couchbase Server.")

        self.mark_test_step(
            "Creating a database in Sync Gateway and adding a user and role."
        )
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
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Sync Gateway, got {len(response.rows)}."
        )
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Edge Server, got {len(response.rows)}."
        )
        logger.info("2 documents synced to Edge Server.")

        self.mark_test_step(
            "Adding a blob with special characters to a document in Edge Server."
        )
        doc_id = "doc_2"
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )
        rev_id = document.revid

        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        attachment_name = "im@g#e$%&*().png"
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )

        assert response is not None, "Failed to add attachment to document."

        logger.info(
            f"Blob with special characters added to document {doc_id} in Edge Server."
        )

        self.mark_test_step("Validating blob with special characters on Sync Gateway.")
        # unicoded_attachment_name = "blob_%2Fim%40g%23e%24%25%26%2A%28%29.png"

        document = await sync_gateway.get_document(sg_db_name, doc_id)
        assert document is not None
        doc_body = document.body

        assert "_attachments" in doc_body, (
            "'_attachments' field is missing in the document response"
        )
        assert attachment_name in doc_body["_attachments"], (
            f"Attachment '{attachment_name}' not found in '_attachments'"
        )
        blob_metadata = doc_body["_attachments"][attachment_name]
        assert blob_metadata["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_metadata['content_type']}'"
        )
        assert "digest" in blob_metadata, "'digest' field is missing in blob metadata"
        assert "length" in blob_metadata, "'length' field is missing in blob metadata"
        assert blob_metadata["length"] > 0, (
            f"Blob length is invalid ({blob_metadata['length']})"
        )
        assert attachment_name in doc_body, (
            f"'{attachment_name}' not found in document body"
        )
        blob_info = doc_body[attachment_name]
        assert blob_info["@type"] == "blob", (
            f"Expected '@type'='blob', got '{blob_info.get('@type')}'"
        )
        assert blob_info["content_type"] == "image/png", (
            f"Expected content_type='image/png', got '{blob_info['content_type']}'"
        )
        assert blob_info["digest"] == blob_metadata["digest"], (
            f"Blob digest mismatch, expected '{blob_metadata['digest']}', got '{blob_info['digest']}'"
        )
        assert blob_info["length"] == blob_metadata["length"], (
            f"Blob length mismatch, expected '{blob_metadata['length']}', got '{blob_info['length']}'"
        )
        logger.info(
            "Blob with special characters validated successfully on Sync Gateway."
        )

        self.mark_test_step("Blob with special characters addition test passed.")
