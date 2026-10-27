# Replication Sanity Tests (Edge Server)

This document describes the sanity test for replication between Couchbase Server, Sync Gateway and Couchbase Lite Edge Server, verifying bidirectional create, update, and delete with a single document in each direction.

## test_replication_sanity

Test that documents replicate correctly in both directions: Sync Gateway → Edge Server (create on SG, update/delete via ES) and Edge Server → Sync Gateway (create on ES, update/delete via SG).

<br>

**Steps:**
1. Create a bucket `bucket-1` on Couchbase Server.
2. Add 10 documents to the bucket:
   * Document IDs: `doc_1` through `doc_10`
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
   * Get all documents from Sync Gateway `db-1`; verify count is 10
   * Wait for Edge Server replication idle again (timeout 5 seconds)
   * Get all documents from Edge Server `db`; verify count is 10
8. **PHASE 1: Sync Gateway cycle (document `doc_11`)**
   * Create document `doc_11` via Sync Gateway in `db-1` with `id`, `channels: ["public"]`, `timestamp`; verify create succeeds
   * Wait until document `doc_11` on Edge Server `db` has the body written; capture revision ID
   * Update document `doc_11` via Edge Server with body including `changed: "yes"` and the captured revision; verify update succeeds
   * Wait until document `doc_11` on Sync Gateway `db-1` has `changed: "yes"`; capture new revision ID
   * Delete document `doc_11` via Sync Gateway using the new revision ID
   * Wait until Edge Server `db` shows `doc_11` as deleted
9. **PHASE 2: Edge Server cycle (document `doc_12`)**
   * Create document `doc_12` via Edge Server in `db` with `id`, `channels: ["public"]`, `timestamp`; verify create succeeds
   * Wait until document `doc_12` on Sync Gateway `db-1` has the body written; capture revision ID
   * Update document `doc_12` via Sync Gateway with body including `changed: "yes"` and the captured revision; verify update succeeds
   * Wait until document `doc_12` on Edge Server `db` has `changed: "yes"`; capture new revision ID
   * Delete document `doc_12` via Edge Server using the new revision ID; verify delete response indicates success
   * Wait until Sync Gateway `db-1` shows `doc_12` as deleted
