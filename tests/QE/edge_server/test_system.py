import json
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

SCRIPT_DIR = str(Path(__file__).parent)


def _doc_body(doc_id: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "channels": ["public"],
        "timestamp": datetime.utcnow().isoformat(),
    }


def _updated_doc_body(doc_id: str) -> dict[str, Any]:
    return {
        **_doc_body(doc_id),
        "changed": "yes",
    }


class TestSystem(CBLTestClass):
    async def _setup_system_test(self, cblpytest: CBLPyTest):
        """Create bucket, 10 docs, Sync Gateway db, Edge Server db; verify 10 docs on both.
        Returns (sync_gateway, edge_server, sg_db_name, es_db_name).
        """
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket on server.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        self.mark_test_step("Adding 10 documents to bucket.")
        for i in range(1, 11):
            doc_id = f"doc_{i}"
            server.upsert_document(bucket_name, doc_id, _doc_body(doc_id))

        self.mark_test_step("Creating a database on Sync Gateway.")
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

        self.mark_test_step("Adding role and user to Sync Gateway.")
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
        await edge_server.wait_for_idle()

        self.mark_test_step("Verifying that Sync Gateway has 10 documents.")
        response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )
        self.mark_test_step("Verifying that Edge Server has 10 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 10, (
            f"Expected 10 documents, but got {len(response.rows)} documents."
        )

        return sync_gateway, edge_server, sg_db_name, es_db_name

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_l(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        end_time = datetime.now() + timedelta(minutes=360)
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)
        doc_counter = 11

        while datetime.now() < end_time:
            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])
            operations = random.choice(
                ["create", "create_update_delete", "create_delete"]
            )
            self.mark_test_step(
                f"Cycle: doc {doc_id} via {cycle}, operations: {operations}"
            )
            doc = _doc_body(doc_id)

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                created_doc = await sync_gateway.create_document(
                    sg_db_name, doc_id, doc
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
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

                rev_id = remote_doc.revid

                if "update" in operations:
                    assert rev_id is not None, "rev_id required for update"
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )
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

                    # Storing the revision ID
                    rev_id = remote_doc.revid

                if "delete" in operations:
                    # Delete on edge server and validate on sync gateway
                    delete_resp = await edge_server.delete_document(
                        doc_id, rev_id, es_db_name
                    )
                    assert (
                        isinstance(delete_resp, dict) and delete_resp.get("ok") is True
                    ), f"Failed to delete document {doc_id} via Edge Server"
                    # Validating on Edge Server
                    try:
                        await edge_server.get_document(es_db_name, doc_id)
                    except CblEdgeServerBadResponseError:
                        pass  # expected, document not found (deleted)
                    # Validating on Sync Gateway
                    time.sleep(2)

                    try:
                        await sync_gateway.get_document(sg_db_name, doc_id)
                    except CblSyncGatewayBadResponseError:
                        pass  # expected, document not found (deleted)
            elif cycle == "edge_server":
                created_doc = await edge_server.put_document_with_id(
                    doc, doc_id, es_db_name
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Edge Server"
                )
                time.sleep(5)
                sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                assert sg_doc is not None, (
                    f"Document {doc_id} does not exist on the sync gateway"
                )
                assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                assert sg_doc.revid is not None, (
                    "Revision ID (_rev) missing in the document"
                )

                rev_id = sg_doc.revid

                if "update" in operations:
                    updated_doc = await edge_server.put_document_with_id(
                        _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                    )

                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Edge Server"
                    )
                    # Validate Update on Sync Gateway
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None
                    assert rev_id != sg_doc.revid, (
                        f"Document {doc_id} update not reflected on Sync Gateway"
                    )
                    # Storing the revision ID
                    rev_id = sg_doc.revid

                if "delete" in operations:
                    # Delete on sync gateway and validate on edge server
                    assert rev_id is not None, "rev_id required for delete"
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    time.sleep(2)

                    try:
                        await edge_server.get_document(es_db_name, doc_id)
                    except CblEdgeServerBadResponseError:
                        pass  # expected, document not found (deleted)
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        end_time = datetime.now() + timedelta(minutes=360)
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)
        edge_server_down = False
        end = datetime.now() + timedelta(minutes=2400)
        doc_counter = 11

        while datetime.now() < end_time:
            if datetime.now() > end:
                await edge_server.start_server()
                time.sleep(10)
                edge_server_down = False

                sg_response = await sync_gateway.get_all_documents(
                    sg_db_name, "_default", "_default"
                )
                es_response = await edge_server.get_all_documents(es_db_name)

                assert len(sg_response.rows) == len(es_response.rows), (
                    "Document count mismatch between Sync Gateway and Edge Server"
                )
            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])
            operations = random.choice(["create", "create_update_delete", "create_delete"])
            self.mark_test_step(f"Cycle: doc {doc_id} via {cycle}, operations: {operations}")
            doc = _doc_body(doc_id)

            if not edge_server_down and random.random() <= 0.4:  # 40% chance of chaos
                await edge_server.kill_server()
                end = datetime.now() + timedelta(minutes=1)
                time.sleep(10)
                edge_server_down = True

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
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

                rev_id = created_doc.revid

                if "update" in operations:
                    assert rev_id is not None, "rev_id required for update"
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )
                    # Validate update on Edge Server
                    if not edge_server_down:
                        remote_doc = await edge_server.get_document(es_db_name, doc_id)

                        assert remote_doc is not None, (
                            f"Document {doc_id} does not exist on the edge server"
                        )
                        assert remote_doc.id == doc_id, f"Document ID mismatch: {remote_doc.id}"
                        assert remote_doc.revid != rev_id, (
                            "Revision ID (_rev) missing in the document"
                        )

                    # Storing the revision ID
                    rev_id = updated_doc.revid

                if "delete" in operations:
                    if not edge_server_down:
                        # Delete on edge server and validate on sync gateway
                        delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                        assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                            f"Failed to delete document {doc_id} via Edge Server"
                        )
                        # Validating on Edge Server
                        try:
                            await edge_server.get_document(es_db_name, doc_id)
                        except CblEdgeServerBadResponseError:
                            pass  # expected, document not found (deleted)
                        # Validating on Sync Gateway
                        time.sleep(2)

                        try:
                            await sync_gateway.get_document(sg_db_name, doc_id)
                        except CblSyncGatewayBadResponseError:
                            pass  # expected, document not found (deleted)
            elif cycle == "edge_server":
                if not edge_server_down:
                    created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                    assert created_doc is not None, (
                        f"Failed to create document {doc_id} via Edge Server"
                    )
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None, (
                        f"Document {doc_id} does not exist on the sync gateway"
                    )
                    assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                    assert sg_doc.revid is not None, "Revision ID (_rev) missing in the document"

                    rev_id = sg_doc.revid

                    if "update" in operations:
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )

                        assert updated_doc is not None, (
                            f"Failed to update document {doc_id} via Edge Server"
                        )
                        # Validate Update on Sync Gateway
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None
                        assert rev_id != sg_doc.revid, (
                            f"Document {doc_id} update not reflected on Sync Gateway"
                        )

                        # Storing the revision ID
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        # Delete on sync gateway and validate on edge server
                        assert rev_id is not None, "rev_id required for delete"
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        time.sleep(2)

                        try:
                            await edge_server.get_document(es_db_name, doc_id)
                        except CblEdgeServerBadResponseError:
                            pass  # expected, document not found (deleted)
            doc_counter += 1
