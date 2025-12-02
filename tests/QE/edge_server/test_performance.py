import time
import statistics
import pytest
from cbltest.api.httpclient import HTTPClient
from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass

class TestPerfEdgeServer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_crud_throughput_latency(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_crud_throughput_latency")
        edge = cblpytest.edge_servers[0]
        await edge.reset_db()
        http_client = cblpytest.http_clients[0]
        client = HTTPClient(http_client, edge)
        await client.connect()
        db = "names"
        n = 100    # total documents
        doc_ids = []
        create_lat = []
        read_lat = []
        update_lat = []
        delete_lat = []
        rev_map = {}
        for i in range(n):
            doc = {"type": "perf_test", "i": i}
            start = time.perf_counter()
            resp = await edge.add_document_auto_id(doc,db,ttl=600)
            create_lat.append(time.perf_counter() - start)
            doc_ids.append(resp["id"])
            rev_map[resp["id"]] = resp["rev"]

        # -----------------------------
        # READ
        # -----------------------------
        for doc_id in doc_ids:
            start = time.perf_counter()
            await edge.get_document(db, doc_id)
            read_lat.append(time.perf_counter() - start)

        # -----------------------------
        # UPDATE
        # -----------------------------
        rev_map_update={}
        for doc_id in doc_ids:
            update_body = {"updated": True}
            start = time.perf_counter()
            resp=await edge.put_document_with_id(update_body,doc_id,db,rev=rev_map[doc_id],ttl=600)
            update_lat.append(time.perf_counter() - start)
            rev_map_update[doc_id] = resp.get("rev")


        # -----------------------------
        # DELETE
        # -----------------------------
        for doc_id in doc_ids:
            start = time.perf_counter()
            await edge.delete_document(doc_id,rev_map_update[doc_id],db )
            delete_lat.append(time.perf_counter() - start)

        # -----------------------------
        # Stats helper
        # -----------------------------
        def stats(latencies):
            return {
                "avg_ms": round(statistics.mean(latencies) * 1000, 3),
                "p50_ms": round(statistics.median(latencies) * 1000, 3),
                "p90_ms": round(statistics.quantiles(latencies, n=10)[8] * 1000, 3),
                "p99_ms": round(sorted(latencies)[int(0.99 * len(latencies))] * 1000, 3),
                "throughput_ops_sec": round(len(latencies) / sum(latencies), 2),
            }

        print("CREATE:", stats(create_lat))
        print("READ:  ", stats(read_lat))
        print("UPDATE:", stats(update_lat))
        print("DELETE:", stats(delete_lat))

        # Optional assertions — enforce minimum performance
        assert False
