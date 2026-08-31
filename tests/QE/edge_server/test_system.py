import asyncio
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblSyncGatewayBadResponseError,
)
from cbltest.api.syncgateway import DatabaseConfig, RemoteDocument, ScopeConfig, SyncGateway
from cbltest.asyncfile import read_json_file, write_derived_json_file

SCRIPT_DIR = str(Path(__file__).parent)

# spec/tests/QE/edge_server/test_system.md fixes these runs at six hours. The elapsed
# window is the only thing that ends them: no loop here breaks out early (the one
# `break`, in multi_client_chaos's chaos_controller, just re-checks end_time after its
# 5-20 minute sleep), and nothing bounds them from outside. The Edge Server job sets
# neither PYTEST_TIMEOUT nor CBL_PYTEST_SESSION_TIMEOUT, and a session timeout would
# not help anyway -- pytest-timeout checks it between tests and sets shouldfail, so it
# never interrupts a test already running. Only a per-test PYTEST_TIMEOUT would.
#
# So nothing in CI runs this file today: jenkins/pipelines/QE/es/Jenkinsfile selects a
# single file through TEST_NAME, which defaults to test_crud.py, and hard-kills the
# stage at 60 minutes. Passing TEST_NAME=test_system.py would be killed roughly a
# sixth of the way in, with no result. These need a longer-running pipeline, or a
# shorter duration agreed with the spec.
SOAK_DURATION = timedelta(minutes=360)


