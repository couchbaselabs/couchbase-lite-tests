from datetime import datetime
from pathlib import Path
import pytest
import time
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload


import logging

logger = logging.getLogger(__name__)


class TestConflicts(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflicts(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step(
            "Starting E2E test with Server, Sync Gateway, Edge Server and 1 client"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 11):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.add_document(bucket_name, doc["id"], doc)
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

        self.mark_test_step("Creating a database in Edge Server.")
        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        await edge_server.kill_server()
        await edge_server.start_server()

        logger.info("Created a database in Edge Server.")

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

        self.mark_test_step("Take Edge Server offline")
        await edge_server.go_offline()
        logger.info("Edge Server is offline")

        self.mark_test_step("Add 5 documents to Sync Gateway")
        for i in range(11, 16):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "edge_server": "no",
            }
            await sync_gateway.create_document(sg_db_name, doc_id, doc)
        logger.info("5 documents added to Sync Gateway")

        self.mark_test_step("Check docs in Sync Gateway")
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 15, (
            f"Expected 15 documents, but got {len(response.rows)} documents."
        )
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway.")

        self.mark_test_step("Add conflicting documents to Edge Server")
        for i in range(11, 16):
            doc_id = f"doc_{i}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
                "edge_server": "yes",
            }
            response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
            assert response is not None, (
                f"Failed to create document {doc_id} via Edge Server."
            )
        logger.info("5 documents added to Edge Server")

        self.mark_test_step("Check docs in Edge Server")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 15, (
            f"Expected 15 documents, but got {len(response.rows)} documents."
        )
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server.")

        self.mark_test_step("Take Edge Server online")
        await edge_server.go_online()
        logger.info("Edge Server is online")

        # self.mark_test_step("Restarting Edge Server")
        # await edge_server.kill_server()
        # await edge_server.start_server()
        # logger.info("Edge Server restarted")

        self.mark_test_step("Check that conflicts have resolved")

        # Wait for conflict resolution to complete
        time.sleep(10)

        self.mark_test_step(
            "Verify both services have 15 documents after conflict resolution"
        )

        # Check Sync Gateway documents
        sg_response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        sg_doc_count = len(sg_response.rows)
        assert sg_doc_count == 15, (
            f"Expected 15 documents in Sync Gateway after conflict resolution, but got {sg_doc_count} documents."
        )
        logger.info(
            f"Sync Gateway has {sg_doc_count} documents after conflict resolution."
        )

        # Check Edge Server documents
        es_response = await edge_server.get_all_documents(es_db_name)
        es_doc_count = len(es_response.rows)
        assert es_doc_count == 15, (
            f"Expected 15 documents in Edge Server after conflict resolution, but got {es_doc_count} documents."
        )
        logger.info(
            f"Edge Server has {es_doc_count} documents after conflict resolution."
        )

        logger.info(
            "Both Sync Gateway and Edge Server have 15 documents after conflict resolution"
        )

        self.mark_test_step(
            "Compare document contents between Sync Gateway and Edge Server"
        )

        # Create maps of documents by ID for easy comparison
        sg_docs = {doc.id: doc for doc in sg_response.rows}
        es_docs = {doc.id: doc for doc in es_response.rows}

        # Verify all document IDs exist in both services
        sg_ids = set(sg_docs.keys())
        es_ids = set(es_docs.keys())

        assert sg_ids == es_ids, (
            f"Document ID mismatch: Sync Gateway has {sg_ids - es_ids} extra IDs, Edge Server has {es_ids - sg_ids} extra IDs"
        )
        logger.info("All document IDs are present in both services")

        # Compare document contents
        conflicts_resolved = 0
        conflict_doc_ids = {f"doc_{i}" for i in range(11, 16)}
        for doc_id in sg_ids:
            # Fetch full document content from both services
            sg_doc = await sync_gateway.get_document(
                sg_db_name, doc_id, "_default", "_default"
            )
            es_doc = await edge_server.get_document(es_db_name, doc_id)

            if doc_id in conflict_doc_ids:
                # These should have been resolved - check if they have consistent content
                if sg_doc.body.get("edge_server") == es_doc.body.get("edge_server"):
                    conflicts_resolved += 1
                    logger.info(
                        f"Conflict resolved for {doc_id}: both services have consistent content"
                    )
                else:
                    logger.warning(
                        f"Conflict not fully resolved for {doc_id}: SG={sg_doc.body.get('edge_server')}, ES={es_doc.body.get('edge_server')}"
                    )
            else:
                # Documents 1-10 should be identical
                assert sg_doc.body == es_doc.body, (
                    f"Document {doc_id} content mismatch between services"
                )
                logger.info(f"Document {doc_id} content matches between services")

        logger.info(
            f"Conflict resolution summary: {conflicts_resolved}/5 conflicts resolved"
        )

        # Verify that at least some conflicts were resolved
        assert conflicts_resolved > 0, "No conflicts were resolved during the test"

        logger.info(
            "Both Sync Gateway and Edge Server have 15 documents with resolved conflicts"
        )

        self.mark_test_step("Test for conflict resolution completed successfully.")
        logger.info("Test completed.")
