import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DatabaseConfig, ScopeConfig
from cbltest.plugins.sgw_cluster_manager import SyncGatewayClusterManager


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestServerSetup(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_server_alternative_address(
        self, cblpytest: CBLPyTest, sg_cluster_manager: SyncGatewayClusterManager
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        self.skip_if_not(
            sg_cluster_manager.has_shell2http_sidecar,
            "shell2http sidecar is not reachable on every Sync Gateway host",
        )
        sg_db = "db"
        bucket_name = "alternate-addr-bucket"
        num_docs = 5

        await cblpytest.clusters[0].create_database(
            sg_db,
            DatabaseConfig(
                bucket=bucket_name,
                num_index_replicas=0,
                scopes={"_default": ScopeConfig(collections={"_default": {}})},
                import_docs=True,
            ),
        )

        self.mark_test_step("Verify SGW is working with default config")
        sg_version = await sg.get_version()
        assert sg_version is not None, "SGW should be running with default config"

        self.mark_test_step("Restart every SGW node with alternate address config (explicit port)")
        await sg_cluster_manager.restart_with_config("bootstrap-alternate")

        self.mark_test_step(f"Create {num_docs} documents via SDK")
        counts_before = [await node.get_import_count(sg_db) for node in cblpytest.sync_gateways]
        for i in range(num_docs):
            doc_id = f"sdk_doc_{i}"
            doc_body = {
                "type": "sdk_doc",
                "index": i,
                "content": f"Document {i} written via SDK for import test",
            }
            await cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

        self.mark_test_step("Verify documents were imported via SGW")
        all_docs = await sg.wait_for_document_count(sg_db, num_docs)
        imported_count = len(all_docs.rows)
        assert imported_count == num_docs, f"Expected {num_docs} imported docs, got {imported_count}"

        self.mark_test_step("Verify at least one SGW node reports an import in expvars")
        counts_after = [await node.get_import_count(sg_db) for node in cblpytest.sync_gateways]
        assert any(after > before for before, after in zip(counts_before, counts_after, strict=True)), (
            f"Expected at least one SGW node to report a new import, got {counts_before} -> {counts_after}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_remove_dcp_cacert_handling(
        self, cblpytest: CBLPyTest, sg_cluster_manager: SyncGatewayClusterManager
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        self.skip_if_not(
            sg_cluster_manager.has_shell2http_sidecar,
            "shell2http sidecar is not reachable on every Sync Gateway host",
        )
        bucket_name = "data-bucket"
        sg_db = "db"

        self.mark_test_step("Create bucket on CBS")
        await cbs.create_bucket(bucket_name)

        self.mark_test_step("Fetch CBS root CA certificate and upload to every SGW node")
        ca_cert_pem = await cbs.get_root_ca_certificate()
        await sg_cluster_manager.upload_certificate(cert_content=ca_cert_pem, cert_name="cbs-ca-cert.pem")

        self.mark_test_step("Restart every SGW node with x509 cacert config")
        await sg_cluster_manager.restart_with_config("bootstrap-x509-cacert-only")

        self.mark_test_step("Verify SGW starts successfully")
        sg_version = await sg.get_version()
        assert sg_version is not None, "SGW should start with ca_cert_path x509 config"

        self.mark_test_step("Verify SGW can connect to CBS via document sync")
        await cblpytest.sync_gateway_cluster.create_database(
            sg_db,
            DatabaseConfig(
                bucket=bucket_name,
                num_index_replicas=0,
                scopes={"_default": ScopeConfig(collections={"_default": {}})},
            ),
        )

        doc_id = "test_cacert_auth"
        doc_body = {"type": "test", "message": "x509 ca_cert_path auth works"}
        await cbs.upsert_document(bucket_name, doc_id, doc_body)
        await sg.wait_for_documents(sg_db, [doc_id])
        sg_doc = await sg.get_document(sg_db, doc_id)
        assert sg_doc.body["message"] == "x509 ca_cert_path auth works"
