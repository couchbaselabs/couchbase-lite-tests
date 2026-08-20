import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorType,
)
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig, ScopeConfig, SyncGateway
from cbltest.utils import retry_assert
from shared.backfill_after_offline import backfill_after_offline
from tenacity import stop_after_attempt, wait_fixed

_CHANNEL_SYNC_FUNCTION = (
    "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
)


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestDocumentChannelHistoryCompaction(CBLTestClass):
    async def _configure_channel_tracking_db(
        self,
        cbs: CouchbaseServer,
        sg: SyncGateway,
        sg_db: str,
        bucket_name: str,
        scopes: dict[str, ScopeConfig] | None = None,
        import_docs: bool = False,
    ) -> None:
        """
        Creates a bucket and configures a Sync Gateway database whose sync function
        assigns channel membership directly from each document's `channels` field, so
        tests can drive channel history purely by editing that field.
        """
        cbs.create_bucket(bucket_name)
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes=scopes if scopes is not None else {"_default": ScopeConfig(collections={"_default": {}})},
            sync=_CHANNEL_SYNC_FUNCTION,
            import_docs=import_docs,
            enable_shared_bucket_access=True if import_docs else None,
        )
        await sg.put_database(sg_db, db_payload)

    async def _latest_seq(
        self,
        sg: SyncGateway,
        sg_db: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> int:
        """Gets the most recent sequence number for a document from the changes feed."""
        changes = await sg.get_changes(sg_db, scope, collection)
        matches = [entry.seq for entry in changes.results if entry.id == doc_id]
        assert matches, f"No changes feed entry found for {doc_id}"
        return max(matches)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_of_doc_that_never_left_a_channel(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        await sg.create_document(sg_db, "doc1", {"channels": ["ABC"]})

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, "doc1")

        self.mark_test_step("Check the history is empty and no error was raised")
        assert history == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_after_leaving_a_channel(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, "doc1", {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        await sg.update_document(sg_db, "doc1", {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, "doc1")

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, "doc1")

        self.mark_test_step(
            "Check the history has an entry for 'ABC' containing exactly the sequence at which the document left it"
        )
        print(f"get_document_channel_history returned: {history!r} (expected leave_seq={leave_seq})")
        assert history == {"ABC": [leave_seq]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_shows_every_historical_seq_for_a_reused_channel_name(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step(
            "Update the document to leave 'ABC' for 'OTHER', then update it again to rejoin 'ABC', "
            "then update it once more to leave 'ABC' for 'OTHER' a second time"
        )
        assert doc.revid is not None
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        first_leave_seq = await self._latest_seq(sg, sg_db, doc_id)
        assert doc.revid is not None
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["ABC"]}, doc.revid)
        assert doc.revid is not None
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        second_leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, doc_id)

        self.mark_test_step(
            "Check the history entry for 'ABC' is a list containing both historical leave-sequences, "
            "in order, and nothing else"
        )
        print(
            f"get_document_channel_history returned: {history!r} "
            f"(expected first_leave_seq={first_leave_seq}, second_leave_seq={second_leave_seq})"
        )
        assert history == {"ABC": [first_leave_seq, second_leave_seq]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_removes_entry_past_its_seq(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' with a sequence past the entry's sequence"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq + 1)

        self.mark_test_step("Check the compact response reports 'ABC' as compacted")
        print(f"compact_document_channel_history returned: {compacted!r} (seq used: {leave_seq + 1})")
        assert compacted == ["ABC"]

        self.mark_test_step("Get the document's channel history again and check the entry for 'ABC' is gone")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        print(f"get_document_channel_history after compact returned: {history!r}")
        assert history == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_channel_not_in_history_is_noop(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC' (it has never left any channel)")
        await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Compact the document's channel history for channel 'OTHER'")
        first_result = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)

        self.mark_test_step("Check the response reports no channels compacted")
        print(f"compact_document_channel_history (nothing to compact) returned: {first_result!r}")
        assert first_result == []

        self.mark_test_step("Repeat the same compact call and check the response is identical (idempotent)")
        second_result = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)
        print(f"compact_document_channel_history (repeat) returned: {second_result!r}")
        assert second_result == first_result == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_nonexistent_docid_returns_404(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Compact the channel history of a document ID that was never created")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.compact_document_channel_history(sg_db, "does_not_exist", 1_000_000)

        self.mark_test_step("Check the request fails with 404")
        print(f"Sync Gateway error on nonexistent docid: code={exc_info.value.code} args={exc_info.value.args!r}")
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_malformed_seq_returns_400(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)

        self.mark_test_step("Attempt to compact 'ABC' with a missing 'seq' field; check the request fails with 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as missing_seq_exc:
            await sg._send_request(
                "post",
                f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
                JSONDictionary({}),
            )
        print(
            f"Sync Gateway error on missing seq: code={missing_seq_exc.value.code} args={missing_seq_exc.value.args!r}"
        )
        assert missing_seq_exc.value.code == 400

        self.mark_test_step("Attempt to compact 'ABC' with a non-integer 'seq' value; check the request fails with 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as non_integer_seq_exc:
            await sg._send_request(
                "post",
                f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
                JSONDictionary({"seq": "not-a-number"}),
            )
        print(
            f"Sync Gateway error on non-integer seq: code={non_integer_seq_exc.value.code} "
            f"args={non_integer_seq_exc.value.args!r}"
        )
        assert non_integer_seq_exc.value.code == 400

    @pytest.mark.skip(
        reason=(
            "Needs new framework plumbing: Sync Gateway's admin API enforces Couchbase-Server-RBAC "
            "roles (e.g. 'Sync Gateway Application' vs 'Sync Gateway Application Read Only') "
            "independently of channel access, but the TDK always talks to the admin API as a full "
            "admin and has no helper to provision a restricted-role caller. Expected behavior once "
            "supported: a caller without the Application role gets 403 on both GET and compact; an "
            "Application Read Only caller gets 200 on GET and 403 on compact."
        )
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_and_compact_require_application_rbac_role(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        pass

    @pytest.mark.asyncio(loop_scope="session")
    async def test_all_keyspace_forms_behave_identically(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_ids = {"bare": "doc_bare", "db_collection": "doc_db_collection", "full": "doc_full"}

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step(
            "Create three documents, each assigned to channel 'ABC', one per keyspace form to be tested"
        )
        revids = {}
        for key, doc_id in doc_ids.items():
            doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})
            assert doc.revid is not None
            revids[key] = doc.revid

        self.mark_test_step("Update each document to move it from 'ABC' to 'OTHER'")
        for key, doc_id in doc_ids.items():
            await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, revids[key])

        self.mark_test_step("Get each document's channel history using the same keyspace form used to update it")
        bare_history = await sg._send_request("get", f"/{sg_db}/_channel_history/{doc_ids['bare']}")
        db_collection_history = await sg._send_request(
            "get", f"/{sg_db}._default/_channel_history/{doc_ids['db_collection']}"
        )
        full_history = await sg.get_document_channel_history(sg_db, doc_ids["full"])

        self.mark_test_step("Check all three histories contain an identical entry for 'ABC'")
        bare_seq = await self._latest_seq(sg, sg_db, doc_ids["bare"])
        db_collection_seq = await self._latest_seq(sg, sg_db, doc_ids["db_collection"])
        full_seq = await self._latest_seq(sg, sg_db, doc_ids["full"])
        print(f"bare keyspace raw response: {bare_history!r} (expected seq={bare_seq})")
        print(f"db.collection keyspace raw response: {db_collection_history!r} (expected seq={db_collection_seq})")
        print(f"full keyspace response: {full_history!r} (expected seq={full_seq})")
        assert bare_history.get("channels", {}) == {"ABC": [bare_seq]}
        assert db_collection_history.get("channels", {}) == {"ABC": [db_collection_seq]}
        assert full_history == {"ABC": [full_seq]}

        self.mark_test_step("Compact all three using their own keyspace form and a sequence past the entry")
        bare_compact = await sg._send_request(
            "post",
            f"/{sg_db}/_channel_history/{doc_ids['bare']}/compact",
            JSONDictionary({"seq": bare_seq + 1}),
        )
        db_collection_compact = await sg._send_request(
            "post",
            f"/{sg_db}._default/_channel_history/{doc_ids['db_collection']}/compact",
            JSONDictionary({"seq": db_collection_seq + 1}),
        )
        full_compact = await sg.compact_document_channel_history(sg_db, doc_ids["full"], full_seq + 1)

        self.mark_test_step("Check all three compacted successfully and all three histories are now empty")
        print(f"bare keyspace compact raw response: {bare_compact!r}")
        print(f"db.collection keyspace compact raw response: {db_collection_compact!r}")
        print(f"full keyspace compact response: {full_compact!r}")
        assert bare_compact.get("compacted_channels") == ["ABC"]
        assert db_collection_compact.get("compacted_channels") == ["ABC"]
        assert full_compact == ["ABC"]
        bare_history_after = await sg._send_request("get", f"/{sg_db}/_channel_history/{doc_ids['bare']}")
        assert bare_history_after.get("channels", {}) == {}
        assert await sg.get_document_channel_history(sg_db, doc_ids["full"]) == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_malformed_keyspace_returns_400(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step(
            "Attempt to get the document's channel history using a keyspace with an empty segment "
            "(db..collection); check the request fails with 400"
        )
        with pytest.raises(CblSyncGatewayBadResponseError) as empty_segment_exc:
            await sg._send_request("get", f"/{sg_db}.._default/_channel_history/{doc_id}")
        print(f"Sync Gateway error on empty-segment keyspace: code={empty_segment_exc.value.code}")
        assert empty_segment_exc.value.code == 400

        self.mark_test_step(
            "Attempt to get the document's channel history using a keyspace with four segments; "
            "check the request fails with 400"
        )
        with pytest.raises(CblSyncGatewayBadResponseError) as four_segment_exc:
            await sg._send_request("get", f"/{sg_db}._default._default.extra/_channel_history/{doc_id}")
        print(f"Sync Gateway error on four-segment keyspace: code={four_segment_exc.value.code}")
        assert four_segment_exc.value.code == 400

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_does_not_change_all_docs_or_changes_feed(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step("Record the document's entry from _all_docs and from _changes")
        all_docs_before = await sg.get_all_documents(sg_db)
        changes_before = await sg.get_changes(sg_db)

        self.mark_test_step("Compact the document's channel history for 'ABC' with a sequence past the entry")
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq + 1)
        assert compacted == ["ABC"]

        self.mark_test_step("Check the document's entry from _all_docs and from _changes is unchanged")
        all_docs_after = await sg.get_all_documents(sg_db)
        changes_after = await sg.get_changes(sg_db)
        print(f"_all_docs revmap before={all_docs_before.revmap!r} after={all_docs_after.revmap!r}")
        assert all_docs_before.revmap == all_docs_after.revmap
        before_ids = {(entry.id, entry.seq) for entry in changes_before.results}
        after_ids = {(entry.id, entry.seq) for entry in changes_after.results}
        print(f"_changes (id, seq) pairs before={before_ids!r} after={after_ids!r}")
        assert before_ids == after_ids

    @pytest.mark.min_couchbase_servers(1)
    @pytest.mark.upg_sgw
    @pytest.mark.asyncio(loop_scope="session")
    async def test_legacy_pre_schema_document_has_no_history(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "data-bucket"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, bucket_name, import_docs=True)

        self.mark_test_step(
            "Create a document assigned to channel 'ABC' directly through Couchbase Server, bypassing "
            "Sync Gateway, so it has no channel-history metadata when Sync Gateway later imports it"
        )
        cbs.upsert_document(bucket_name, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Wait until Sync Gateway has imported the document")

        async def _confirm_imported() -> None:
            remote_doc = await sg.get_document(sg_db, doc_id)
            assert remote_doc is not None, f"{doc_id} not yet visible on Sync Gateway"

        await retry_assert(_confirm_imported, wait_fixed(1), stop_after_attempt(15))

        self.mark_test_step("Get the document's channel history and check it is empty, with no error")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        print(f"channel history of freshly-imported legacy document: {history!r}")
        assert history == {}

        self.mark_test_step("Update the document through Sync Gateway to move it from 'ABC' to 'OTHER'")
        doc = await sg.get_document(sg_db, doc_id)
        assert doc is not None and doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step("Get the document's channel history again and check it now has a fresh entry for 'ABC'")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        print(f"channel history after first real mutation: {history!r} (expected leave_seq={leave_seq})")
        assert history == {"ABC": [leave_seq]}

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_flagship_offline_revoke_then_compact_before_reconnect_still_removes_document(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"
        username = "alice"
        password = "pass"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a user with access to channel 'ABC' only")
        await sg.reset_user(sg_db, username, password, ["ABC"])

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Reset a local database and pull as that user so the document replicates to the device")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]
        initial_replicator = Replicator(
            db,
            sg.replication_url(sg_db),
            collections=[ReplicatorCollectionEntry()],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator(username, password),
            enable_document_listener=True,
            pinned_server_cert=sg.tls_cert(),
        )
        await initial_replicator.start()
        initial_status = await initial_replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        print(f"initial sync status error: {initial_status.error!r}")
        print(
            "initial sync document_updates: "
            f"{[(e.document_id, str(e.flags)) for e in initial_replicator.document_updates]!r}"
        )
        assert initial_status.error is None
        assert any(entry.document_id == doc_id for entry in initial_replicator.document_updates), (
            f"{doc_id} did not replicate to the device on initial sync"
        )

        async def _revoke_and_compact_while_offline() -> None:
            self.mark_test_step(
                "Update the document to move it from 'ABC' to 'OTHER', then compact the document's "
                "channel history for 'ABC' with a sequence past the entry"
            )
            nonlocal doc
            assert doc.revid is not None
            await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
            leave_seq = await self._latest_seq(sg, sg_db, doc_id)
            compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq + 1)
            print(f"compact during offline window returned: {compacted!r} (seq used: {leave_seq + 1})")
            assert compacted == ["ABC"]

        self.mark_test_step("Reconnect: start a new pull replicator for the same user")
        reconnect_replicator = await backfill_after_offline(
            db,
            sg,
            sg_db,
            ReplicatorBasicAuthenticator(username, password),
            while_offline=_revoke_and_compact_while_offline,
        )

        self.mark_test_step("Check the device received the document with the access-removed flag set")
        print(
            "reconnect document_updates: "
            f"{[(e.document_id, str(e.flags)) for e in reconnect_replicator.document_updates]!r}"
        )
        removal_entries = [entry for entry in reconnect_replicator.document_updates if entry.document_id == doc_id]
        assert removal_entries, f"Device never heard about {doc_id} again after reconnecting"
        assert any(entry.flags & ReplicatorDocumentFlags.ACCESS_REMOVED for entry in removal_entries), (
            f"Device reconnected after the offline revoke+compact window but {doc_id} was not "
            f"reported as access-removed: {[str(e.flags) for e in removal_entries]}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_enormous_seq_never_removes_an_active_channel_membership(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channels 'ABC' and 'OTHER'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC", "OTHER"]})

        self.mark_test_step("Update the document to leave 'OTHER' (keeping 'ABC'), creating one historical entry")
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["ABC"]}, doc.revid)

        self.mark_test_step(
            "Compact the document's channel history for both 'ABC' and 'OTHER' with an enormous sequence number"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, 2**48)

        self.mark_test_step("Check the response reports only 'OTHER' as compacted, never 'ABC'")
        print(f"compact with enormous seq (2**48) returned: {compacted!r}")
        assert compacted == ["OTHER"], (
            f"Compaction with an enormous seq must never report an active (never-left) channel: {compacted}"
        )

        self.mark_test_step(
            "Get the document's channel history and check no entry for 'ABC' exists (it was never in "
            "history) and the 'OTHER' entry is gone"
        )
        history = await sg.get_document_channel_history(sg_db, doc_id)
        print(f"channel history after enormous-seq compact: {history!r}")
        assert history == {}

        self.mark_test_step(
            "Get the document directly from Sync Gateway and check it is still assigned to channel 'ABC'"
        )
        current = await sg.get_document(sg_db, doc_id)
        assert current is not None
        print(f"document body after enormous-seq compact: {current.body!r}")
        assert current.body.get("channels") == ["ABC"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_stale_entry_leaves_live_regranted_same_channel_untouched(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to leave 'ABC' for 'OTHER', then update it again to rejoin 'ABC'")
        assert doc.revid is not None
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        stale_leave_seq = await self._latest_seq(sg, sg_db, doc_id)
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["ABC"]}, doc.revid)

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' with a sequence past the historical (first) entry only"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, stale_leave_seq + 1)

        self.mark_test_step("Check the response reports 'ABC' as compacted")
        print(f"compact of stale (already-superseded) entry returned: {compacted!r}")
        assert compacted == ["ABC"]

        self.mark_test_step("Get the document's channel history and check the entry for 'ABC' is gone")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        print(f"channel history after compacting the stale entry: {history!r}")
        assert history == {}

        self.mark_test_step(
            "Get the document directly from Sync Gateway and check it is still currently assigned to channel 'ABC'"
        )
        current = await sg.get_document(sg_db, doc_id)
        assert current is not None
        print(f"document body after compacting the stale entry: {current.body!r}")
        assert current.body.get("channels") == ["ABC"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_collection_isolation_for_same_docid_and_channel_name(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "shared_doc"

        self.mark_test_step(
            "Configure a Sync Gateway database with two collections, each with a channel-membership sync function"
        )
        await self._configure_channel_tracking_db(
            cbs,
            sg,
            sg_db,
            "data-bucket",
            scopes={"_default": ScopeConfig(collections={"col1": {}, "col2": {}})},
        )

        self.mark_test_step(
            "In each collection, create a document with the same ID and assign it to a channel with the same name"
        )
        doc1 = await sg.create_document(sg_db, doc_id, {"channels": ["SHARED"]}, collection="col1")
        doc2 = await sg.create_document(sg_db, doc_id, {"channels": ["SHARED"]}, collection="col2")

        self.mark_test_step("In each collection, update the document to move it out of that channel")
        assert doc1.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc1.revid, collection="col1")
        seq1 = await self._latest_seq(sg, sg_db, doc_id, collection="col1")
        assert doc2.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc2.revid, collection="col2")
        seq2 = await self._latest_seq(sg, sg_db, doc_id, collection="col2")

        self.mark_test_step("Compact the channel history for that channel in the first collection only")
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, seq1 + 1, collection="col1")
        print(f"compact in col1 returned: {compacted!r}")
        assert compacted == ["SHARED"]

        self.mark_test_step("Check the first collection's history entry is gone")
        history1 = await sg.get_document_channel_history(sg_db, doc_id, collection="col1")
        print(f"col1 history after compact: {history1!r}")
        assert history1 == {}

        self.mark_test_step("Check the second collection's history entry for the same channel name is still present")
        history2 = await sg.get_document_channel_history(sg_db, doc_id, collection="col2")
        print(f"col2 history (should be unaffected): {history2!r} (expected seq2={seq2})")
        assert history2 == {"SHARED": [seq2]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_compact_racing_a_document_edit_surfaces_a_clean_conflict(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step(
            "Concurrently: compact the document's channel history for 'ABC', and update the document's body again"
        )
        assert doc.revid is not None
        results = await asyncio.gather(
            sg.compact_document_channel_history(sg_db, doc_id, leave_seq + 1),
            sg.update_document(sg_db, doc_id, {"channels": ["OTHER"], "marker": "raced"}, doc.revid),
            return_exceptions=True,
        )

        self.mark_test_step(
            "Check that at least one of the two concurrent operations either succeeded cleanly or "
            "failed with a surfaced conflict error -- never both silently 'succeeding' while only one "
            "actually applied"
        )
        print(f"concurrent compact/update raw results: {results!r}")
        errors = [r for r in results if isinstance(r, BaseException)]
        for err in errors:
            code = err.code if isinstance(err, CblSyncGatewayBadResponseError) else None
            print(f"concurrent operation raised: {type(err).__name__} code={code} args={getattr(err, 'args', None)!r}")
        assert len(errors) <= 1, f"Both concurrent operations failed, nothing succeeded cleanly: {results}"
        for err in errors:
            assert isinstance(err, CblSyncGatewayBadResponseError), (
                f"Expected a clean Sync Gateway error on conflict, got: {err!r}"
            )
            assert err.code in (409, 500), f"Expected a conflict-style error code, got {err.code}"

        self.mark_test_step(
            "Get the document's channel history and directly from Sync Gateway, and check the final "
            "state is internally consistent"
        )
        final_history = await sg.get_document_channel_history(sg_db, doc_id)
        final_doc = await sg.get_document(sg_db, doc_id)
        print(f"final channel history: {final_history!r}")
        print(f"final document body: {final_doc.body if final_doc is not None else None!r}")
        assert final_doc is not None
        assert isinstance(final_history, dict)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_response_is_a_flat_compacted_channels_list(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, "data-bucket")

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        assert doc.revid is not None
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)
        leave_seq = await self._latest_seq(sg, sg_db, doc_id)

        self.mark_test_step("Compact the document's channel history for 'ABC' with a sequence past the entry")
        raw_response = await sg._send_request(
            "post",
            f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
            JSONDictionary({"seq": leave_seq + 1}),
        )

        self.mark_test_step(
            "Check the raw response body is exactly {'compacted_channels': ['ABC']}, not nested under the document ID"
        )
        print(f"raw compact response body: {raw_response!r}")
        assert raw_response == {"compacted_channels": ["ABC"]}

    @pytest.mark.min_couchbase_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_imports_a_not_yet_imported_document_first(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "data-bucket"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await self._configure_channel_tracking_db(cbs, sg, sg_db, bucket_name)

        self.mark_test_step(
            "Write a document directly into the Couchbase Server bucket, bypassing Sync Gateway entirely, "
            "so it has no Sync Gateway metadata yet"
        )
        cbs.upsert_document(bucket_name, doc_id, {"channels": ["ABC"]})
        print(f"wrote {doc_id!r} directly to CBS bucket {bucket_name!r}; not yet queried via Sync Gateway")

        self.mark_test_step("Compact the document's channel history without first waiting for it to be imported")
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)
        print(f"compact on a not-yet-confirmed-imported document returned: {compacted!r}")

        self.mark_test_step("Check the compact call succeeded rather than erroring or silently skipping the document")
        assert compacted == []

        self.mark_test_step(
            "Get the document from Sync Gateway and check it was imported with a real revision, not left stale"
        )
        imported = await sg.get_document(sg_db, doc_id)
        print(
            f"post-compact get_document: exists={imported is not None} "
            f"revid={getattr(imported, 'revid', None)!r} cv={getattr(imported, 'cv', None)!r} "
            f"body={getattr(imported, 'body', None)!r}"
        )
        assert imported is not None, f"{doc_id} was never imported by Sync Gateway"
        assert imported.revid is not None or imported.cv is not None
        assert imported.body.get("channels") == ["ABC"]
