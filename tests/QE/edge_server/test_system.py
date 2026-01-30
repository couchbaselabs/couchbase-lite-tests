import json
import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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


class TestSystem(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_l(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting system test with Server, Sync Gateway, Edge Server and 1 client"
        )

        # Calculate end time for 6 hours from now
        end_time = datetime.now() + timedelta(minutes=360)

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
            _config = json.load(file)
        assert isinstance(_config, dict), "config must be a dict"
        config: dict[str, Any] = _config
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

        # Run until 6 hours have passed
        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])

            # Randomize the operation type (create, create_update_delete, create_delete)
            operations = random.choice(
                ["create", "create_update_delete", "create_delete"]
            )
            if cycle == "edge_server":
                self.mark_test_step(
                    f"Starting {cycle} cycle for {doc_id} with operations: {operations}"
                )

            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            if cycle == "sync_gateway":
                logger.info(f"Starting Sync Gateway cycle for {doc_id}")

                # Create on Sync Gateway and validate on Edge Server
                created_doc = await sync_gateway.create_document(
                    sg_db_name, doc_id, doc
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
                logger.info(f"Document {doc_id} created via Sync Gateway.")

                time.sleep(random.uniform(1, 5))

                remote_doc = await edge_server.get_document(es_db_name, doc_id)
                assert remote_doc is not None, (
                    f"Document {doc_id} does not exist on the edge server."
                )
                assert remote_doc.id == doc_id, (
                    f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
                )
                assert remote_doc.revid is not None, (
                    "Revision ID (_rev) missing in the document"
                )

                logger.info(
                    f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
                )
                rev_id = remote_doc.revid

                if "update" in operations:
                    # Update on sync gateway and validate on edge server
                    logger.info(f"Updating document {doc_id} via Sync Gateway")
                    updated_doc_body = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "changed": "yes",
                    }
                    assert rev_id is not None, "rev_id required for update"
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, updated_doc_body, rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )

                    logger.info(f"Document {doc_id} updated via Sync Gateway")

                    # Validate update on Edge Server
                    logger.info(f"Validating update for {doc_id} on Edge Server")

                    remote_doc = await edge_server.get_document(es_db_name, doc_id)

                    assert remote_doc is not None, (
                        f"Document {doc_id} does not exist on the edge server"
                    )
                    assert remote_doc.id == doc_id, (
                        f"Document ID mismatch: {remote_doc.id}"
                    )
                    assert remote_doc.revid != rev_id, (
                        "Revision ID (_rev) missing in the document"
                    )

                    logger.info(
                        f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
                    )

                    # Storing the revision ID
                    rev_id = remote_doc.revid

                if "delete" in operations:
                    # Delete on edge server and validate on sync gateway
                    logger.info(f"Deleting document {doc_id} via Edge Server")

                    delete_resp = await edge_server.delete_document(
                        doc_id, rev_id, es_db_name
                    )
                    assert (
                        isinstance(delete_resp, dict) and delete_resp.get("ok") is True
                    ), f"Failed to delete document {doc_id} via Edge Server"

                    logger.info(f"Document {doc_id} deleted via Edge Server")

                    # Validating on Edge Server
                    logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                    try:
                        await edge_server.get_document(es_db_name, doc_id)
                    except CblEdgeServerBadResponseError:
                        pass  # expected, document not found (deleted)

                    logger.info(f"Document {doc_id} deleted from Edge Server")

                    # Validating on Sync Gateway
                    logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                    time.sleep(2)

                    try:
                        await sync_gateway.get_document(sg_db_name, doc_id)
                    except CblSyncGatewayBadResponseError:
                        pass  # expected, document not found (deleted)

                    logger.info(f"Document {doc_id} deleted from Sync Gateway")

            elif cycle == "edge_server":
                logger.info(f"Starting Edge Server cycle for {doc_id}")

                logger.info(f"Creating document {doc_id} via Edge Server")
                doc = {
                    "id": doc_id,
                    "channels": ["public"],
                    "timestamp": datetime.utcnow().isoformat(),
                }

                created_doc = await edge_server.put_document_with_id(
                    doc, doc_id, es_db_name
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Edge Server"
                )

                logger.info(f"Document {doc_id} created via Edge Server")

                time.sleep(5)

                logger.info(f"Validating document {doc_id} on Sync Gateway")
                sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                assert sg_doc is not None, (
                    f"Document {doc_id} does not exist on the sync gateway"
                )
                assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                assert sg_doc.revid is not None, (
                    "Revision ID (_rev) missing in the document"
                )

                logger.info(
                    f"Document {doc_id} fetched successfully from edge server with data: {sg_doc}"
                )

                rev_id = sg_doc.revid

                if "update" in operations:
                    # Create, update, delete and validate on Sync Gateway

                    logger.info(
                        f"Updating document by adding a 'changed' sub document in {doc_id} via Edge Server"
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

                    # Validate Update on Sync Gateway
                    logger.info(f"Validating update for {doc_id} on Sync Gateway")
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None
                    assert rev_id != sg_doc.revid, (
                        f"Document {doc_id} update not reflected on Sync Gateway"
                    )

                    logger.info(f"Document {doc_id} update reflected on Sync Gateway")

                    # Storing the revision ID
                    rev_id = sg_doc.revid

                if "delete" in operations:
                    # Delete on sync gateway and validate on edge server
                    logger.info(f"Deleting document {doc_id} via Sync Gateway")
                    assert rev_id is not None, "rev_id required for delete"
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)

                    logger.info(f"Document {doc_id} deleted via Sync Gateway")

                    logger.info(f"Validating deletion of {doc_id} on Edge Server")
                    time.sleep(2)

                    try:
                        await edge_server.get_document(es_db_name, doc_id)
                    except CblEdgeServerBadResponseError:
                        pass  # expected, document not found (deleted)

                    logger.info(f"Document {doc_id} deleted from Edge Server")

            doc_counter += 1

        logger.info("Test completed after 6 hours.")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting system test with Server, Sync Gateway, Edge Server and 1 client with intermittent connectivity with Edge Server"
        )

        # Calculate end time for 6 hours from now
        end_time = datetime.now() + timedelta(minutes=360)

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
            _config = json.load(file)
        assert isinstance(_config, dict), "config must be a dict"
        config: dict[str, Any] = _config
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name=es_db_name, config_file=config_path
        )
        await edge_server.wait_for_idle()

        logger.info("Edge Server configured with replication to Sync Gateway.")

        edge_server_down = False
        end = datetime.now() + timedelta(minutes=2400)

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

        # Run until 6 hours have passed
        while datetime.now() < end_time:
            if datetime.now() > end:
                self.mark_test_step("Edge server is back online")
                logger.info("Edge server is back online")

                await edge_server.start_server()
                time.sleep(10)
                edge_server_down = False

                self.mark_test_step(
                    "Check that Edge Server and Sync Gateway have the same number of documents"
                )
                sg_response = await sync_gateway.get_all_documents(
                    sg_db_name, "_default", "_default"
                )
                es_response = await edge_server.get_all_documents(es_db_name)

                assert len(sg_response.rows) == len(es_response.rows), (
                    "Document count mismatch between Sync Gateway and Edge Server"
                )
                self.mark_test_step(
                    f"BOTH SERVERS HAVE {len(sg_response.rows)} DOCUMENTS"
                )
                logger.info(
                    f"Sync Gateway has {len(sg_response.rows)} documents and Edge Server has {len(es_response.rows)} documents"
                )

            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])

            # Randomize the operation type (create, create_update_delete, create_delete)
            operations = random.choice(
                ["create", "create_update_delete", "create_delete"]
            )
            self.mark_test_step(
                f"Starting {cycle} cycle for {doc_id} with operations: {operations}"
            )

            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            if not edge_server_down and random.random() <= 0.4:  # 40% chance of chaos
                self.mark_test_step("Edge server goes offline for 2 minutes")
                logger.info("Edge server goes offline for 2 minutes")

                await edge_server.kill_server()
                end = datetime.now() + timedelta(minutes=1)
                time.sleep(10)
                edge_server_down = True

            if cycle == "sync_gateway":
                logger.info(f"Starting Sync Gateway cycle for {doc_id}")

                # Create on Sync Gateway and validate on Edge Server
                created_doc = await sync_gateway.create_document(
                    sg_db_name, doc_id, doc
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
                logger.info(f"Document {doc_id} created via Sync Gateway.")

                time.sleep(random.uniform(1, 5))

                if not edge_server_down:
                    remote_doc = await edge_server.get_document(es_db_name, doc_id)
                    assert remote_doc is not None, (
                        f"Document {doc_id} does not exist on the edge server."
                    )
                    assert remote_doc.id == doc_id, (
                        f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
                    )
                    assert remote_doc.revid is not None, (
                        "Revision ID (_rev) missing in the document"
                    )

                    logger.info(
                        f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
                    )
                rev_id = created_doc.revid

                if "update" in operations:
                    # Update on sync gateway and validate on edge server
                    logger.info(f"Updating document {doc_id} via Sync Gateway")
                    updated_doc_body = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "changed": "yes",
                    }
                    assert rev_id is not None, "rev_id required for update"
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, updated_doc_body, rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )

                    logger.info(f"Document {doc_id} updated via Sync Gateway")

                    # Validate update on Edge Server
                    if not edge_server_down:
                        logger.info(f"Validating update for {doc_id} on Edge Server")

                        remote_doc = await edge_server.get_document(es_db_name, doc_id)

                        assert remote_doc is not None, (
                            f"Document {doc_id} does not exist on the edge server"
                        )
                        assert remote_doc.id == doc_id, (
                            f"Document ID mismatch: {remote_doc.id}"
                        )
                        assert remote_doc.revid != rev_id, (
                            "Revision ID (_rev) missing in the document"
                        )

                        logger.info(
                            f"Document {doc_id} fetched successfully from edge server with data: {remote_doc}"
                        )

                    # Storing the revision ID
                    rev_id = updated_doc.revid

                if "delete" in operations:
                    if not edge_server_down:
                        # Delete on edge server and validate on sync gateway
                        logger.info(f"Deleting document {doc_id} via Edge Server")

                        delete_resp = await edge_server.delete_document(
                            doc_id, rev_id, es_db_name
                        )
                        assert (
                            isinstance(delete_resp, dict)
                            and delete_resp.get("ok") is True
                        ), f"Failed to delete document {doc_id} via Edge Server"

                        logger.info(f"Document {doc_id} deleted via Edge Server")

                        # Validating on Edge Server
                        logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                        try:
                            await edge_server.get_document(es_db_name, doc_id)
                        except CblEdgeServerBadResponseError:
                            pass  # expected, document not found (deleted)

                        logger.info(f"Document {doc_id} deleted from Edge Server")

                        # Validating on Sync Gateway
                        logger.info(f"Validating deletion of {doc_id} on Sync Gateway")
                        time.sleep(2)

                        try:
                            await sync_gateway.get_document(sg_db_name, doc_id)
                        except CblSyncGatewayBadResponseError:
                            pass  # expected, document not found (deleted)

                        logger.info(f"Document {doc_id} deleted from Sync Gateway")

            elif cycle == "edge_server":
                if not edge_server_down:
                    logger.info(f"Starting Edge Server cycle for {doc_id}")

                    logger.info(f"Creating document {doc_id} via Edge Server")
                    doc = {
                        "id": doc_id,
                        "channels": ["public"],
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                    created_doc = await edge_server.put_document_with_id(
                        doc, doc_id, es_db_name
                    )
                    assert created_doc is not None, (
                        f"Failed to create document {doc_id} via Edge Server"
                    )

                    logger.info(f"Document {doc_id} created via Edge Server")

                    logger.info(f"Validating document {doc_id} on Sync Gateway")
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None, (
                        f"Document {doc_id} does not exist on the sync gateway"
                    )
                    assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                    assert sg_doc.revid is not None, (
                        "Revision ID (_rev) missing in the document"
                    )

                    logger.info(
                        f"Document {doc_id} fetched successfully from edge server with data: {sg_doc}"
                    )

                    rev_id = sg_doc.revid

                    if "update" in operations:
                        # Create, update, delete and validate on Sync Gateway

                        logger.info(
                            f"Updating document by adding a 'changed' sub document in {doc_id} via Edge Server"
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

                        # Validate Update on Sync Gateway
                        logger.info(f"Validating update for {doc_id} on Sync Gateway")
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None
                        assert rev_id != sg_doc.revid, (
                            f"Document {doc_id} update not reflected on Sync Gateway"
                        )

                        logger.info(
                            f"Document {doc_id} update reflected on Sync Gateway"
                        )

                        # Storing the revision ID
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        # Delete on sync gateway and validate on edge server
                        logger.info(f"Deleting document {doc_id} via Sync Gateway")
                        assert rev_id is not None, "rev_id required for delete"
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)

                        logger.info(f"Document {doc_id} deleted via Sync Gateway")

                        logger.info(f"Validating deletion of {doc_id} on Edge Server")
                        time.sleep(2)

                        try:
                            await edge_server.get_document(es_db_name, doc_id)
                        except CblEdgeServerBadResponseError:
                            pass  # expected, document not found (deleted)

                        logger.info(f"Document {doc_id} deleted from Edge Server")

            doc_counter += 1

        logger.info("Test completed after 6 hours.")
