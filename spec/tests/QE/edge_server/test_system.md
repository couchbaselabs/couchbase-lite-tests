# System Tests (Edge Server)

This document describes the long-running system tests for Couchbase Lite Edge Server replication and resilience, including a stability run and a chaos run with periodic Edge Server kill/restart.

## test_system_one_client_l

Test that create, update, and delete operations replicate correctly between Sync Gateway and Edge Server over an extended period (up to 6 hours), with cycle (sync_gateway or edge_server) and operations (create, create_update_delete, or create_delete) randomly chosen per document.

**Parameters:**
- Document counter starts at 11 and increments each iteration
- `cycle`: Random choice from `["sync_gateway", "edge_server"]`
- `operations`: Random choice from `["create", "create_update_delete", "create_delete"]`

<br>

**Steps:**
1. **Setup**
   * Create a bucket `bucket-1` on Couchbase Server
   * Add 10 documents `doc_1` through `doc_10` to the bucket (each with `id`, `channels: ["public"]`, `timestamp`)
   * Create a database `db-1` on Sync Gateway with bucket `bucket-1`, sync function `function(doc){channel(doc.channels);}`, num_index_replicas: 0
   * Add role `stdrole` and user `sync_gateway` to Sync Gateway with collection access `_default._default: ["public"]`
   * Create database `db` on Edge Server using config `test_e2e_empty_database.json` with replication source set to Sync Gateway URL for `db-1`
   * Wait for Edge Server replication to become idle
   * Get all documents from Sync Gateway `db-1`; verify count is 10
   * Get all documents from Edge Server `db`; verify count is 10
2. Set document counter to 11; run loop until 6 hours have elapsed (or test stop).
3. For each iteration: set `doc_id` to `doc_{counter}`; randomly choose `cycle` and `operations` as above.
4. **If cycle is `sync_gateway`:**
   * Create document `doc_id` via Sync Gateway in `db-1` with standard body; verify create succeeds
   * Wait a random 1–5 seconds
   * Get document `doc_id` from Edge Server `db`; verify it exists, `id` matches, and `_rev` is present; capture revision ID
   * If `operations` includes update: update document via Sync Gateway with body including `changed: "yes"` and captured revision; verify update succeeds; get document from Edge Server again and verify revision ID changed; set captured revision to new value
   * If `operations` includes delete: delete document via Edge Server using captured revision; verify delete succeeds; get document from Edge Server and verify request fails; wait 2 seconds; get document from Sync Gateway and verify request fails
5. **If cycle is `edge_server`:**
   * Create document `doc_id` via Edge Server in `db` with standard body; verify create succeeds
   * Wait 5 seconds
   * Get document `doc_id` from Sync Gateway `db-1`; verify it exists, `id` matches, and `_rev` is present; capture revision ID
   * If `operations` includes update: update document via Edge Server with body including `changed: "yes"` and captured revision; verify update succeeds; get document from Sync Gateway and verify revision ID changed; set captured revision to new value
   * If `operations` includes delete: delete document via Sync Gateway using captured revision; wait 2 seconds; get document from Edge Server and verify request fails
6. Increment document counter; repeat from step 3.

## test_system_one_client_chaos

Test that replication and document counts remain consistent when the Edge Server is periodically killed and restarted (40% chance per iteration, 1-minute down window), with random create/update/delete operations over an extended period.

**Parameters:**
- Same as test_system_one_client_l for document counter, `cycle`, and `operations`
- Chaos: when Edge Server is up, with probability 0.4 kill Edge Server and set down window to 1 minute; after window expires, restart Edge Server and verify document counts match between SG and ES

<br>

**Steps:**
1. **Setup:** Same as test_system_one_client_l (bucket, 10 docs, SG db `db-1`, ES db `db`, verify 10 docs on both). Initialize `edge_server_down = false` and chaos window end (e.g. far future). Set document counter to 11.
2. Run loop until 6 hours have elapsed (or test stop).
3. **Chaos recovery:** If current time is past the chaos window end:
   * Start the Edge Server; wait 10 seconds; set `edge_server_down = false`
   * Get document counts from Sync Gateway and Edge Server; verify they are equal
4. Set `doc_id` to `doc_{counter}`; randomly choose `cycle` and `operations` as in test_system_one_client_l.
5. **Chaos trigger:** If Edge Server is up and random value ≤ 0.4:
   * Kill the Edge Server; set chaos window end to current time + 1 minute; wait 10 seconds; set `edge_server_down = true`
6. **If cycle is `sync_gateway`:**
   * Create document `doc_id` via Sync Gateway in `db-1`; verify create succeeds; wait 1–5 seconds
   * If not `edge_server_down`: get document from Edge Server `db` and verify it exists with matching `id` and present `_rev`; capture revision from created doc for update/delete
   * If `operations` includes update: update via Sync Gateway with `changed: "yes"` and revision; verify update succeeds; if not `edge_server_down`, get document from Edge Server and verify revision changed; set revision to updated doc’s revision
   * If `operations` includes delete and not `edge_server_down`: delete via Edge Server; verify success; verify get from Edge Server fails; wait 2 seconds; verify get from Sync Gateway fails
7. **If cycle is `edge_server` and not `edge_server_down`:**
   * Create document `doc_id` via Edge Server in `db`; verify create succeeds; get from Sync Gateway and verify exists with matching `id` and `_rev`; capture revision
   * If `operations` includes update: update via Edge Server with `changed: "yes"` and revision; verify update succeeds; get from Sync Gateway and verify revision changed; set revision to new value
   * If `operations` includes delete: delete via Sync Gateway using revision; wait 2 seconds; verify get from Edge Server fails
8. Increment document counter; repeat from step 2.
