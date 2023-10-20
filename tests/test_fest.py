from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import SnapshotUpdater
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.replicator import Replicator, ReplicatorType, ReplicatorCollectionEntry
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, WaitForDocumentEventEntry, \
    ReplicatorDocumentFlags


class TestFest(CBLTestClass):
    @pytest.mark.asyncio
    async def test_create_tasks(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("1 Reset SG and load 'todo' dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "todo")

        self.mark_test_step("2 Reset local databases db1 and db2, and load them with the 'todo' dataset")
        db1, db2 = await cblpytest.test_servers[0].create_and_reset_db("todo", ["db1", "db2"])

        self.mark_test_step("""
            3 Start a replicator
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

        self.mark_test_step("""
            4 Start another replicator
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

        self.mark_test_step("5 Snapshot db1")
        snap1 = await db1.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db2-list1"),
            SnapshotDocumentEntry("_default.tasks", "db2-list1-task1")
        ])

        self.mark_test_step("6 Snapshot db2")
        snap2 = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("7 Create a role and list and task docs in db1")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user1.db1-list1.contributor", collection_access)

        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l1.jpg"})

        self.mark_test_step("8 Create a role and list and task docs in db2")
        await cloud.create_role("todo", "lists.user1.db2-list1.contributor", collection_access)
        async with db2.batch_updater() as b:
            b.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db2-list1-task1",
                              new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                              {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                              new_blobs={"image": "l2.jpg"})

        self.mark_test_step("9 Check the replications events in db1")
        await repl2.wait_for_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db1-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("10 Check the replications events in db2")
        await repl1.wait_for_doc_events({
            WaitForDocumentEventEntry("_default.lists", "db2-list1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE),
            WaitForDocumentEventEntry("_default.tasks", "db2-list1-task1", ReplicatorType.PULL,
                                      ReplicatorDocumentFlags.NONE)})

        self.mark_test_step("11 Verify the snapshot from step 5")
        snapshot_updater = SnapshotUpdater(snap1)
        snapshot_updater.upsert_document("_default.lists", "db2-list1", [{"name": "db2 list1"}, {"owner": "user1"}])
        snapshot_updater.upsert_document("_default.tasks", "db2-list1-task1",
                                         new_properties=[{"name": "db2 list1 task1"}, {"complete": True},
                                                         {"taskList": {"id": "db2-list1", "owner": "user1"}}],
                                         new_blobs={"image": "l2.jpg"})
        verify_result = await db1.verify_documents(snapshot_updater)
        assert verify_result.result is True, f"The verification failed for db1: {verify_result.description}"

        self.mark_test_step("12 Verify the snapshot from step 6")
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
        self.mark_test_step("1 Reset SG and load 'todo' dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "todo")

        self.mark_test_step("2 Reset local databases db1 and db2, and load them with the 'todo' dataset")
        db1, db2 = await cblpytest.test_servers[0].create_and_reset_db("todo", ["db1", "db2"])

        self.mark_test_step("""
            3 Start a replicator
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

        self.mark_test_step("""
            4 Start another replicator
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

        self.mark_test_step("5 Snapshot db2")
        snap = await db2.create_snapshot([
            SnapshotDocumentEntry("_default.lists", "db1-list1"),
            SnapshotDocumentEntry("_default.tasks", "db1-list1-task1")
        ])

        self.mark_test_step("6 Create a role and list and task docs in db1")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user1.db1-list1.contributor", collection_access)

        async with db1.batch_updater() as b:
            b.upsert_document("_default.lists", "db1-list1", [{"name": "db1 list1"}, {"owner": "user1"}])
            b.upsert_document("_default.tasks", "db1-list1-task1",
                              new_properties=[{"name": "db1 list1 task1"}, {"complete": False},
                                              {"taskList": {"id": "db1-list1", "owner": "user1"}}],
                              new_blobs={"image": "l5.jpg"})

        self.mark_test_step("7 Check the replications events in db2")
        await repl2.wait_for_doc_events({
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
        await repl1.wait_for_doc_events({
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
        self.mark_test_step("1 Reset SG and load 'todo' dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "todo")

        self.mark_test_step("2 Reset local databases db1 and db2, and load them with the 'todo' dataset")
        db1, db2 = await cblpytest.test_servers[0].create_and_reset_db("todo", ["db1", "db2"])

        self.mark_test_step("""
            3 Start a replicator
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

        self.mark_test_step("""
            4 Start another replicator
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

        self.mark_test_step("5 Create a role and list and task docs in db1")
        collection_access: dict[str, Any] = {
            "_default": {
                "lists": {"admin_channels": []},
                "tasks": {"admin_channels": []},
                "users": {"admin_channels": []}
            }
        }
        await cloud.create_role("todo", "lists.user1.db1-list1.contributor", collection_access)

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
        await repl2.wait_for_doc_events({
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
        await repl2.wait_for_doc_events(
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
