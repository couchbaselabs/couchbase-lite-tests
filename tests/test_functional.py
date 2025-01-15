from datetime import timedelta
from pathlib import Path
from random import randint
from typing import List
import random
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, \
    WaitForDocumentEventEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null

from cbltest.api.edgeserver import EdgeServer, BulkDocOperation
from conftest import cblpytest


class TestFunctional(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_all_crud(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("start test")
        #Fetch all docs
        dbname="names"
        edge_server=cblpytest.edge_servers[0]
        all_docs=await edge_server.get_all_documents(dbname)
        #  Send an initial GET request to fetch a document
        self.mark_test_step("Fetch a specific document")
        document_id = random.choice(all_docs.rows).id
        self.mark_test_step(f" Document ID: {document_id}")
        doc = await edge_server.get_document(dbname,document_id)
        self.mark_test_step(f" Document : {doc.body}")
        assert doc is not None

        # Fetch all databases
        self.mark_test_step("Fetch all databases")
        all_dbs = await edge_server.get_all_dbs()
        self.mark_test_step(f" Databases : {all_dbs}")
        assert dbname in all_dbs

        self.mark_test_step("Fetch  database info")
        all_dbs = await edge_server.get_db_info(dbname)
        self.mark_test_step(f" Database info : {all_dbs}")
        assert "names" in all_dbs.values()
        #  Apply bulk changes to documents
        self.mark_test_step("Apply bulk changes to documents")
        bulk_changes=[]
        for i in range(10):
            bulk_changes.append(BulkDocOperation(_id=f'names_{i+100}',body={"rev":1, "idx":i}))
            bulk_changes.append(BulkDocOperation(_id=f'names_{i}',body={"rev":2, "idx":i},rev=all_docs.rows[i].revid,optype="delete"))
        resp=await edge_server.bulk_doc_op(bulk_changes,dbname)
        self.mark_test_step(f" Bulk changes : {resp}")
        self.mark_test_step("Fetch the changes feed")
        changes = await edge_server.changes_feed(dbname)
        self.mark_test_step(f" Changes feed : {changes}")

        self.mark_test_step("Fetch all active tasks")
        # active_tasks = await edge_server.get_active_tasks()
        # self.mark_test_step(f" Active Tasks : {active_tasks}")
        # assert len(active_tasks) > 0

        # Step 11: Query and get query results
        self.mark_test_step("Query and get query results")
        # query_results = await edge_server.adhoc_query(dbname,query="SELECT * FROM _default")
        # self.mark_test_step(f" Query Result : {query_results}")
        # assert len(query_results) > 0

        # Step 12: Fetch a document with invalid scope and collection
        self.mark_test_step("Fetch document with invalid scope and collection")
        try:
            resp =await edge_server.get_document(db_name=dbname,doc_id="airline_10", scope="invalid_scope",
                                                collection="invalid_collection")\

        except Exception as e:
            assert "404" in str(e)


        # Step 13: Fetch document using If-None-Match header
        # self.mark_test_step("Fetch document using If-None-Match header")
        # e_tag = all_docs[50].rev
        # try:
        #     await db.get_document("name_1", headers={"If-None-Match": e_tag})
        # except Exception as e:
        #     assert "304" in str(e)

        # Step 14: Delete the document
        self.mark_test_step("Delete the document")
        resp=await edge_server.delete_document(all_docs.rows[36].id,all_docs.rows[36].revid,dbname)
        self.mark_test_step(f" Delete response : {resp}")
        try:
            await edge_server.get_document(dbname,all_docs.rows[36].id)
        except Exception as e:
            assert "404" in str(e)
            self.mark_test_step("Fetch deleted document failed as expected")

        # Step 15: Create a document with an automatic docID
        self.mark_test_step("Create a document with an automatic docID")
        doc_id = await edge_server.add_document_auto_id({"name": "New Airline", "type": "airline"},dbname)
        self.mark_test_step(f" Document ID added: {doc_id}")
        assert doc_id is not None

        # Step 16: Fetch a subdocument and verify its content
        self.mark_test_step("Fetch a subdocument")
        subdoc = await edge_server.get_sub_document(doc_id.get("id"), "name",dbname)
        self.mark_test_step(f" sub Document : {subdoc}")
        assert subdoc == "New Airline"

        # Step 17: Update the subdocument
        # self.mark_test_step("Update the subdocument")
        # resp=await edge_server.put_sub_document(doc_id.get("id"), revid,{"name": "Updated Airline"})
        # self.mark_test_step(f" Update Document response: {resp}")
        # updated_doc = await db.get_sub_document(doc_id, "name")
        # self.mark_test_step(f" Get updated Document : {updated_doc}")
        # assert updated_doc == "Updated Airline"
        #
        # # Step 18: Delete the subdocument
        # self.mark_test_step("Delete the subdocument")
        # resp=await edge_server.delete_sub_document(doc_id,"name",dbname)
        # self.mark_test_step(f" deleted sub document response: {resp}")
        # try:
        #     await edge_server.get_sub_document(doc_id,"name")
        # except Exception as e:
        #     assert "404" in str(e)
        #     self.mark_test_step("Fetch deleted sub document failed as expected")
        #
        # self.mark_test_step("Simulate conflicts with PUT and DELETE requests")
        # try:
        #     await edge_server.update_document(doc_id, {"name": "Conflict"}, rev_id="invalid_rev")
        # except Exception as e:
        #     assert "409" in str(e)
        #     self.mark_test_step(" Conflict success")

        self.mark_test_step("E2E replication test completed successfully.")
        await cblpytest.test_servers[0].cleanup()

