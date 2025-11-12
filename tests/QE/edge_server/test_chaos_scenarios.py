import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import List

import pytest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.api.httpclient import ClientFactory, HTTPClient
from cbltest.api.json_generator import JSONGenerator


class TestEdgeServerChaos(CBLTestClass):
    # set up : changes -> ES3 <- ES2 <<- ES1 <- SGW
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_server_offline_sync_and_recovery(
        self, cblpytest, dataset_path
    ) -> None:
        self.mark_test_step("Edge Server Offline Sync and Recovery")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        # Get infrastructure components
        edge_server1 = cblpytest.edge_servers[0]
        edge_server2 = cblpytest.edge_servers[1]
        edge_server3 = cblpytest.edge_servers[2]

        await edge_server1.reset_db()
        await edge_server2.reset_db()
        await edge_server3.reset_db()

        sgw = cblpytest.sync_gateways[0]

        http_clients = cblpytest.http_clients[0]

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
        edge_server1 = await edge_server1.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )

        # setup edge 2
        config_path2 = (
            f"{file_path}/environment/edge_server/config/test_edge_to_edge_server.json"
        )
        source_db = edge_server1.replication_url("travel")
        with open(config_path2, "r") as file:
            config = json.load(file)

        # Update the source dynamically
        config["replications"][0]["source"] = source_db

        # Save the updated config
        with open(config_path2, "w") as file:
            json.dump(config, file, indent=4)
        edge_server2 = await edge_server2.set_config(
            config_path2, "/opt/couchbase-edge-server/etc/config.json"
        )

        # set up edge server3
        source_db = edge_server2.replication_url("travel")
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
        edge_server3 = await edge_server3.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )

        # set up client
        client = HTTPClient(http_clients, edge_server3)
        await client.connect()
        # 5. Monitor replication status
        self.mark_test_step("Monitor replication progress")
        status = await client.all_replication_status()
        assert "error" not in status[0].keys(), (
            f"Replication setup failure: {status[0]}"
        )
        print(status)

        # get all documents from travel.hotels

        all_docs = await client.get_all_documents(
            db_name="travel", collection="travel.hotels"
        )
        revmap = all_docs.revmap

        # delete all docs in collection travel.hotels in es3
        bulk_ops = [
            BulkDocOperation({"_deleted": True}, _id=doc_id, rev=rev, optype="delete")
            for doc_id, rev in revmap.items()
        ]
        resp = await client.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        print(resp)
        # kill server.
        await edge_server3.kill_server()

        # 6. Verify deletes on ES2 and ES1 and SGW
        self.mark_test_step("Verify document deleted")
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        # Get from SGW
        sgw_docs = await sgw.get_all_documents(
            "travel", scope="travel", collection="hotels"
        )

        assert (
            len(edge1_docs.rows) == len(sgw_docs.rows) == len(edge2_docs.rows) == 0
        ), (
            f"Collection hotels count mismatch in len(edge1_docs.rows): {len(edge1_docs.rows)} ,  len(sgw_docs.rows): {len(sgw_docs.rows)}, len(edge2_docs.rows):  {len(edge2_docs.rows)}"
        )

        # start server
        await edge_server3.start_server()
        # 7. Test inserts through HTTP client
        self.mark_test_step("Test document inserts")
        docgen = JSONGenerator(seed=10, size=10000)
        create_docs = docgen.generate_all_documents()
        bulk_ops = [BulkDocOperation(doc, optype="create") for doc in create_docs]
        resp = await edge_server3.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        print(resp)
        self.mark_test_step("Verify document inserted")
        # Update via Edge HTTP client
        all_docs = await client.get_all_documents(
            db_name="travel", collection="travel.hotels"
        )
        assert len(all_docs.rows) == docgen.size, "Inserted document count mismatch"
        # kill server
        await edge_server3.kill_server()

        # Verify create propagated to ES2, Es1, SGW
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        # Get from SGW
        sgw_docs = await sgw.get_all_documents(
            "travel", scope="travel", collection="hotels"
        )

        assert (
            len(edge1_docs.rows)
            == len(sgw_docs.rows)
            == len(edge2_docs.rows)
            == docgen.size
        ), (
            f"Collection hotels count mismatch in len(edge1_docs.rows): {len(edge1_docs.rows)} ,  len(sgw_docs.rows): {len(sgw_docs.rows)}, len(edge2_docs.rows):  {len(edge2_docs.rows)} and {docgen.size}"
        )

    async def perform_operation(
        self, client, optype, docs_dict, docgen, db_name, scope, collection, revmap
    ):
        """Perform async CRUD operation based on random optype"""
        try:
            if optype == "create":
                # Generate new document
                new_doc = docgen.generate_document(str(uuid.uuid4()))
                doc_id = new_doc["_id"]
                response = await client.put_document_with_id(
                    document=new_doc,
                    db_name=db_name,
                    scope=scope,
                    collection=collection,
                    doc_id=doc_id,
                )
                docs_dict[doc_id] = new_doc  # Add to existing docs
                revmap[doc_id] = response.get("rev")
                return response["ok"]

            # Select random existing document for other operations
            doc_id = random.choice(list(docs_dict.keys()))

            if optype == "update":
                updated_doc = docgen.update_document(docs_dict[doc_id])
                response = await client.put_document_with_id(
                    doc_id=doc_id,
                    document=updated_doc,
                    db_name=db_name,
                    scope=scope,
                    collection=collection,
                    rev=revmap[doc_id],
                )
                docs_dict[doc_id] = updated_doc  # Update local copy
                revmap[doc_id] = response.get("rev")
                return response["ok"]

            if optype == "delete":
                response = await client.delete_document(
                    doc_id,
                    revid=revmap[doc_id],
                    db_name=db_name,
                    scope=scope,
                    collection=collection,
                )
                print(response)
                if response.get("ok"):
                    del docs_dict[doc_id]  # Remove from local dict
                return response["ok"]

            if optype == "read":
                remote_doc = await client.get_document(
                    db_name=db_name, scope=scope, collection=collection, doc_id=doc_id
                )
                doc = docs_dict.get(doc_id)
                for key, value in remote_doc.body.items():
                    assert doc.get(key) == value
                return True

        except Exception as e:
            return {"error": str(e), "optype": optype, "doc_id": doc_id}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_server_with_multiple_rest_clients(
        self, cblpytest, dataset_path
    ) -> None:
        self.mark_test_step("Edge Server with 25 REST Clients Performing Reads/Writes")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        http_clients = cblpytest.http_clients
        # setup  config
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        config_path = f"{file_path}/environment/edge_server/config/test_edge_server_with_multiple_rest_clients.json"
        edge_server = await edge_server.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )

        factory = ClientFactory(
            vms=http_clients, edge_server=edge_server, num_clients_per_vm=5
        )
        await factory.create_clients()
        docgen = JSONGenerator(seed=10, size=10000)
        docs_list = docgen.generate_all_documents()
        bulk_ops = [BulkDocOperation(doc, optype="create") for doc in docs_list]
        await edge_server.bulk_doc_op(bulk_ops, db_name="db")
        self.mark_test_step("Verify document inserted")
        try:
            # Update via Edge HTTP client
            all_docs = await edge_server.get_all_documents(db_name="db")
            assert len(all_docs.rows) == docgen.size, "Inserted document count mismatch"
            revmap = all_docs.revmap
            docs_dict = {x["_id"]: x for x in docs_list}

            # random CRUD and verification
            optype = ["create", "update", "delete", "read"]
            for i in range(1000):
                op = random.choice(optype)
                client = factory.clients[random.randint(1, len(http_clients) * 5)]
                self.mark_test_step(f"{i} {op} {client.vm_ip} {client.client_id} ")
                result = await self.perform_operation(
                    client,
                    op,
                    docs_dict,
                    docgen,
                    db_name="db",
                    scope="",
                    collection="",
                    revmap=revmap,
                )
                assert result is True, f"{op} failed for client {client.vm_ip}"
            #     validate
            all_docs = await edge_server.get_all_documents(db_name="db")
            assert len(all_docs.rows) == len(docs_dict), "CRUD document count mismatch"
            for doc_id in docs_dict.keys():
                remote_doc = await edge_server.get_document(db_name="db", doc_id=doc_id)
                doc = docs_dict.get(doc_id)
                for key, value in remote_doc.body.items():
                    assert doc.get(key) == value
        except Exception as e:
            factory.disconnect()
            raise e

    async def kill_edge_perform_ops(
        self, kill_server: List, ops_server: List, docgen, revmap, docs_list
    ):
        for server in kill_server:
            await server.kill_server()
        self.mark_test_step(f"Edge servers in {kill_server} killed")
        primary_server = ops_server[0]
        update_docs = docgen.update_all_documents(docs_list)
        bulk_ops = [
            BulkDocOperation(doc, optype="update", rev=revmap.get(doc.get("_id")))
            for doc in update_docs
        ]
        resp = await primary_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        self.mark_test_step(f"Docs updated in {ops_server}")
        print(resp)
        # validate in op_list
        all_docs_list = []
        for server in ops_server:
            all_docs = await server.get_all_documents(
                db_name="travel", collection="travel.hotels"
            )
            all_docs_list.append(all_docs)
            assert len(all_docs.rows) == docgen.size, "Inserted document count mismatch"

        #     start kill_servers
        for server in kill_server:
            await server.start_server()
        self.mark_test_step("Edge servers started")

        for server in kill_server:
            for doc in update_docs:
                remote_doc = await server.get_document(
                    db_name="travel",
                    scope="travel",
                    collection="hotels",
                    doc_id=doc.get("_id"),
                )
                for key, value in remote_doc.body.items():
                    assert doc.get(key) == value
        self.mark_test_step("Edge servers replication verified")
        return update_docs

    @pytest.mark.asyncio(loop_scope="session")
    async def test_3_edge_with_sync(self, cblpytest, dataset_path) -> None:
        self.mark_test_step("test_3_edge_with_sync")
        # kill each server one by and and update docs on other 2, verify consistency
        # Preconditions

        # Get infrastructure components
        edge_server1 = cblpytest.edge_servers[0]
        edge_server2 = cblpytest.edge_servers[1]
        edge_server3 = cblpytest.edge_servers[2]

        await edge_server1.reset_db()
        await edge_server2.reset_db()
        await edge_server3.reset_db()

        # 1. Configure Edge Server2 with replication to edge 1
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        self.mark_test_step("Configure Edge Server with travel dataset")
        source_db = edge_server1.replication_url("travel")

        # Load the existing config
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

        # setup edge 3
        source_db = edge_server2.replication_url("travel")
        config["replications"][0]["source"] = source_db

        # Save the updated config
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server3 = await edge_server3.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )

        # set up edge server1
        source_db = edge_server3.replication_url("travel")
        config["replications"][0]["source"] = source_db

        # Save the updated config
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server1 = await edge_server1.set_config(
            config_path, "/opt/couchbase-edge-server/etc/config.json"
        )
        #     Empty the travel.hotels collection
        all_docs = await edge_server1.get_all_documents(
            db_name="travel", collection="travel.hotels"
        )
        revmap = all_docs.revmap

        # delete all docs in collection travel.hotels in es1
        bulk_ops = [
            BulkDocOperation({"_deleted": True}, _id=doc_id, rev=rev, optype="delete")
            for doc_id, rev in revmap.items()
        ]
        resp = await edge_server1.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        print(resp)

        self.mark_test_step("Verify document deleted")
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge3_docs = await edge_server3.get_all_documents(
            "travel", collection="travel.hotels"
        )

        assert (
            len(edge1_docs.rows) == len(edge3_docs.rows) == len(edge2_docs.rows) == 0
        ), (
            f"Collection hotels count mismatch in len(edge1_docs.rows): {len(edge1_docs.rows)} ,  len(edge3_docs.rows): {len(edge3_docs.rows)}, len(edge2_docs.rows):  {len(edge2_docs.rows)}"
        )

        docgen = JSONGenerator(seed=10, size=10000)
        docs_list = docgen.generate_all_documents()
        bulk_ops = [BulkDocOperation(doc, optype="create") for doc in docs_list]
        resp = await edge_server1.bulk_doc_op(
            bulk_ops, db_name="travel", collection="travel.hotels"
        )

        self.mark_test_step("Verify document created")
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        edge3_docs = await edge_server3.get_all_documents(
            "travel", collection="travel.hotels"
        )

        assert (
            len(edge1_docs.rows)
            == len(edge3_docs.rows)
            == len(edge2_docs.rows)
            == 10000
        ), (
            f"Collection hotels count mismatch in len(edge1_docs.rows): {len(edge1_docs.rows)} ,  len(edge3_docs.rows): {len(edge3_docs.rows)}, len(edge2_docs.rows):  {len(edge2_docs.rows)}"
        )

        self.mark_test_step("killing edge_server1  ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server1],
            [edge_server3, edge_server2],
            docgen,
            edge3_docs.revmap,
            docs_list,
        )
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        self.mark_test_step("killing edge_server2  ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server2],
            [edge_server1, edge_server3],
            docgen,
            edge1_docs.revmap,
            docs_list,
        )
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        self.mark_test_step("killing edge_server3  ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server3],
            [edge_server2, edge_server1],
            docgen,
            edge2_docs.revmap,
            docs_list,
        )
        edge2_docs = await edge_server2.get_all_documents(
            "travel", collection="travel.hotels"
        )
        self.mark_test_step("killing edge_server1,edge_server3  ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server1, edge_server3],
            [edge_server2],
            docgen,
            edge2_docs.revmap,
            docs_list,
        )
        edge3_docs = await edge_server3.get_all_documents(
            "travel", collection="travel.hotels"
        )
        self.mark_test_step("killing edge_server1 ,edge_server2 ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server1, edge_server2],
            [edge_server3],
            docgen,
            edge3_docs.revmap,
            docs_list,
        )
        edge1_docs = await edge_server1.get_all_documents(
            "travel", collection="travel.hotels"
        )
        self.mark_test_step("killing edge_server2,edge_server3  ")
        docs_list = await self.kill_edge_perform_ops(
            [edge_server2, edge_server3],
            [edge_server1],
            docgen,
            edge1_docs.revmap,
            docs_list,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_kill_sgw_mid_replication(self, cblpytest, dataset_path) -> None:
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

        client = HTTPClient(http_client, edge_server)
        await client.connect()
        # # 5. Monitor replication status
        self.mark_test_step("Monitor replication progress")
        status = await client.all_replication_status()
        assert "error" not in status[0].keys(), f"Replication setup failure: {status}"
        hotel_docs = await client.get_all_documents(
            "travel",
            collection="travel.hotels",
        )
        bulk_ops = [
            BulkDocOperation({"_deleted": True}, _id=doc_id, rev=rev, optype="delete")
            for doc_id, rev in hotel_docs.revmap.items()
        ]

        resp = await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        print(resp)

        self.mark_test_step("Verify document deleted")
        edge_docs = await edge_server.get_all_documents(
            "travel", collection="travel.hotels"
        )
        sgw_docs = await sgw.get_all_documents(
            "travel", scope="travel", collection="hotels"
        )
        assert len(edge_docs.rows) == len(sgw_docs.rows) == 0, (
            f"Collection hotels count mismatch in len(edge_docs.rows): {len(edge_docs.rows)} ,  len(sgw_docs.rows): {len(sgw_docs.rows)}"
        )

        docgen = JSONGenerator(seed=10, size=10000)
        docs_list = docgen.generate_all_documents()
        bulk_ops = [BulkDocOperation(doc, optype="create") for doc in docs_list]
        await edge_server.bulk_doc_op(
            bulk_ops, db_name="travel", collection="travel.hotels"
        )

        self.mark_test_step("Sleep for 2 minutes")
        time.sleep(120)
        self.mark_test_step("Verify document created")
        edge_docs = await edge_server.get_all_documents(
            "travel", collection="travel.hotels"
        )
        sgw_docs = await sgw.get_all_documents(
            "travel", scope="travel", collection="hotels"
        )
        assert len(edge_docs.rows) == len(sgw_docs.rows) == 10000, (
            f"Collection hotels count mismatch in len(edge_docs.rows): {len(edge_docs.rows)} ,  len(sgw_docs.rows): {len(sgw_docs.rows)}"
        )

        update_docs = docgen.update_all_documents(docs_list)
        bulk_ops = [
            BulkDocOperation(
                doc, optype="update", rev=edge_docs.revmap.get(doc.get("_id"))
            )
            for doc in update_docs
        ]
        result = await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        sgw.kill_server()
        revmap = {doc.get("id"): doc.get("rev") for doc in result}

        update_docs = docgen.update_all_documents(update_docs)
        bulk_ops = [
            BulkDocOperation(doc, optype="update", rev=revmap.get(doc.get("_id")))
            for doc in update_docs
        ]
        await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        sgw.start_server()
        self.mark_test_step("Sleep for 2 minutes")
        time.sleep(120)
        self.mark_test_step("Verify document updated")
        edge_docs = await edge_server.get_all_documents(
            "travel", collection="travel.hotels"
        )
        sgw_docs = await sgw.get_all_documents(
            "travel", scope="travel", collection="hotels"
        )
        assert len(edge_docs.rows) == len(sgw_docs.rows) == docgen.size, (
            f"Collection hotels count mismatch in len(edge_docs.rows): {len(edge_docs.rows)} ,  len(sgw_docs.rows): {len(sgw_docs.rows)}"
        )
