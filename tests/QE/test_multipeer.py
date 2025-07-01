import asyncio
from random import randint

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry
from cbltest.api.test_functions import compare_doc_results_p2p

import logging

logger = logging.getLogger(__name__)


@pytest.mark.min_test_servers(2)
class TestMultipeer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_large_mesh_consistency(self, cblpytest: CBLPyTest):
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)

        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        logger.info("Created databases on all devices")

        self.mark_test_step("Add 50 documents to the database on all devices")
        
        for device_idx, db in enumerate(all_dbs, 1):
            doc_num = 1
            async with db.batch_updater() as b:
                for _ in range(50):
                    b.upsert_document(
                        "_default._default",
                        f"device{device_idx}-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        logger.info("Added 50 documents to the database on all devices")

        self.mark_test_step("Start multipeer replicator on all devices")
        multipeer_replicators = [
            MultipeerReplicator(
                "mesh-test", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

        logger.info("Started multipeer replicator on all devices")

        self.mark_test_step("Wait for idle status on all devices")
        for multipeer in multipeer_replicators:
            status = await multipeer.wait_for_idle()
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Check that all device databases have the same content")
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        logger.info("All databases have the same content")

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])

        logger.info("All multipeer replicators stopped")
        logger.info("Successfully completed test_large_mesh_consistency")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_scalable_conflict_resolution(self, cblpytest: CBLPyTest):
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]


        self.mark_test_step("""
            Insert conflict1 on each device with its unique key in 'counter':
            {"counter": {"deviceX": 1}}
        """)
        for idx, db in enumerate(all_dbs):
            device_key = f"device{idx + 1}"
            await db.upsert_document("_default._default","conflict1",{"counter": {device_key:1}})

        self.mark_test_step("Start multipeer replication with merge conflict resolver")

        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest",
                db,
                ReplicatorCollectionEntry(["_default._default"],conflict_resolver= ReplicatorConflictResolver("merge", {"property": "counter"})),
            )
            for db in all_dbs
        ]
        await asyncio.gather(*[mp.start() for mp in multipeer_replicators])

        self.mark_test_step("Wait for idle status on all devices")
        for mp in multipeer_replicators:
            status = await mp.wait_for_idle()
            assert all(r.status.replicator_error is None for r in status.replicators), \
                "Multipeer replicator should not have any errors"

        self.mark_test_step("Verify conflict1 is resolved identically on all devices with 15 device keys")
        results = await asyncio.gather(
            *[db.get_document("_default._default", "conflict1") for db in all_dbs]
        )
        expected_keys = {f"device{i + 1}" for i in range(len(all_dbs))}
        for doc in results:
            counter = doc["conflict1"]["counter"]
            assert set(counter.keys()) == expected_keys, "All 15 device keys must be present"
            assert all(value == 1 for value in counter.values()), "Each key's value must be 1"
            assert results[0]["_rev"]==doc["_rev"], f"revision IDs dont match for {doc}"

        self.mark_test_step("Stopping multipeer replicator on all devices")
        await asyncio.gather(*[mp.stop() for mp in multipeer_replicators])


