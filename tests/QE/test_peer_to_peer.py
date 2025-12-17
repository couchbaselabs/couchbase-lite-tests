import asyncio
import json
from pathlib import Path
from datetime import timedelta
from random import randint
from cbltest.api.json_generator import JSONGenerator
import pytest
from aiohttp import BasicAuth
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.listener import Listener
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.api.testserver import TestServer
from cbltest.api.test_functions import compare_doc_results_p2p

import inspect
# print("TestServer class:", inspect.getfile(TestServer))
@pytest.mark.min_test_servers(2)
class TestPeerToPeer(CBLTestClass):
    def setup_method(self, method):
        super().setup_method(method)
        self.doc_ids = None
        self.docgen = None

    async def testserver_crud(self,db,num_of_docs,optype="insert",documents=None):
        async def insert_each_batch(start, value=10,documents=None):
            async with db.batch_updater() as b:
                for i in self.doc_ids[start: start + value]:
                    # print(f"upserting: ")
                    b.upsert_document(
                        "_default._default",
                        i,
                        documents[i]
                    )
        if optype=="insert":
            self.docgen=JSONGenerator(size=num_of_docs , format="key-value")
            documents = self.docgen.generate_all_documents()
            print(f"documents:{documents}")
            self.doc_ids = list(documents.keys())
            print(f"ids:{self.doc_ids}")
            for start in range(0, len(self.doc_ids), 10):
                await insert_each_batch(start,documents=documents)

        elif optype=="update":
            updated_docs = self.docgen.update_all_documents(documents)
            documents.update(updated_docs)
            for start in range(0, len(self.doc_ids), 10):
                await insert_each_batch(start,documents=documents)
        else:
            raise ValueError(f"Invalid optype: {optype}")
        return documents

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, ReplicatorType.PUSH_AND_PULL),
        (100, False, ReplicatorType.PUSH)
    ])
    async def test_peer_to_peer_concurrent_replication(self, cblpytest: CBLPyTest, dataset_path: Path,num_of_docs, continuous, replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step("Start listener on Device-1")
        listener = Listener(all_dbs[0], ["_default._default"], 59840)
        await listener.start()
        await asyncio.sleep(0.3)
        self.mark_test_step(f"listener started at {listener.port}")
        port=listener.port if listener.port is not None else 59840
        self.mark_test_step(f"Add {num_of_docs} docs to Device-2")
        documents=await self.testserver_crud(all_dbs[1], num_of_docs)
        endpoint=cblpytest.test_servers[1].replication_url("db1",port)
        self.mark_test_step(f"""
                    Start a replicator on Device-2 with listener endpoint
                    * endpoint: {endpoint}
                    * collections : `_default._default`
                    * type: {replicator_type}
                    * continuous: {continuous}
                """)
        replicator = Replicator(
            all_dbs[1],
            endpoint=endpoint,
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator.start()
        self.mark_test_step("Ensure replication is complete")
        status = None
        if continuous:
            status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"
        self.mark_test_step("Perform concurrent updates to both listener and client")
        for i in range(3):
            await asyncio.gather(*(self.testserver_crud(db, num_of_docs, optype="update",documents=documents) for db in all_dbs[:2]))

        self.mark_test_step("Wait till replication is complete")
        if continuous:
            status = await replicator.wait_for(ReplicatorActivityLevel.IDLE,timeout=timedelta(seconds=200))
        else:
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED,timeout=timedelta(seconds=200))
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener.stop()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, "push_pull"),
        (10, False, "push_pull"),
        (100, False, "push" ),
        (100, True, "push"),
    ])
    async def test_peer_to_peer_oneClient_toManyServers(self, cblpytest: CBLPyTest,num_of_docs, continuous, replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step(f"Add {num_of_docs} docs to Device-1")
        await self.testserver_crud(all_dbs[0], num_of_docs)

        self.mark_test_step("Start listener on Device-2 and Device-3")
        listener1 = Listener(all_dbs[1], ["_default._default"], 59840)
        await listener1.start()
        listener2 = Listener(all_dbs[2], ["_default._default"], 59840)
        await listener2.start()
        self.mark_test_step("Setup Replication on Device-1 with listener endpoint-1")
        replicator1 = Replicator(
            all_dbs[0],
            endpoint=cblpytest.test_servers[1].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator1.start()

        self.mark_test_step("Setup Replication on Device-1 with listener endpoint-2")

        replicator2 = Replicator(
            all_dbs[0],
            endpoint=cblpytest.test_servers[2].replication_url("db1", listener2.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator2.start()
        self.mark_test_step("Wait till replication is complete")
        status = None
        if continuous:
            status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator2: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener1.stop()
        await listener2.stop()


    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, "push_pull"),
        (10, False, "push_pull"),
        (100, False, "push"),
        (100, True, "push"),
    ])
    async def test_peer_to_peer_oneServer_toManyClients(self, cblpytest: CBLPyTest, num_of_docs, continuous,
                                                        replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step(f"Add {num_of_docs} docs to Device-1")
        await self.testserver_crud(all_dbs[0], num_of_docs)

        self.mark_test_step("Start listener on Device-1")
        listener1 = Listener(all_dbs[0], ["_default._default"], 59840)
        await listener1.start()
        self.mark_test_step("Setup Replication on Device-2 with listener endpoint-1")
        replicator1 = Replicator(
            all_dbs[1],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator1.start()

        self.mark_test_step("Setup Replication on Device-3 with listener endpoint-1")
        replicator2 = Replicator(
            all_dbs[2],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator2.start()
        self.mark_test_step("Wait till replication is complete")
        status = None
        if continuous:
            status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator2: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener1.stop()
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, "push_pull"),
        (10, False, "push_pull"),
        (100, False, "push"),
        (100, True, "push"),
    ])
    async def test_peer_to_peer_oneServer_twoClients_on_single_db(self, cblpytest: CBLPyTest, num_of_docs, continuous,
                                                        replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step(f"Add {num_of_docs} docs to Device-1")
        await self.testserver_crud(all_dbs[0], num_of_docs)
        self.mark_test_step("Start listener on Device-1")
        listener1 = Listener(all_dbs[0], ["_default._default"], 59840)
        await listener1.start()
        self.mark_test_step("Setup 3 different Replication sessions using same db on Device-2 with listener endpoint-1")
        replicator1 = Replicator(
            all_dbs[1],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator1.start()
        replicator2 = Replicator(
            all_dbs[1],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator2.start()
        replicator3 = Replicator(
            all_dbs[1],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator3.start()

        self.mark_test_step("Wait till replication is complete on all 3 sessions")
        status = None
        if continuous:
            status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator2: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator3.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator3.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator3: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener1.stop()
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, "push_pull"),
        (10, False, "push_pull"),
        (100, False, "push"),
        (100, True, "push"),
    ])
    async def test_peer_to_peer_replication_with_multiple_dbs(self, cblpytest: CBLPyTest, num_of_docs, continuous,
                                                        replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )

        self.mark_test_step("Create 3 dbs and sdd 10 docs each to Device-1")
        client_db_list = await cblpytest.test_servers[0].create_and_reset_db(["db1","db2","db3"])
        await self.testserver_crud(client_db_list[0], num_of_docs)
        await self.testserver_crud(client_db_list[1], num_of_docs)
        await self.testserver_crud(client_db_list[2], num_of_docs)
        self.mark_test_step("Create 3 dbs and start 3 listeners on Device-2")
        server_db_list = await cblpytest.test_servers[1].create_and_reset_db(["db1", "db2", "db3"])
        listener1 = Listener(server_db_list[0], ["_default._default"], 59840)
        await listener1.start()
        listener2 = Listener(server_db_list[1], ["_default._default"], 59841)
        await listener2.start()
        listener3 = Listener(server_db_list[2], ["_default._default"], 59842)
        await listener3.start()
        self.mark_test_step("Setup 3 different Replication sessions using corresponding dbs on Device-1 with listener endpoints")
        replicator1 = Replicator(
            client_db_list[0],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator1.start()
        replicator2 = Replicator(
            client_db_list[1],
            endpoint=cblpytest.test_servers[0].replication_url("db2", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator2.start()
        replicator3 = Replicator(
            client_db_list[2],
            endpoint=cblpytest.test_servers[0].replication_url("db3", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator3.start()
        self.mark_test_step("Wait till replication is complete on all 3 sessions")
        status = None
        if continuous:
            status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator2.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator2: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        if continuous:
            status = await replicator3.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator3.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator3: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        self.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in server_db_list
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener1.stop()
        await listener2.stop()
        await listener3.stop()
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("num_of_docs, continuous, replicator_type", [
        (10, True, "push_pull"),
        (10, False, "push_pull"),
        (100, False, "push"),
        (100, True, "push"),
    ])
    async def test_peer_to_peer_with_server_down(self, cblpytest:CBLPyTest,num_of_docs, continuous, replicator_type):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 2.8.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on two devices"
        )
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step(f"Add {num_of_docs} docs to Device-2")
        docs=await self.testserver_crud(all_dbs[1], num_of_docs)

        self.mark_test_step("Asynchronously: Setup continuous Replication on Device-2 with listener endpoint and perform updates and stop and start the listener on the same port")
        listener1 = Listener(all_dbs[0], ["_default._default"], 59840)
        await listener1.start()
        replicator1 = Replicator(
            all_dbs[1],
            endpoint=cblpytest.test_servers[0].replication_url("db1", listener1.port),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            continuous=continuous,
        )
        await replicator1.start()
        async def stop_restart_task():
            listener1.stop()
            listener1 = Listener(all_dbs[0], ["_default._default"], 59840)
            await listener1.start()

        tasks = [self.testserver_crud(all_dbs[1], num_of_docs,optype="update",documents=docs), stop_restart_task()]
        await asyncio.gather(*tasks)
        self.mark_test_step("Wait till replication is complete")
        status = None
        if continuous:
            status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        else:
            status = await replicator1.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator1: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        sself.mark_test_step("Check that all docs are replicated correctly.")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in server_db_list
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Stop listener")
        await listener1.stop()

