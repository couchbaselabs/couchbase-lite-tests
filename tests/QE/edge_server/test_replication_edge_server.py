import asyncio
import json
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud

SCRIPT_DIR = str(Path(__file__).parent)


class TestEdgeServerSync(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_sgw_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("test_edge_to_sgw_replication")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")
        sgw = cblpytest.sync_gateways[0]
        source_db = sgw.replication_url("travel")

        self.mark_test_step("Configure Edge Server with travel dataset")
        config_path = f"{SCRIPT_DIR}/config/test_sgw_edge_server.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = source_db
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="travel", config_file=config_path
        )

        self.mark_test_step("Monitor replication progress")
        is_idle = False
        status = None
        while not is_idle:
            status = await edge_server.all_replication_status()
            assert "error" not in status[0].keys(), (
                f"Replication setup failure: {status}"
            )
            if status[0]["status"] == "Idle":
                is_idle = True

        self.mark_test_step("Verify document parity")
        for collection in [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]:
            edge_docs = await edge_server.get_all_documents(
                "travel", collection=collection
            )

            # Get from SGW
            sgw_docs = await sgw.get_all_documents(
                "travel", scope="travel", collection=collection.split(".")[1]
            )

            assert len(edge_docs.rows) == len(sgw_docs.rows), (
                f"Collection {collection} count mismatch"
            )

            for edge_doc, sgw_doc in zip(edge_docs.rows, sgw_docs.rows):
                assert edge_doc.id == sgw_doc.id, "Document ID mismatch"

        self.mark_test_step("Test document updates")
        update_doc = {
            "_id": "airline_10000",
            "type": "airline",
            "name": "Updated Airline",
            "data": "UPD",
        }

        await edge_server.put_document_with_id(
            update_doc, "airline_10000", "travel", collection="travel.airlines", ttl=30
        )

        sgw_doc = await sgw.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert sgw_doc.body["name"] == "Updated Airline", "Update not propagated"
        await asyncio.sleep(60)
        self.mark_test_step(
            "Verify TTL document purged on Edge server and not Sync Gateway"
        )
        sgw_doc = await sgw.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert sgw_doc.body["name"] == "Updated Airline", (
            "Document should not have purged from Sync gateway"
        )
        failed = False
        edge_doc = None
        try:
            edge_doc = await edge_server.get_document(
                "travel", collection="travel.airlines", doc_id="airline_10000"
            )
        except Exception as e:
            failed = True
            self.mark_test_step(f"Document purged on Edge server as expected: {e}")
        assert failed, f"Document not purged on Edge server {edge_doc}"
        await edge_server.stop_replication(status[0]["task_id"])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("test_edge_to_edge_replication")
        config_path1 = f"{SCRIPT_DIR}/config/test_primary_edge.json"
        config_path2 = f"{SCRIPT_DIR}/config/test_edge_to_edge_server.json"

        self.mark_test_step("Configure Edge Server with travel dataset")
        edge_server1 = await cblpytest.edge_servers[0].configure_dataset(
            db_name="travel", config_file=config_path1
        )
        source_db = edge_server1.replication_url("travel")
        with open(config_path2) as file:
            config = json.load(file)
        config["replications"][0]["source"] = source_db
        with open(config_path2, "w") as file:
            json.dump(config, file, indent=4)

        edge_server2 = await cblpytest.edge_servers[1].configure_dataset(
            db_name="travel", config_file=config_path2
        )

        self.mark_test_step("Monitor replication progress")
        is_idle = False
        status = None
        while not is_idle:
            status = await edge_server2.all_replication_status()
            assert "error" not in status[0].keys(), (
                f"Replication setup failure: {status}"
            )
            if status[0]["status"] == "Idle":
                is_idle = True

        self.mark_test_step("Verify document parity")
        for collection in [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]:
            edge_docs = await edge_server1.get_all_documents(
                "travel", collection=collection
            )
            edge2_docs = await edge_server2.get_all_documents(
                "travel", collection=collection
            )
            assert len(edge_docs.rows) == len(edge2_docs.rows), (
                f"Collection {collection} count mismatch"
            )
            for edge_doc, edge2_doc in zip(edge_docs.rows, edge2_docs.rows):
                assert edge_doc.id == edge2_doc.id, "Document ID mismatch"

        self.mark_test_step("Test document updates")
        update_doc = {
            "_id": "airline_10000",
            "type": "airline",
            "name": "Updated Airline",
            "data": "UPD",
        }

        # Update via Edge HTTP client
        await edge_server2.put_document_with_id(
            update_doc, "airline_10000", "travel", collection="travel.airlines", ttl=30
        )

        edge_doc = await edge_server1.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert edge_doc.body["name"] == "Updated Airline", "Update not propagated"
        await asyncio.sleep(60)
        self.mark_test_step(
            "Verify TTL document purged on Edge server2 and not Edge server1"
        )
        edge_doc = await edge_server1.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert edge_doc.body["name"] == "Updated Airline", (
            "Document should not have purged from Edge server1"
        )
        failed = False
        try:
            edge_doc = await edge_server2.get_document(
                "travel", collection="travel.airlines", doc_id="airline_10000"
            )
        except Exception as e:
            failed = True
            self.mark_test_step(f"Document purged on Edge server2 as expected: {e}")
        assert failed, f"Document not purged on Edge server2 {edge_doc}"
        await edge_server2.stop_replication(status[0]["task_id"])
