import asyncio
import json
import random
from pathlib import Path

import pytest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.api.json_generator import JSONGenerator

SCRIPT_DIR = str(Path(__file__).parent)


class TestEdgeServerChaos(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_kill_sgw_mid_replication(self, cblpytest, dataset_path) -> None:
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
        await edge_server.wait_for_idle()

        hotel_docs = await edge_server.get_all_documents(
            "travel", collection="travel.hotels"
        )
        bulk_ops = [
            BulkDocOperation({"_deleted": True}, _id=doc_id, rev=rev, optype="delete")
            for doc_id, rev in hotel_docs.revmap.items()
        ]

        await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        self.mark_test_step("Verify document deleted")
        await asyncio.sleep(120)
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
        bulk_ops = [
            BulkDocOperation(body=doc, _id=id, optype="create")
            for id, doc in docs_list.items()
        ]
        await edge_server.bulk_doc_op(
            bulk_ops, db_name="travel", collection="travel.hotels"
        )

        self.mark_test_step("Monitor replication progress")
        await edge_server.wait_for_idle()

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
                body=doc, _id=id, optype="update", rev=edge_docs.revmap.get(id)
            )
            for id, doc in update_docs.items()
        ]
        result = await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        await edge_server.set_firewall_rules(deny=[sgw.hostname])
        revmap = {doc.get("id"): doc.get("rev") for doc in result}

        update_docs = docgen.update_all_documents(update_docs)
        bulk_ops = [
            BulkDocOperation(body=doc, _id=id, optype="update", rev=revmap.get(id))
            for id, doc in update_docs.items()
        ]
        await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        await edge_server.set_firewall_rules(allow=[sgw.hostname])
        self.mark_test_step("Monitor replication progress")
        await edge_server.wait_for_idle()

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
        await edge_server.reset_firewall()

    async def kill_edge_perform_ops(
        self, kill_server: list, ops_server: list, docgen, revmap, docs_list
    ):
        for server in kill_server:
            await server.kill_server()
        self.mark_test_step(f"Edge servers in {kill_server} killed")
        primary_server = ops_server[0]
        update_docs = docgen.update_all_documents(docs_list)
        bulk_ops = [
            BulkDocOperation(body=doc, _id=id, optype="update", rev=revmap.get(id))
            for id, doc in update_docs.items()
        ]
        await primary_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")
        self.mark_test_step(f"Docs updated in {ops_server}")
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
            for doc_id in random.sample(list(update_docs.keys()), 50):
                await server.get_document(
                    db_name="travel", scope="travel", collection="hotels", doc_id=doc_id
                )
            all_docs = await server.get_all_documents(
                db_name="travel", scope="travel", collection="hotels"
            )
            assert len(all_docs.rows) == docgen.size
        self.mark_test_step("Edge servers replication verified")
        return update_docs

    @pytest.mark.asyncio(loop_scope="session")
    async def test_3_edge_with_sync(self, cblpytest, dataset_path) -> None:
        self.mark_test_step("test_3_edge_with_sync")
        self.mark_test_step("Configure Edge Server1 with travel dataset")
        edge_server1 = await cblpytest.edge_servers[0].configure_dataset(
            db_name="travel",
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )
        self.mark_test_step("Configure Edge Server2 with ES1 replication URL")
        source_db = edge_server1.replication_url("travel")
        config_path = f"{SCRIPT_DIR}/config/test_edge_to_edge_server.json"
        with open(config_path) as file:
            config = json.load(file)
        config["replications"][0]["source"] = source_db
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server2 = await cblpytest.edge_servers[1].configure_dataset(
            db_name="travel", config_file=config_path
        )

        self.mark_test_step("Configure Edge Server3 with ES2 replication URL")
        source_db = edge_server2.replication_url("travel")
        config["replications"][0]["source"] = source_db
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server3 = await cblpytest.edge_servers[2].configure_dataset(
            db_name="travel", config_file=config_path
        )

        self.mark_test_step("Configure Edge Server1 with ES3 replication URL")
        source_db = edge_server3.replication_url("travel")
        config["replications"][0]["source"] = source_db
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
        edge_server1 = await edge_server1.configure_dataset(
            db_name="travel", config_file=config_path
        )
        self.mark_test_step("Empty the travel.hotels collection")
        all_docs = await edge_server1.get_all_documents(
            db_name="travel", collection="travel.hotels"
        )
        revmap = all_docs.revmap
        bulk_ops = [
            BulkDocOperation({"_deleted": True}, _id=doc_id, rev=rev, optype="delete")
            for doc_id, rev in revmap.items()
        ]
        await edge_server1.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

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

        docgen = JSONGenerator(seed=10, size=1000)
        docs_list = docgen.generate_all_documents()
        bulk_ops = [
            BulkDocOperation(body=doc, _id=id, optype="create")
            for id, doc in docs_list.items()
        ]
        await edge_server1.bulk_doc_op(
            bulk_ops, db_name="travel", collection="travel.hotels"
        )

        self.mark_test_step("Verify document created")
        await edge_server1.wait_for_idle()
        await edge_server2.wait_for_idle()
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
            len(edge1_docs.rows) == len(edge3_docs.rows) == len(edge2_docs.rows) == 1000
        ), (
            f"Collection hotels count mismatch in len(edge1_docs.rows): {len(edge1_docs.rows)} ,  len(edge3_docs.rows): {len(edge3_docs.rows)}, len(edge2_docs.rows):  {len(edge2_docs.rows)}"
        )

        self.mark_test_step("killing edge_server1 ")
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

        self.mark_test_step("killing edge_server1,edge_server3  ")
        await self.kill_edge_perform_ops(
            [edge_server1, edge_server3],
            [edge_server2],
            docgen,
            edge1_docs.revmap,
            docs_list,
        )
