import asyncio
import json
import time
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

        is_idle = False
        while not is_idle:
            status = await edge_server.all_replication_status()
            assert "error" not in status[0].keys(), (
                f"Replication setup failure: {status}"
            )
            if status[0]["status"] == "Idle":
                is_idle = True

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
                body=doc, _id=id, optype="update", rev=edge_docs.revmap.get(id)
            )
            for id, doc in update_docs.items()
        ]
        result = await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        await edge_server.go_online_offline(deny=[sgw.hostname])
        revmap = {doc.get("id"): doc.get("rev") for doc in result}

        update_docs = docgen.update_all_documents(update_docs)
        bulk_ops = [
            BulkDocOperation(body=doc, _id=id, optype="update", rev=revmap.get(id))
            for id, doc in update_docs.items()
        ]
        await edge_server.bulk_doc_op(bulk_ops, "travel", "travel", "hotels")

        await edge_server.go_online_offline(allow=[sgw.hostname])
        self.mark_test_step("Sleep for 2 minutes")
        await asyncio.sleep(120)
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
