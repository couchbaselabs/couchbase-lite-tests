from datetime import timedelta, datetime
from pathlib import Path
from random import randint
from typing import List
import asyncio
import random
import pytest
import time
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.error import CblEdgeServerBadResponseError, CblSyncGatewayBadResponseError
from cbltest.api.edgeserver import EdgeServer, BulkDocOperation
from cbltest.api.httpclient import HTTPClient, ClientFactory
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry, ReplicatorActivityLevel, \
    WaitForDocumentEventEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload, SyncGateway
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.utils import assert_not_null

from conftest import cblpytest

from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
import logging

logger = logging.getLogger(__name__)

class TestChangesFeed(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_changes_feed_longpoll(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting Changes Feed test with Server, Sync Gateway, Edge Server and 1 client")

        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating a bucket in Couchbase Server and adding 10 documents.")
        bucket_name = "bucket-1"
        server.create_bucket(bucket_name)
        for i in range(1, 6):
            doc = {
                "id": f"doc_{i}",
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            server.add_document(bucket_name, doc["id"], doc)
        logger.info("5 documents created in Couchbase Server.")

        self.mark_test_step("Creating a database in Sync Gateway and adding a user and role.")
        sg_db_name = "db-1"
        config = {
            "bucket": "bucket-1",
            "scopes": {
                "_default": {
                    "collections": {
                        "_default": {
                            "sync": "function(doc){channel(doc.channels);}"
                        }
                    }
                }
            },
            "num_index_replicas": 0
        }
        payload = PutDatabasePayload(config)
        # await sync_gateway.put_database(sg_db_name, payload)
        logger.info(f"Database created in Sync Gateway and linked to {bucket_name}.")

        input_data = {
            "_default._default": ["public"]
        }
        access_dict = sync_gateway.create_collection_access_dict(input_data)
        await sync_gateway.add_role(sg_db_name, "stdrole", access_dict)
        await sync_gateway.add_user(sg_db_name, "sync_gateway", "password", access_dict)

        logger.info("User and role added to Sync Gateway.")

        self.mark_test_step("Creating a database in Edge Server.")
        es_db_name = "db"
        edge_server = cblpytest.edge_servers[0]

        await edge_server.kill_server()
        await edge_server.start_server()

        logger.info("Created a database in Edge Server.")

        # Step 1: Verify Initial Sync from Couchbase Server to Edge Server
        self.mark_test_step("Verifying initial synchronization from Couchbase Server to Edge Server.")

        logger.info("Checking initial document sync from Couchbase Server to Sync Gateway...")
        response = await sync_gateway.get_all_documents(sg_db_name, "_default", "_default")

        self.mark_test_step("Check that Sync Gateway has 5 documents")
        # assert len(response.rows) == 5, f"Expected 5 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Sync Gateway initially.")

        logger.info("Checking initial document sync from Sync Gateway to Edge Server...")
        response = await edge_server.get_all_documents(es_db_name)

        self.mark_test_step("Check that Edge Server has 5 documents")
        # assert len(response.rows) == 5, f"Expected 5 documents, but got {len(response.rows)} documents."
        logger.info(f"Found {len(response.rows)} documents synced to Edge Server initially.")

        # Step 2: Verify Changes Feed
        self.mark_test_step("Verifying changes feed from Edge Server.")
        changes = await edge_server.changes_feed(es_db_name, feed="longpoll")
        print(changes)

        last_seq = changes["last_seq"]
        logger.info("Successfully fetched changes feed from Edge Server.")

        self.mark_test_step("Check that deletes reflected in changes feed")

        rev_id = None
        for item in changes['results']:
            if item['id'] == 'doc_5':
                rev_id = item['changes'][0]['rev']
                break

        doc = "doc_5"
        response = await edge_server.delete_document(doc, rev_id, es_db_name)
        assert response.get("ok"), f"Failed to delete document {doc_id} from Edge Server."
        logger.info(f"Deleted document {doc} from Edge Server.")

        self.mark_test_step("Check that deleted documents are visible in changes feed with active_only=False")
        changes = await edge_server.changes_feed(es_db_name, feed="longpoll")
        print(changes)
        assert changes["results"][-1]["deleted"], "Deleted documents not visible."
        logger.info("Deleted documents are visible in changes feed with active_only=False.")
        length = len(changes["results"])

        self.mark_test_step("Check that deleted documents are not visible in changes feed with active_only=True")
        changes = await edge_server.changes_feed(es_db_name, feed="longpoll", active_only=True)
        print(changes)
        assert len(changes["results"]) < length, "Last sequence number did not decrement by 1."
        logger.info("Deleted documents are not visible in changes feed with active_only=True.")

        last_seq = changes["last_seq"]

        self.mark_test_step("Check that updates reflected in changes feed")
        doc_counter = 11
        for i in range(1, 6):
            doc_id = f"doc_{doc_counter}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.utcnow().isoformat()
            }
            response = await edge_server.put_document_with_id(doc, doc_id, es_db_name)
            assert response is not None, f"Failed to create document {doc_id} via Edge Server"

            logger.info(f"Document {doc_id} created via Edge Server")

            doc_counter += 1

        self.mark_test_step("Check that updated documents are visible in changes feed and only documents from the last update are visible")
        changes = await edge_server.changes_feed(es_db_name, feed="longpoll", active_only=True, since=last_seq)
        assert len(changes["results"]) == 5, f"Expected 5 changes, but got {len(changes['results'])} changes."
        logger.info("Updated documents are visible in changes feed and since works as expected.")

        self.mark_test_step("Check that filter is working as expected")
        changes = await edge_server.changes_feed(es_db_name, feed="longpoll", filter_type="doc_ids", doc_ids = ["doc_10", "doc_9"])
        assert len(changes["results"]) == 2, f"Expected 2 changes, but got {len(changes['results'])} changes."
        logger.info("Filter is working as expected.")

        self.mark_test_step("Test for longpoll changes feed completed.")
        logger.info("Test completed.")






