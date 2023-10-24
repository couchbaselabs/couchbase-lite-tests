from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater, Database
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, WaitForDocumentEventEntry, \
    ReplicatorDocumentFlags


class TestFest(CBLTestClass):
    async def setup_test_fest_cloud(self, cblpytest: CBLPyTest, dataset_path: Path) -> CouchbaseCloud:
        self.mark_test_step("1 Reset SG and load 'todo' dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "todo")

        self.mark_test_step("2 Create SG role lists.user1.db1-list1.contributor")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user1.db1-list1.contributor", collection_access)

        return cloud

    async def setup_test_fest_dbs(self, cblpytest: CBLPyTest) -> list[Database, Database]:
        self.mark_test_step("3 Reset local databases db1 and db2 and load them with the 'todo' dataset")
        return await cblpytest.test_servers[0].create_and_reset_db("todo", ["db1", "db2"])

    async def setup_test_fest_repls(self, cblpytest: CBLPyTest, db1: Database, db2: Database, step: int = 4) -> \
            tuple[Replicator, Replicator]:
        self.mark_test_step(f"""
                {step} Start a replicator
                    * endpoint: '/todo'
                    * database: 'db1'
                    * collections : '_default.lists', '_default.tasks', '_default.users'
                    * type: push-and-pull
                    * continuous: true
                    * enableDocumentListener: true
                    * credentials: user1/pass
            """)
        repl1 = Replicator(db1, cblpytest.sync_gateways[0].replication_url("todo"),
                           replicator_type=ReplicatorType.PUSH_AND_PULL, continuous=True,
                           collections=[
                               ReplicatorCollectionEntry(["_default.lists", "_default.tasks", "_default.users"])],
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           enable_document_listener=True)
        await repl1.start()

        self.mark_test_step(f"""
                {step + 1} Start another replicator
                    * endpoint: '/todo'
                    * database: 'db2'
                    * collections : '_default.lists', '_default.tasks', '_default.users'
                    * type: push-and-pull
                    * continuous: true
                    * enableDocumentListener: true
                    * credentials: user1/pass
            """)
        repl2 = Replicator(db2, cblpytest.sync_gateways[0].replication_url("todo"),
                           replicator_type=ReplicatorType.PUSH_AND_PULL, continuous=True,
                           collections=[
                               ReplicatorCollectionEntry(["_default.lists", "_default.tasks", "_default.users"])],
                           authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                           enable_document_listener=True)
        await repl2.start()

        return repl1, repl2

    @pytest.mark.asyncio
    async def test_create_tasks(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        cloud = await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2)

        self.mark_test_step("6 Create SG role lists.user1.db2-list1.contributor")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user1.db2-list1.contributor", collection_access)

        self.mark_test_step("7 Snapshot db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("8 Snapshot db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("9 Create a list and a task in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("10 Create a list and a task in 'db2'")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db2-list1-task1",
                              new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                              new_blobs={"image": "l2.jpg"})

        self.mark_test_step("11 Check the replications events in db1")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("12 Check the replications events in db2")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db2-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db2-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("13 Verify the snapshot from step 7")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db2-list1-task1",
                                         new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                                         {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l2.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("14 Verify the snapshot from step 8")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": True},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l1.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

    @pytest.mark.asyncio
    async def test_update_task(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2)

        self.mark_test_step("5 Snapshot db2")
        snap = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("6 Create a list and a task in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})

        self.mark_test_step("7 Check the replications events in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("8 Verify the snapshot from step 5")
        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l5.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

        self.mark_test_step("9 Snapshot db1")
        snap = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("10 Update the db1-list1-task1 task in db2")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                              new_blobs={"image": "l10.jpg"})

        self.mark_test_step("11 Check the replications events in db1")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("12 Verify the snapshot from step 9")
        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                                         new_blobs={"image": "l10.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

    @pytest.mark.asyncio
    async def test_delete_task(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2)

        self.mark_test_step("5 Create a list and a task in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("6 Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("7 Wait and check the pull document replication events in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})
        repl2.clear_document_updates()

        self.mark_test_step("8 Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("9. Delete the _default.tasks, db1-list1-task1 task in db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.tasks", "db1-list1-task1")

        self.mark_test_step("10. Wait and check the pull deleted document replication event in db2")
        await repl2.wait_for_all_doc_events(
            {WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                       ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("11 Verify that _default.tasks.db1-list1-task1 was deleted from db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("12 Verify that _default.tasks.db1-list1-task1 was deleted from db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

    @pytest.mark.asyncio
    async def test_delete_list(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2)

        self.mark_test_step("5 Create a list and two tasks in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})
            b.upsert_document("_default.tasks", "db1-list1-task2",
                              new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})

        self.mark_test_step("6 Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("7 Wait and check the pull document replication events in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})
        repl2.clear_document_updates()

        self.mark_test_step("8 Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("9. Delete the _default.tasks, db1-list1-task1 task in db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.lists", "db1-list1")
            b.delete_document("_default.tasks", "db1-list1-task1")
            b.delete_document("_default.tasks", "db1-list1-task2")

        self.mark_test_step("10. Wait and check the pull deleted document replication event in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("11 Verify that _default.tasks.db1-list1-task1 was deleted from db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("12 Verify that _default.tasks.db1-list1-task1 was deleted from db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

    @pytest.mark.asyncio
    async def test_delete_list(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2)

        self.mark_test_step("5 Create a list and two tasks in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})
            b.upsert_document("_default.tasks", "db1-list1-task2",
                              new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})

        self.mark_test_step("6 Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("7 Wait and check the pull document replication events in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})
        repl2.clear_document_updates()

        self.mark_test_step("8 Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("9. Delete the _default.tasks, db1-list1-task1 task in db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.lists", "db1-list1")
            b.delete_document("_default.tasks", "db1-list1-task1")
            b.delete_document("_default.tasks", "db1-list1-task2")

        self.mark_test_step("10. Wait and check the pull deleted document replication event in db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("11 Verify that _default.tasks.db1-list1-task1 was deleted from db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("12 Verify that _default.tasks.db1-list1-task1 was deleted from db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"

    @pytest.mark.skip(reason="Failing")
    @pytest.mark.asyncio
    async def test_create_tasks_two_users(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        cloud = await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)

        self.mark_test_step("4 Create SG role lists.user2.db2-list1.contributor")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user2.db2-list1.contributor", collection_access)

        self.mark_test_step("5 Create a list and a task in 'db1'")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("6 Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("7 Create a list and a task in 'db2'")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user2"}])
            b.upsert_document("_default.tasks", "db2-list1-task1",
                              new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db2-list1", "owner": "user2"}}],
                              new_blobs={"image": "l2.jpg"})

        self.mark_test_step("8 Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, db1, db2, 9)

        self.mark_test_step("11 Verify no document replication events in db1, in 10 seconds")
        found = await repl1.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db2-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db2-list1-task1", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #1"

        self.mark_test_step("12 Verify no document replication events in db1, in 10 seconds")
        found = await repl2.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"""There were unexpected replication events on replicator #2: {found.collection}, {found.id}, {found.direction}, {found.flags}"""

        self.mark_test_step("13 Verify that db1 has not changed")
        verify_result = await db1.verify_documents(SnapshotUpdater(snap1))
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("14 Verify that db2 has not changed")
        verify_result = await db2.verify_documents(SnapshotUpdater(snap2))
        assert verify_result.result is True, f"The verification failed for db2: {verify_result.description}"
