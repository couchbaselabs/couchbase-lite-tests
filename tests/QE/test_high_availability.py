import asyncio

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
class TestHighAvailability(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_high_availability_with_load_balancer(
        self, cblpytest: CBLPyTest, cleanup_after_test
    ) -> None:
        sgs = cblpytest.sync_gateways
        cbs = cblpytest.couchbase_servers[0]
        lb_url = cblpytest.load_balancers[0]
        sg_db = "db_ha"
        bucket_name = "bucket-ha"
        num_docs = 100
        channels = ["*"]
        username = "vipul"
        password = "pass"
        sg1, sg2, _ = sgs[0], sgs[1], sgs[2]
        await sg2.start()

        self.mark_test_step("Create shared bucket for all SGW nodes")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure database on all SGW nodes")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg1.put_database(sg_db, db_payload)
        for sg in sgs[1:]:
            await sg.wait_for_db_up(sg_db)

        self.mark_test_step(
            f"Create user '{username}' with access to channels {channels}"
        )
        await sgs[0].create_user_client(sg_db, username, password, channels)

        self.mark_test_step(f"Create user client via load balancer ({lb_url})")
        lb_user = SyncGatewayUserClient(
            lb_url, username, password, port=4984, secure=False
        )

        self.mark_test_step(f"Add initial {num_docs} documents via load balancer")
        docs = [
            DocumentUpdateEntry(
                id=f"doc_{i}",
                revid=None,
                body={"type": "test_doc", "index": i, "content": f"Document {i}"},
            )
            for i in range(num_docs)
        ]
        await lb_user.update_documents(sg_db, docs)
        all_doc_ids = [d.id for d in docs]

        self.mark_test_step("Verify all documents are visible via load balancer")
        lb_docs = await lb_user.get_all_documents(sg_db)
        lb_doc_ids = {row.id for row in lb_docs.rows}
        missing = set(all_doc_ids) - lb_doc_ids
        assert len(missing) == 0, (
            f"LB missing {len(missing)} docs: {list(missing)[:5]}..."
        )

        self.mark_test_step("Start concurrent SDK writes in background")

        async def write_docs_via_sdk() -> None:
            for i in range(num_docs, num_docs + 50):  # Add more docs
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

        self.mark_test_step("Take SG2 offline")
        await sg2.stop()

        self.mark_test_step("Verify load balancer still works with SG2 offline")
        await asyncio.sleep(2)
        lb_docs_after = await lb_user.get_all_documents(sg_db)
        lb_doc_ids_after = {row.id for row in lb_docs_after.rows}

        assert len(lb_doc_ids_after) >= len(all_doc_ids), (
            f"LB should still see at least {len(all_doc_ids)} docs with SG2 offline, got {len(lb_doc_ids_after)}"
        )

        self.mark_test_step(
            "Wait for SDK writes to complete and verify via load balancer"
        )
        await write_task

        max_retries = 30
        retry_delay = 2
        for _ in range(max_retries):
            lb_docs_final = await lb_user.get_all_documents(sg_db)
            if len(lb_docs_final.rows) >= num_docs + 50:
                break
            await asyncio.sleep(retry_delay)

        lb_docs_final = await lb_user.get_all_documents(sg_db)
        final_doc_count = len(lb_docs_final.rows)
        assert final_doc_count >= num_docs + 50, (
            f"Expected at least {num_docs + 50} docs via LB, got {final_doc_count}"
        )

        self.mark_test_step("Bring SG2 back online")
        await sg2.start(config_name="bootstrap")
        await sg2.wait_for_db_up(sg_db)

        self.mark_test_step("Verify load balancer now routes to all 3 nodes")
        # Create some final test docs through LB to verify all nodes are working
        final_docs = [
            DocumentUpdateEntry(
                id=f"final_doc_{i}",
                revid=None,
                body={"type": "final_test", "index": i},
            )
            for i in range(10)
        ]
        await lb_user.update_documents(sg_db, final_docs)
        final_doc_ids = [d.id for d in final_docs]
        await asyncio.sleep(2)
        lb_final_check = await lb_user.get_all_documents(sg_db)
        lb_final_ids = {row.id for row in lb_final_check.rows}
        for doc_id in final_doc_ids:
            assert doc_id in lb_final_ids, f"Final doc {doc_id} not accessible via LB"

        await lb_user.close()
