import asyncio
from enum import Enum
from random import randint
import uuid
import time
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry
from cbltest.api.test_functions import compare_doc_results_p2p

class JSONGenerator:
    def __init__(self, seed=random.randint(0, sys.maxsize), size=60000):
        self.seed = seed
        self.size = size

    def generate_document(self, doc_id: str) -> Dict[str, Any]:
        """Generate a single JSON document with reproducible random data"""
        random.seed(self.seed + int(doc_id.split("-")[0], 16))
        return {
            doc_id: {
                "data": {
                    "temperature": random.uniform(-20, 40),
                    "humidity": random.randint(0, 100),
                    "status": random.choice(["active", "inactive", "maintenance"]),
                },
                "metadata": {
                    "version": 1,
                    "created_at": int(time.time()),
                    "modified_at": int(time.time()),
                },
            }
        }

    def update_document(self, doc: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
        """Update a document with reproducible modifications"""
        offset = int(doc_id.split("-")[0], 16)
        random.seed(self.seed + offset)

        doc["data"]["temperature"] += random.uniform(-5, 5)
        doc["data"]["humidity"] = (doc["data"]["humidity"] + random.randint(-10, 10)) % 100
        doc["data"]["status"] = random.choice(["active", "inactive", "maintenance"])
        doc["metadata"]["version"] = doc["metadata"]["version"] + 1
        doc["metadata"]["modified_at"] = int(time.time())
        return {doc_id: doc}

    def batch_process(
        self,
        process_fn: Callable,
        items_ids: List[Any],
        items_doc: Dict[str, Any] = None,
        batch_size: int = 1000
    ) -> Dict[Any, Any]:
        """Generic batch processing function with threading"""
        results = {}

        def process_batch(batch):
            result = {}
            for item in batch:
                output = process_fn(items_doc[item], item) if items_doc is not None else process_fn(item)
                result.update(output)
            return result

        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(process_batch, items_ids[i:i + batch_size])
                for i in range(0, len(items_ids), batch_size)
            ]
            for future in futures:
                results.update(future.result())

        return results

    def generate_all_documents(self, size=None) -> Dict[str, Dict[str, Any]]:
        """Generate all documents using parallel processing"""
        if size is None:
            size = self.size
        print(f"Generating {size} documents...")
        start = time.time()

        doc_ids = [str(uuid.uuid4()) for _ in range(size)]
        documents = self.batch_process(
            self.generate_document,
            doc_ids
        )

        print(f"Generated {len(documents)} documents in {time.time() - start:.2f}s")
        return documents

    def update_all_documents(self, documents: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Update all documents with consistent modifications"""
        print("Updating documents...")
        start = time.time()

        doc_ids = list(documents.keys())
        updated = self.batch_process(
            self.update_document,
            doc_ids,
            documents
        )

        print(f"Updated {len(updated)} documents in {time.time() - start:.2f}s")
        return updated

@pytest.mark.min_test_servers(5)
class TestSystemMultipeer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_system(self, cblpytest: CBLPyTest):
        NUM_DEVICES = len(cblpytest.test_servers)
        TEST_DURATION = timedelta(hours=24)
        CRUD_INTERVAL = timedelta(minutes=5)
        NO_OF_DOCS = 100000
        MAX_DOCS_PER_CRUD = 5000
        MAX_STOP_TESTSERVERS = int(0.5*NUM_DEVICES)
        docgen=JSONGenerator(1,NO_OF_DOCS)

        self.mark_test_step("Reset local databases on 10 devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]
        db1 = all_dbs[0]

        documents = docgen.generate_all_documents()
        doc_ids = set(documents.keys())
        self.mark_test_step("""
                    Add docs to the database on device 1
                """)

        async with db1.batch_updater() as b:
            for i in doc_ids:
                b.upsert_document(
                    "_default._default",i, documents[i]
                )

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

        self.mark_test_step(f"Starting the System test for {NUM_DEVICES} devices ")
        while datetime.utcnow() < end_time:
            insert_testserver=random.randint(0,NUM_DEVICES-1)
            delete_testserver=random.randint(0,NUM_DEVICES-1)
            update_testserver=random.randint(0,NUM_DEVICES-1)

            insert_count=random.randint(1,MAX_DOCS_PER_CRUD)
            delete_count=random.randint(1,MAX_DOCS_PER_CRUD)
            update_count=random.randint(1,MAX_DOCS_PER_CRUD)
            num_updates=random.randint(1,10)

            crud_ids=random.sample(doc_ids,(delete_count+update_count)) #to ensure no overlaps in IDs
            to_delete = crud_ids[:delete_count]
            to_update = crud_ids[delete_count:]
            should_stop_testserver = random.random() < 0.25  # decides randomly if the selected testserver should be down

            new_docs = docgen.generate_all_documents(size=insert_count)
            new_doc_ids = new_docs.keys()
            documents.update(new_docs) # add newly generated docs to the documents dict
            doc_ids.update(new_doc_ids) # add newly generated doc_ids to the doc_ids list


            doc_ids.difference_update(to_delete)
            docs_to_update = {k: documents[k] for k in to_update}

            # Insert new docs
            async def insert_task():
                async with all_dbs[insert_testserver].batch_updater() as b:
                    for i in new_doc_ids:
                        b.upsert_document("_default._default", i, new_docs[i])

            # Delete random existing docs
            async def delete_task():
                async with all_dbs[delete_testserver].batch_updater() as b:
                    for doc_id in to_delete:
                        b.delete_document("_default._default", doc_id)
                        documents.pop(doc_id)

            # Update existing documents
            async def update_task():
                nonlocal docs_to_update
                for i in range(num_updates):
                    updated_docs = docgen.update_all_documents(docs_to_update)
                    documents.update(updated_docs)
                    async with all_dbs[update_testserver].batch_updater() as b:
                        for doc_id in to_update:
                            b.upsert_document("_default._default", doc_id, updated_docs[doc_id] )
                    docs_to_update=updated_docs

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
            self.mark_test_step("Wait for idle status on all devices ")
            for multipeer in multipeer_replicators:
                status = await multipeer.wait_for_idle()
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

            await asyncio.sleep(CRUD_INTERVAL.total_seconds())

        self.mark_test_step("Stopping all multipeer replicators")
        await asyncio.gather(*[r.stop() for r in multipeer_replicators])

    #simultaneously inserting 10000 documents and blobs different docs to each CBL and starting replication
    @pytest.mark.asyncio(loop_scope="session")
    async def test_volume_with_blobs(self, cbltest: CBLTestClass):
        NO_OF_DOCS=10000
        docgen = JSONGenerator(10, NO_OF_DOCS)

        self.mark_test_step("Reset local databases on all devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]
        db1 = all_dbs[0]

        documents = docgen.generate_all_documents()
        doc_ids = set(documents.keys())
        self.mark_test_step("""
                            Add docs with blobs to the database on device 1
                        """)
        blobs_list=["s1.jpg","s2.jpg","s3.jpg","s4.jpg","s5.jpg","s6.jpg","s7.jpg","s8.jpg","s9.jpg","s10.jpg","l1.jpg","l2.jpg","l3.jpg"]
        async with db1.batch_updater() as b:
            for i in doc_ids:
                b.upsert_document(
                    "_default._default", i, documents[i], new_blobs={"img":random.choice(blobs_list)}
                )

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
        self.mark_test_step("Wait for idle status on all devices")
        for mp in multipeer_replicators:
            status = await mp.wait_for_idle()
            assert all(r.status.replicator_error is None for r in status.replicators), \
                "Multipeer replicator should not have any errors"

        self.mark_test_step(
            "Verifying that all devices have identical document content"
        )
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for idx,all_docs in enumerate(all_docs_results[1:],start=1):
            for id in all_docs_results[0]["_default._default"]:
                assert id in all_docs["_default._default"],f"Doc '{id}' present in dict1 but not dict {idx}"
                assert "img" in all_docs["_default._default"][id]
                assert all_docs["_default._default"][id]["img"]["length"] > 0
                assert all_docs["_default._default"][id]["img"]["content_type"]=="image/jpeg", f"property:content_type not in replicated doc with id {id} and testserver_id {idx} "

        self.mark_test_step("Stopping all multipeer replicators")
        await asyncio.gather(*[r.stop() for r in multipeer_replicators])








