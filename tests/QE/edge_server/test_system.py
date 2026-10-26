import asyncio
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import (
    CblEdgeServerBadResponseError,
)
from cbltest.api.syncgateway import AllDocumentsResponse, DatabaseConfig, ScopeConfig, SyncGateway
from cbltest.asyncfile import read_json_file, write_json_file
from cbltest.utils import async_retry_assert

SCRIPT_DIR = str(Path(__file__).parent)
TOTAL_TEST_TIME = timedelta(minutes=360)


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


async def _wait_for_edge_server_to_match(
    sync_gateway: SyncGateway, edge_server: EdgeServer, sg_db_name: str, es_db_name: str
) -> AllDocumentsResponse:
    """Wait until Edge Server holds every document that Sync Gateway does, and return Sync Gateway's _all_docs."""
    sg_docs = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
    await edge_server.wait_for_documents(es_db_name, [row.id for row in sg_docs.rows])
    return sg_docs


@pytest.mark.min_edge_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.skip("These tests are marked for 6 hours each and flake as is - see CBL-8867")
class TestSystem(CBLTestClass):
    async def _setup_system_test(
        self, cblpytest: CBLPyTest, tmp_path: Path
    ) -> tuple[SyncGateway, EdgeServer, str, str]:
        """Create bucket, 10 docs, Sync Gateway db, Edge Server db; verify 10 docs on both.
        Returns (sync_gateway, edge_server, sg_db_name, es_db_name).
        """
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket on server.")
        bucket_name = "bucket-1"
        await server.create_bucket(bucket_name)
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
        config_path = str(tmp_path / "es_config.json")
        await write_json_file(config_path, config)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=es_db_name, config_file=config_path)

        self.mark_test_step("Verifying that Sync Gateway has 10 documents.")
        response = await sync_gateway.wait_for_document_count(sg_db_name, 10)
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."
        self.mark_test_step("Verifying that Edge Server has 10 documents.")
        await edge_server.wait_for_documents(es_db_name, [row.id for row in response.rows])
        response = await edge_server.get_all_documents(es_db_name)
        assert len(response.rows) == 10, f"Expected 10 documents, but got {len(response.rows)} documents."

        return sync_gateway, edge_server, sg_db_name, es_db_name

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_l(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        end_time = datetime.now(UTC) + TOTAL_TEST_TIME
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest, tmp_path)
        es_since = 0
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

                self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
                remote_doc = await edge_server.wait_for_document_body(es_db_name, doc_id, doc)

                rev_id = remote_doc.revid

                if "update" in operations:
                    assert rev_id is not None, "rev_id required for update"
                    self.mark_test_step(f"Updating {doc_id} on Sync Gateway.")
                    updated_doc = await sync_gateway.update_document(
                        sg_db_name, doc_id, _updated_doc_body(doc_id), rev_id
                    )
                    assert updated_doc is not None, f"Failed to update document {doc_id} via Sync Gateway"
                    self.mark_test_step(f"Verifying {doc_id} update on Edge Server.")
                    remote_doc = await edge_server.wait_for_document_body(es_db_name, doc_id, {"changed": "yes"})

                    # Storing the revision ID
                    rev_id = remote_doc.revid

                if "delete" in operations:
                    # Delete on edge server and validate on sync gateway
                    self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                    assert rev_id is not None, f"Document {doc_id} has no revision ID."
                    sg_since = await sync_gateway.get_last_sequence(sg_db_name)
                    delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                        f"Failed to delete document {doc_id} via Edge Server"
                    )
                    # Validating on Edge Server
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Sync Gateway.")
                    await sync_gateway.wait_for_documents(sg_db_name, [doc_id], deleted=True, since=sg_since)
            elif cycle == "edge_server":
                self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                assert created_doc is not None, f"Failed to create document {doc_id} via Edge Server"
                self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
                sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, doc)

                rev_id = sg_doc.revid

                if "update" in operations:
                    self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                    updated_doc = await edge_server.put_document_with_id(
                        _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                    )

                    assert updated_doc is not None, f"Failed to update document {doc_id} via Edge Server"
                    # Validate Update on Sync Gateway
                    self.mark_test_step(f"Verifying {doc_id} update on Sync Gateway.")
                    sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, {"changed": "yes"})
                    # Storing the revision ID
                    rev_id = sg_doc.revid

                if "delete" in operations:
                    # Delete on sync gateway and validate on edge server
                    assert rev_id is not None, "rev_id required for delete"
                    self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Edge Server.")
                    tombstones = await edge_server.wait_for_documents(
                        es_db_name, [doc_id], deleted=True, since=es_since
                    )
                    es_since = tombstones[doc_id]["seq"]
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_one_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        end_time = datetime.now(UTC) + TOTAL_TEST_TIME
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest, tmp_path)
        es_since = 0
        edge_server_down = False
        end = datetime.now(UTC) + timedelta(minutes=2400)
        doc_counter = 11

        while datetime.now(UTC) < end_time:
            if edge_server_down and datetime.now(UTC) > end:
                self.mark_test_step("Restarting Edge Server after chaos window.")
                await cblpytest.edge_servers[0].start_server()
                edge_server_down = False

                self.mark_test_step("Verifying doc counts match after Edge Server restart.")
                sg_response = await _wait_for_edge_server_to_match(sync_gateway, edge_server, sg_db_name, es_db_name)
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
                await cblpytest.edge_servers[0].kill_server()
                end = datetime.now(UTC) + timedelta(minutes=1)
                edge_server_down = True

            if cycle == "sync_gateway":
                # Create on Sync Gateway and validate on Edge Server
                self.mark_test_step(f"Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                assert created_doc is not None, f"Failed to create document {doc_id} via Sync Gateway."

                if not edge_server_down:
                    self.mark_test_step(f"Verifying {doc_id} on Edge Server.")
                    await edge_server.wait_for_document_body(es_db_name, doc_id, doc)

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
                        await edge_server.wait_for_document_body(es_db_name, doc_id, {"changed": "yes"})

                    # Storing the revision ID
                    rev_id = updated_doc.revid

                if "delete" in operations and not edge_server_down:
                    # Delete on edge server and validate on sync gateway
                    self.mark_test_step(f"Deleting {doc_id} on Edge Server.")
                    assert rev_id is not None, f"Document {doc_id} has no revision ID."
                    sg_since = await sync_gateway.get_last_sequence(sg_db_name)
                    delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                        f"Failed to delete document {doc_id} via Edge Server"
                    )
                    # Validating on Edge Server
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    self.mark_test_step(f"Verifying {doc_id} deleted on Sync Gateway.")
                    await sync_gateway.wait_for_documents(sg_db_name, [doc_id], deleted=True, since=sg_since)
            elif cycle == "edge_server":
                if not edge_server_down:
                    self.mark_test_step(f"Creating {doc_id} on Edge Server.")
                    created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                    assert created_doc is not None, f"Failed to create document {doc_id} via Edge Server"
                    self.mark_test_step(f"Verifying {doc_id} on Sync Gateway.")
                    sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, doc)

                    rev_id = sg_doc.revid

                    if "update" in operations:
                        self.mark_test_step(f"Updating {doc_id} on Edge Server.")
                        updated_doc = await edge_server.put_document_with_id(
                            _updated_doc_body(doc_id), doc_id, es_db_name, rev=rev_id
                        )

                        assert updated_doc is not None, f"Failed to update document {doc_id} via Edge Server"
                        # Validate Update on Sync Gateway
                        self.mark_test_step(f"Verifying {doc_id} update on Sync Gateway.")
                        sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, {"changed": "yes"})

                        # Storing the revision ID
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        # Delete on sync gateway and validate on edge server
                        assert rev_id is not None, "rev_id required for delete"
                        self.mark_test_step(f"Deleting {doc_id} on Sync Gateway.")
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        self.mark_test_step(f"Verifying {doc_id} deleted on Edge Server.")
                        tombstones = await edge_server.wait_for_documents(
                            es_db_name, [doc_id], deleted=True, since=es_since
                        )
                        es_since = tombstones[doc_id]["seq"]
            doc_counter += 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_concurrent(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now(UTC) + TOTAL_TEST_TIME
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest, tmp_path)

        async def client_worker(client_id: int) -> None:
            doc_counter = 1
            es_since = 0

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

                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Edge Server.")
                    remote_doc = await edge_server.wait_for_document_body(es_db_name, doc_id, doc)
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
                        remote_doc = await edge_server.wait_for_document_body(es_db_name, doc_id, {"changed": "yes"})
                        rev_id = remote_doc.revid

                    if "delete" in operations:
                        self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Edge Server.")
                        assert rev_id is not None, f"Document {doc_id} has no revision ID."
                        sg_since = await sync_gateway.get_last_sequence(sg_db_name)
                        delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                        assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                            f"[Client {client_id}] Failed to delete {doc_id} via Edge Server"
                        )
                        self.mark_test_step(
                            f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server and Sync Gateway."
                        )
                        with pytest.raises(CblEdgeServerBadResponseError):
                            await edge_server.get_document(es_db_name, doc_id)
                        await sync_gateway.wait_for_documents(sg_db_name, [doc_id], deleted=True, since=sg_since)

                else:  # edge_server
                    self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Edge Server.")
                    created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                    assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Edge Server"

                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Sync Gateway.")
                    sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, doc)
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
                        sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, {"changed": "yes"})
                        rev_id = sg_doc.revid

                    if "delete" in operations:
                        assert rev_id is not None, f"[Client {client_id}] rev_id required for delete of {doc_id}"
                        self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Sync Gateway.")
                        await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server.")
                        tombstones = await edge_server.wait_for_documents(
                            es_db_name, [doc_id], deleted=True, since=es_since
                        )
                        es_since = tombstones[doc_id]["seq"]

                doc_counter += 1

        async with asyncio.TaskGroup() as tg:
            for i in range(NUM_CLIENTS):
                tg.create_task(client_worker(i))

        self.mark_test_step("Verifying final doc counts match between SG and Edge Server.")
        sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
        es_response = await edge_server.get_all_documents(es_db_name)
        assert len(sg_response.rows) == len(es_response.rows), (
            f"Final doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system_multi_client_chaos(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        NUM_CLIENTS = 4
        end_time = datetime.now(UTC) + TOTAL_TEST_TIME
        (
            sync_gateway,
            edge_server,
            sg_db_name,
            es_db_name,
        ) = await self._setup_system_test(cblpytest, tmp_path)
        # Per worker, since another worker's later tombstone does not bound this one's.
        es_since: dict[int, int] = {i: 0 for i in range(NUM_CLIENTS)}

        shared = {"edge_server_down": False, "outages": 0, "paused": False, "active": 0}
        cycle_state = asyncio.Condition()
        recent_docs: list[str] = []

        @asynccontextmanager
        async def worker_cycle() -> AsyncIterator[None]:
            """Hold one worker cycle open, first waiting out any pause from workers_paused."""
            async with cycle_state:
                await cycle_state.wait_for(lambda: not shared["paused"])
                shared["active"] += 1
            try:
                yield
            finally:
                async with cycle_state:
                    shared["active"] -= 1
                    cycle_state.notify_all()

        @asynccontextmanager
        async def workers_paused() -> AsyncIterator[None]:
            """Stop new worker cycles and wait for the running ones to finish, resuming them on exit."""
            async with cycle_state:
                shared["paused"] = True
                await cycle_state.wait_for(lambda: shared["active"] == 0)
            try:
                yield
            finally:
                async with cycle_state:
                    shared["paused"] = False
                    cycle_state.notify_all()

        async def chaos_controller() -> None:
            while datetime.now(UTC) < end_time:
                # Random quiet period of 5–20 minutes between chaos events.
                await asyncio.sleep(random.uniform(300, 1200))
                if datetime.now(UTC) >= end_time:
                    break

                # Flag the outage before the kill, so a worker that fails mid-step can tell why.
                self.mark_test_step("Triggering chaos: killing Edge Server.")
                shared["edge_server_down"] = True
                shared["outages"] += 1
                await cblpytest.edge_servers[0].kill_server()

                # Keep edge server down for ~1 minute then restart.
                await asyncio.sleep(60)

                self.mark_test_step("Restarting Edge Server after chaos window.")
                await cblpytest.edge_servers[0].start_server()
                shared["edge_server_down"] = False

                async with workers_paused():
                    self.mark_test_step("Verifying doc counts match after Edge Server restart.")
                    await wait_for_counts_to_match()

        async def wait_for_counts_to_match() -> None:
            """Poll for up to 60s until Sync Gateway and Edge Server hold the same number of docs."""

            async def _poll() -> None:
                sg_response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")
                es_response = await edge_server.get_all_documents(es_db_name)
                assert len(sg_response.rows) == len(es_response.rows), (
                    f"Doc count mismatch: SG has {len(sg_response.rows)}, ES has {len(es_response.rows)}"
                )

            await async_retry_assert(_poll, tenacity.wait_fixed(1), tenacity.stop_after_delay(60))

        async def fire_read_burst(doc_id: str) -> None:
            if shared["edge_server_down"]:
                return
            self.mark_test_step(f"Firing {NUM_CLIENTS} concurrent reads of {doc_id} on Edge Server.")
            reads = [edge_server.get_document(es_db_name, doc_id) for _ in range(NUM_CLIENTS)]
            results = await asyncio.gather(*reads, return_exceptions=True)
            for result in results:
                if not isinstance(result, Exception):
                    assert result is not None

        async def run_cycle(client_id: int, doc_id: str, edge_server_up: bool) -> None:
            """Create doc_id through a random server, then maybe update and delete it, checking each step replicates."""
            cycle = random.choice(["sync_gateway", "edge_server"])
            operations = random.choice(["create", "create_update_delete", "create_delete"])
            self.mark_test_step(f"[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}")
            doc = _doc_body(doc_id)

            if cycle == "sync_gateway":
                self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Sync Gateway.")
                created_doc = await sync_gateway.create_document(sg_db_name, doc_id, doc)
                assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Sync Gateway"

                if edge_server_up:
                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Edge Server.")
                    await edge_server.wait_for_document_body(es_db_name, doc_id, doc)
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
                    assert updated_doc is not None, f"[Client {client_id}] Failed to update {doc_id} via Sync Gateway"
                    if edge_server_up:
                        self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Edge Server.")
                        await edge_server.wait_for_document_body(es_db_name, doc_id, {"changed": "yes"})
                    rev_id = updated_doc.revid

                if "delete" in operations and edge_server_up:
                    self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Edge Server.")
                    assert rev_id is not None, f"Document {doc_id} has no revision ID."
                    sg_since = await sync_gateway.get_last_sequence(sg_db_name)
                    delete_resp = await edge_server.delete_document(doc_id, rev_id, es_db_name)
                    assert isinstance(delete_resp, dict) and delete_resp.get("ok") is True, (
                        f"[Client {client_id}] Failed to delete {doc_id} via Edge Server"
                    )
                    with pytest.raises(CblEdgeServerBadResponseError):
                        await edge_server.get_document(es_db_name, doc_id)
                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Sync Gateway.")
                    await sync_gateway.wait_for_documents(sg_db_name, [doc_id], deleted=True, since=sg_since)

            elif edge_server_up:
                self.mark_test_step(f"[Client {client_id}] Creating {doc_id} on Edge Server.")
                created_doc = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
                assert created_doc is not None, f"[Client {client_id}] Failed to create {doc_id} via Edge Server"

                self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} on Sync Gateway.")
                sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, doc)
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
                    assert updated_doc is not None, f"[Client {client_id}] Failed to update {doc_id} via Edge Server"
                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} update on Sync Gateway.")
                    sg_doc = await sync_gateway.wait_for_document_body(sg_db_name, doc_id, {"changed": "yes"})
                    rev_id = sg_doc.revid

                if "delete" in operations:
                    assert rev_id is not None, f"[Client {client_id}] rev_id required for delete of {doc_id}"
                    self.mark_test_step(f"[Client {client_id}] Deleting {doc_id} on Sync Gateway.")
                    await sync_gateway.delete_document(doc_id, rev_id, sg_db_name)
                    self.mark_test_step(f"[Client {client_id}] Verifying {doc_id} deleted on Edge Server.")
                    tombstones = await edge_server.wait_for_documents(
                        es_db_name, [doc_id], deleted=True, since=es_since[client_id]
                    )
                    es_since[client_id] = tombstones[doc_id]["seq"]

            # Jitter, so the workers do not run in lockstep or flood Sync Gateway while Edge Server is down.
            await asyncio.sleep(random.uniform(1, 5))

        async def client_worker(client_id: int) -> None:
            doc_counter = 1
            while datetime.now(UTC) < end_time:
                doc_id = f"cc{client_id}_doc_{doc_counter}"
                async with worker_cycle():
                    # Decided once, since Edge Server can restart mid-cycle without the docs this cycle wrote.
                    edge_server_up = not shared["edge_server_down"]
                    outages = shared["outages"]
                    try:
                        await run_cycle(client_id, doc_id, edge_server_up)
                    except Exception:
                        if not edge_server_up or shared["outages"] == outages:
                            raise
                        self.mark_test_step(
                            f"[Client {client_id}] Abandoned {doc_id}: Edge Server went down mid-cycle."
                        )
                doc_counter += 1

        async with asyncio.TaskGroup() as tg:
            for i in range(NUM_CLIENTS):
                tg.create_task(client_worker(i))
            tg.create_task(chaos_controller())

        self.mark_test_step("Verifying final doc counts match between SG and Edge Server.")
        await wait_for_counts_to_match()