def _doc_body(doc_id: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "channels": ["public"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _updated_doc_body(doc_id: str) -> dict[str, Any]:
    return {
        **_doc_body(doc_id),
        "changed": "yes",
    }


async def _get_document_after_rev(
    edge_server: EdgeServer,
    db_name: str,
    doc_id: str,
    previous_rev: str | None,
    *,
    timeout: float = 30.0,
) -> RemoteDocument | None:
    """
    Read doc_id from the Edge Server, waiting for a revision newer than
    previous_rev to arrive.

    A write made on Sync Gateway reaches the Edge Server by replication, so
    reading straight back races the replicator. Returns as soon as the
    revision differs, or the last revision seen once the timeout expires, so
    the caller's own assertion reports a genuine mismatch.
    """
    deadline = time.monotonic() + timeout
    remote_doc = await edge_server.get_document(db_name, doc_id)
    while time.monotonic() < deadline:
        if remote_doc is not None and remote_doc.revid != previous_rev:
            return remote_doc

        await asyncio.sleep(0.5)
        remote_doc = await edge_server.get_document(db_name, doc_id)

    return remote_doc


@pytest.mark.es
@pytest.mark.min_edge_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSystem(CBLTestClass):
    async def _setup_system_test(self, cblpytest: CBLPyTest) -> tuple[SyncGateway, EdgeServer, str, str]:
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
        payload = DatabaseConfig(
            bucket="bucket-1",
            scopes={
                "_default": ScopeConfig(collections={"_default": {"sync": "function(doc){channel(doc.channels);}"}})
            },
            num_index_replicas=0,
        )
        await cblpytest.sync_gateway_cluster.create_database(sg_db_name, payload)

        self.mark_test_step("Adding role and user to Sync Gateway.")
        input_data = {"_default._default": ["public"]}
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        self.mark_test_step("Creating a database on Edge Server with replication to Sync Gateway.")
        es_db_name = "db"
        config_path = f"{SCRIPT_DIR}/config/test_e2e_empty_database.json"
        config = await read_json_file(config_path)
        config["replications"][0]["source"] = sync_gateway.replication_url(sg_db_name)
        config_path = await write_derived_json_file(config_path, config)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=es_db_name, config_file=config_path)
        await edge_server.wait_for_idle()

        self.mark_test_step("Verifying that Sync Gateway has 10 documents.")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        self.mark_test_step("Verifying that Edge Server has 10 documents.")
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."

        return sync_gateway, edge_server, sg_db_name, es_db_name

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_l(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        end_time = datetime.now(UTC) + SOAK_DURATION
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)
        doc_counter = 11

        while datetime.now(UTC) < end_time:
            doc_id = f"doc_{doc_counter}"

            # Randomize whether the operation happens in the Sync Gateway cycle or Edge Server cycle
            cycle = random.choice(["sync_gateway", "edge_server"])
            operations = random.choice(["create", "create_update_delete", "create_delete"])
            self.mark_test_step(f"Cycle: doc {doc_id} via {cycle}, operations: {operations}")
            doc = _doc_body(doc_id)

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                self.mark_test_step(f"Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                assert created_doc is not None, f"Failed to create document {doc_id} via Sync Gateway."
                # Allow replication to propagate before validating (eventual consistency).
                await asyncio.sleep(random.uniform(1, 5))

                self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
                remote_doc = await edge_server.get_document(es_db_name, doc_id)
                assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server."
                assert remote_doc.id == doc_id, f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
                assert remote_doc.revid is not None, "Revision ID (_rev) missing in the document"

                rev_id = remote_doc.revid

                if "update" in operations:
                    assert rev_id is not None, "rev_id required for update"
                    self.mark_test_step(f"Updating {doc_id} on Sync Gateway.")
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, f"Failed to update document {doc_id} via Sync Gateway"
                    self.mark_test_step(f"Verifying {doc_id} update on Edge Server.")
                    remote_doc = await _get_document_after_rev(edge_server, es_db_name, doc_id, rev_id)

                    assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server"
                    assert remote_doc.id == doc_id, f"Document ID mismatch: {remote_doc.id}"
                    assert remote_doc.revid != rev_id, f"Document {doc_id} rev unchanged after update"

                    # Storing the revision ID
                    rev_id = remote_doc.revid

                if "delete" in operations:
                    # Delete on edge server and validate on sync gateway
                    self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                    assert rev_id is not None, f"Document {doc_id} has no revision ID."
                    delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                        f"Failed to delete document {doc_id} via Edge Server"
                    )
                    # Validating on Edge Server
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    # Allow replication to propagate before validating (eventual consistency).
                    await asyncio.sleep(2)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Sync Gateway.")
                    with pytest.raises(CblSyncGatewayBadResponseError):
                        await sync_gateway.get_document(sg_db_name, doc_id)
            elif cycle == "edge_server":
                self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                assert created_doc is not None, f"Failed to create document {doc_id} via Edge Server"
                # Allow replication to propagate before validating (eventual consistency).
                await asyncio.sleep(5)
                self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
                sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                assert sg_doc is not None, f"Document {doc_id} does not exist on the sync gateway"
                assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                assert sg_doc.revid is not None, "Revision ID (_rev) missing in the document"

                rev_id = sg_doc.revid

                if "update" in operations:
                    self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                    updated_doc = await edge_server.put_document_with_id(
                        _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                    )

                    assert updated_doc is not None, f"Failed to update document {doc_id} via Edge Server"
                    # Validate Update on Sync Gateway
                    self.mark_test_step(f"Verifying {doc_id} update on Sync Gateway.")
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None
                    assert rev_id != sg_doc.revid, f"Document {doc_id} update not reflected on Sync Gateway"
                    # Storing the revision ID
                    rev_id = sg_doc.revid

                if "delete" in operations:
                    # Delete on sync gateway and validate on edge server
                    assert rev_id is not None, "rev_id required for delete"
                    self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    # Allow replication to propagate before validating (eventual consistency).
                    await asyncio.sleep(2)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Edge Server.")
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        end_time = datetime.now(UTC) + SOAK_DURATION
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)
        edge_server_down = False
        # When chaos has killed the Edge Server, the time to restart it; None
        # when nothing is pending. It must be cleared once consumed, or every
        # later iteration retries the restart and Edge Server fails to bind
        # its port with "Address already in use".
        restart_at: datetime | None = None
        doc_counter = 11

        while datetime.now(UTC) < end_time:
            if restart_at is not None and datetime.now(UTC) > restart_at:
                self.mark_test_step("Restarting Edge Server after chaos window.")
                await edge_server.start_server()
                # Allow edge server to stabilize after restart.
                await asyncio.sleep(10)
                edge_server_down = False
                restart_at = None

                self.mark_test_step("Verifying doc counts match after Edge Server restart.")
                sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
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
                self.mark_test_step("Triggering chaos: killing Edge Server.")
                await edge_server.kill_server()
                restart_at = datetime.now(UTC) + timedelta(minutes=1)
                # Allow time after stopping edge server before next operations.
                await asyncio.sleep(10)
                edge_server_down = True

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                self.mark_test_step(f"Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                assert created_doc is not None, f"Failed to create document {doc_id} via Sync Gateway."
                # Allow replication to propagate before validating (eventual consistency).
                await asyncio.sleep(random.uniform(1, 5))

                if not edge_server_down:
                    self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
                    remote_doc = await edge_server.get_document(es_db_name, doc_id)
                    assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server."
                    assert remote_doc.id == doc_id, f"Document ID mismatch: expected {doc_id}, got {remote_doc.id}"
                    assert remote_doc.revid is not None, "Revision ID (_rev) missing in the document"

                rev_id = created_doc.revid

                if "update" in operations:
                    assert rev_id is not None, "rev_id required for update"
                    self.mark_test_step(f"Updating {doc_id} on Sync Gateway.")
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, f"Failed to update document {doc_id} via Sync Gateway"
                    # Validate update on Edge Server
                    if not edge_server_down:
                        self.mark_test_step(f"Verifying {doc_id} update on Edge Server.")
                        remote_doc = await _get_document_after_rev(edge_server, es_db_name, doc_id, rev_id)

                        assert remote_doc is not None, f"Document {doc_id} does not exist on the edge server"
                        assert remote_doc.id == doc_id, f"Document ID mismatch: {remote_doc.id}"
                        assert remote_doc.revid != rev_id, f"Document {doc_id} rev unchanged after update"

                    # Storing the revision ID
                    rev_id = updated_doc.revid

                if "delete" in operations and not edge_server_down:
                    # Delete on edge server and validate on sync gateway
                    self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                    assert rev_id is not None, f"Document {doc_id} has no revision ID."
                    delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                        f"Failed to delete document {doc_id} via Edge Server"
                    )
                    # Validating on Edge Server
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    # Allow replication to propagate before validating (eventual consistency).
                    await asyncio.sleep(2)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Sync Gateway.")
                    with pytest.raises(CblSyncGatewayBadResponseError):
                        await sync_gateway.get_document(sg_db_name, doc_id)
            elif cycle == "edge_server":
                if not edge_server_down:
                    self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                    created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                    assert created_doc is not None, f"Failed to create document {doc_id} via Edge Server"
                    self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None, f"Document {doc_id} does not exist on the sync gateway"
                    assert sg_doc.id == doc_id, f"Document ID mismatch: {sg_doc.id}"
                    assert sg_doc.revid is not None, "Revision ID (_rev) missing in the document"

                    rev_id = sg_doc.revid

                    if "update" in operations:
                        self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )

                        assert updated_doc is not None, f"Failed to update document {doc_id} via Edge Server"
                        # Validate Update on Sync Gateway
                        self.mark_test_step(f"Verifying {doc_id} update on Sync Gateway.")
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None
                        assert rev_id != sg_doc.revid, f"Document {doc_id} update not reflected on Sync Gateway"

                        # Storing the revision ID
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        # Delete on sync gateway and validate on edge server
                        assert rev_id is not None, "rev_id required for delete"
                        self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        # Allow replication to propagate before validating (eventual consistency).
                        await asyncio.sleep(2)
                        self.mark_test_step(f"Verifying {doc_id} deleted on Edge Server.")
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_concurrent(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now(UTC) + SOAK_DURATION
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)

        async def client_worker(client_id: int) -> None:
            doc_counter = 1

            while datetime.now(UTC) < end_time:
                doc_id = f"c{client_id}_doc_{doc_counter}"
                cycle = random.choice(["sync_gateway", "edge_server"])
                operations = random.choice(["create", "create_update_delete", "create_delete"])
                self.mark_test_step(f"[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}")
                doc = _doc_body(doc_id)

                if cycle == "sync_gateway":
                    self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Sync Gateway.")
                    created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                    assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Sync Gateway"
                    await asyncio.sleep(random.uniform(1, 5))

                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Edge Server.")
                    remote_doc = await edge_server.get_document(es_db_name, doc_id)
                    assert remote_doc is not None, f"[Client {client_id}] {doc_id} missing on Edge Server"
                    assert remote_doc.id == doc_id, (
                        f"[Client {client_id}] Doc ID mismatch: expected {doc_id}, got {remote_doc.id}"
                    )
                    assert remote_doc.revid is not None, f"[Client {client_id}] {doc_id} missing _rev on Edge Server"
                    rev_id = remote_doc.revid

                    if "update" in operations:
                        self.mark_test_step(f"[Client {client_id}] Updating {doc_id} on Sync Gateway.")
                        updated_doc = await sync_gateway.update_document(
                            sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Sync Gateway"
                        )
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Edge Server.")
                        remote_doc = await _get_document_after_rev(edge_server, es_db_name, doc_id, rev_id)
                        assert remote_doc is not None, (
                            f"[Client {client_id}] {doc_id} missing on Edge Server after update"
                        )
                        assert remote_doc.revid != rev_id, f"[Client {client_id}] {doc_id} rev unchanged after update"
                        rev_id = remote_doc.revid

                    if "delete" in operations:
                        self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Edge Server.")
                        assert rev_id is not None, f"Document {doc_id} has no revision ID."
                        delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                        assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
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
                    self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Edge Server.")
                    created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                    assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Edge Server"
                    await asyncio.sleep(5)

                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Sync Gateway.")
                    sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                    assert sg_doc is not None, f"[Client {client_id}] {doc_id} missing on Sync Gateway"
                    assert sg_doc.id == doc_id, f"[Client {client_id}] Doc ID mismatch: {sg_doc.id}"
                    assert sg_doc.revid is not None, f"[Client {client_id}] {doc_id} missing _rev on Sync Gateway"
                    rev_id = sg_doc.revid

                    if "update" in operations:
                        self.mark_test_step(f"[Client {client_id}] Updating {doc_id} on Edge Server.")
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Edge Server"
                        )
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Sync Gateway.")
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None
                        assert rev_id != sg_doc.revid, (
                            f"[Client {client_id}] {doc_id} update not reflected on Sync Gateway"
                        )
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        assert rev_id is not None, f"[Client {client_id}] rev_id required for delete of {doc_id}"
                        self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Sync Gateway.")
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        await asyncio.sleep(2)
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server.")
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)

                doc_counter += 1

        await asyncio.gather(*[client_worker(i) for i in range(NUM_CLIENTS)])

        self.mark_test_step("Verifying final doc counts match between SG and Edge Server.")
        sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
        es_response = await edge_server.get_all_documents(es_db_name)
        assert len(sg_response.rows) == len(es_response.rows), (
            f"Final doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now(UTC) + SOAK_DURATION
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest)

        shared = {"edge_server_down": False}
        recent_docs: list[str] = []

        async def chaos_controller() -> None:
            while datetime.now(UTC) < end_time:
                # Random quiet period of 5–20 minutes between chaos events.
                await asyncio.sleep(random.uniform(300, 1200))
                if datetime.now(UTC) >= end_time:
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

                self.mark_test_step("Verifying doc counts match after Edge Server restart.")
                sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
                es_response = await edge_server.get_all_documents(es_db_name)
                assert len(sg_response.rows) == len(es_response.rows), (
                    "Document count mismatch between Sync Gateway and Edge Server after restart"
                )

        async def fire_read_burst(doc_id: str) -> None:
            if shared["edge_server_down"]:
                return
            self.mark_test_step(f"Firing {NUM_CLIENTS} concurrent reads of {doc_id} on Edge Server.")
            reads = [edge_server.get_document(es_db_name, doc_id) for _ in range(NUM_CLIENTS)]
            results = await asyncio.gather(*reads, return_exceptions=True)
            for result in results:
                if not isinstance(result, Exception):
                    assert result is not None

        async def client_worker(client_id: int) -> None:
            doc_counter = 1

            while datetime.now(UTC) < end_time:
                doc_id = f"cc{client_id}_doc_{doc_counter}"
                cycle = random.choice(["sync_gateway", "edge_server"])
                operations = random.choice(["create", "create_update_delete", "create_delete"])
                self.mark_test_step(f"[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}")
                doc = _doc_body(doc_id)

                if cycle == "sync_gateway":
                    self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Sync Gateway.")
                    created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                    assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Sync Gateway"
                    await asyncio.sleep(random.uniform(1, 5))

                    if not shared["edge_server_down"]:
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Edge Server.")
                        remote_doc = await edge_server.get_document(es_db_name, doc_id)
                        assert remote_doc is not None, f"[Client {client_id}] {doc_id} missing on Edge Server"
                        assert remote_doc.id == doc_id, (
                            f"[Client {client_id}] Doc ID mismatch: expected {doc_id}, got {remote_doc.id}"
                        )
                        assert remote_doc.revid is not None, (
                            f"[Client {client_id}] {doc_id} missing _rev on Edge Server"
                        )
                        if len(recent_docs) >= 10:
                            recent_docs.pop(0)
                        recent_docs.append(doc_id)
                        await fire_read_burst(doc_id)

                    rev_id = created_doc.revid

                    if "update" in operations:
                        assert rev_id is not None, f"[Client {client_id}] rev_id required for update of {doc_id}"
                        self.mark_test_step(f"[Client {client_id}] Updating {doc_id} on Sync Gateway.")
                        updated_doc = await sync_gateway.update_document(
                            sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                        )
                        assert updated_doc is not None, (
                            f"[Client {client_id}] Failed to update {doc_id} via Sync Gateway"
                        )
                        if not shared["edge_server_down"]:
                            self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Edge Server.")
                            remote_doc = await _get_document_after_rev(edge_server, es_db_name, doc_id, rev_id)
                            assert remote_doc is not None, (
                                f"[Client {client_id}] {doc_id} missing on Edge Server after update"
                            )
                            assert remote_doc.revid != rev_id, (
                                f"[Client {client_id}] {doc_id} rev unchanged after update"
                            )
                        rev_id = updated_doc.revid

                    if "delete" in operations and not shared["edge_server_down"]:
                        self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Edge Server.")
                        assert rev_id is not None, f"Document {doc_id} has no revision ID."
                        delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                        assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                            f"[Client {client_id}] Failed to delete {doc_id} via Edge Server"
                        )
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
                        await asyncio.sleep(2)
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Sync Gateway.")
                        with pytest.raises(CblSyncGatewayBadResponseError):
                            await sync_gateway.get_document(sg_db_name, doc_id)

                else:  # edge_server
                    if not shared["edge_server_down"]:
                        self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Edge Server.")
                        created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                        assert created_doc is not None, (
                            f"[Client {client_id}] Failed to create {doc_id} via Edge Server"
                        )
                        await asyncio.sleep(5)

                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Sync Gateway.")
                        sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                        assert sg_doc is not None, f"[Client {client_id}] {doc_id} missing on Sync Gateway"
                        assert sg_doc.id == doc_id, f"[Client {client_id}] Doc ID mismatch: {sg_doc.id}"
                        assert sg_doc.revid is not None, f"[Client {client_id}] {doc_id} missing _rev on Sync Gateway"
                        rev_id = sg_doc.revid
                        if len(recent_docs) >= 10:
                            recent_docs.pop(0)
                        recent_docs.append(doc_id)
                        await fire_read_burst(doc_id)

                        if "update" in operations:
                            self.mark_test_step(f"[Client {client_id}] Updating {doc_id} on Edge Server.")
                            updated_doc = await edge_server.put_document_with_id(
                                _updated_doc_body(doc_id),
                                doc_id,
                                es_db_name,
                                rev=rev_id,
                            )
                            assert updated_doc is not None, (
                                f"[Client {client_id}] Failed to update {doc_id} via Edge Server"
                            )
                            self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Sync Gateway.")
                            sg_doc = await sync_gateway.get_document(sg_db_name, doc_id)
                            assert sg_doc is not None
                            assert rev_id != sg_doc.revid, (
                                f"[Client {client_id}] {doc_id} update not reflected on Sync Gateway"
                            )
                            rev_id = sg_doc.revid

                        if "delete" in operations:
                            assert rev_id is not None, f"[Client {client_id}] rev_id required for delete of {doc_id}"
                            self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Sync Gateway.")
                            await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                            await asyncio.sleep(2)
                            self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server.")
                            with pytest.raises(CblEdgeServerBadResponseError):
                                await edge_server.get_document(es_db_name, doc_id)

                doc_counter += 1

        tasks = [client_worker(i) for i in range(NUM_CLIENTS)]
        tasks.append(chaos_controller())
        await asyncio.gather(*tasks)

        self.mark_test_step("Verifying final doc counts match between SG and Edge Server.")
        sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
        es_response = await edge_server.get_all_documents(es_db_name)
        assert len(sg_response.rows) == len(es_response.rows), (
            f"Final doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
        )
