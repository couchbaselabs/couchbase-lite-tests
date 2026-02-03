# Changes Feed Tests (Edge Server)

This document describes the tests for the changes feed API in Couchbase Lite Edge Server, verifying that longpoll, active_only, since, and doc_ids filtering behave correctly.

## test_changes_feed_longpoll

Test that the longpoll changes feed reflects document creates, deletes (with active_only behaviour), since-based incremental changes, and doc_ids filter.

<br>

**Steps:**
1. Create a bucket `bucket-1` on Couchbase Server.
2. Add 5 documents to the bucket:
   * Document IDs: `doc_1`, `doc_2`, `doc_3`, `doc_4`, `doc_5`
   * Each document: `id`, `channels: ["public"]`, `timestamp`
3. Create a database `db-1` on Sync Gateway:
   * bucket: `bucket-1`
   * sync function: `function(doc){channel(doc.channels);}`
   * num_index_replicas: 0
4. Add role `stdrole` and user `sync_gateway` to Sync Gateway with collection access `_default._default: ["public"]`.
5. Create database `db` on Edge Server:
   * config: `test_e2e_empty_database.json` with replication source set to Sync Gateway URL for `db-1`
6. Wait for Edge Server replication to become idle.
7. Verify initial sync:
   * Get all documents from Sync Gateway `db-1`; verify count is 5
   * Get all documents from Edge Server `db`; verify count is 5
8. **Changes feed and delete:**
   * Call Edge Server changes feed for `db` with `feed=longpoll`; capture `last_seq`
   * From the changes results, find the revision ID for document `doc_5`
   * Delete document `doc_5` on Edge Server using the captured revision ID; verify delete succeeds
9. **Deleted document visibility:**
   * Call changes feed with `feed=longpoll` (no `active_only`); verify the last result has `deleted: true`; record the number of results
   * Call changes feed with `feed=longpoll` and `active_only=true`; verify the number of results is less than the previous count (deleted document excluded)
   * Capture the new `last_seq` from the active_only changes response
10. **Incremental changes (since):**
    * Create 5 new documents on Edge Server: `doc_11`, `doc_12`, `doc_13`, `doc_14`, `doc_15` (each with `id`, `channels: ["public"]`, `timestamp`); verify each put succeeds
    * Call changes feed with `feed=longpoll`, `active_only=true`, and `since` set to the captured `last_seq`; verify exactly 5 results are returned
11. **Filter (doc_ids):**
    * Call changes feed with `feed=longpoll`, `filter_type=doc_ids`, and `doc_ids=["doc_10", "doc_9"]`; verify exactly 2 results are returned
