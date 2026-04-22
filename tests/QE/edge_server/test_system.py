import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
                self.mark_test_step(f"Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(
                    sg_db_name, doc_id, doc
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
                # Allow replication to propagate before validating (eventual consistency).
                time.sleep(random.uniform(1, 5))

                self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
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
                    self.mark_test_step(f"Updating {doc_id} on Sync Gateway.")
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )
                    self.mark_test_step(f"Verifying {doc_id} update on Edge Server.")
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
                    self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                    delete_resp = await edge_server.delete_document(
                        doc_id, rev_id, es_db_name
                    )
                    assert (
                        isinstance(delete_resp, dict) and delete_resp.get("ok") is True
                    ), f"Failed to delete document {doc_id} via Edge Server"
                    # Validating on Edge Server
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    # Allow replication to propagate before validating (eventual consistency).
                    time.sleep(2)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Sync Gateway.")
                    with pytest.raises(CblSyncGatewayBadResponseError):
                        await sync_gateway.get_document(sg_db_name, doc_id)
            elif cycle == "edge_server":
                self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                created_doc = await edge_server.put_document_with_id(
                    doc, doc_id, es_db_name
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Edge Server"
                )
                # Allow replication to propagate before validating (eventual consistency).
                time.sleep(5)
                self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
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
                    self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                    updated_doc = await edge_server.put_document_with_id(
                        _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                    )

                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Edge Server"
                    )
                    # Validate Update on Sync Gateway
                    self.mark_test_step(f"Verifying {doc_id} update on Sync Gateway.")
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
                    self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    # Allow replication to propagate before validating (eventual consistency).
                    time.sleep(2)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Edge Server.")
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
                self.mark_test_step("Restarting Edge Server after chaos window.")
                await edge_server.start_server()
                # Allow edge server to stabilize after restart.
                time.sleep(10)
                edge_server_down = False

                self.mark_test_step(
                    "Verifying doc counts match after Edge Server restart."
                )
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
            operations = random.choice(
                ["create", "create_update_delete", "create_delete"]
            )
            self.mark_test_step(
                f"Cycle: doc {doc_id} via {cycle}, operations: {operations}"
            )
            doc = _doc_body(doc_id)

            if not edge_server_down and random.random() <= 0.4:  # 40% chance of chaos
                self.mark_test_step("Triggering chaos: killing Edge Server.")
                await edge_server.kill_server()
                end = datetime.now() + timedelta(minutes=1)
                # Allow time after stopping edge server before next operations.
                time.sleep(10)
                edge_server_down = True

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                self.mark_test_step(f"Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(
                    sg_db_name, doc_id, doc
                )
                assert created_doc is not None, (
                    f"Failed to create document {doc_id} via Sync Gateway."
                )
                # Allow replication to propagate before validating (eventual consistency).
                time.sleep(random.uniform(1, 5))

                if not edge_server_down:
                    self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
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
                    self.mark_test_step(f"Updating {doc_id} on Sync Gateway.")
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, (
                        f"Failed to update document {doc_id} via Sync Gateway"
                    )
                    # Validate update on Edge Server
                    if not edge_server_down:
                        self.mark_test_step(
                            f"Verifying {doc_id} update on Edge Server."
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
                    rev_id = updated_doc.revid

                if "delete" in operations:
                    if not edge_server_down:
                        # Delete on edge server and validate on sync gateway
                        self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                        delete_resp = await edge_server.delete_document(
                            doc_id, rev_id, es_db_name
                        )
                        assert (
                            isinstance(delete_resp, dict)
                            and delete_resp.get("ok") is True
                        ), f"Failed to delete document {doc_id} via Edge Server"
                        # Validating on Edge Server
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
                        # Allow replication to propagate before validating (eventual consistency).
                        time.sleep(2)
                        self.mark_test_step(
                            f"Verifying {doc_id} deleted on Sync Gateway."
                        )
                        with pytest.raises(CblSyncGatewayBadResponseError):
                            await sync_gateway.get_document(sg_db_name, doc_id)
            elif cycle == "edge_server":
                if not edge_server_down:
                    self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                    created_doc = await edge_server.put_document_with_id(
                        doc, doc_id, es_db_name
                    )
                    assert created_doc is not None, (
                        f"Failed to create document {doc_id} via Edge Server"
                    )
                    self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
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
                        self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )

                        assert updated_doc is not None, (
                            f"Failed to update document {doc_id} via Edge Server"
                        )
                        # Validate Update on Sync Gateway
                        self.mark_test_step(
                            f"Verifying {doc_id} update on Sync Gateway."
                        )
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
                        self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        # Allow replication to propagate before validating (eventual consistency).
                        time.sleep(2)
                        self.mark_test_step(
                            f"Verifying {doc_id} deleted on Edge Server."
                        )
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_concurrent(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now() + timedelta(minutes=360)
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)

        async def client_worker(client_id: int) -> None:
            doc_counter = 1

            while datetime.now() < end_time:
                doc_id = f"c{client_id}_doc_{doc_counter}"
                cycle = random.choice(["sync_gateway", "edge_server"])
                operations = random.choice(
                    ["create", "create_update_delete", "create_delete"]
                )
                self.mark_test_step(
                    f"[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}"
                )
                doc = _doc_body(doc_id)

                if cycle == "sync_gateway":
                    self.mark_test_step(
                        f"[Client {client_id}] Creating {doc_id} on Sync Gateway."
                    )
                    created_doc = await sync_gateway.create_document(
                        sg_db_name, doc_id, doc
                    )
                    assert created_doc is not None, (
                        f"[Client {client_id}] Failed to create {doc_id} via Sync Gateway"
                    )
                    await asyncio.sleep(random.uniform(1, 5))

                    self.mark_test_step(
                        f"[Client {client_id}] Verifying {doc_id} on Edge Server."
                    )
                    remote_doc = await edge_server.get_document(es_db_name, doc_id)
                    assert remote_doc is not None, (
                        f"[Client {client_id}] {doc_id} missing on Edge Server"
                    )
                    assert remote_doc.id == doc_id, (
                        f"[Client {client_id}] Doc ID mismatch: expected {doc_id}, got {remote_doc.id}"
                    )
                    assert remote_doc.revid is not None, (
                        f"[Client {client_id}] {doc_id} missing _rev on Edge Server"
                    )
                    rev_id = remote_doc.revid

                    if "update" in operations:
                        self.mark_test_step(
                            f"[Client {client_id}] Updating {doc_id} on Sync Gateway."
                        )
                        updated_doc = await sync_gateway.update_document(
                            sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Sync Gateway"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} update on Edge Server."
                        )
                        remote_doc = await edge_server.get_document(es_db_name, doc_id)
                        assert remote_doc is not None, (
                            f"[Client {client_id}] {doc_id} missing on Edge Server after update"
                        )
                        assert remote_doc.revid != rev_id, (
                            f"[Client {client_id}] {doc_id} rev unchanged after update"
                        )
                        rev_id = remote_doc.revid

                    if "delete" in operations:
                        self.mark_test_step(
                            f"[Client {client_id}] Deleting {doc_id} on Edge Server."
                        )
                        delete_resp = await edge_server.delete_document(
                            doc_id, rev_id, es_db_name
                        )
                        assert (
                            isinstance(delete_resp, dict)
                            and delete_resp.get("ok") is True
                        ), (
                            f"[Client {client_id}] Failed to delete {doc_id} via Edge Server"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server and Sync Gateway."
                        )
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
                        await asyncio.sleep(2)
                        with pytest.raises(CblSyncGatewayBadResponseError):
                            await sync_gateway.get_document(sg_db_name, doc_id)

                else:  # edge_server
                    self.mark_test_step(
                        f"[Client {client_id}] Creating {doc_id} on Edge Server."
                    )
                    created_doc = await edge_server.put_document_with_id(
                        doc, doc_id, es_db_name
                    )
                    assert created_doc is not None, (
                        f"[Client {client_id}] Failed to create {doc_id} via Edge Server"
                    )
                    await asyncio.sleep(5)

                    self.mark_test_step(
                        f"[Client {client_id}] Verifying {doc_id} on Sync Gateway."
                    )
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None, (
                        f"[Client {client_id}] {doc_id} missing on Sync Gateway"
                    )
                    assert sg_doc.id == doc_id, (
                        f"[Client {client_id}] Doc ID mismatch: {sg_doc.id}"
                    )
                    assert sg_doc.revid is not None, (
                        f"[Client {client_id}] {doc_id} missing _rev on Sync Gateway"
                    )
                    rev_id = sg_doc.revid

                    if "update" in operations:
                        self.mark_test_step(
                            f"[Client {client_id}] Updating {doc_id} on Edge Server."
                        )
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Edge Server"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} update on Sync Gateway."
                        )
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None
                        assert rev_id != sg_doc.revid, (
                            f"[Client {client_id}] {doc_id} update not reflected on Sync Gateway"
                        )
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        assert rev_id is not None, (
                            f"[Client {client_id}] rev_id required for delete of {doc_id}"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Deleting {doc_id} on Sync Gateway."
                        )
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        await asyncio.sleep(2)
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server."
                        )
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)

                doc_counter += 1

        await asyncio.gather(*[client_worker(i) for i in range(NUM_CLIENTS)])

        self.mark_test_step(
            "Verifying final doc counts match between SG and Edge Server."
        )
        sg_response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        es_response = await edge_server.get_all_documents(es_db_name)
        assert len(sg_response.rows) == len(es_response.rows), (
            f"Final doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_chaos(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now() + timedelta(minutes=360)
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)

        shared = {"edge_server_down": False, "recent_docs": []}

        async def chaos_controller() -> None:
            while datetime.now() < end_time:
                # Random quiet period of 5–20 minutes between chaos events.
                await asyncio.sleep(random.uniform(300, 1200))
                if datetime.now() >= end_time:
                    break

                self.mark_test_step("Triggering chaos: killing Edge Server.")
                await edge_server.kill_server()
                shared["edge_server_down"] = True
                # Allow time for clients to observe the outage before next operations.
                await asyncio.sleep(10)

                # Keep edge server down for ~1 minute then restart.
                await asyncio.sleep(60)

                self.mark_test_step("Restarting Edge Server after chaos window.")
                await edge_server.start_server()
                # Allow edge server to stabilize after restart.
                await asyncio.sleep(10)
                shared["edge_server_down"] = False

                self.mark_test_step(
                    "Verifying doc counts match after Edge Server restart."
                )
                sg_response = await sync_gateway.get_all_documents(
                    sg_db_name, "_default", "_default"
                )
                es_response = await edge_server.get_all_documents(es_db_name)
                assert len(sg_response.rows) == len(es_response.rows), (
                    "Document count mismatch between Sync Gateway and Edge Server after restart"
                )

        async def fire_read_burst(doc_id: str) -> None:
            if shared["edge_server_down"]:
                return
            self.mark_test_step(
                f"Firing {NUM_CLIENTS} concurrent reads of {doc_id} on Edge Server."
            )
            reads = [
                edge_server.get_document(es_db_name, doc_id) for _ in range(NUM_CLIENTS)
            ]
            results = await asyncio.gather(*reads, return_exceptions=True)
            for result in results:
                if not isinstance(result, Exception):
                    assert result is not None

        async def client_worker(client_id: int) -> None:
            doc_counter = 1

            while datetime.now() < end_time:
                doc_id = f"cc{client_id}_doc_{doc_counter}"
                cycle = random.choice(["sync_gateway", "edge_server"])
                operations = random.choice(
                    ["create", "create_update_delete", "create_delete"]
                )
                self.mark_test_step(
                    f"[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}"
                )
                doc = _doc_body(doc_id)

                if cycle == "sync_gateway":
                    self.mark_test_step(
                        f"[Client {client_id}] Creating {doc_id} on Sync Gateway."
                    )
                    created_doc = await sync_gateway.create_document(
                        sg_db_name, doc_id, doc
                    )
                    assert created_doc is not None, (
                        f"[Client {client_id}] Failed to create {doc_id} via Sync Gateway"
                    )
                    await asyncio.sleep(random.uniform(1, 5))

                    if not shared["edge_server_down"]:
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} on Edge Server."
                        )
                        remote_doc = await edge_server.get_document(es_db_name, doc_id)
                        assert remote_doc is not None, (
                            f"[Client {client_id}] {doc_id} missing on Edge Server"
                        )
                        assert remote_doc.id == doc_id, (
                            f"[Client {client_id}] Doc ID mismatch: expected {doc_id}, got {remote_doc.id}"
                        )
                        assert remote_doc.revid is not None, (
                            f"[Client {client_id}] {doc_id} missing _rev on Edge Server"
                        )
                        recent = shared["recent_docs"]
                        if len(recent) >= 10:
                            recent.pop(0)
                        recent.append(doc_id)
                        await fire_read_burst(doc_id)

                    rev_id = created_doc.revid

                    if "update" in operations:
                        assert rev_id is not None, (
                            f"[Client {client_id}] rev_id required for update of {doc_id}"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Updating {doc_id} on Sync Gateway."
                        )
                        updated_doc = await sync_gateway.update_document(
                            sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Sync Gateway"
                        )
                        if not shared["edge_server_down"]:
                            self.mark_test_step(
                                f"[Client {client_id}] Verifying {doc_id} update on Edge Server."
                            )
                            remote_doc = await edge_server.get_document(
                                es_db_name, doc_id
                            )
                            assert remote_doc is not None, (
                                f"[Client {client_id}] {doc_id} missing on Edge Server after update"
                            )
                            assert remote_doc.revid != rev_id, (
                                f"[Client {client_id}] {doc_id} rev unchanged after update"
                            )
                        rev_id = updated_doc.revid

                    if "delete" in operations:
                        if not shared["edge_server_down"]:
                            self.mark_test_step(
                                f"[Client {client_id}] Deleting {doc_id} on Edge Server."
                            )
                            delete_resp = await edge_server.delete_document(
                                doc_id, rev_id, es_db_name
                            )
                            assert (
                                isinstance(delete_resp, dict)
                                and delete_resp.get("ok") is True
                            ), (
                                f"[Client {client_id}] Failed to delete {doc_id} via Edge Server"
                            )
                            with pytest.raises(CblEdgeServerBadResponseError):
                                await edge_server.get_document(es_db_name, doc_id)
                            await asyncio.sleep(2)
                            self.mark_test_step(
                                f"[Client {client_id}] Verifying {doc_id} deleted on Sync Gateway."
                            )
                            with pytest.raises(CblSyncGatewayBadResponseError):
                                await sync_gateway.get_document(sg_db_name, doc_id)

                else:  # edge_server
                    if not shared["edge_server_down"]:
                        self.mark_test_step(
                            f"[Client {client_id}] Creating {doc_id} on Edge Server."
                        )
                        created_doc = await edge_server.put_document_with_id(
                            doc, doc_id, es_db_name
                        )
                        assert created_doc is not None, (
                            f"[Client {client_id}] Failed to create {doc_id} via Edge Server"
                        )
                        await asyncio.sleep(5)

                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} on Sync Gateway."
                        )
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None, (
                            f"[Client {client_id}] {doc_id} missing on Sync Gateway"
                        )
                        assert sg_doc.id == doc_id, (
                            f"[Client {client_id}] Doc ID mismatch: {sg_doc.id}"
                        )
                        assert sg_doc.revid is not None, (
                            f"[Client {client_id}] {doc_id} missing _rev on Sync Gateway"
                        )
                        rev_id = sg_doc.revid
                        recent = shared["recent_docs"]
                        if len(recent) >= 10:
                            recent.pop(0)
                        recent.append(doc_id)
                        await fire_read_burst(doc_id)

                        if "update" in operations:
                            self.mark_test_step(
                                f"[Client {client_id}] Updating {doc_id} on Edge Server."
                            )
                            updated_doc = await edge_server.put_document_with_id(
                                _updated_doc_body(doc_id),
                                doc_id,
                                es_db_name,
                                rev=rev_id,
                            )
                            assert updated_doc is not None, (
                                f"[Client {client_id}] Failed to update {doc_id} via Edge Server"
                            )
                            self.mark_test_step(
                                f"[Client {client_id}] Verifying {doc_id} update on Sync Gateway."
                            )
                            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                            assert sg_doc is not None
                            assert rev_id != sg_doc.revid, (
                                f"[Client {client_id}] {doc_id} update not reflected on Sync Gateway"
                            )
                            rev_id = sg_doc.revid

                        if "delete" in operations:
                            assert rev_id is not None, (
                                f"[Client {client_id}] rev_id required for delete of {doc_id}"
                            )
                            self.mark_test_step(
                                f"[Client {client_id}] Deleting {doc_id} on Sync Gateway."
                            )
                            await sync_gateway.delete_document(
                                doc_id, rev_id, sg_db_name
                            )
                            await asyncio.sleep(2)
                            self.mark_test_step(
                                f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server."
                            )
                            with pytest.raises(CblEdgeServerBadResponseError):
                                await edge_server.get_document(es_db_name, doc_id)

                doc_counter += 1

        tasks = [client_worker(i) for i in range(NUM_CLIENTS)]
        tasks.append(chaos_controller())
        await asyncio.gather(*tasks)

        self.mark_test_step(
            "Verifying final doc counts match between SG and Edge Server."
        )
        sg_response = await sync_gateway.get_all_documents(
            sg_db_name, "_default", "_default"
        )
        es_response = await edge_server.get_all_documents(es_db_name)
        assert len(sg_response.rows) == len(es_response.rows), (
            f"Final doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
        )
