import asyncio
import random
import re
from datetime import timedelta
from random import randint

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator_types import (
    ReplicatorCollectionEntry,
    ReplicatorConflictResolver,
)
from cbltest.api.test_functions import compare_doc_results_p2p


@pytest.mark.min_test_servers(2)
class TestMultipeer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_scalable_conflict_resolution(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step(
            "Reset local database and load `empty` dataset on all devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step("""
                Insert conflict1 on each device with its unique key in 'counter':
                {"counter": {"deviceX": X}}
            """)
        for idx, db in enumerate(all_dbs):
            device_key = f"device{idx + 1}"
            async with db.batch_updater() as b:
                await b.upsert_document(
                    "_default._default",
                    "conflict1",
                    [{"counter": {device_key: idx + 1}}],
                )

        self.mark_test_step("Start multipeer replication with merge conflict resolver")

        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest",
                db,
                [
                    ReplicatorCollectionEntry(
                        ["_default._default"],
                        conflict_resolver=ReplicatorConflictResolver(
                            "merge-dict", {"property": "counter"}
                        ),
                    )
                ],
            )
            for db in all_dbs
        ]
        await asyncio.gather(*[mp.start() for mp in multipeer_replicators])

        self.mark_test_step("Wait for idle status on all devices")
        try:
            for mp in multipeer_replicators:
                status = await mp.wait_for_idle(timeout=timedelta(seconds=60))
                assert all(
                    r.status.replicator_error is None for r in status.replicators
                ), "Multipeer replicator should not have any errors"
        except Exception:
            self.mark_test_step("Replication staus fetch timed out")

        self.mark_test_step(
            "Verify conflict1 is resolved identically on all devices with 15 device keys"
        )
        results = await asyncio.gather(
            *[
                db.get_document(DocumentEntry("_default._default", "conflict1"))
                for db in all_dbs
            ]
        )
        expected_keys = {f"device{i + 1}" for i in range(len(all_dbs))}
        retry = 5
        for doc in results:
            counter = doc.body["counter"]
            assert set(counter.keys()) == expected_keys, (
                "All device keys must be present"
            )
            assert all(value == int(re.search(r'\d+$', key).group()) for key, value in counter.items()), (
                "Each key's value must be device_id"
            )
            while results[0].revs != doc.revs and retry > 0:
                self.mark_test_step("Rev IDs don't match, wait for 30 seconds")
                await asyncio.sleep(30)
                retry = retry - 1
                for mp in multipeer_replicators:
                    status = await mp.wait_for_idle(timeout=timedelta(seconds=300))
                    assert all(
                        r.status.replicator_error is None for r in status.replicators
                    ), "Multipeer replicator should not have any errors"
                results = await asyncio.gather(
                    *[
                        db.get_document(DocumentEntry("_default._default", "conflict1"))
                        for db in all_dbs
                    ]
                )
                assert results[0].revs == doc.revs, (
                    f"revision IDs dont match for {doc} even after 5 retries"
                )

        self.mark_test_step("Stopping multipeer replicator on all devices")
        await asyncio.gather(*[mp.stop() for mp in multipeer_replicators])
