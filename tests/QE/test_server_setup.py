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
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "alternate-addr-bucket"
        num_docs = 5

        cbs.create_bucket(bucket_name)
        db_config = {
            "bucket": bucket_name,
            "num_index_replicas": 0,
            "scopes": {"_default": {"collections": {"_default": {}}}},
            "import_docs": True,
        }
        await sg.put_database(sg_db, PutDatabasePayload(db_config))
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step("Verify SGW is working with default config")
        sg_version = await sg.get_version()
        assert sg_version is not None, "SGW should be running with default config"

        self.mark_test_step("Restart SGW with alternate address config (explicit port)")
        await sg.restart_with_config("bootstrap-alternate")
        await sg.wait_for_db_up(sg_db)

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
        assert import_count != 0, f"Expected import_count > 0, got {import_count}"
        await sg.restart_with_config("bootstrap")
        await sg.wait_for_db_up(sg_db)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_dcp_cacert_handling(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        bucket_name = "data-bucket"
        sg_db = "db"

        self.mark_test_step("Create bucket on CBS")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Fetch CBS root CA certificate and upload to SGW")
        ca_cert_pem = await cbs.get_root_ca_certificate()
        await sg.upload_certificate(
            cert_content=ca_cert_pem, cert_name="cbs-ca-cert.pem"
        )

        self.mark_test_step("Restart SGW with x509 cacert config")
        await sg.restart_with_config("bootstrap-x509-cacert-only")

        self.mark_test_step("Verify SGW starts successfully")
        sg_version = await sg.get_version()
        assert sg_version is not None, "SGW should start with ca_cert_path x509 config"

        self.mark_test_step("Verify SGW can connect to CBS via document sync")
        await sg.put_database(
            sg_db,
            PutDatabasePayload(
                {
                    "bucket": bucket_name,
                    "num_index_replicas": 0,
                    "scopes": {"_default": {"collections": {"_default": {}}}},
                }
            ),
        )
        await sg.wait_for_db_up(sg_db)

        doc_id = "test_cacert_auth"
        doc_body = {"type": "test", "message": "x509 ca_cert_path auth works"}
        cbs.upsert_document(bucket_name, doc_id, doc_body)
        await asyncio.sleep(3)
        sg_doc = await sg.get_document(sg_db, doc_id)
        assert sg_doc is not None, "SGW should import document from CBS"
        assert sg_doc.body["message"] == "x509 ca_cert_path auth works"

        await sg.restart_with_config()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_server_custom_ports(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "custom-port-bucket"

        try:
            self.mark_test_step("Reconfigure CBS ports via shell2http")
            await cbs.reconfigure_ports(9091, 19091, 12210, 12207)

            self.mark_test_step("Attempt CBS operations with new port configuration")
            await cbs.create_bucket_via_rest(bucket_name)

            self.mark_test_step("Restart Sync Gateway with alternate bootstrap")
            await sg.restart_with_config("bootstrap-cbs-alternate")
            sg_version = await sg.get_version()
            assert sg_version is not None, (
                f"SGW should be running with custom CBS ports: {sg_version}"
            )

            self.mark_test_step("Create database and verify full SGW functionality")
            db_config = {
                "bucket": bucket_name,
                "index": {"num_replicas": 0},
                "scopes": {"_default": {"collections": {"_default": {}}}},
                "import_docs": True,
            }
            await sg.put_database(sg_db, PutDatabasePayload(db_config))
            await sg.wait_for_db_up(sg_db)

            self.mark_test_step("Test document import with custom CBS ports")
            doc_id = "test_custom_ports"
            doc_body = {
                "type": "test_doc",
                "content": "Testing custom CBS ports functionality",
            }

            self.mark_test_step(
                "Upsert document to CBS and wait for import to complete"
            )
            await cbs.upsert_document_via_rest(bucket_name, doc_id, doc_body)
            await asyncio.sleep(3)

            sg_doc = await sg.get_document(sg_db, doc_id)
            assert sg_doc is not None, (
                "SGW should have imported document with custom CBS ports"
            )
            assert sg_doc.body["content"] == "Testing custom CBS ports functionality"
        finally:
            self.mark_test_step("Restore CBS to default ports")
            await cbs.reconfigure_ports()

            self.mark_test_step("Reset SGW to original configuration")
            await sg.restart_with_config()
