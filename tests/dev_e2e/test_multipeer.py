import asyncio
from enum import Enum
from random import randint

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry
from cbltest.api.test_functions import compare_doc_results_p2p


class RapidChangesMode(Enum):
    START = ("start",)
    STOP = "stop"


@pytest.mark.min_test_servers(2)
class TestMultipeer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_medium_mesh_sanity(self, cblpytest: CBLPyTest):
        self.mark_test_step(
            "Reset local database and load `empty` dataset on all devices"
        )
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]
        db1 = all_dbs[0]

        self.mark_test_step("""
            Add 10 docs to the database on device 1
            * docID: doc<1-10>
            * body: {"random": <random-num>}
        """)
        async with db1.batch_updater() as b:
            for i in range(1, 11):
                b.upsert_document(
                    "_default._default", f"doc{i}", [{"random": randint(1, 100000)}]
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
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

        self.mark_test_step("Wait for idle status on all devices except device 1")
        for multipeer in multipeer_replicators[1:]:
            status = await multipeer.wait_for_idle()
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step(
            "Check that all databases on devices other than 1 have identical content to the database on device 1"
        )
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_medium_mesh_consistency(
        self,
        cblpytest: CBLPyTest,
    ):
        self.mark_test_step(
            "Reset local database and load `empty` dataset on all devices"
        )
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step("""
            Add 10 docs to the database on all devices
            * docID: doc<1-x> (10 per device)
            * body: {"random": <random-num>}                    
        """)
        doc_num = 1
        for db in all_dbs:
            async with db.batch_updater() as b:
                for _ in range(10):
                    b.upsert_document(
                        "_default._default",
                        f"doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

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
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

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

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])
