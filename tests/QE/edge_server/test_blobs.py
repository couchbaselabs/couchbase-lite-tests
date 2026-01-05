import logging
from datetime import datetime
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload

logger = logging.getLogger(__name__)


class TestBlobs(CBLTestClass):

    @pytest.mark.asyncio(loop_scope="session")
    async def test_blob_get_nonexistent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to get nonexistent blob from a document in Edge Server"
        )

        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

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
        edge_server = cblpytest.edge_servers[0]

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

        rev_id = document.rev_id

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
        edge_server = cblpytest.edge_servers[0]

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
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.rev_id

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
        edge_server = cblpytest.edge_servers[0]

        doc_id = "doc_blob"

        self.mark_test_step("Try to add blob to nonexistent document in Edge Server.")
        logger.info("Try to add blob to nonexistent document in Edge Server.")

        attachment_name = "test.png"
        # Read test image as binary data
        with open("../resources/images/test.png", "rb") as img_file:
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
        edge_server = cblpytest.edge_servers[0]

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
        with open("../resources/images/test.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.rev_id

        attachment_name = "test.png"
        response = await edge_server.put_sub_document(
            doc_id, rev_id, attachment_name, es_db_name, value=image_data
        )

        assert response is not None, "Failed to add attachment to document."

        logger.info(f"First blob added to document {doc_id} in Edge Server.")

        # Read test image as binary data
        with open("../resources/images/test2.png", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.rev_id

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
        edge_server = cblpytest.edge_servers[0]

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
        with open("../resources/images/20mb.jpg", "rb") as img_file:
            image_data = img_file.read()

        # Add the image as an attachment to the document
        document = await edge_server.get_document(es_db_name, doc_id)
        assert document is not None, (
            f"Document {doc_id} does not exist on the edge server."
        )

        rev_id = document.rev_id

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