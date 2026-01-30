import json
import logging
from datetime import datetime
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload

logger = logging.getLogger(__name__)
SCRIPT_DIR = str(Path(__file__).parent)


class TestLogging(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_audit_logging_default(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting Audit Logging test with Server, Sync Gateway, Edge Server and 1 client"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 6):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc["id"], doc)
        logger.info("5 documents created in Couchbase Server.")

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

        self.mark_test_step("Configure Edge Server with default audit config.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_audit.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        logger.info("Edge Server configured with default audit.")

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

        self.mark_test_step("Check that Sync Gateway has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Sync Gateway initially."
        )

        logger.info(
            "Checking initial document sync from Sync Gateway to Edge Server..."
        )
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Edge Server initially."
        )

        self.mark_test_step("Checking audit logs for start and stop")
        log = await edge_server.check_log("57344")
        assert len(log) > 0, "Audit log for start event not found"
        log = await edge_server.check_log("100002")
        assert log == [], "Audit log for stop event not found"
        logger.info("Audit logs checked for start and stop")

        self.mark_test_step("Checking audit logs for public HTTP requests")
        log = await edge_server.check_log("100003")
        assert log == [], "Audit log for public HTTP request found"
        logger.info("Audit logs checked for public HTTP requests")

        self.mark_test_step("Checking audit logs for replication events")
        log = await edge_server.check_log("57355")
        assert len(log) > 0, "Audit log for start of replication event not found"
        log = await edge_server.check_log("100013")
        assert log == [], "Audit log for stop of replication event not found"
        logger.info("Audit logs checked for replication events")

        self.mark_test_step(
            "Checking no audit logs for document changes with default events enabled"
        )
        # Create
        log = await edge_server.check_log("100015")
        assert log == [], "Audit log for create event found"
        # Read
        log = await edge_server.check_log("100016")
        assert log == [], "Audit log for read event found"
        # Update
        log = await edge_server.check_log("100017")
        assert log == [], "Audit log for update event found"
        # Delete
        log = await edge_server.check_log("100018")
        assert log == [], "Audit log for delete event found"
        logger.info(
            "Audit logs checked for document changes with default events enabled"
        )

        self.mark_test_step("Audit logging test completed.")
        logger.info("Audit logging test successfully completed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_audit_logging_disabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting Audit Logging test with Server, Sync Gateway, Edge Server and 1 client"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 6):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc["id"], doc)
        logger.info("5 documents created in Couchbase Server.")

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

        self.mark_test_step("Configure Edge Server with audit disabled config.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_audit_disabled.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        logger.info("Edge Server configured with audit disabled.")

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

        self.mark_test_step("Check that Sync Gateway has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Sync Gateway initially."
        )

        logger.info(
            "Checking initial document sync from Sync Gateway to Edge Server..."
        )
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Edge Server initially."
        )

        self.mark_test_step("Checking audit logs for start and stop")
        log = await edge_server.check_log("100001")
        assert log == [], "Audit log for start event found"
        log = await edge_server.check_log("100002")
        assert log == [], "Audit log for stop event found"
        logger.info("Audit logs checked for start and stop")

        self.mark_test_step("Checking audit logs for public HTTP requests")
        log = await edge_server.check_log("100003")
        assert log == [], "Audit log for public HTTP request found"
        logger.info("Audit logs checked for public HTTP requests")

        self.mark_test_step("Checking audit logs for replication events")
        log = await edge_server.check_log("100012")
        assert log == [], "Audit log for start of replication event found"
        log = await edge_server.check_log("100013")
        assert log == [], "Audit log for stop of replication event found"
        logger.info("Audit logs checked for replication events")

        self.mark_test_step("Audit logging test completed.")
        logger.info("Audit logging test successfully completed.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_audit_logging_enabled(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting Audit Logging test with Server, Sync Gateway, Edge Server and 1 client"
        )

        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Creating a bucket in Couchbase Server and adding 10 documents."
        )
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 6):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }
            server.upsert_document(bucket_name, doc["id"], doc)
        logger.info("5 documents created in Couchbase Server.")

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

        self.mark_test_step("Configure Edge Server with audit enabled config.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_audit_enabled.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        logger.info("Edge Server configured with audit enabled.")

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

        self.mark_test_step("Check that Sync Gateway has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Sync Gateway initially."
        )

        logger.info(
            "Checking initial document sync from Sync Gateway to Edge Server..."
        )
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 5 documents")
        assert len(response.rows) == 5, (
            f"Expected 5 documents, but got {len(response.rows)} documents."
        )
        logger.info(
            f"Found {len(response.rows)} documents synced to Edge Server initially."
        )

        self.mark_test_step("Checking audit logs for start and stop")
        log = await edge_server.check_log("100001")
        assert len(log) > 0, "Audit log for start event not found"
        log = await edge_server.check_log("100002")
        assert log == [], "Audit log for stop event not found"
        logger.info("Audit logs checked for start and stop")

        self.mark_test_step("Checking audit logs for public HTTP requests")
        log = await edge_server.check_log("100003")
        assert len(log) > 0, "Audit log for public HTTP request not found"
        logger.info("Audit logs checked for public HTTP requests")

        self.mark_test_step("Checking audit logs for replication events")
        log = await edge_server.check_log("100012")
        assert len(log) > 0, "Audit log for start of replication event not found"
        log = await edge_server.check_log("100013")
        assert log == [], "Audit log for stop of replication event found"
        logger.info("Audit logs checked for replication events")

        self.mark_test_step("Checking no audit logs for document changes initially")
        # Create
        log = await edge_server.check_log("100015")
        assert log == [], "Audit log for create event found"
        # Read
        log = await edge_server.check_log("100016")
        assert log == [], "Audit log for read event found"
        # Update
        log = await edge_server.check_log("100017")
        assert log == [], "Audit log for update event found"
        # Delete
        log = await edge_server.check_log("100018")
        assert log == [], "Audit log for delete event found"

        logger.info("Audit logs checked for document changes")

        self.mark_test_step("Make CRUD requests and verify audit logs")

        # --- Edge Server Cycle ---
        doc_id = "doc_6"

        # Create document
        logger.info(f"Creating document {doc_id} via Edge Server")
        doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
        assert response is not None, (
            f"Failed to create document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} created via Edge Server")

        # Read document
        logger.info(f"Reading document {doc_id} via Edge Server")
        response = await edge_server.get_document(es_db_name, doc_id)
        assert response is not None, (
            f"Failed to read document {doc_id} via Edge Server."
        )

        # Storing the revision ID
        rev_id = response.revid

        logger.info(f"Document {doc_id} read via Edge Server")

        # Update document
        logger.info(f"Updating document {doc_id} via Sync Gateway")
        updated_doc = {
            "id": doc_id,
            "channels": ["public"],
            "timestamp": datetime.utcnow().isoformat(),
            "changed": "yes",
        }

        response = await edge_server.put_document_with_id(
            updated_doc, doc_id, es_db_name, rev=rev_id
        )

        assert response is not None, (
            f"Failed to update document {doc_id} via Edge Server"
        )

        logger.info(f"Document {doc_id} updated via Edge Server")

        rev_id = response.revid

        # Delete document
        logger.info(f"Deleting document {doc_id} via Edge Server.")

        response = await edge_server.delete_document(doc_id, rev_id, es_db_name)

        assert response.get("ok"), (
            f"Failed to delete document {doc_id} via Edge Server."
        )

        logger.info(f"Document {doc_id} deleted via Edge Server.")

        self.mark_test_step("Check that audit logs are generated for CRUD operations")
        # Create
        log = await edge_server.check_log("100015")
        assert len(log) > 0, "Audit log for create event not found"
        # Read
        log = await edge_server.check_log("100016")
        assert len(log) > 0, "Audit log for read event not found"
        # Update
        log = await edge_server.check_log("100017")
        assert len(log) > 0, "Audit log for update event not found"
        # Delete
        log = await edge_server.check_log("100018")
        assert len(log) > 0, "Audit log for delete event not found"

        self.mark_test_step("Audit logging test completed.")
        logger.info("Audit logging test successfully completed.")