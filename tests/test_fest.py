from pathlib import Path
from typing import Optional, List, Any

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
    async def setup_test_fest_cloud(self, cblpytest: CBLPyTest, dataset_path: Path,
                                    roles: Optional[List[str]] = None) -> CouchbaseCloud:
        self.mark_test_step("Reset SG and load todo dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "todo")

        sg_roles = roles if roles is not None else ["lists.user1.db1-list1.contributor"]
        self.mark_test_step(f"Create SG roles: {', '.join(sg_roles)}")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        for role in sg_roles:
            await cloud.create_role("todo", role, collection_access)

        return cloud

    async def setup_test_fest_dbs(self, cblpytest: CBLPyTest) -> List[Database]:
        self.mark_test_step("Reset local databases load them with the todo dataset")
        return await cblpytest.test_servers[0].create_and_reset_db("todo", ["db1", "db2"])

    async def setup_test_fest_repls(self, cblpytest: CBLPyTest, dbs: tuple[Database, Database],
                                    users: tuple[str, str] = ("user1", "user1")) -> tuple[Replicator, Replicator]:
        self.mark_test_step(f"""
                Create a replicator
                    * endpoint: /todo
                    * database: {dbs[0].name}
                    * collections : _default.lists, _default.tasks, _default.users
                    * type: push-and-pull
                    * continuous: true
                    * enableDocumentListener: true
                    * credentials: users[0]/pass
            """)
        repl1 = Replicator(dbs[0], cblpytest.sync_gateways[0].replication_url("todo"),
                           replicator_type=ReplicatorType.PUSH_AND_PULL, continuous=True,
                           collections=[
                               ReplicatorCollectionEntry(["_default.lists", "_default.tasks", "_default.users"])],
                           authenticator=ReplicatorBasicAuthenticator(users[0], "pass"),
                           enable_document_listener=True)

        self.mark_test_step(f"""
                Create another replicator
                    * endpoint: /todo
                    * database: {dbs[1].name}
                    * collections : _default.lists, _default.tasks, _default.users
                    * type: push-and-pull
                    * continuous: true
                    * enableDocumentListener: true
                    * credentials: users[1]/pass
            """)
        repl2 = Replicator(dbs[1], cblpytest.sync_gateways[0].replication_url("todo"),
                           replicator_type=ReplicatorType.PUSH_AND_PULL, continuous=True,
                           collections=[
                               ReplicatorCollectionEntry(["_default.lists", "_default.tasks", "_default.users"])],
                           authenticator=ReplicatorBasicAuthenticator(users[1], "pass"),
                           enable_document_listener=True)

        return repl1, repl2

    @pytest.mark.asyncio
    async def test_create_tasks(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path, ["lists.user1.db1-list1.contributor",
                                                                   "lists.user1.db2-list1.contributor"])
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2))

        self.mark_test_step("Snapshot db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("Snapshot db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Create a list and a task in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("Create a list and a task in db2")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db2-list1-task1",
                              new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                              new_blobs={"image": "l2.jpg"})

        self.mark_test_step("Wait for the new docs to be pulled to db1")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db2-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db2-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("Wait for the new docs to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("Verify that the new docs are in db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db2-list1-task1",
                                         new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                                         {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l2.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        self.mark_test_step("Verify that the new docs are in db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": True},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l1.jpg"})
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_update_task(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2))

        self.mark_test_step("Snapshot db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("Create a list and a task in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})

        self.mark_test_step("Snapshot db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Wait for the new docs to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("Verify that the new docs are in db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l5.jpg"})
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        self.mark_test_step("Update the db1-list1-task1 task in db2")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                              new_blobs={"image": "l10.jpg"})

        self.mark_test_step("Wait for the new doc to be pulled to db1")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("Verify that the doc has been updated in db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                                         new_blobs={"image": "l10.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_delete_task(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2))

        self.mark_test_step("Create a list and a task in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Wait for the updated doc to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})
        repl2.clear_document_updates()

        self.mark_test_step("Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("Delete the task _default.tasks.db1-list1-task1 in db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.tasks", "db1-list1-task1")

        self.mark_test_step("Wait for the deleted document to be pulled to db2")
        await repl2.wait_for_all_doc_events(
            {WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                       ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("Verify that _default.tasks.db1-list1-task1 was deleted from db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        self.mark_test_step("Verify that _default.tasks.db1-list1-task1 was deleted from db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_delete_list(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path)
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2))

        self.mark_test_step("Create a list and two tasks in db1")
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

        self.mark_test_step("Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Wait for the new docs to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})
        repl2.clear_document_updates()

        self.mark_test_step("Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("Delete the _default.tasks, db1-list1-task1 task in db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.lists", "db1-list1")
            b.delete_document("_default.tasks", "db1-list1-task1")
            b.delete_document("_default.tasks", "db1-list1-task2")

        self.mark_test_step("Wait for the deleted documents to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("Verify that _default.tasks.db1-list1-task1 was deleted from db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        self.mark_test_step("Verify that _default.tasks.db1-list1-task1 was deleted from db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.delete_document("_default.lists", "db1-list1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_create_tasks_two_users(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path, ["lists.user1.db1-list1.contributor",
                                                                   "lists.user2.db2-list1.contributor"])
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2), ("user1", "user2"))

        self.mark_test_step("Create a list and a task in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("Create a list and a task in db2")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user2"}])
            b.upsert_document("_default.tasks", "db2-list1-task1",
                              new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db2-list1", "owner": "user2"}}],
                              new_blobs={"image": "l2.jpg"})

        self.mark_test_step("Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Verify that there are no document replication events in db1, for 10 seconds")
        found = await repl1.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db2-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db2-list1-task1", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #1: " \
                              "{found.collection}, {found.id}, {found.direction}, {found.flags}"

        self.mark_test_step("Verify that there are no document replication events in db2, for 10 seconds")
        found = await repl2.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #2: " \
                              "{found.collection}, {found.id}, {found.direction}, {found.flags}"

        self.mark_test_step("Verify that db1 has not changed")
        verify_result = await db1.verify_documents(SnapshotUpdater(snap1))
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        self.mark_test_step("Verify that db2 has not changed")
        verify_result = await db2.verify_documents(SnapshotUpdater(snap2))
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_share_list(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path, ["lists.user1.db1-list1.contributor"])
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2), ("user1", "user2"))

        self.mark_test_step("Snapshot documents in db2")
        snap = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2"),
            SnapshotDocumentEntry("_default.users", "db1-list1-user2")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Create a list and two tasks in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})
            b.upsert_document("_default.tasks", "db1-list1-task2",
                              new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}])

        self.mark_test_step("Verify that there are no document replication events in db2, for 10 seconds")
        found = await repl2.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #2: " \
                              "{found.collection}, {found.id}, {found.direction}, {found.flags}"

        self.mark_test_step("Verify that there are no new documents in db2")
        verify_result = await db2.verify_documents(SnapshotUpdater(snap))
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        self.mark_test_step("Create a user document to share the _default.lists.db1-list1 from db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.users", "db1-list1-user2",
                              [{"username": "user2"}, {"taskList": {"id": "db1-list1", "owner": "user1"}}])

        self.mark_test_step("Wait for the the newly visible documents to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step(
            "Verify snapshot that the new docs are in db2 and that _default.users.db1-list1-user2 is not")
        snapshot_updater = SnapshotUpdater(snap)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l1.jpg"})
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task2",
                                         new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}])
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_update_shared_tasks(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path, ["lists.user1.db1-list1.contributor"])
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2), ("user1", "user2"))

        self.mark_test_step("Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2"),
            SnapshotDocumentEntry("_default.users", "db1-list1-user2")
        ])

        self.mark_test_step("Create a list and two tasks in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})
            b.upsert_document("_default.tasks", "db1-list1-task2",
                              new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "s1.jpg"})

        self.mark_test_step("Snapshot documents in db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Verify that there are no document replication events in db2, for 10 seconds")
        found = await repl2.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #2: " \
                              "{found.collection}, {found.id}, {found.direction}, {found.flags}"

        self.mark_test_step("Create a user document to share the _default.lists.db1-list1 from db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.users", "db1-list1-user2",
                              [{"username": "user2"}, {"taskList": {"id": "db1-list1", "owner": "user1"}}])

        self.mark_test_step("Wait for the newly visible docs to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step(
            "Verify that the newly visible docs are in db2 and that _default.users.db1-list1-user2 is not")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l1.jpg"})
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task2",
                                         new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "s1.jpg"})
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        self.mark_test_step("Update _default.tasks.db1-list1-task1 and delete db1-list1-task2 in db2")
        async with db2.batch_updater() as b:
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                              new_blobs={"image": "s1.jpg"})
            b.delete_document("_default.tasks", "db1-list1-task2")

        self.mark_test_step("Wait for the changes to be pulled to db1")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("Verify that the new docs are in db1")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "Updated db1 list1 task1"}, {"complete": True}],
                                         new_blobs={"image": "s1.jpg"})
        snapshot_updater.delete_document("_default.tasks", "db1-list1-task2")
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db1: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio
    async def test_unshare_list(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.setup_test_fest_cloud(cblpytest, dataset_path, ["lists.user1.db1-list1.contributor"])
        db1, db2 = await self.setup_test_fest_dbs(cblpytest)
        repl1, repl2 = await self.setup_test_fest_repls(cblpytest, (db1, db2), ("user1", "user2"))

        self.mark_test_step("Snapshot documents in db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task2"),
            SnapshotDocumentEntry("_default.users", "db1-list1-user2")
        ])

        self.mark_test_step("Start the replicators")
        await repl1.start()
        await repl2.start()

        self.mark_test_step("Create a list and two tasks in db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})
            b.upsert_document("_default.tasks", "db1-list1-task2",
                              new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "s1.jpg"})

        self.mark_test_step("Verify that there are no document replication events in db1, for 10 seconds")
        found = await repl2.wait_for_any_doc_event({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PUSH_AND_PULL, None),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PUSH_AND_PULL, None)},
            max_retries=10)
        assert found is None, f"There were unexpected replication events on replicator #2: " \
                              "{found.collection}, {found.id}, {found.direction}, {found.flags}"

        self.mark_test_step("Create a user document to share the _default.lists.db1-list1 from db1")
        async with db1.batch_updater() as b:
            b.upsert_document("_default.users", "db1-list1-user2",
                              [{"username": "user2"}, {"taskList": {"id": "db1-list1", "owner": "user1"}}])

        self.mark_test_step("Wait for the newly visible documents to be pulled to db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step(
            "Verify that the newly visible docs are in db2 and that _default.users.db1-list1-user2 is not")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task1",
                                         new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l1.jpg"})
        snapshot_updater.upsert_document("_default.tasks", "db1-list1-task2",
                                         new_properties=[{"name": "db1 list1 task2"}, {"complete": True},
                                                         {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                                         new_blobs={"image": "s1.jpg"})
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        self.mark_test_step("Unshare the db1-list1 list by deleting _default.users.db1-list1-user2 from db1")
        async with db1.batch_updater() as b:
            b.delete_document("_default.users", "db1-list1-user2")

        self.mark_test_step("Verify that the deletion is pushed from db1")
        await repl1.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.users", "db1-list1-user2", ReplicatorType.PUSH,
                                      ReplicatorDocumentFlags.DELETED)})

        self.mark_test_step("Wait for the newly invisible documents to be removed from db2")
        await repl2.wait_for_all_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task2", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.ACCESS_REMOVED)})

        self.mark_test_step("Verify that the shared list and its tasks do not exist in db2")
        snapshot_updater = SnapshotUpdater(snap2)
        snapshot_updater.purge_document("_default.lists", "db1-list1")
        snapshot_updater.purge_document("_default.tasks", "db1-list1-task1")
        snapshot_updater.purge_document("_default.tasks", "db1-list1-task2")
        verify_result = await db2.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"Unexpected docs in db2: {verify_result.description}"

        await cblpytest.test_servers[0].cleanup()
