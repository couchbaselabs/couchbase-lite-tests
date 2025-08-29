import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.json_generator import JSONGenerator
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_doc_results_p2p, compare_local_and_remote


@pytest.mark.min_test_servers(2)
class TestSystemMultipeer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_system(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts,">= 3.3.0")
        NUM_DEVICES = len(cblpytest.test_servers)
        TEST_DURATION = timedelta(hours=1)
        CRUD_INTERVAL = timedelta(minutes=3)
        NO_OF_DOCS = 1000
        MAX_DOCS_PER_CRUD = 50
        MAX_STOP_TESTSERVERS = int(0.5 * NUM_DEVICES)
        docgen = JSONGenerator(1, NO_OF_DOCS, format="key-value")

        self.mark_test_step("Reset local databases on 10 devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]
        db1 = all_dbs[0]

        documents = docgen.generate_all_documents()
        doc_ids = list(documents.keys())
        self.mark_test_step("""
                    Add docs to the database on device 1
                """)

        async def insert_each_batch(start, value=10):
            async with db1.batch_updater() as b:
                for i in doc_ids[start:start + value]:
                    b.upsert_document(
                        "_default._default", i, documents[i]
                    )

        for start in range(0, len(doc_ids), 10):
            await insert_each_batch(start)
        # await asyncio.gather(*[insert_each_batch(start) for start in range(0,NO_OF_DOCS,100)])

        self.mark_test_step("""
                            Start a multipeer replicator on all devices
                            * peerGroupID: “com.couchbase.testing”
                            * identity: anonymous
                            * authenticator: accept-all (null)
                            * collections: default collection                    
                        """)
        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        await asyncio.gather(*[r.start() for r in multipeer_replicators])

        start_time = datetime.utcnow()
        end_time = start_time + TEST_DURATION

        await asyncio.sleep(CRUD_INTERVAL.total_seconds())

        self.mark_test_step(f"Starting the System test for {NUM_DEVICES} devices ")
        while datetime.utcnow() < end_time:
            insert_testserver = random.randint(0, NUM_DEVICES - 1)
            delete_testserver = random.randint(0, NUM_DEVICES - 1)
            update_testserver = random.randint(0, NUM_DEVICES - 1)

            insert_count = random.randint(1, MAX_DOCS_PER_CRUD)
            delete_count = random.randint(1, MAX_DOCS_PER_CRUD)
            update_count = random.randint(1, MAX_DOCS_PER_CRUD)
            num_updates = random.randint(1, 3)

            crud_ids = random.sample(doc_ids, (delete_count + update_count))  # to ensure no overlaps in IDs
            to_delete = crud_ids[:delete_count]
            to_update = crud_ids[delete_count:]
            # should_stop_testserver = random.random() < 0.25  # decides randomly if the selected testserver should be down
            should_stop_testserver = True
            new_docs = docgen.generate_all_documents(size=insert_count)
            new_doc_ids = list(new_docs.keys())
            documents.update(new_docs)  # add newly generated docs to the documents dict
            doc_ids.extend(new_doc_ids)  # add newly generated doc_ids to the doc_ids list

            doc_ids = list(set(doc_ids) - set(to_delete))
            docs_to_update = {k: documents[k] for k in to_update}

            # Insert new docs
            async def insert_task():
                for start in range(0, len(new_doc_ids), 10):
                    end = min(start + 10, len(new_doc_ids))
                    async with all_dbs[insert_testserver].batch_updater() as b:
                        for i in new_doc_ids[start:end]:
                            b.upsert_document("_default._default", i, new_docs[i])

            # Delete random existing docs
            async def delete_task():
                for start in range(0, len(to_delete), 20):
                    end = min(start + 20, len(to_delete))
                    async with all_dbs[delete_testserver].batch_updater() as b:
                        for doc_id in to_delete[start:end]:
                            b.delete_document("_default._default", doc_id)
                            documents.pop(doc_id)

            # Update existing documents
            async def update_task():
                nonlocal docs_to_update
                for i in range(num_updates):
                    updated_docs = docgen.update_all_documents(docs_to_update)
                    documents.update(updated_docs)
                    for start in range(0, len(to_update), 10):
                        end = min(start + 10, len(to_update))
                        async with all_dbs[update_testserver].batch_updater() as b:
                            for doc_id in to_update[start:end]:
                                b.upsert_document("_default._default", doc_id, updated_docs[doc_id])
                        docs_to_update = updated_docs

            async def stop_restart_task():
                stop_testserver_count = random.randint(1, MAX_STOP_TESTSERVERS)
                stop_indices = random.sample(range(NUM_DEVICES), stop_testserver_count)
                self.mark_test_step(f"Stopping testservers {stop_indices}")

                async def stop_and_restart(idx):
                    await multipeer_replicators[idx].stop()
                    await asyncio.sleep(random.randint(100, 300))
                    await multipeer_replicators[idx].start()

                await asyncio.gather(*(stop_and_restart(idx) for idx in stop_indices))

            tasks = [insert_task(), delete_task(), update_task()]
            if should_stop_testserver:
                tasks.append(stop_restart_task())
            await asyncio.gather(*tasks)
            await asyncio.sleep(CRUD_INTERVAL.total_seconds())
            self.mark_test_step("Wait for idle status on all devices ")
            for multipeer in multipeer_replicators:
                try:
                    status = await multipeer.wait_for_idle(timeout=timedelta(seconds=100))
                except Exception:
                    self.mark_test_step("Replication staus fetch timed out")
                assert all(r.status.replicator_error is None for r in status.replicators), (
                    "Multipeer replicator should not have any errors"
                )

            self.mark_test_step(
                "Verifying that all devices have identical document content"
            )
            all_docs_collection = [
                db.get_all_documents("_default._default") for db in all_dbs
            ]
            all_docs_results = await asyncio.gather(*all_docs_collection)
            for all_docs in all_docs_results[1:]:
                assert compare_doc_results_p2p(
                    all_docs_results[0]["_default._default"], all_docs["_default._default"]
                ), "All databases should have the same content"

        self.mark_test_step("Stopping all multipeer replicators")
        await asyncio.gather(*[r.stop() for r in multipeer_replicators])

    # simultaneously inserting 10000 documents and blobs different docs to each CBL and starting replication
    @pytest.mark.asyncio(loop_scope="session")
    async def test_volume_with_blobs(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts,">= 3.3.0")
        NO_OF_DOCS = 100000
        docgen = JSONGenerator(10, NO_OF_DOCS, format="key-value")

        self.mark_test_step("Reset local databases on all devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]
        db1 = all_dbs[0]

        documents = docgen.generate_all_documents()
        doc_ids = set(documents.keys())
        doc_ids_list = list(documents.keys())
        self.mark_test_step("""
                            Add docs with blobs to the database on device 1
                        """)
        blobs_list = ["s1.jpg", "s2.jpg", "s3.jpg", "s4.jpg", "s5.jpg", "s6.jpg", "s7.jpg", "s8.jpg", "s9.jpg",
                      "s10.jpg", "l1.jpg", "l2.jpg", "l3.jpg"]

        async def insert_each_batch(start, value=10):
            async with db1.batch_updater() as b:
                for i in doc_ids_list[start:start + value]:
                    b.upsert_document(
                        "_default._default", i, documents[i], new_blobs={"img": random.choice(blobs_list)}
                    )

        for start in range(0, len(doc_ids), 10):
            await insert_each_batch(start)

        self.mark_test_step("""
                            Start a multipeer replicator on all devices
                            * peerGroupID: “com.couchbase.testing”
                            * identity: anonymous
                            * authenticator: accept-all (null)
                            * collections: default collection                    
                        """)
        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        await asyncio.gather(*[r.start() for r in multipeer_replicators])
        # await asyncio.sleep(180)
        self.mark_test_step("Wait for idle status on all devices")
        for mp in multipeer_replicators:
            status = await mp.wait_for_idle(timeout=timedelta(seconds=6000))
            assert all(r.status.replicator_error is None for r in status.replicators), \
                "Multipeer replicator should not have any errors"

        self.mark_test_step(
            "Verifying that all devices have identical document content"
        )
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"
        self.mark_test_step("Stopping all multipeer replicators")
        await asyncio.gather(*[r.stop() for r in multipeer_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multipeer_end_to_end(self, cblpytest: CBLPyTest, dataset_path: Path):
        #  CB-server1           CB-server2
        #   SGW1                    SGW2 ----  CBL5
        #    /                       \
        # CBL1 <--> CBL2<--->CBL3<--->CBL4
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts,">= 3.3.0")
        DOC_COUNT = 1000

        self.mark_test_step("Reset SG and load `names` dataset")
        cloud_1 = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud_1.configure_dataset(dataset_path, "names")

        cloud_2 = CouchbaseCloud(cblpytest.sync_gateways[1], cblpytest.couchbase_servers[1])
        await cloud_2.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset DBs on all CBL clients and SGWs")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        num_devices = len(cblpytest.test_servers)
        assert num_devices >= 5, "Need at least 5 devices for this test"

        self.mark_test_step("Start push/pull replication with SGW1")

        self.mark_test_step("""
                    Start a replicator:
                        * endpoint: `/names`
                        * collections : `_default._default`
                        * type: push-pull
                        * continuous: true
                        * credentials: user1/pass
                        * enable_document_listener: true
                """)
        replicator1 = Replicator(
            all_dbs[0],
            cblpytest.sync_gateways[0].replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            continuous=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator1.start()

        self.mark_test_step("Start push/pull replication with SGW2")
        self.mark_test_step("""
                            Start a replicator:
                                * endpoint: `/names`
                                * collections : `_default._default`
                                * type: push-pull
                                * continuous: true
                                * credentials: user1/pass
                                * enable_document_listener: true
                        """)
        replicator2 = Replicator(
            all_dbs[-2],
            cblpytest.sync_gateways[1].replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            continuous=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator2.start()

        self.mark_test_step("""
                            Start a replicator:
                                * endpoint: `/names`
                                * collections : `_default._default`
                                * type: push-pull
                                * continuous: true
                                * credentials: user1/pass
                                * enable_document_listener: true
                        """)
        replicator3 = Replicator(
            all_dbs[-1],
            cblpytest.sync_gateways[1].replication_url("names"),
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            enable_document_listener=True,
            continuous=True,
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator3.start()

        # === STEP 4: Start multipeer replication in a mesh pattern ===
        self.mark_test_step("Start CBL <-> CBL replication (multipeer)")
        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest",
                db,
                [ReplicatorCollectionEntry(["_default._default"])],
            )
            for db in all_dbs[:-1]
        ]
        await asyncio.gather(*[mp.start() for mp in multipeer_replicators])

        # === STEP 5: Create doc at Server & push via SGW ===

        async def insert_server(server, bucket="names"):
            docgen = JSONGenerator(random.randint(1, 10), size=DOC_COUNT)
            server_docs = docgen.generate_all_documents()
            for key, value in server_docs.items():
                server.upsert_document(bucket, key, value)

        async def insert_sgw(sgw, db_name="names"):
            docgen = JSONGenerator(random.randint(11, 20), size=DOC_COUNT)
            sgw_docs = docgen.generate_all_documents()
            docs_list = []
            for key, value in sgw_docs.items():
                docs_list.append(DocumentUpdateEntry(key, revid=None, body=value))
            await sgw.upsert_documents(db_name, docs_list)

        async def insert_testserver(testserver_db):
            docgen = JSONGenerator(random.randint(21, 50), size=DOC_COUNT, format="key-value")
            testserver_docs = docgen.generate_all_documents()
            testserver_keys = list(testserver_docs.keys())
            for start in range(0, DOC_COUNT, 10):
                end = min(start + 10, DOC_COUNT)
                async with testserver_db.batch_updater() as b:
                    for key in testserver_keys[start:end]:
                        b.upsert_document("_default._default", key, testserver_docs[key])

        async def stop_and_restart_testserver(idx):
            await multipeer_replicators[idx].stop()
            await asyncio.sleep(random.randint(10, 30))
            await multipeer_replicators[idx].start()

        tasks = [insert_server(cblpytest.couchbase_servers[0], ), insert_server(cblpytest.couchbase_servers[1]),
                 insert_sgw(cblpytest.sync_gateways[0]), insert_sgw(cblpytest.sync_gateways[1]),
                 insert_testserver(all_dbs[0]), insert_testserver(all_dbs[2]), insert_testserver(all_dbs[3]),
                 stop_and_restart_testserver(1)]
        await asyncio.gather(*tasks)
        self.mark_test_step("Wait for idle status on all devices ")
        await asyncio.sleep(300)
        for multipeer in multipeer_replicators:
            status = await multipeer.wait_for_idle(timeout=timedelta(seconds=500))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )
        status = await replicator1.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await replicator2.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        status = await replicator3.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step(
            "Verifying that all devices have identical document content"
        )
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        self.mark_test_step("Check that all docs are replicated correctly in SGW1")
        await compare_local_and_remote(
            all_dbs[0],
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
        )
        self.mark_test_step("Check that all docs are replicated correctly in SGW2")
        await compare_local_and_remote(
            all_dbs[-1],
            cblpytest.sync_gateways[0],
            ReplicatorType.PUSH_AND_PULL,
            "names",
            ["_default._default"],
        )

        self.mark_test_step("Stopping all multipeer replicators")
        await asyncio.gather(*[r.stop() for r in multipeer_replicators])

        for testserver in cblpytest.test_servers:
            await testserver.cleanup()
