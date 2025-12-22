import asyncio
from pathlib import Path
from typing import cast

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import PutDatabasePayload


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestServerSetup(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_server_alternative_address(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Test that Sync Gateway can start successfully after switching to an
        alternate address configuration with explicit port.

        Steps:
        1. Set up SGW with default bootstrap config
        2. Create a database and verify it works
        3. Restart SGW with alternate config (explicit CBS port)
        4. Create documents via SDK
        5. Verify SGW imports the documents (import_count incremented)
        """
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "alternate-addr-bucket"
        num_docs = 5

        self.mark_test_step("Set up bucket and database with default config")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)
        await asyncio.sleep(3)

        db_config = {
            "bucket": bucket_name,
            "num_index_replicas": 0,
            "scopes": {"_default": {"collections": {"_default": {}}}},
            "import_docs": True,
        }
        db_status = await sg.get_database_status(sg_db)
        if db_status is not None:
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, PutDatabasePayload(db_config))
        await asyncio.sleep(3)

        self.mark_test_step("Verify SGW is working with default config")
        sg_version = await sg.get_version()
        assert sg_version is not None, "SGW should be running with default config"

        self.mark_test_step("Restart SGW with alternate address config (explicit port)")
        await sg.restart_with_config("bootstrap-alternate")

        self.mark_test_step("Verify SGW restarted successfully")
        sg_version_after = await sg.get_version()
        assert sg_version_after is not None, (
            "SGW should be running after restart with alternate config"
        )

        self.mark_test_step("Re-create database after restart")
        db_status = await sg.get_database_status(sg_db)
        if db_status is None:
            await sg.put_database(sg_db, PutDatabasePayload(db_config))
            await asyncio.sleep(3)

        self.mark_test_step(f"Create {num_docs} documents via SDK")
        for i in range(num_docs):
            doc_id = f"sdk_doc_{i}"
            doc_body = {
                "type": "sdk_doc",
                "index": i,
                "content": f"Document {i} written via SDK for import test",
            }
            cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

        self.mark_test_step("Wait for SGW to import documents")
        await asyncio.sleep(5)

        self.mark_test_step("Verify documents were imported via SGW")
        all_docs = await sg.get_all_documents(sg_db)
        imported_count = len([r for r in all_docs.rows])
        assert imported_count == num_docs, (
            f"Expected {num_docs} imported docs, got {imported_count}"
        )

        self.mark_test_step("Verify import_count in expvars")
        expvars = await sg._send_request("get", "/_expvar")
        assert isinstance(expvars, dict)
        expvars_dict = cast(dict, expvars)
        import_count = (
            expvars_dict.get("syncgateway", {})
            .get("per_db", {})
            .get(sg_db, {})
            .get("shared_bucket_import", {})
            .get("import_count", 0)
        )
        assert import_count >= num_docs, (
            f"Expected import_count >= {num_docs}, got {import_count}"
        )

        self.mark_test_step("Restart SGW back to default config")
        await sg.restart_with_config("bootstrap")

        self.mark_test_step("Cleanup")
        db_status = await sg.get_database_status(sg_db)
        if db_status is not None:
            await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
