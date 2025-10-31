from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import BulkDocOperation
from cbltest.api.httpclient import ClientFactory


class TestCrud(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_information_retrieval(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_basic_information_retrieval")
        edge_server = cblpytest.edge_servers[0]
        self.mark_test_step("get server information")
        version = await edge_server.get_version()
        self.mark_test_step(f"VERSION:{version.raw}")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_database_config(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_database_config")
        edge_server = cblpytest.edge_servers[0]
        self.mark_test_step("fetch all databases")
        all_dbs = await edge_server.get_all_dbs()
        self.mark_test_step(f" Databases : {all_dbs}")
        db_name = all_dbs[0]
        self.mark_test_step("Fetch  database info")
        db_info = await edge_server.get_db_info(db_name)
        self.mark_test_step(f"Fetched  database info: {db_info}")
        assert db_info is not None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_single_doc_crud(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_single_doc_crud")
        db_name = "names"
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        self.mark_test_step("create single document with Auto ID")
        doc = {"test": "This is a test document"}
        resp1 = await edge_server.add_document_auto_id(doc, db_name)
        id1 = resp1.get("id")
        rev1 = resp1.get("rev")
        self.mark_test_step("fetch single doc")
        doc2 = await edge_server.get_document(db_name, doc_id=id1)
        self.mark_test_step(f"Fetched doc {doc}")
        assert doc2.body.get("test") == "This is a test document"
        assert doc2.revision == rev1
        self.mark_test_step("create single doc with id")
        id2 = "test50"
        resp2 = await edge_server.put_document_with_id(doc, id2, db_name)
        rev2 = resp2.get("rev")
        self.mark_test_step(f"update single doc of rev={rev2}")
        new_doc = {"test2": "This is updated test doc"}
        update = await edge_server.put_document_with_id(new_doc, id2, db_name, rev=rev2)
        rev3 = update.get("rev")
        self.mark_test_step(f"fetch updated doc of rev {rev3}")
        doc3 = await edge_server.get_document(db_name, doc_id=id2)
        self.mark_test_step(f"Fetched doc {doc3}")
        assert doc3.body.get("test2") == new_doc.get("test2")
        self.mark_test_step("delete single doc")
        await edge_server.delete_document(doc_id=id2, revid=rev3, db_name=db_name)
        self.mark_test_step("fetch deleted doc")
        try:
            await edge_server.get_document(db_name, doc_id=id2)
        except Exception as e:
            self.mark_test_step(
                f"Deleted doc successfully threw exception on retrieval: {e}"
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_doc_crud(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_multiple_doc_crud")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        http_clients = cblpytest.http_clients
        assert len(http_clients) == 3, "Test requires 3 HTTP clients"
        self.mark_test_step("create multiple clients")
        factory = ClientFactory(
            vms=http_clients, edge_server=edge_server, num_clients_per_vm=3
        )
        await factory.create_clients()
        self.mark_test_step("Fetch all documents")
        db_name = "names"
        single_client = factory.clients.get(1)
        all_docs = await single_client.get_all_documents(db_name)
        self.mark_test_step(f"Fetch  all documents result len={all_docs.rows}")
        self.mark_test_step("create multiple documents")
        bulk_changes = []
        deleted = []
        updated = []
        created = []
        for i in range(1, 11):
            bulk_changes.append(
                BulkDocOperation(_id=f"name_{i + 200}", body={"rev": 1, "idx": i})
            )  # insertions
            created.append(f"name_{i + 200}")
            bulk_changes.append(
                BulkDocOperation(
                    _id=all_docs.rows[i].id,
                    body={},
                    rev=all_docs.rows[i].revid,
                    optype="delete",
                )
            )  # deletions
            deleted.append(all_docs.rows[i].id)
            bulk_changes.append(
                BulkDocOperation(
                    _id=all_docs.rows[i + 10].id,
                    body={"rev": 2, "idx": i + 10},
                    rev=all_docs.rows[i + 10].revid,
                    optype="update",
                )
            )
            updated.append(all_docs.rows[i + 10].id)

        resp = await single_client.bulk_doc_op(docs=bulk_changes, db_name=db_name)
        self.mark_test_step(f"Bulk doc operation result: {resp}")
        client_request_dict = {
            1: {
                "method": "get_all_documents",
                "params": {"db_name": db_name, "keys": created},
            },
            2: {
                "method": "get_all_documents",
                "params": {"db_name": db_name, "keys": deleted},
            },
            3: {
                "method": "get_all_documents",
                "params": {"db_name": db_name, "keys": updated},
            },
        }
        resp, err, failed = await factory.make_unique_params_client_request(
            client_request_dict
        )
        self.mark_test_step(f"Response: {resp},error: {err},failed: {failed}")
        assert len(resp[1]) == len(resp[3]) == 10
        assert len(resp[2]) == 0
        self.mark_test_step("Fetch Documents succeeded")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sub_doc_crud(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_sub_doc_crud")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        db_name = "names"
        self.mark_test_step("create single document with Auto ID")
        doc = {"test": "This is a test document", "testKey": None}
        resp1 = await edge_server.add_document_auto_id(doc, db_name)
        id1 = resp1.get("id")
        rev1 = resp1.get("rev")
        sample_value = "test_value"
        self.mark_test_step("Insert a subdocument")
        resp = await edge_server.put_sub_document(
            id=id1, revid=rev1, key="test_key", db_name=db_name, value=sample_value
        )
        self.mark_test_step(f" Insert sub-doc response: {resp}")
        updated_doc = await edge_server.get_sub_document(
            id1, "test_key", db_name=db_name
        )
        self.mark_test_step(f" Get updated Document : {updated_doc}")
        assert updated_doc.get("test_key") == sample_value
        self.mark_test_step("Delete the subdocument")
        resp = await edge_server.delete_sub_document(
            id1, resp.get("rev"), "test_key", db_name
        )
        self.mark_test_step(f" deleted sub document response: {resp}")
        try:
            await edge_server.get_sub_document(id1, "test_key", db_name=db_name)
        except Exception as e:
            assert "404" in str(e)
            self.mark_test_step("Fetch deleted sub document failed as expected")
