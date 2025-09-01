import asyncio
import random
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
    async def test_large_mesh_sanity(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step("Add 20 documents to the database on device 1")

        db1 = all_dbs[0]

        async with db1.batch_updater() as b:
            for i in range(1, 21):
                b.upsert_document("_default._default", f"doc{i}", [{"random": randint(1, 100000)}])

        self.mark_test_step("Start multipeer replicator on all devices")
        multipeer_replicators = [
            MultipeerReplicator(
                "mesh-test", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

        self.mark_test_step("Wait for idle status on all devices")
        for multipeer in multipeer_replicators[1:]:
            status = await multipeer.wait_for_idle(timeout=timedelta(seconds=60))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Check that all device databases have the same content")

        all_docs_collection = [db.get_all_documents("_default._default") for db in all_dbs]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_large_mesh_consistency(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)

        all_dbs = [dbs[0] for dbs in all_devices_dbs]

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

        self.mark_test_step("Start multipeer replicator on all devices")
        multipeer_replicators = [
            MultipeerReplicator(
                "mesh-test", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

        self.mark_test_step("Wait for idle status on all devices")
        for multipeer in multipeer_replicators:
            status = await multipeer.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Check that all device databases have the same content")
        all_docs_collection = [db.get_all_documents("_default._default") for db in all_dbs]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content"

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_network_partition(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        # Ensure we have at least 6 devices and at most 15
        assert 6 <= len(all_dbs) <= 15, f"Need 6-15 devices, got {len(all_dbs)}"

        # Dynamically split devices into 3 groups
        total_devices = len(all_dbs)
        group_size = total_devices // 3
        remainder = total_devices % 3

        # Distribute remainder devices across groups
        group1_size = group_size + (1 if remainder > 0 else 0)
        group2_size = group_size + (1 if remainder > 1 else 0)
        group3_size = group_size

        group1_dbs = all_dbs[:group1_size]
        group2_dbs = all_dbs[group1_size : group1_size + group2_size]
        group3_dbs = all_dbs[group1_size + group2_size :]

        self.mark_test_step("Add unique documents to each peer group")

        # Calculate documents per device to get 100 docs per group
        docs_per_device_group1 = 100 // len(group1_dbs) if len(group1_dbs) > 0 else 0
        docs_per_device_group2 = 100 // len(group2_dbs) if len(group2_dbs) > 0 else 0
        docs_per_device_group3 = 100 // len(group3_dbs) if len(group3_dbs) > 0 else 0

        # Add documents to group 1
        doc_num = 1
        for db in group1_dbs:
            async with db.batch_updater() as b:
                for _ in range(docs_per_device_group1):
                    b.upsert_document(
                        "_default._default",
                        f"group1-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        # Add documents to group 2
        doc_num = 1
        for db in group2_dbs:
            async with db.batch_updater() as b:
                for _ in range(docs_per_device_group2):
                    b.upsert_document(
                        "_default._default",
                        f"group2-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        # Add documents to group 3
        doc_num = 1
        for db in group3_dbs:
            async with db.batch_updater() as b:
                for _ in range(docs_per_device_group3):
                    b.upsert_document(
                        "_default._default",
                        f"group3-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        total_docs_group1 = len(group1_dbs) * docs_per_device_group1
        total_docs_group2 = len(group2_dbs) * docs_per_device_group2
        total_docs_group3 = len(group3_dbs) * docs_per_device_group3

        self.mark_test_step("Start multipeer replicators with different peer groups")

        # Start replicators with different peer groups
        group1_replicators = [
            MultipeerReplicator("group1", db, [ReplicatorCollectionEntry(["_default._default"])])
            for db in group1_dbs
        ]
        group2_replicators = [
            MultipeerReplicator("group2", db, [ReplicatorCollectionEntry(["_default._default"])])
            for db in group2_dbs
        ]
        group3_replicators = [
            MultipeerReplicator("group3", db, [ReplicatorCollectionEntry(["_default._default"])])
            for db in group3_dbs
        ]

        # Start all replicators
        all_replicators = group1_replicators + group2_replicators + group3_replicators
        start_tasks = [replicator.start() for replicator in all_replicators]
        await asyncio.gather(*start_tasks)

        # Wait for initial replication within each group
        for replicator in all_replicators:
            status = await replicator.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Verify groups are isolated from each other")
        # Check that group 1 devices can't see group 2 or 3
        if group1_dbs and group2_dbs:
            group1_status = await group1_replicators[0].get_status()
            group1_peer_count = len(group1_status.replicators)
            assert group1_peer_count == len(group1_dbs) - 1, (
                f"Group 1 should only see {len(group1_dbs) - 1} peers, got {group1_peer_count}"
            )

        # Check that group 2 devices can't see group 1 or 3
        if group2_dbs and group3_dbs:
            group2_status = await group2_replicators[0].get_status()
            group2_peer_count = len(group2_status.replicators)
            assert group2_peer_count == len(group2_dbs) - 1, (
                f"Group 2 should only see {len(group2_dbs) - 1} peers, got {group2_peer_count}"
            )

        # Check that group 3 devices can't see group 1 or 2
        if group3_dbs:
            group3_status = await group3_replicators[0].get_status()
            group3_peer_count = len(group3_status.replicators)
            assert group3_peer_count == len(group3_dbs) - 1, (
                f"Group 3 should only see {len(group3_dbs) - 1} peers, got {group3_peer_count}"
            )

        self.mark_test_step("Verify each group can see its own documents")
        # Check group 1 can see its own documents
        if group1_dbs:
            group1_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group1_dbs]
            )
            for docs in group1_docs:
                assert len(docs["_default._default"]) == total_docs_group1, (
                    f"Group 1 should have {total_docs_group1} docs, got {len(docs['_default._default'])}"
                )

        # Check group 2 can see its own documents
        if group2_dbs:
            group2_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group2_dbs]
            )
            for docs in group2_docs:
                assert len(docs["_default._default"]) == total_docs_group2, (
                    f"Group 2 should have {total_docs_group2} docs, got {len(docs['_default._default'])}"
                )

        # Check group 3 can see its own documents
        if group3_dbs:
            group3_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group3_dbs]
            )
            for docs in group3_docs:
                assert len(docs["_default._default"]) == total_docs_group3, (
                    f"Group 3 should have {total_docs_group3} docs, got {len(docs['_default._default'])}"
                )

        self.mark_test_step("Verify each group has expected documents")
        # Check group 1 has expected docs
        if group1_dbs:
            group1_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group1_dbs]
            )
            for docs in group1_docs:
                assert len(docs["_default._default"]) == total_docs_group1, (
                    f"Group 1 should have {total_docs_group1} docs, got {len(docs['_default._default'])}"
                )

        # Check group 2 has expected docs
        if group2_dbs:
            group2_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group2_dbs]
            )
            for docs in group2_docs:
                assert len(docs["_default._default"]) == total_docs_group2, (
                    f"Group 2 should have {total_docs_group2} docs, got {len(docs['_default._default'])}"
                )

        # Check group 3 has expected docs
        if group3_dbs:
            group3_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in group3_dbs]
            )
            for docs in group3_docs:
                assert len(docs["_default._default"]) == total_docs_group3, (
                    f"Group 3 should have {total_docs_group3} docs, got {len(docs['_default._default'])}"
                )

        self.mark_test_step("Stop group 2 replicators and restart with group 1's peer ID")
        # Stop group 2 replicators
        if group2_replicators:
            await asyncio.gather(*[replicator.stop() for replicator in group2_replicators])

            # Restart group 2 with group 1's peer ID
            group2_replicators = [
                MultipeerReplicator(
                    "group1", db, [ReplicatorCollectionEntry(["_default._default"])]
                )
                for db in group2_dbs
            ]
            start_tasks = [replicator.start() for replicator in group2_replicators]
            await asyncio.gather(*start_tasks)

        # Wait for replication between group 1 and group 2
        all_replicators = group1_replicators + group2_replicators + group3_replicators
        for replicator in all_replicators:
            status = await replicator.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Verify group 1 and group 2 devices have combined documents")
        # Check combined group 1+2 has expected docs
        if group1_dbs and group2_dbs:
            combined_group_dbs = group1_dbs + group2_dbs
            combined_docs = await asyncio.gather(
                *[db.get_all_documents("_default._default") for db in combined_group_dbs]
            )
            expected_combined = total_docs_group1 + total_docs_group2
            for docs in combined_docs:
                assert len(docs["_default._default"]) == expected_combined, (
                    f"Combined group should have {expected_combined} docs, got {len(docs['_default._default'])}"
                )

        self.mark_test_step("Stop group 3 replicators and restart with group 1's peer ID")
        # Stop group 3 replicators
        if group3_replicators:
            await asyncio.gather(*[replicator.stop() for replicator in group3_replicators])

            # Restart group 3 with group 1's peer ID
            group3_replicators = [
                MultipeerReplicator(
                    "group1", db, [ReplicatorCollectionEntry(["_default._default"])]
                )
                for db in group3_dbs
            ]
            start_tasks = [replicator.start() for replicator in group3_replicators]
            await asyncio.gather(*start_tasks)

        # Wait for replication across all groups
        all_replicators = group1_replicators + group2_replicators + group3_replicators
        for replicator in all_replicators:
            status = await replicator.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Verify all devices have all documents")
        # Check all devices have all docs
        all_docs_results = await asyncio.gather(
            *[db.get_all_documents("_default._default") for db in all_dbs]
        )
        total_expected_docs = total_docs_group1 + total_docs_group2 + total_docs_group3
        for docs in all_docs_results:
            assert len(docs["_default._default"]) == total_expected_docs, (
                f"All devices should have {total_expected_docs} docs, got {len(docs['_default._default'])}"
            )

        # Verify all devices have identical content
        for docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], docs["_default._default"]
            ), "All databases should have the same content"

        await asyncio.gather(*[replicator.stop() for replicator in all_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_scalable_conflict_resolution(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts,">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

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
                await b.upsert_document("_default._default", "conflict1", [{"counter": {device_key: idx + 1}}])

        self.mark_test_step("Start multipeer replication with merge conflict resolver")

        multipeer_replicators = [
            MultipeerReplicator(
                "couchtest",
                db,
                [ReplicatorCollectionEntry(["_default._default"],conflict_resolver=ReplicatorConflictResolver("merge-dict",{"property": "counter"}))],
            )
            for db in all_dbs
        ]
        await asyncio.gather(*[mp.start() for mp in multipeer_replicators])

        self.mark_test_step("Wait for idle status on all devices")
        try:
            for mp in multipeer_replicators:
                status = await mp.wait_for_idle(timeout=timedelta(seconds=60))
                assert all(r.status.replicator_error is None for r in status.replicators), \
                    "Multipeer replicator should not have any errors"
        except Exception:
            self.mark_test_step("Replication staus fetch timed out")

        self.mark_test_step("Verify conflict1 is resolved identically on all devices with 15 device keys")
        results = await asyncio.gather(
            *[db.get_document(DocumentEntry("_default._default", "conflict1")) for db in all_dbs]
        )
        expected_keys = {f"device{i + 1}" for i in range(len(all_dbs))}
        retry = 5
        for doc in results:
            counter = doc.body["counter"]
            assert set(counter.keys()) == expected_keys, "All device keys must be present"
            assert all(value == int(key[-1]) for key, value in counter.items()), "Each key's value must be 1"
            while results[0].revs != doc.revs and retry > 0:
                self.mark_test_step("Rev IDs don't match, wait for 30 seconds")
                await asyncio.sleep(30)
                retry = retry - 1
                for mp in multipeer_replicators:
                    status = await mp.wait_for_idle(timeout=timedelta(seconds=300))
                    assert all(r.status.replicator_error is None for r in status.replicators), \
                        "Multipeer replicator should not have any errors"
            assert results[0].revs == doc.revs, f"revision IDs dont match for {doc} even after 5 retries"

        self.mark_test_step("Stopping multipeer replicator on all devices")
        await asyncio.gather(*[mp.stop() for mp in multipeer_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_dynamic_peer_addition_removal(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")
        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        # Ensure we have at least 6 devices
        assert len(all_dbs) >= 6, f"Need at least 6 devices, got {len(all_dbs)}"

        # Calculate device distribution
        total_devices = len(all_dbs)
        initial_devices = max(3, total_devices // 2)  # At least 3, up to half of total
        additional_devices = min(3, total_devices - initial_devices)  # Up to 3 additional
        devices_to_remove = min(2, initial_devices // 3)  # Remove 1-2 devices

        # Split devices
        initial_dbs = all_dbs[:initial_devices]
        additional_dbs = all_dbs[initial_devices : initial_devices + additional_devices]

        self.mark_test_step("Add documents to initial devices")

        # Add documents to initial devices
        for device_idx, db in enumerate(initial_dbs, 1):
            doc_num = 1
            async with db.batch_updater() as b:
                for _ in range(20):  # 20 docs per device
                    b.upsert_document(
                        "_default._default",
                        f"device{device_idx}-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        total_initial_docs = len(initial_dbs) * 20

        self.mark_test_step("Start multipeer replicator on initial devices")

        # Start replicators on initial devices
        initial_replicators = [
            MultipeerReplicator(
                "dynamic-mesh", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in initial_dbs
        ]
        start_tasks = [replicator.start() for replicator in initial_replicators]
        await asyncio.gather(*start_tasks)

        # Wait for some initial replication progress (not all devices, just a few)
        devices_to_wait = max(1, len(initial_dbs) // 2)  # Wait for half of initial devices
        for i, replicator in enumerate(initial_replicators[:devices_to_wait]):
            status = await replicator.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Add additional devices to the mesh")

        # Add documents to additional devices
        for device_idx, db in enumerate(additional_dbs, len(initial_dbs) + 1):
            doc_num = 1
            async with db.batch_updater() as b:
                for _ in range(20):  # 20 docs per device
                    b.upsert_document(
                        "_default._default",
                        f"device{device_idx}-doc{doc_num}",
                        [{"random": randint(1, 100000)}],
                    )
                    doc_num += 1

        total_additional_docs = len(additional_dbs) * 20

        # Start replicators on additional devices
        additional_replicators = [
            MultipeerReplicator(
                "dynamic-mesh", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in additional_dbs
        ]
        start_tasks = [replicator.start() for replicator in additional_replicators]
        await asyncio.gather(*start_tasks)

        # Wait a short time for replication to start, then remove devices
        await asyncio.sleep(2)  # Give replication a moment to begin

        self.mark_test_step(
            f"Remove {devices_to_remove} random devices from the mesh while replication is active"
        )

        # Randomly select devices to remove (mix of initial and additional devices)
        all_replicators = initial_replicators + additional_replicators
        devices_to_remove_indices = random.sample(range(len(all_replicators)), devices_to_remove)
        devices_to_remove_indices.sort(reverse=True)  # Remove from highest index first

        removed_replicators = []
        remaining_replicators = []
        remaining_dbs = []

        for i, replicator in enumerate(all_replicators):
            if i in devices_to_remove_indices:
                removed_replicators.append(replicator)
            else:
                remaining_replicators.append(replicator)
                remaining_dbs.append(all_dbs[i])

        # Stop the selected replicators while replication is still happening
        await asyncio.gather(*[replicator.stop() for replicator in removed_replicators])

        self.mark_test_step("Wait for remaining devices to stabilize after removal")

        # Wait for remaining devices to reach idle
        for i, replicator in enumerate(remaining_replicators):
            status = await replicator.wait_for_idle(timeout=timedelta(seconds=300))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Verify remaining devices achieve full data consistency")

        # Check all remaining devices have all documents
        all_docs_results = await asyncio.gather(
            *[db.get_all_documents("_default._default") for db in remaining_dbs]
        )
        total_expected_docs = total_initial_docs + total_additional_docs

        for i, docs in enumerate(all_docs_results):
            actual_count = len(docs["_default._default"])
            assert actual_count == total_expected_docs, (
                f"Device {i + 1} should have {total_expected_docs} docs, got {actual_count}"
            )

        # Verify all devices have identical content
        for i, docs in enumerate(all_docs_results[1:], 2):
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], docs["_default._default"]
            ), f"Device {i} should have the same content as device 1"

        # Cleanup remaining replicators
        await asyncio.gather(*[replicator.stop() for replicator in remaining_replicators])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_large_document_replication(self, cblpytest: CBLPyTest):
        for ts in cblpytest.test_servers:
            await self.skip_if_cbl_not(ts, ">= 3.3.0")
        self.mark_test_step("Reset local database and load `empty` dataset on all devices")

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        self.mark_test_step("Add 10 large documents with xl1.jpg blob to the database on device 1")
        db1 = all_dbs[0]

        async with db1.batch_updater() as b:
            for i in range(1, 11):  # Add 10 documents
                b.upsert_document(
                    "_default._default", f"large_doc{i}", new_blobs={"image": "xl1.jpg"}
                )

        self.mark_test_step("Start multipeer replicator on all devices")
        multipeer_replicators = [
            MultipeerReplicator(
                "large-doc-mesh", db, [ReplicatorCollectionEntry(["_default._default"])]
            )
            for db in all_dbs
        ]
        
        mpstart_tasks = [multipeer.start() for multipeer in multipeer_replicators]
        await asyncio.gather(*mpstart_tasks)

        self.mark_test_step("Wait for idle status on all devices")
        for device_idx, multipeer in enumerate(multipeer_replicators[1:], 2):
            status = await multipeer.wait_for_idle(timeout=timedelta(seconds=200))
            assert all(r.status.replicator_error is None for r in status.replicators), (
                "Multipeer replicator should not have any errors"
            )

        self.mark_test_step("Check that all device databases have the same content")

        all_docs_collection = [db.get_all_documents("_default._default") for db in all_dbs]
        all_docs_results = await asyncio.gather(*all_docs_collection)

        # Verify document count on each device
        for device_idx, docs in enumerate(all_docs_results, 1):
            doc_count = len(docs["_default._default"])
            assert doc_count == 10, f"Device {device_idx} should have 10 docs, got {doc_count}"

        # Verify content matches across all devices
        for device_idx, docs in enumerate(all_docs_results[1:], 2):
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], docs["_default._default"]
            ), f"Device {device_idx} content does not match device 1"

        await asyncio.gather(*[multipeer.stop() for multipeer in multipeer_replicators])
