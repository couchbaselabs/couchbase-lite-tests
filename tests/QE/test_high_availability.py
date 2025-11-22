import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload
from packaging.version import Version


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(3)
@pytest.mark.min_couchbase_servers(1)
class TestHighAvailability(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_high_availability(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sgs = cblpytest.sync_gateways
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "data-bucket"
        num_docs = 100
        sg1, sg2, sg3 = sgs[0], sgs[1], sgs[2]

        self.mark_test_step("Create shared bucket for all SGW nodes")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step(
            f"Configure database '{sg_db}' on all {len(sgs)} SGW nodes (pointing to shared bucket)"
        )
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        for sg in sgs:
            db_status = await sg.get_database_status(sg_db)
            if db_status is not None:
                await sg.delete_database(sg_db)
            await sg.put_database(sg_db, db_payload)

        self.mark_test_step("Wait for all SGW nodes to be ready")
        await asyncio.sleep(5)

        self.mark_test_step(
            f"Start concurrent SDK writes ({num_docs} docs) in background"
        )

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

        self.mark_test_step("Wait for some docs to be written")
        await asyncio.sleep(5)

        self.mark_test_step("Delete database on sg2 to simulate node being offline")
        await sg2.delete_database(sg_db)

        self.mark_test_step("Verify sg2 database is offline")
        sg2_status = await sg2.get_database_status(sg_db)
        assert sg2_status is None, (
            f"sg2 database should be offline, but status is: {sg2_status}"
        )

        self.mark_test_step("Get current doc count from sg1 and sg3 (sg2 offline)")
        sg1_docs_during = await sg1.get_all_documents(sg_db)
        sg1_count_during = len([r for r in sg1_docs_during.rows])
        sg3_docs_during = await sg3.get_all_documents(sg_db)
        sg3_count_during = len([r for r in sg3_docs_during.rows])
        assert sg1_count_during == sg3_count_during == num_docs, (
            f"sg1 has {sg1_count_during} docs, sg3 has {sg3_count_during} docs (while sg2 is offline)"
        )

        self.mark_test_step("Wait for all SDK writes to complete")
        await write_task
        sgw_version_obj = await sg1.get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")

        self.mark_test_step("Check if sg1 and sg3 database is still online")
        sg1_status = await sg1.get_database_status(sg_db)
        sg3_status = await sg3.get_database_status(sg_db)
        if sg1_status is None or sg1_status.state != "Online":
            await sg1.delete_database(sg_db)
            await sg1.put_database(sg_db, db_payload)
            await asyncio.sleep(5)
        if sg3_status is None or sg3_status.state != "Online":
            await sg3.delete_database(sg_db)
            await sg3.put_database(sg_db, db_payload)
            await asyncio.sleep(5)

        self.mark_test_step(
            "Wait for documents to be imported by sg1 and sg3 (with retry logic)"
        )
        max_retries = 20
        retry_delay = 2
        sg1_doc_revs = {}
        sg1_doc_vv = {}
        sg3_doc_revs = {}
        sg3_doc_vv = {}
        for retry in range(max_retries):
            sg1_all_docs = await sg1.get_all_documents(sg_db)
            sg3_all_docs = await sg3.get_all_documents(sg_db)
            sg1_doc_revs = {row.id: row.revision for row in sg1_all_docs.rows}
            sg3_doc_revs = {row.id: row.revision for row in sg3_all_docs.rows}
            if supports_version_vectors:
                sg1_doc_vv = {row.id: row.cv for row in sg1_all_docs.rows}
                sg3_doc_vv = {row.id: row.cv for row in sg3_all_docs.rows}
            if len(sg1_doc_revs) == num_docs and len(sg3_doc_revs) == num_docs:
                break
            await asyncio.sleep(retry_delay)
        assert len(sg1_doc_revs) == len(sg3_doc_revs) == num_docs, (
            f"Not all docs visible on sg1 and sg3. Expected: {num_docs}, Got: {len(sg1_doc_revs)} and {len(sg3_doc_revs)}"
        )
        if supports_version_vectors:
            assert len(sg1_doc_vv) == len(sg3_doc_vv) == num_docs, (
                f"Not all docs visible on sg1 and sg3. Expected: {num_docs}, Got: {len(sg1_doc_vv)} and {len(sg3_doc_vv)}"
            )

        self.mark_test_step(
            "Bring sg2 back online and verify it catches up (with retry logic)"
        )
        # Check if database already exists (shared bucket might have recreated it)
        sg2_status_before = await sg2.get_database_status(sg_db)
        if sg2_status_before is not None:
            await sg2.delete_database(sg_db)
            await asyncio.sleep(2)
        await sg2.put_database(sg_db, db_payload)
        for retry in range(max_retries):
            sg2_all_docs = await sg2.get_all_documents(sg_db)
            sg2_doc_revs = {row.id: row.revision for row in sg2_all_docs.rows}
            if supports_version_vectors:
                sg2_doc_vv = {row.id: row.cv for row in sg2_all_docs.rows}
            if len(sg2_doc_revs) == num_docs:
                break
            await asyncio.sleep(retry_delay)
        assert len(sg2_doc_revs) == num_docs, (
            f"sg2 did not catch up after coming back online. Expected: {num_docs}, Got: {len(sg2_doc_revs)}"
        )
        if supports_version_vectors:
            assert len(sg2_doc_vv) == num_docs, (
                f"Not all docs visible on sg2. Expected: {num_docs}, Got: {len(sg2_doc_vv)}"
            )

        self.mark_test_step("Verify revision ID consistency between all three nodes")
        for doc_id, doc_rev in sg1_doc_revs.items():
            assert doc_id in sg2_doc_revs, f"Document {doc_id} not found on sg2"
            assert sg2_doc_revs[doc_id] == doc_rev == sg3_doc_revs[doc_id], (
                f"Document {doc_id} revision mismatch: sg1={doc_rev}, sg2={sg2_doc_revs[doc_id]}, sg3={sg3_doc_revs[doc_id]}"
            )
        if supports_version_vectors:
            self.mark_test_step(
                "Verify version vector consistency between all three nodes (SGW 4.0+)"
            )
            for doc_id, doc_vv in sg1_doc_vv.items():
                assert doc_id in sg2_doc_vv, f"Document {doc_id} not found on sg2"
                assert sg2_doc_vv[doc_id] == doc_vv == sg3_doc_vv[doc_id], (
                    f"Document {doc_id} version vector mismatch: sg1={doc_vv}, sg2={sg2_doc_vv[doc_id]}, sg3={sg3_doc_vv[doc_id]}"
                )

        for sg in sgs:
            await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
