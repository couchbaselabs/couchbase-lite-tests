# Document Channel History Compaction Tests

Covers `/{keyspace}/_channel_history/{docid}` (GET) and
`/{keyspace}/_channel_history/{docid}/compact` (POST) — the per-document side of Sync
Gateway's channel-history compaction feature added in #491. See
`test_user_access_history_compaction.md` for the per-user side of the same feature.

Every database used below is configured with a sync function that assigns channel
membership directly from each document's `channels` field
(`function foo(doc,oldDoc,meta){if(doc._deleted){channel(oldDoc.channels)}else{channel(doc.channels)}}`),
so "leaving a channel" in these tests just means updating that field. Compaction only
ever removes *historical* (already-ended) channel-membership entries; it never touches a
document's live, current channel assignment.

One test below is implemented as an explicit `skip` rather than dropped, per repo
convention of keeping test intent visible even when it can't run yet:
- `test_get_and_compact_require_application_rbac_role` — the TDK has no support yet for
  provisioning a restricted (non-"Application") Couchbase Server RBAC caller against the
  Sync Gateway admin API; this needs new framework plumbing before it can run for real.

A `seq=0` compact test was considered but dropped entirely (not kept as a skip): the REST
handler 400s on `seq=0` before reaching the documented no-op code path, making the
documented no-op behavior unreachable through this REST-only suite. The existing
malformed-`seq` test already covers the real (400) behavior, so nothing is lost.

## test_get_history_of_doc_that_never_left_a_channel

A document that has always lived in the same channel has no channel history yet.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Get the document's channel history.
4. Check the history is empty and no error was raised.

## test_get_history_after_leaving_a_channel

Leaving a channel creates a history entry recording when.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Get the document's channel history.
5. Check the history has an entry for `ABC` containing exactly the sequence at which the document left it.

## test_get_history_shows_every_historical_seq_for_a_reused_channel_name

The doc-side history entry for a channel name is a flat list of every sequence at which
the document left that channel, not just the most recent one — a different wire shape
than the user-side `{start_seq, end_seq}` pair, so the TDK parser must not assume the two
endpoints share a shape.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to leave `ABC` for `OTHER`, then rejoin `ABC` then remove `ABC` a second time.
4. Get the document's channel history.
5. Check the history entry for `ABC` is a list containing both historical leave-sequences, and nothing else.

## test_compact_removes_entry_past_its_seq

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Compact the document's channel history for `ABC` with a sequence past the entry's sequence.
5. Check the compact response reports `ABC` as compacted.
6. Get the document's channel history again and check the entry for `ABC` is gone.

## test_compact_channel_not_in_history_is_noop

Compacting a channel name that was never in the document's history is not an error.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC` (it has never left any channel).
3. Compact the document's channel history for channel `OTHER`.
4. Check the response reports no channels compacted.
5. Repeat the same compact call and check the response is identical (idempotent).

## test_compact_nonexistent_docid_returns_404

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Compact the channel history of a document ID that was never created.
3. Check the request fails with 404.

## test_compact_malformed_seq_returns_400

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Attempt to compact `ABC` with a missing `seq` field; check the request fails with 400.
5. Attempt to compact `ABC` with a non-integer `seq` value; check the request fails with 400.

## test_get_and_compact_require_application_rbac_role

