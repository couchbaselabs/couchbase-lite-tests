import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload

SCRIPT_DIR = str(Path(__file__).parent)


class TestBlobs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_blobs_create_delete(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket on server.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 2 documents to bucket.")
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)

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

        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        self.mark_test_step(
            "Creating a database on Edge Server with replication to Sync Gateway; waiting for idle."
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

        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )

        self.mark_test_step("Verifying that Sync Gateway has 2 documents.")
        assert len(response.rows) == 2, (
            f"Expected 2 documents, but got {len(response.rows)} documents."
        )

        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Verifying that Edge Server has 2 documents.")
        assert len(response.rows) == 2, (
            f"Expected 2 documents, but got {len(response.rows)} documents."
        )

        self.mark_test_step("Adding a blob to document on Edge Server.")
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

        # Add the image as an attachment to the document
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )
        assert response is not None, "Failed to add attachment to document."

        self.mark_test_step("Verifying that blob is replicated to Sync Gateway.")
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

        self.mark_test_step("Deleting blob from document on Edge Server.")
        delete_resp = await edge_server.delete_sub_document(
            doc_id, rev_id, attachment_name, es_db_name
        )

        assert isinstance(delete_resp, dict) and delete_resp.get("ok"), (
            f"Failed to delete blob from document {doc_id} in Edge Server."
        )

        self.mark_test_step("Verifying that blob is removed on Sync Gateway.")
        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
        assert sg_doc is not None

        assert "_attachments" not in sg_doc.body, (
            "'_attachments' field is present in the document response"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_blob(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Creating a database on Edge Server.")
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Creating a document on Edge Server.")
        doc_id = "doc_empty_blob"
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, f"Failed to create document {doc_id}."

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

        self.mark_test_step("Validating empty blob can be retrieved.")
        blob = await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)
        assert blob is not None, "Failed to retrieve empty blob from document."
        assert blob.body == empty_blob, "Empty blob data mismatch."

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Creating a bucket on server.")
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]
        sg_db_name = "db-1"
        es_db_name = "db"

        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 2 documents to bucket.")
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)

        self.mark_test_step("Creating a database on Sync Gateway.")
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
        self.mark_test_step("Adding role to Sync Gateway.")
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        self.mark_test_step("Adding user to Sync Gateway.")
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        config_path = f"{SCRIPT_DIR}/config/test_e2e_empty_database.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        self.mark_test_step(
            "Creating a database on Edge Server with replication to Sync Gateway."
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        self.mark_test_step("Waiting for idle.")
        await edge_server.wait_for_idle()

        self.mark_test_step("Verifying that Sync Gateway has 2 documents.")
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Sync Gateway, got {len(response.rows)}."
        )
        self.mark_test_step("Verifying that Edge Server has 2 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Edge Server, got {len(response.rows)}."
        )

        self.mark_test_step("Adding a blob to document on Edge Server.")
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

        self.mark_test_step("Verifying that blob is present on Sync Gateway.")
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_get_nonexistent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Creating a database on Edge Server.")
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Create document.")
        doc_id = "doc_updation"

        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        self.mark_test_step("Verifying that get nonexistent blob fails.")
        attachment_name = "missing_blob.png"

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_sub_document(doc_id, attachment_name, es_db_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_delete_nonexistent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_deletion"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        self.mark_test_step("Deleting nonexistent blob from a document in Edge Server.")

        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.revid

        self.mark_test_step("Verify delete nonexistent blob fails.")
        attachment_name = "missing_blob.png"

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.delete_sub_document(
                doc_id, rev_id, attachment_name, es_db_name
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_update_incorrect_rev(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_updation"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        self.mark_test_step("Add a blob to the document in Edge Server.")

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

        self.mark_test_step("Verifying that update blob with wrong rev fails.")
        updated_data = b"updated blob data"

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.put_sub_document(
                doc_id, "incorrect rev", attachment_name, es_db_name, value=updated_data
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_put_nonexistent_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Verifying that put blob on nonexistent document fails.")
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_blob"

        self.mark_test_step("Try to add blob to nonexistent document in Edge Server.")

        attachment_name = "test.png"
        # Read test image as binary data
        blob_path = dataset_path.parent / "edge-server" / "blobs" / "test.png"
        with open(blob_path, "rb") as img_file:
            image_data = img_file.read()

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.put_sub_document(
                doc_id, "1-abcdef", attachment_name, es_db_name, value=image_data
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_blobs_same_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Creating a database on Edge Server.")
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        doc_id = "doc_blob"

        self.mark_test_step("Adding a document to Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        self.mark_test_step("Add first blob to document.")
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

        self.mark_test_step("Adding second blob to same document.")
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_exceeding_maxsize(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Creating a database on Edge Server.")
        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Create document.")
        doc_id = "doc_blob"

        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        self.mark_test_step("Verify blob over max size returns 413.")
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

        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await edge_server.put_sub_document(
                doc_id, rev_id, attachment_name, es_db_name, value=image_data
            )
        assert "413" in str(excinfo.value), (
            f"Expected HTTP 413 status code in error message but got '{str(excinfo.value)}'"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_special_characters(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Creating a bucket on server.")
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        sg_db_name = "db-1"

        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 2 documents to bucket.")
        for i in range(1, 3):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            server.upsert_document(bucket_name, doc_id, doc)

        self.mark_test_step("Creating a database on Sync Gateway.")
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
        self.mark_test_step("Waiting for idle.")
        await edge_server.wait_for_idle()

        self.mark_test_step("Verifying that Sync Gateway has 2 documents.")
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Sync Gateway, got {len(response.rows)}."
        )
        self.mark_test_step("Verifying that Edge Server has 2 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 2, (
            f"Expected 2 documents on Edge Server, got {len(response.rows)}."
        )

        self.mark_test_step("Adding blob with special-character name.")
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

        self.mark_test_step("Verifying that blob is present on Sync Gateway.")
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
