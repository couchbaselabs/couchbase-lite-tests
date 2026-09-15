import asyncio

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorAuthenticator,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorType,
)
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig, RemoteDocument, ScopeConfig, SyncGateway

_CHANNEL_SYNC_FUNCTION = (
    "function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}"
)

_BUCKET = "data-bucket"

_CHANNEL_TRACKING_CONFIG = DatabaseConfig(
    bucket=_BUCKET,
    index=IndexConfig(num_replicas=0),
    scopes={"_default": ScopeConfig(collections={"_default": {"sync": _CHANNEL_SYNC_FUNCTION}})},
)


async def _one_shot_pull(
    db: Database,
    sync_gateway: SyncGateway,
    db_name: str,
    authenticator: ReplicatorAuthenticator,
) -> Replicator:
    """
    Runs a one-shot pull replicator to completion and returns it so the caller can assert
    on what it pulled via `document_updates`.
    """
    replicator = Replicator(
        db,
        sync_gateway.replication_url(db_name),
        replicator_type=ReplicatorType.PULL,
        authenticator=authenticator,
        collections=[ReplicatorCollectionEntry()],
        enable_document_listener=True,
        pinned_server_cert=sync_gateway.tls_cert(),
    )
    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is None, f"Pull replicator failed: {status.error}"
    return replicator


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestDocumentChannelHistoryCompaction(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_of_doc_that_never_left_a_channel(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        await sg.create_document(sg_db, "doc1", {"channels": ["ABC"]})

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, "doc1")

        self.mark_test_step("Check the history is empty and no error was raised")
        assert history == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_after_leaving_a_channel(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, "doc1", {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        doc = await sg.update_document(sg_db, "doc1", {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        leave_seq = doc.seq

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, "doc1")

        self.mark_test_step(
            "Check the history has an entry for 'ABC' containing exactly the sequence at which the document left it"
        )
        assert history == {"ABC": [leave_seq]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_history_shows_every_historical_seq_for_a_reused_channel_name(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step(
            "Update the document to leave 'ABC' for 'OTHER', then rejoin 'ABC' then remove 'ABC' a second time"
        )
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        first_leave_seq = doc.seq
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["ABC", "OTHER"]}, doc.revid)
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        second_leave_seq = doc.seq

        self.mark_test_step("Get the document's channel history")
        history = await sg.get_document_channel_history(sg_db, doc_id)

        self.mark_test_step(
            "Check the history entry for 'ABC' is a list containing both historical leave-sequences, and nothing else"
        )
        assert history == {"ABC": [second_leave_seq, first_leave_seq]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_removes_entry_past_its_seq(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        leave_seq = doc.seq

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' using the exact sequence at which it left"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq)

        self.mark_test_step("Check the compact response reports 'ABC' as compacted")
        assert compacted == ["ABC"]

        self.mark_test_step("Get the document's channel history again and check the entry for 'ABC' is gone")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        assert history == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_channel_not_in_history_is_noop(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC' (it has never left any channel)")
        await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step(
            "Compact the document's channel history with a sequence number that has no matching history entry"
        )
        first_result = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)

        self.mark_test_step("Check the response reports no channels compacted")
        assert first_result == []

        self.mark_test_step("Repeat the same compact call and check the response is identical (idempotent)")
        second_result = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)
        assert second_result == first_result == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_nonexistent_docid_returns_404(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Compact the channel history of a document ID that was never created")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.compact_document_channel_history(sg_db, "does_not_exist", 1_000_000)

        self.mark_test_step("Check the request fails with 404")
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_malformed_seq_returns_400(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid)

        self.mark_test_step("Attempt to compact 'ABC' with a missing 'seq' field; check the request fails with 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as missing_seq_exc:
            await sg._send_request(
                "post",
                f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
                JSONDictionary({}),
            )
        assert missing_seq_exc.value.code == 400

        self.mark_test_step("Attempt to compact 'ABC' with a non-integer 'seq' value; check the request fails with 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as non_integer_seq_exc:
            await sg._send_request(
                "post",
                f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
                JSONDictionary({"seq": "not-a-number"}),
            )
        assert non_integer_seq_exc.value.code == 400

    @pytest.mark.skip(reason="https://jira.issues.couchbase.com/browse/CBG-5796")
    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_and_compact_require_application_rbac_role(self, cblpytest: CBLPyTest) -> None:
        pass

    @pytest.mark.asyncio(loop_scope="session")
    async def test_all_keyspace_forms_behave_identically(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_ids = {"bare": "doc_bare", "db_collection": "doc_db_collection", "full": "doc_full"}

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step(
            "Create three documents, each assigned to channel 'ABC', one per keyspace form to be tested"
        )
        revids = {}
        for key, doc_id in doc_ids.items():
            doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})
            revids[key] = doc.revid

        self.mark_test_step("Update each document to move it from 'ABC' to 'OTHER'")
        updated_docs = {}
        for key, doc_id in doc_ids.items():
            updated_docs[key] = await sg.update_document(
                sg_db, doc_id, {"channels": ["OTHER"]}, revids[key], wait_for_caching_feed=True
            )

        self.mark_test_step("Get each document's channel history using the same keyspace form used to update it")
        bare_history = await sg._send_request("get", f"/{sg_db}/_channel_history/{doc_ids['bare']}")
        db_collection_history = await sg._send_request(
            "get", f"/{sg_db}._default/_channel_history/{doc_ids['db_collection']}"
        )
        full_history = await sg.get_document_channel_history(sg_db, doc_ids["full"])

        self.mark_test_step("Check all three histories contain an identical entry for 'ABC'")
        bare_seq = updated_docs["bare"].seq
        db_collection_seq = updated_docs["db_collection"].seq
        full_seq = updated_docs["full"].seq
        assert bare_history == {"ABC": [bare_seq]}
        assert db_collection_history == {"ABC": [db_collection_seq]}
        assert full_history == {"ABC": [full_seq]}

        self.mark_test_step(
            "Compact all three using their own keyspace form and the exact sequence at which each entry ended"
        )
        bare_compact = await sg._send_request(
            "post",
            f"/{sg_db}/_channel_history/{doc_ids['bare']}/compact",
            JSONDictionary({"seq": bare_seq}),
        )
        db_collection_compact = await sg._send_request(
            "post",
            f"/{sg_db}._default/_channel_history/{doc_ids['db_collection']}/compact",
            JSONDictionary({"seq": db_collection_seq}),
        )
        full_compact = await sg.compact_document_channel_history(sg_db, doc_ids["full"], full_seq)

        self.mark_test_step("Check all three compacted successfully and all three histories are now empty")
        assert bare_compact.get("compacted_channels") == ["ABC"]
        assert db_collection_compact.get("compacted_channels") == ["ABC"]
        assert full_compact == ["ABC"]
        bare_history_after = await sg._send_request("get", f"/{sg_db}/_channel_history/{doc_ids['bare']}")
        assert bare_history_after == {}
        assert await sg.get_document_channel_history(sg_db, doc_ids["full"]) == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_malformed_keyspace_returns_400(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step(
            "Attempt to get the document's channel history using a keyspace with an empty segment "
            "(db..collection); check the request fails with 500 and the expected error message "
            "(bug: CBG-5748 -- should be a 400, update this assertion once fixed)"
        )
        with pytest.raises(CblSyncGatewayBadResponseError) as empty_segment_exc:
            await sg._send_request("get", f"/{sg_db}.._default/_channel_history/{doc_id}")
        assert empty_segment_exc.value.code == 500
        assert "keyspace fields cannot be empty" in str(empty_segment_exc.value)

        self.mark_test_step(
            "Attempt to get the document's channel history using a keyspace with an extra segment "
            "(db.scope.collection.extra); check the request fails with 500 "
            "(bug: CBG-5806 -- should be a 400, update this assertion once fixed)"
        )
        with pytest.raises(CblSyncGatewayBadResponseError) as four_segment_exc:
            await sg._send_request("get", f"/{sg_db}._default._default.extra/_channel_history/{doc_id}")
        assert four_segment_exc.value.code == 500

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_does_not_change_all_docs_or_changes_feed(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        leave_seq = doc.seq

        self.mark_test_step("Record the document's entry from _all_docs and from _changes")
        all_docs_before = await sg.get_all_documents(sg_db)
        changes_before = await sg.get_changes(sg_db)

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' using the exact sequence at which it left"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq)
        assert compacted == ["ABC"]

        self.mark_test_step("Check the document's entry from _all_docs and from _changes is unchanged")
        all_docs_after = await sg.get_all_documents(sg_db)
        changes_after = await sg.get_changes(sg_db)
        assert all_docs_before.revmap == all_docs_after.revmap
        before_ids = {(entry.id, entry.seq) for entry in changes_before.results}
        after_ids = {(entry.id, entry.seq) for entry in changes_after.results}
        assert before_ids == after_ids

    @pytest.mark.min_couchbase_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_legacy_pre_schema_document_has_no_history(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = _BUCKET
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(
            sg_db,
            DatabaseConfig(
                bucket=_BUCKET,
                index=IndexConfig(num_replicas=0),
                scopes={"_default": ScopeConfig(collections={"_default": {"sync": _CHANNEL_SYNC_FUNCTION}})},
                enable_shared_bucket_access=True,
            ),
        )

        self.mark_test_step(
            "Create a document assigned to channel 'ABC' directly through Couchbase Server, bypassing "
            "Sync Gateway, so it has no channel-history metadata when Sync Gateway later imports it"
        )
        cbs.upsert_document(bucket_name, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Perform on demand import")
        await sg.get_document(sg_db, doc_id)

        self.mark_test_step("Get the document's channel history and check it is empty, with no error")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        assert history == {}

        self.mark_test_step("Update the document through Sync Gateway to move it from 'ABC' to 'OTHER'")
        doc = await sg.get_document(sg_db, doc_id)
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        leave_seq = doc.seq

        self.mark_test_step("Get the document's channel history again and check it now has a fresh entry for 'ABC'")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        assert history == {"ABC": [leave_seq]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_enormous_seq_never_removes_an_active_channel_membership(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channels 'ABC' and 'OTHER'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC", "OTHER"]})

        self.mark_test_step("Update the document to leave 'OTHER' (keeping 'ABC'), creating one historical entry")
        await sg.update_document(sg_db, doc_id, {"channels": ["ABC"]}, doc.revid)

        self.mark_test_step(
            "Compact the document's channel history for both 'ABC' and 'OTHER' with an enormous sequence number"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, 2**48)

        self.mark_test_step("Check the response reports only 'OTHER' as compacted, never 'ABC'")
        assert compacted == ["OTHER"], (
            f"Compaction with an enormous seq must never report an active (never-left) channel: {compacted}"
        )

        self.mark_test_step(
            "Get the document's channel history and check no entry for 'ABC' exists (it was never in "
            "history) and the 'OTHER' entry is gone"
        )
        history = await sg.get_document_channel_history(sg_db, doc_id)
        assert history == {}

        self.mark_test_step(
            "Get the document directly from Sync Gateway and check it is still assigned to channel 'ABC'"
        )
        current = await sg.get_document(sg_db, doc_id)
        assert current is not None
        assert current.body.get("channels") == ["ABC"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_stale_entry_leaves_live_regranted_same_channel_untouched(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to leave 'ABC', recording the sequence at which it left")
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER-0"]}, doc.revid, wait_for_caching_feed=True)
        stale_leave_seq = doc.seq

        self.mark_test_step("Make the document rejoin 'ABC'")
        await sg.update_document(sg_db, doc_id, {"channels": ["ABC"]}, doc.revid)

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' using the exact sequence at which it first left, "
            "without touching the current (rejoined) membership"
        )
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, stale_leave_seq)

        self.mark_test_step("Check the response reports 'ABC' as compacted")
        assert compacted == ["ABC"]

        self.mark_test_step("Get the document's channel history and check the entry for 'ABC' is gone")
        history = await sg.get_document_channel_history(sg_db, doc_id)
        assert "ABC" not in history, f"'ABC' should have been compacted out of history: {history!r}"

        self.mark_test_step(
            "Get the document directly from Sync Gateway and check it is still currently assigned to channel 'ABC'"
        )
        current = await sg.get_document(sg_db, doc_id)
        assert current is not None
        assert current.body.get("channels") == ["ABC"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_collection_isolation_for_same_docid_and_channel_name(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "shared_doc"

        self.mark_test_step(
            "Configure a Sync Gateway database with two collections, each with a channel-membership sync function"
        )
        await cblpytest.clusters[0].create_database(
            sg_db,
            DatabaseConfig(
                bucket=_BUCKET,
                index=IndexConfig(num_replicas=0),
                scopes={
                    "_default": ScopeConfig(
                        collections={
                            "col1": {"sync": _CHANNEL_SYNC_FUNCTION},
                            "col2": {"sync": _CHANNEL_SYNC_FUNCTION},
                        }
                    )
                },
            ),
        )

        self.mark_test_step(
            "In each collection, create a document with the same ID and assign it to a channel with the same name"
        )
        doc1 = await sg.create_document(sg_db, doc_id, {"channels": ["SHARED"]}, collection="col1")
        doc2 = await sg.create_document(sg_db, doc_id, {"channels": ["SHARED"]}, collection="col2")

        self.mark_test_step("In each collection, update the document to move it out of that channel")
        doc1 = await sg.update_document(
            sg_db, doc_id, {"channels": ["OTHER"]}, doc1.revid, collection="col1", wait_for_caching_feed=True
        )
        seq1 = doc1.seq
        doc2 = await sg.update_document(
            sg_db, doc_id, {"channels": ["OTHER"]}, doc2.revid, collection="col2", wait_for_caching_feed=True
        )
        seq2 = doc2.seq

        self.mark_test_step("Compact the channel history for that channel in the first collection only")
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, seq1, collection="col1")
        assert compacted == ["SHARED"]

        self.mark_test_step("Check the first collection's history entry is gone")
        history1 = await sg.get_document_channel_history(sg_db, doc_id, collection="col1")
        assert history1 == {}

        self.mark_test_step("Check the second collection's history entry for the same channel name is still present")
        history2 = await sg.get_document_channel_history(sg_db, doc_id, collection="col2")
        assert history2 == {"SHARED": [seq2]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_compact_racing_a_document_edit_surfaces_a_clean_conflict(
        self, cblpytest: CBLPyTest
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        # Only the compact can lose: it never retries a CAS mismatch.
        # The update goes first so its write lands inside the compact's window.
        race_offset_seconds = 0.0005
        race_attempts = 120

        self.mark_test_step(
            f"Race a compact against an update of the same document {race_attempts} times, "
            "checking after every attempt that the state Sync Gateway is left in matches what each of "
            "the two operations reported -- never both 'succeeding' while only one actually applied"
        )
        for attempt in range(race_attempts):
            doc_id = f"doc{attempt}"
            doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})
            doc = await sg.update_document(
                sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True
            )
            leave_seq = doc.seq

            updating = asyncio.create_task(
                sg.update_document(sg_db, doc_id, {"channels": ["OTHER"], "marker": "raced"}, doc.revid)
            )
            # The await starts the update; the delay holds the compact back.
            await asyncio.sleep(race_offset_seconds)
            # A lost race is a 409.
            compact_result: list[str] | None
            try:
                compact_result = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq)
            except CblSyncGatewayBadResponseError as e:
                if e.code != 409:
                    raise
                compact_result = None
            update_result: RemoteDocument | None
            try:
                update_result = await updating
            except CblSyncGatewayBadResponseError as e:
                if e.code != 409:
                    raise
                update_result = None

            assert compact_result or update_result, (
                f"[attempt {attempt}] both the compact and the update lost the race, so neither of them applied"
            )

            final_history = await sg.get_document_channel_history(sg_db, doc_id)
            final_doc = await sg.get_document(sg_db, doc_id)
            assert final_doc is not None

            # The entry is gone if and only if the compact reported removing it.
            if compact_result:
                assert final_history == {}, (
                    f"[attempt {attempt}] the compact reported compacting {compact_result}, but the "
                    f"channel history is {final_history}"
                )
            else:
                assert final_history == {"ABC": [leave_seq]}, (
                    f"[attempt {attempt}] the compact lost the race, so the channel history should "
                    f"still be {{'ABC': [{leave_seq}]}}, but it is {final_history}"
                )

            # The body change lands if and only if the update reported success.
            if update_result:
                assert final_doc.body == {"channels": ["OTHER"], "marker": "raced"}, (
                    f"[attempt {attempt}] the update reported success, but the document body is {final_doc.body}"
                )
            else:
                assert final_doc.body == {"channels": ["OTHER"]}, (
                    f"[attempt {attempt}] the update lost the race, so the document body should still "
                    f"be {{'channels': ['OTHER']}}, but it is {final_doc.body}"
                )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_response_is_a_flat_compacted_channels_list(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Update the document to move it from 'ABC' to 'OTHER'")
        doc = await sg.update_document(sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True)
        leave_seq = doc.seq

        self.mark_test_step(
            "Compact the document's channel history for 'ABC' using the exact sequence at which it left"
        )
        raw_response = await sg._send_request(
            "post",
            f"/{sg_db}._default._default/_channel_history/{doc_id}/compact",
            JSONDictionary({"seq": leave_seq}),
        )

        self.mark_test_step(
            "Check the raw response body is exactly {'compacted_channels': ['ABC']}, not nested under the document ID"
        )
        assert raw_response == {"compacted_channels": ["ABC"]}

    @pytest.mark.min_couchbase_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_imports_a_not_yet_imported_document_first(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = _BUCKET
        doc_id = "doc1"

        self.mark_test_step(
            "Configure a Sync Gateway database with a channel-membership sync function and automatic import disabled"
        )
        await cblpytest.clusters[0].create_database(
            sg_db,
            DatabaseConfig(
                bucket=_BUCKET,
                index=IndexConfig(num_replicas=0),
                scopes={"_default": ScopeConfig(collections={"_default": {"sync": _CHANNEL_SYNC_FUNCTION}})},
                import_docs=False,
                enable_shared_bucket_access=True,
            ),
        )

        self.mark_test_step(
            "Write a document directly into the Couchbase Server bucket, bypassing Sync Gateway entirely, "
            "so it has no Sync Gateway metadata yet"
        )
        cbs.upsert_document(bucket_name, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Compact the document's channel history without first waiting for it to be imported")
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, 1_000_000)

        self.mark_test_step("Check the compact call succeeded rather than erroring or silently skipping the document")
        assert compacted == []

        self.mark_test_step(
            "Get the document from Sync Gateway and check it was imported with a real revision, not left stale"
        )
        imported = await sg.get_document(sg_db, doc_id)
        assert imported is not None, f"{doc_id} was never imported by Sync Gateway"
        assert imported.body.get("channels") == ["ABC"]

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_before_reconnect_still_delivers_revoke(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        sg_db = "db"
        doc_id = "doc1"
        username = "leo"
        password = "pass"

        self.mark_test_step("Configure a Sync Gateway database with a channel-membership sync function")
        await cblpytest.clusters[0].create_database(sg_db, _CHANNEL_TRACKING_CONFIG)

        self.mark_test_step("Create user 'leo' with permanent access to channel 'ABC' (never revoked)")
        await sg.reset_user(sg_db, username, password, ["ABC"])

        self.mark_test_step("Create a document assigned to channel 'ABC'")
        doc = await sg.create_document(sg_db, doc_id, {"channels": ["ABC"]})

        self.mark_test_step("Reset a local database and pull as that user so the document replicates to the device")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]
        authenticator = ReplicatorBasicAuthenticator(username, password)
        initial_replicator = await _one_shot_pull(db, sg, sg_db, authenticator)
        assert any(entry.document_id == doc_id for entry in initial_replicator.document_updates), (
            f"{doc_id} did not replicate to the device on initial sync"
        )

        self.mark_test_step(
            "While the client is offline (i.e. between the two one-shot pulls), update the document to leave "
            "channel 'ABC' for 'OTHER', then compact the document's channel history for 'ABC' before it reconnects"
        )
        updated_doc = await sg.update_document(
            sg_db, doc_id, {"channels": ["OTHER"]}, doc.revid, wait_for_caching_feed=True
        )
        leave_seq = updated_doc.seq
        compacted = await sg.compact_document_channel_history(sg_db, doc_id, leave_seq)
        assert compacted == ["ABC"]
        assert await sg.get_document_channel_history(sg_db, doc_id) == {}

        self.mark_test_step("Bring the client back online: start a new pull replicator for the same user")
        reconnect_replicator = await _one_shot_pull(db, sg, sg_db, authenticator)

        self.mark_test_step(
            "Check that the device still received the document with the access-removed flag set --  (unlike the "
            "user-access side, where the equivalent check is retroactive and reads exactly what gets compacted)"
        )
        removal_entries = [entry for entry in reconnect_replicator.document_updates if entry.document_id == doc_id]
        assert removal_entries, f"Device never heard about {doc_id} again after reconnecting"
        assert any(entry.flags & ReplicatorDocumentFlags.ACCESS_REMOVED for entry in removal_entries), (
            f"Device reconnected after the offline channel-departure-and-compact window but {doc_id} was not "
            f"reported as access-removed: {[str(e.flags) for e in removal_entries]}"
        )

        self.mark_test_step("Check that the document is no longer present on the client")
        all_docs = await db.get_all_documents("_default._default")
        assert not any(entry.id == doc_id for entry in all_docs["_default._default"]), (
            f"Expected {doc_id} to have been removed from the client after the access-removed notification"
        )