Skipped — needs new framework plumbing. Sync Gateway's admin API enforces
Couchbase-Server-RBAC roles (e.g. "Sync Gateway Application" vs "Sync Gateway Application
Read Only") independently of channel access, and the TDK currently always talks to the
admin API as a full admin. There is no existing helper to provision a restricted-role
caller, so `get`/`compact` RBAC enforcement (expect: a caller without the Application role
gets 403 on both; an Application Read Only caller gets 200 on GET and 403 on compact)
cannot be exercised yet.

## test_all_keyspace_forms_behave_identically

The bare-`db`, `db.collection`, and `db.scope.collection` keyspace forms must all resolve
to the same default collection and behave identically.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create three documents, each assigned to channel `ABC`, one per keyspace form to be tested.
3. Update each document to move it from `ABC` to `OTHER`.
4. Get each document's channel history using the same keyspace form used to update it.
5. Check all three histories contain an identical entry for `ABC`.
6. Compact all three using their own keyspace form and a sequence past the entry.
7. Check all three compacted successfully and all three histories are now empty.

## test_malformed_keyspace_returns_400

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Attempt to get the document's channel history using a keyspace with an empty segment (`db..collection`); check the request fails with 400.
4. Attempt to get the document's channel history using a keyspace with four segments; check the request fails with 400.

## test_compact_does_not_change_all_docs_or_changes_feed

Compaction only touches the history record; it must never be visible through the normal
document-listing endpoints.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Record the document's entry from `_all_docs` and from `_changes`.
5. Compact the document's channel history for `ABC` with a sequence past the entry.
6. Check the document's entry from `_all_docs` and from `_changes` is unchanged.

## test_legacy_pre_schema_document_has_no_history

A document that predates channel-history tracking (no `ChannelSet`/history fields at all)
must not error and must start accumulating fresh history normally after its next
mutation.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC` directly through Couchbase Server, bypassing Sync Gateway, so it has no channel-history metadata when Sync Gateway later imports it.
3. Wait until Sync Gateway has imported the document.
4. Get the document's channel history and check it is empty, with no error.
5. Update the document through Sync Gateway to move it from `ABC` to `OTHER`.
6. Get the document's channel history again and check it now has a fresh entry for `ABC`.

## test_compact_enormous_seq_never_removes_an_active_channel_membership

Critical safety invariant: no matter how large a compaction sequence is, a channel the
document is *currently* in (never left) must never be removed by compaction — only
already-ended history entries are eligible.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channels `ABC` and `OTHER`.
3. Update the document to leave `OTHER` (keeping `ABC`), creating one historical entry.
4. Compact the document's channel history for both `ABC` and `OTHER` with an enormous sequence number.
5. Check the response reports only `OTHER` as compacted, never `ABC`.
6. Get the document's channel history and check no entry for `ABC` exists (it was never in history) and the `OTHER` entry is gone.
7. Get the document directly from Sync Gateway and check it is still assigned to channel `ABC`.

## test_compact_stale_entry_leaves_live_regranted_same_channel_untouched

A document loses and then regains the *same* channel name before compaction runs.
Compacting the stale (already-ended) entry must leave the live, current membership in
that same channel completely untouched.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Make some seq-updates, then make the original document rejoin `ABC`.
4. Compact the document's channel history for `ABC` with a sequence past the historical (first) entry only.
5. Check the response reports `ABC` as compacted.
6. Get the document's channel history and check the entry for `ABC` is gone.
7. Get the document directly from Sync Gateway and check it is still currently assigned to channel `ABC`.

## test_compact_collection_isolation_for_same_docid_and_channel_name

The same document ID and channel name reused in two different collections are entirely
separate documents from Sync Gateway's point of view; compacting one must never affect
the other.

1. Configure a Sync Gateway database with two collections, each with a channel-membership sync function.
2. In each collection, create a document with the same ID and assign it to a channel with the same name.
3. In each collection, update the document to move it out of that channel.
4. Compact the channel history for that channel in the first collection only.
5. Check the first collection's history entry is gone.
6. Check the second collection's history entry for the same channel name is still present.

## test_concurrent_compact_racing_a_document_edit_surfaces_a_clean_conflict

Sync Gateway does not retry compaction on a CAS conflict, so a compact racing a real
edit to the same document must surface a clean, visible error rather than silently
dropping one of the two operations.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Concurrently: compact the document's channel history for `ABC`, and update the document's body again.
5. Check that at least one of the two concurrent operations either succeeded cleanly or failed with a surfaced conflict error — never both silently "succeeding" while only one actually applied.
6. Get the document's channel history and directly from Sync Gateway, and check the final state is internally consistent (either the compact result matches an empty/compacted history, or the edit is visible, but not a state that contradicts both responses).

## test_compact_response_is_a_flat_compacted_channels_list

The OpenAPI spec documents a nested-by-docid response shape for this endpoint, but the
real handler returns a flat list; the TDK parser must trust the implementation.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Create a document assigned to channel `ABC`.
3. Update the document to move it from `ABC` to `OTHER`.
4. Compact the document's channel history for `ABC` with a sequence past the entry.
5. Check the raw response body is exactly `{"compacted_channels": ["ABC"]}`, not nested under the document ID.

## test_compact_imports_a_not_yet_imported_document_first

A document written straight into the Couchbase Server bucket has no Sync Gateway metadata
yet. Compacting it must not error or silently skip it — Sync Gateway must import it first.

1. Configure a Sync Gateway database with a channel-membership sync function.
2. Write a document directly into the Couchbase Server bucket, bypassing Sync Gateway entirely, so it has no Sync Gateway metadata yet.
3. Compact the document's channel history without first waiting for it to be imported.
4. Check the compact call succeeded rather than erroring or silently skipping the document.
5. Get the document from Sync Gateway and check it was imported with a real revision, not left stale.
