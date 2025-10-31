from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
import os
from cbltest.api.httpclient import HTTPClient
import json


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

        # Get infrastructure components
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        sgw = cblpytest.sync_gateways[0]
        http_client = cblpytest.http_clients[0]

        # 1. Configure Edge Server with travel dataset
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        self.mark_test_step("Configure Edge Server with travel dataset")
        source_db = sgw.replication_url("travel")
        # Load the existing config
        config_path = (
            f"{file_path}/environment/edge_server/config/test_sgw_edge_server.json"
        )
        with open(config_path, "r") as file:
            config = json.load(file)

        # Update the source dynamically
        config["replications"][0]["source"] = source_db

        # Save the updated config
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server = await edge_server.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )
        await edge_server.add_user("admin", "password")
        edge_server.set_auth("admin", "password")
        client = HTTPClient(http_client, edge_server)
        await client.connect()
        # # 5. Monitor replication status
        self.mark_test_step("Monitor replication progress")
        status = await client.all_replication_status()
        print(status)

        # 6. Verify documents via HTTP client
        self.mark_test_step("Verify document parity")
        for collection in [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]:
            # Get from Edge
            edge_docs = await client.get_all_documents("travel", collection=collection)

            # Get from SGW
            sgw_docs = await sgw.get_all_documents(
                "travel", scope="travel", collection=collection.split(".")[1]
            )

            assert len(edge_docs.rows) == len(sgw_docs.rows), (
                f"Collection {collection} count mismatch"
            )

            for edge_doc, sgw_doc in zip(edge_docs.rows, sgw_docs.rows):
                assert edge_doc.id == sgw_doc.id, "Document ID mismatch"

        # 7. Test updates through HTTP client
        self.mark_test_step("Test document updates")
        update_doc = {
            "_id": "airline_10000",
            "type": "airline",
            "name": "Updated Airline",
            "iata": "UPD",
        }

        # Update via Edge HTTP client
        await client.put_document_with_id(
            update_doc, "airline_10000", "travel", collection="travel.airlines"
        )

        # Verify update propagated to SGW
        sgw_doc = await sgw.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert sgw_doc.body["name"] == "Updated Airline", "Update not propagated"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_to_edge_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        self.mark_test_step("test_edge_to_edge_replication")

        # Get infrastructure components
        edge_server1 = cblpytest.edge_servers[0]
        edge_server2 = cblpytest.edge_servers[1]
        http_client = cblpytest.http_clients[0]
        await edge_server1.reset_db()
        await edge_server2.reset_db()
        # 1. Configure Edge Server with travel dataset
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        self.mark_test_step("Configure Edge Server with travel dataset")
        # Load the existing config to edge1
        config_path1 = (
            f"{file_path}/environment/edge_server/config/test_primary_edge.json"
        )
        edge_server1 = await edge_server1.set_config(
            config_path1, "/opt/couchbase-edge-server/etc/config.json"
        )
        source_db = edge_server1.replication_url("travel")
        config_path = (
            f"{file_path}/environment/edge_server/config/test_edge_to_edge_server.json"
        )
        with open(config_path, "r") as file:
            config = json.load(file)

        # Update the source dynamically
        config["replications"][0]["source"] = source_db

        # Save the updated config
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)

        edge_server2 = await edge_server2.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )

        client = HTTPClient(http_client, edge_server2)
        await client.connect()
        # # 5. Monitor replication status
        self.mark_test_step("Monitor replication progress")
        status = await client.all_replication_status()
        print(status)

        # 6. Verify documents via HTTP client
        self.mark_test_step("Verify document parity")
        for collection in [
            "travel.airlines",
            "travel.airports",
            "travel.hotels",
            "travel.landmarks",
            "travel.routes",
        ]:
            # Get from Edge
            edge_docs = await client.get_all_documents("travel", collection=collection)

            # Get from edge2
            edge2_docs = await edge_server2.get_all_documents(
                "travel", collection=collection
            )

            assert len(edge_docs.rows) == len(edge2_docs.rows), (
                f"Collection {collection} count mismatch"
            )

            for edge_doc, edge2_doc in zip(edge_docs.rows, edge2_docs.rows):
                assert edge_doc.id == edge2_doc.id, "Document ID mismatch"

        # 7. Test updates through HTTP client
        self.mark_test_step("Test document updates")
        update_doc = {
            "_id": "airline_10000",
            "type": "airline",
            "name": "Updated Airline",
            "iata": "UPD",
        }

        # Update via Edge HTTP client
        await client.put_document_with_id(
            update_doc, "airline_10000", "travel", collection="travel.airlines"
        )

        # Verify update propagated to SGW
        sgw_doc = await edge_server2.get_document(
            db_name="travel",
            scope="travel",
            collection="airlines",
            doc_id="airline_10000",
        )
        assert sgw_doc.body["name"] == "Updated Airline", "Update not propagated"
