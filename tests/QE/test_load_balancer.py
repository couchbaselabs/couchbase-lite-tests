import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import (
    DocumentUpdateEntry,
    PutDatabasePayload,
    SyncGatewayUserClient,
)


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(3)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_load_balancers(1)
class TestLoadBalancer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_load_balance_sanity(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sgs = cblpytest.sync_gateways[0:3]
        cbs = cblpytest.couchbase_servers[0]
        lb_url = cblpytest.load_balancers[0]
        sg_db = "db"
        bucket_name = "data-bucket"
        num_docs = 100
        channels = ["ABC", "CBS"]
        username = "vipul"
        password = "pass"

        self.mark_test_step("Create shared bucket for all SGW nodes")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure database on all SGW nodes")
        db_config = {
            "bucket": bucket_name,
            "num_index_replicas": 0,
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        for sg in sgs:
            db_status = await sg.get_database_status(sg_db)
            if db_status is not None:
                await sg.delete_database(sg_db)
            await sg.put_database(sg_db, db_payload)

        self.mark_test_step(
            f"Create user '{username}' with access to channels {channels}"
        )
        await sgs[0].create_user_client(sg_db, username, password, channels)

        self.mark_test_step(f"Create user client via load balancer ({lb_url})")
        lb_user = SyncGatewayUserClient(
            lb_url, username, password, port=4984, secure=False
        )

        self.mark_test_step(f"Add {num_docs} documents via load balancer")
        docs = [
            DocumentUpdateEntry(
                id=f"lb_doc_{i}",
                revid=None,
                body={"type": "lb_test", "index": i, "channels": channels},
            )
            for i in range(num_docs)
        ]
        await lb_user.update_documents(sg_db, docs)
        all_doc_ids = [d.id for d in docs]
        await asyncio.sleep(5)

        self.mark_test_step("Verify all documents are visible via load balancer")
        lb_docs = await lb_user.get_all_documents(sg_db)
        lb_doc_ids = {row.id for row in lb_docs.rows}
        missing = set(all_doc_ids) - lb_doc_ids
        assert len(missing) == 0, (
            f"LB missing {len(missing)} docs: {list(missing)[:5]}..."
        )
        assert len(lb_doc_ids) == num_docs, (
            f"LB sees {len(lb_doc_ids)} docs, expected {num_docs}"
        )

        self.mark_test_step(
            "Verify documents are visible from each SG node (admin API)"
        )
        for i, sg in enumerate(sgs):
            sg_docs = await sg.get_all_documents(sg_db)
            sg_doc_ids = {row.id for row in sg_docs.rows}
            missing = set(all_doc_ids) - sg_doc_ids
            assert len(missing) == 0, (
                f"SG{i} missing {len(missing)} docs: {list(missing)[:5]}..."
            )

        self.mark_test_step("Verify document count consistency across all nodes")
        doc_counts = []
        for sg in sgs:
            sg_docs = await sg.get_all_documents(sg_db)
            doc_counts.append(len(sg_docs.rows))
        assert all(c == doc_counts[0] for c in doc_counts), (
            f"Document counts differ across SG nodes: {doc_counts}"
        )

        await lb_user.close()
        for sg in sgs:
            await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_down_with_load_balancer(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sgs = cblpytest.sync_gateways[0:3]
        cbs = cblpytest.couchbase_servers[0]
        sg1, sg2, sg3 = sgs[0], sgs[1], sgs[2]
        sg_db = "db"
        bucket_name = "data-bucket"
        num_docs = 100

        self.mark_test_step("Create shared bucket for all SGW nodes")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure database on all SGW nodes")
        db_config = {
            "bucket": bucket_name,
            "num_index_replicas": 0,
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        for sg in sgs:
            db_status = await sg.get_database_status(sg_db)
            if db_status is not None:
                await sg.delete_database(sg_db)
            await sg.put_database(sg_db, db_payload)
        await asyncio.sleep(3)

        self.mark_test_step("Start concurrent SDK writes in background")

        async def write_docs_via_sdk() -> None:
            for i in range(num_docs):
                doc_id = f"sdk_doc_{i}"
                doc_body = {
                    "type": "sdk_doc",
                    "index": i,
                    "content": f"Document {i} written via SDK",
                }
                cbs.upsert_document(
                    bucket_name, doc_id, doc_body, "_default", "_default"
                )

        write_task = asyncio.create_task(write_docs_via_sdk())

        self.mark_test_step("Wait for some documents to be written")
        await asyncio.sleep(2)

        self.mark_test_step("Take SG2 offline by deleting its database")
        await sg2.delete_database(sg_db)

        self.mark_test_step("Verify SG2 database is offline")
        sg2_status = await sg2.get_database_status(sg_db)
        assert sg2_status is None, f"SG2 database should be offline, got: {sg2_status}"

        self.mark_test_step("Wait for SDK writes to complete")
        await write_task

        self.mark_test_step("Verify documents are visible on SG1 and SG3 (with retry)")
        max_retries = 30
        retry_delay = 2
        sg1_doc_ids = set()
        sg3_doc_ids = set()
        for _ in range(max_retries):
            sg1_docs = await sg1.get_all_documents(sg_db)
            sg3_docs = await sg3.get_all_documents(sg_db)
            sg1_doc_ids = {row.id for row in sg1_docs.rows}
            sg3_doc_ids = {row.id for row in sg3_docs.rows}
            if len(sg1_doc_ids) >= num_docs and len(sg3_doc_ids) >= num_docs:
                break
            await asyncio.sleep(retry_delay)
        assert len(sg1_doc_ids) >= num_docs, (
            f"SG1 has {len(sg1_doc_ids)} docs, expected {num_docs}"
        )
        assert len(sg3_doc_ids) >= num_docs, (
            f"SG3 has {len(sg3_doc_ids)} docs, expected {num_docs}"
        )

        self.mark_test_step("Bring SG2 back online")
        sg2_status_before = await sg2.get_database_status(sg_db)
        if sg2_status_before is not None:
            await sg2.delete_database(sg_db)
            await asyncio.sleep(2)
        await sg2.put_database(sg_db, db_payload)

        self.mark_test_step("Verify SG2 catches up with all documents")
        sg2_doc_ids = set()
        for _ in range(max_retries):
            sg2_docs = await sg2.get_all_documents(sg_db)
            sg2_doc_ids = {row.id for row in sg2_docs.rows}
            if len(sg2_doc_ids) >= num_docs:
                break
            await asyncio.sleep(retry_delay)
        assert len(sg2_doc_ids) >= num_docs, (
            f"SG2 did not catch up. Has {len(sg2_doc_ids)} docs, expected {num_docs}"
        )

        self.mark_test_step("Verify document consistency across all nodes")
        expected_ids = {f"sdk_doc_{i}" for i in range(num_docs)}
        for sg_name, sg_ids in [
            ("SG1", sg1_doc_ids),
            ("SG2", sg2_doc_ids),
            ("SG3", sg3_doc_ids),
        ]:
            missing = expected_ids - sg_ids
            assert len(missing) == 0, f"{sg_name} missing docs: {list(missing)[:5]}..."

        for sg in sgs:
            await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
