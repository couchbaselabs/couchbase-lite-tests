# Logging Tests (Edge Server)

This document describes the tests for audit logging in Couchbase Lite Edge Server, verifying that audit events are recorded or omitted according to the database configuration (default, disabled, enabled).

## test_audit_logging

Test that audit logging respects the database configuration and records or omits expected events; when enabled, also verify CRUD operations generate audit entries.

**Parameters:**
- `audit_mode`: Audit configuration mode (`default`, `disabled`, or `enabled`)

<br>

**Steps:**
1. Create a bucket `bucket-1` on Couchbase Server.
2. Add 5 documents to the bucket:
   * Document IDs: `doc_1` through `doc_5`
   * Each document: `id`, `channels: ["public"]`, `timestamp`
3. Create a database `db-1` on Sync Gateway:
   * bucket: `bucket-1`
   * sync function: `function(doc){channel(doc.channels);}`
   * num_index_replicas: 0
4. Add role `stdrole` and user `sync_gateway` to Sync Gateway with collection access `_default._default: ["public"]`.
5. Create database `db` on Edge Server with audit config per `audit_mode`:
   * config: `test_e2e_audit.json` with replication source set to Sync Gateway URL for `db-1`
   * **default:** leave audit config unchanged
   * **disabled:** set `logging.audit.disable: "*"` and remove `enable` if present
   * **enabled:** set `logging.audit.enable: "*"` and remove `disable` if present
6. Wait for Edge Server replication to become idle.
7. Verify document counts:
   * Get all documents from Sync Gateway `db-1`; verify count is 5
   * Get all documents from Edge Server `db`; verify count is 5
8. For each audit event in the assertion list for `audit_mode`, call Edge Server `check_log(event_id)` and verify presence or absence of entries:
   * **default:** event 57344 (server started) and 57355 (inter-server replication start) must have at least one entry; 57345, 57346, 57356, 57358, 57359, 57360, 57361 must have no entries
   * **disabled:** events 57344, 57345, 57346, 57355, 57356 must have no entries
   * **enabled:** events 57344, 57346, 57355 must have at least one entry; 57345, 57356, 57358, 57359, 57360, 57361 (before CRUD) must have no entries
9. If `audit_mode` is `enabled`, perform CRUD on a single document via Edge Server:
   * Create document `doc_6` with `id`, `channels: ["public"]`, `timestamp`; verify create succeeds
   * Get document `doc_6` from Edge Server; verify it exists; capture revision ID
   * Update document `doc_6` with body including `changed: "yes"` and the captured revision; verify update succeeds; capture new revision ID
   * Delete document `doc_6` using the new revision ID; verify delete succeeds
10. If `audit_mode` is `enabled`, verify CRUD audit entries:
    * For event IDs 57358 (create document), 57359 (read document), 57360 (update document), 57361 (delete document), call `check_log(event_id)` and verify at least one log entry exists for each
