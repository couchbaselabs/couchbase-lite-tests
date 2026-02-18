import asyncio
from datetime import timedelta
from random import randint

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.listener import Listener
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.test_functions import compare_doc_results_p2p


@pytest.mark.cbl
@pytest.mark.min_test_servers(3)
class TestPeerToPeerTopology(CBLTestClass):
    @pytest.mark.parametrize(
        "num_of_docs, continuous, replicator_type",
        [(10, True, "push_pull"), (100, False, "push_pull")],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_peer_to_peer_topology_mesh(
        self, cblpytest: CBLPyTest, num_of_docs, continuous, replicator_type
    ):
        replicator_type_map = {
            "push_pull": ReplicatorType.PUSH_AND_PULL,
            "pull": ReplicatorType.PULL,
            "push": ReplicatorType.PUSH,
        }
        replicator_type = replicator_type_map[replicator_type]

        self.mark_test_step(
            "Reset local database and load `empty` dataset on all devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        # Run 3 phases: Peer 1 -> (2,3), Peer 2 -> (1,3), Peer 3 -> (1,2)
        for phase in range(1, 4):
            source_peer_idx = phase - 1  # 0, 1, 2 for peers 1, 2, 3
            target_peers = [
                i for i in range(3) if i != source_peer_idx
            ]  # Other two peers

            self.mark_test_step(
                f"PHASE {phase}: Peer {phase} -> Peers {[p + 1 for p in target_peers]}"
            )

            self.mark_test_step(
                f"Add {num_of_docs} documents to the database on peer {phase}"
            )
            source_db = all_dbs[source_peer_idx]

            batch_size = 10
            for start in range(1, num_of_docs + 1, batch_size):
                end = min(start + batch_size, num_of_docs + 1)
                async with source_db.batch_updater() as b:
                    for i in range(start, end):
                        b.upsert_document(
                            "_default._default",
                            f"phase{phase}-peer{phase}-doc{i}",
                            [{"random": randint(1, 100000)}],
                        )

            self.mark_test_step(
                f"Start listeners on peers {[p + 1 for p in target_peers]}"
            )
            listeners = []
            for target_idx in target_peers:
                listener = Listener(
                    all_dbs[target_idx], ["_default._default"], 59840, disable_tls=True
                )
                await listener.start()
                listeners.append((target_idx, listener))

            self.mark_test_step(
                f"Setup replicators from peer {phase} to peers {[p + 1 for p in target_peers]}"
            )
            replicators = []
            for target_idx, listener in listeners:
                listener_port = 59840 if listener.port is None else listener.port
                replicator = Replicator(
                    source_db,
                    endpoint=cblpytest.test_servers[target_idx].replication_url(
                        "db1", listener_port
                    ),
                    replicator_type=replicator_type,
                    collections=[ReplicatorCollectionEntry(["_default._default"])],
                    continuous=continuous,
                )
                replicators.append((target_idx, replicator))

            self.mark_test_step(
                f"Start replication from peer {phase} to peers {[p + 1 for p in target_peers]}"
            )
            for _, replicator in replicators:
                await replicator.start()

            self.mark_test_step(f"Wait for replication from peer {phase} to complete")
            target_activity = (
                ReplicatorActivityLevel.IDLE
                if continuous
                else ReplicatorActivityLevel.STOPPED
            )
            for target_idx, replicator in replicators:
                status = await replicator.wait_for(
                    target_activity,
                    timeout=timedelta(seconds=300),
                    interval=timedelta(seconds=1),
                )
                assert status.error is None, (
                    f"Error waiting for replicator from peer {phase} to peer {target_idx + 1}: "
                    f"({status.error.domain} / {status.error.code}) {status.error.message}"
                )

            self.mark_test_step(
                f"Check that all device databases have the replicated documents after phase {phase}"
            )
            all_docs_collection = [
                db.get_all_documents("_default._default") for db in all_dbs
            ]
            all_docs_results = await asyncio.gather(*all_docs_collection)
            for all_docs in all_docs_results[1:]:
                assert compare_doc_results_p2p(
                    all_docs_results[0]["_default._default"],
                    all_docs["_default._default"],
                ), f"All databases should have the same content after phase {phase}"

            self.mark_test_step(f"Stop listeners after phase {phase}")
            for _, listener in listeners:
                await listener.stop()

    @pytest.mark.parametrize(
        "num_of_docs, continuous, replicator_type",
        [
            (10, True, "push_pull"),
            (100, False, "pull"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_peer_to_peer_topology_loop(
        self, cblpytest: CBLPyTest, num_of_docs, continuous, replicator_type
    ):
        replicator_type_map = {
            "push_pull": ReplicatorType.PUSH_AND_PULL,
            "pull": ReplicatorType.PULL,
            "push": ReplicatorType.PUSH,
        }
        replicator_type = replicator_type_map[replicator_type]

        self.mark_test_step(
            "Reset local database and load `empty` dataset on all devices"
        )

        reset_tasks = [ts.create_and_reset_db(["db1"]) for ts in cblpytest.test_servers]
        all_devices_dbs = await asyncio.gather(*reset_tasks)
        all_dbs = [dbs[0] for dbs in all_devices_dbs]

        # Run 3 phases: Peer 1 -> Peer 2, Peer 2 -> Peer 3, Peer 3 -> Peer 1

        for phase in range(1, 4):
            source_peer_idx = phase - 1  # 0, 1, 2 for peers 1, 2, 3
            target_peer_idx = phase % 3  # 1, 2, 0 (wraps around)

            self.mark_test_step(
                f"PHASE {phase}: Peer {phase} -> Peer {target_peer_idx + 1}"
            )

            self.mark_test_step(
                f"Add {num_of_docs} documents to the database on peer {phase}"
            )
            source_db = all_dbs[source_peer_idx]

            batch_size = 10
            for start in range(1, num_of_docs + 1, batch_size):
                end = min(start + batch_size, num_of_docs + 1)
                async with source_db.batch_updater() as b:
                    for i in range(start, end):
                        b.upsert_document(
                            "_default._default",
                            f"phase{phase}-peer{phase}-doc{i}",
                            [{"random": randint(1, 100000)}],
                        )

            self.mark_test_step(f"Start listener on peer {target_peer_idx + 1}")
            listener = Listener(
                all_dbs[target_peer_idx], ["_default._default"], 59840, disable_tls=True
            )
            await listener.start()

            self.mark_test_step(
                f"Setup replicator from peer {phase} to peer {target_peer_idx + 1}"
            )
            listener_port = 59840 if listener.port is None else listener.port
            replicator = Replicator(
                source_db,
                endpoint=cblpytest.test_servers[target_peer_idx].replication_url(
                    "db1", listener_port
                ),
                replicator_type=replicator_type,
                collections=[ReplicatorCollectionEntry(["_default._default"])],
                continuous=continuous,
            )

            self.mark_test_step(
                f"Start replication from peer {phase} to peer {target_peer_idx + 1}"
            )
            await replicator.start()

            self.mark_test_step(
                f"Wait for replication from peer {phase} to peer {target_peer_idx + 1} to complete"
            )
            target_activity = (
                ReplicatorActivityLevel.IDLE
                if continuous
                else ReplicatorActivityLevel.STOPPED
            )
            status = await replicator.wait_for(
                target_activity,
                timeout=timedelta(seconds=300),
                interval=timedelta(seconds=1),
            )
            assert status.error is None, (
                f"Error waiting for replicator from peer {phase} to peer {target_peer_idx + 1}: "
                f"({status.error.domain} / {status.error.code}) {status.error.message}"
            )

            # Verify source and target have same content (not all peers yet)
            self.mark_test_step(
                f"Verify that peer {phase} and peer {target_peer_idx + 1} have the same content after phase {phase}"
            )
            source_docs = await source_db.get_all_documents("_default._default")
            target_docs = await all_dbs[target_peer_idx].get_all_documents(
                "_default._default"
            )
            assert compare_doc_results_p2p(
                source_docs["_default._default"], target_docs["_default._default"]
            ), (
                f"Peer {phase} and peer {target_peer_idx + 1} should have the same content after phase {phase}"
            )

            self.mark_test_step(f"Stop listener after phase {phase}")
            await listener.stop()

        # After all phases complete, verify all peers have converged to same content
        self.mark_test_step(
            "Verify all device databases have converged to the same content after all phases"
        )
        all_docs_collection = [
            db.get_all_documents("_default._default") for db in all_dbs
        ]
        all_docs_results = await asyncio.gather(*all_docs_collection)
        for all_docs in all_docs_results[1:]:
            assert compare_doc_results_p2p(
                all_docs_results[0]["_default._default"], all_docs["_default._default"]
            ), "All databases should have the same content after all phases complete"
