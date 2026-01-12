import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass


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
        db_name = "db"
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
        rev3: str = update["rev"]
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
    async def test_sub_doc_crud(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_sub_doc_crud")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        db_name = "db"
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
            id1, resp["rev"], "test_key", db_name
        )
        self.mark_test_step(f" deleted sub document response: {resp}")
        try:
            await edge_server.get_sub_document(id1, "test_key", db_name=db_name)
        except Exception as e:
            assert "404" in str(e)
            self.mark_test_step("Fetch deleted sub document failed as expected")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_single_doc_crud_ttl(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_single_doc_crud_tll")
        db_name = "db"
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()

        self.mark_test_step("create single document with Auto ID")
        doc = {"test": "This is a test document"}
        resp1 = await edge_server.add_document_auto_id(doc, db_name, ttl=20)
        id1 = resp1.get("id")
        self.mark_test_step("fetch single doc after ttl 20")
        await asyncio.sleep(20)
        failed = False
        try:
            await edge_server.get_document(db_name, doc_id=id1)
        except Exception as e:
            failed = True
            self.mark_test_step(f"Fetch doc {doc} failed as expected {e}")
        assert failed, "Doc fetch successful despite expiry"

        self.mark_test_step(
            "create single doc with id of a TTL=50 and update the TTL=20"
        )
        id2 = "test50"
        resp2 = await edge_server.put_document_with_id(doc, id2, db_name, ttl=50)
        rev2 = resp2.get("rev")

        self.mark_test_step(f"update doc of rev={rev2} to TTL 20")
        new_doc = {"test2": "This is updated test doc"}
        update = await edge_server.put_document_with_id(
            new_doc, id2, db_name, rev=rev2, ttl=20
        )
        rev3 = update.get("rev")
        self.mark_test_step(f"fetch updated doc of rev {rev3} with TTL=20")
        doc3 = await edge_server.get_document(db_name, doc_id=id2)
        self.mark_test_step(f"Fetched doc {doc3}")
        assert doc3.body.get("test2") == new_doc.get("test2")
        self.mark_test_step("fetch update doc after 20 seconds")
        await asyncio.sleep(20)
        failed = False
        try:
            await edge_server.get_document(db_name, doc_id=id1)
        except Exception as e:
            failed = True
            self.mark_test_step(f"Fetch doc failed as expected {e}")
        assert failed, "Doc fetch successful despite expiry"

        self.mark_test_step("delete a single doc of expiry 60 seconds")
        new_doc = {"test3": "This is new test doc"}
        id3 = "test100"
        update = await edge_server.put_document_with_id(new_doc, id3, db_name, ttl=60)
        rev3 = update["rev"]
        await edge_server.delete_document(doc_id=id3, revid=rev3, db_name=db_name)
        self.mark_test_step("fetch deleted doc")
        try:
            await edge_server.get_document(db_name, doc_id=id2)
        except Exception as e:
            self.mark_test_step(
                f"Deleted doc successfully threw exception on retrieval: {e}"
            )
