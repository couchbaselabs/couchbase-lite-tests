# System Tests (Edge Server)

This document describes the long-running system tests for Couchbase Lite Edge Server replication and resilience, including a stability run and a chaos run with periodic Edge Server kill/restart.

## test_system_one_client_l

Test that create, update, and delete operations replicate correctly between Sync Gateway and Edge Server over an extended period (up to 6 hours), with cycle (sync_gateway or edge_server) and operations (create, create_update_delete, or create_delete) randomly chosen per document.

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

## test_system_multi_client_concurrent

Test that 4 concurrent async client coroutines can independently perform create, update, and delete operations via both Sync Gateway and Edge Server over an extended period (up to 6 hours) without interference, and that document counts reconcile correctly at the end.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` (bucket-1 with 10 docs, SG db `db-1`, ES db `db` with replication, verify 10 docs on both).
2. Define `client_worker(client_id)` as an async coroutine. Each worker initialises its own `doc_counter` at 1 and loops until 6 hours have elapsed.
3. For each iteration in `client_worker`: set `doc_id` to `c{client_id}_doc_{doc_counter}`; randomly choose `cycle` and `operations`.
4. **If cycle is `sync_gateway`:**
   * Create document `doc_id` via Sync Gateway in `db-1` with standard body; verify create succeeds
   * Wait a random 1–5 seconds (`asyncio.sleep`, non-blocking)
   * Get document `doc_id` from Edge Server `db`; verify it exists, `id` matches, and `_rev` is present; capture revision ID
   * If `operations` includes update: update document via Sync Gateway with body including `changed: "yes"` and captured revision; verify update succeeds; get document from Edge Server and verify revision changed; set captured revision to new value
   * If `operations` includes delete: delete document via Edge Server using captured revision; verify delete succeeds; verify get from Edge Server raises `CblEdgeServerBadResponseError`; wait 2 seconds; verify get from Sync Gateway raises `CblSyncGatewayBadResponseError`
5. **If cycle is `edge_server`:**
   * Create document `doc_id` via Edge Server in `db` with standard body; verify create succeeds
   * Wait 5 seconds (`asyncio.sleep`, non-blocking)
   * Get document `doc_id` from Sync Gateway `db-1`; verify it exists, `id` matches, and `_rev` is present; capture revision ID
   * If `operations` includes update: update document via Edge Server with body including `changed: "yes"` and captured revision; verify update succeeds; get document from Sync Gateway and verify revision changed; set captured revision to new value
   * If `operations` includes delete: delete document via Sync Gateway using captured revision; wait 2 seconds; verify get from Edge Server raises `CblEdgeServerBadResponseError`
6. Increment `doc_counter`; repeat from step 3.
7. Launch all 4 `client_worker` coroutines concurrently with `asyncio.gather`; all run simultaneously for the full 6-hour window.
8. **Final reconciliation:** Get all documents from Sync Gateway and Edge Server; verify counts are equal.

## test_system_multi_client_chaos

Test that 4 concurrent async client coroutines continue to operate correctly while a dedicated `chaos_controller` coroutine kills and restarts the Edge Server at random intervals (every 5–20 minutes, with a 1-minute down window), verifying document count consistency after each restart and at the end of the 6-hour run.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` (bucket-1 with 10 docs, SG db `db-1`, ES db `db` with replication, verify 10 docs on both). Initialise `shared = {"edge_server_down": False}` and `recent_docs = []`.
2. Define `chaos_controller()` as an async coroutine that loops until 6 hours have elapsed:
   * Wait a random 5–20 minutes (`asyncio.sleep(300–1200)`, non-blocking)
   * If the 6-hour window has expired, exit the loop
   * Kill the Edge Server; set `shared["edge_server_down"] = True`; wait 10 seconds
   * Wait an additional 60 seconds (1-minute down window)
   * Restart the Edge Server; wait 10 seconds; set `shared["edge_server_down"] = False`
   * Get all documents from Sync Gateway and Edge Server; verify counts are equal
3. Define `fire_read_burst(doc_id)` as an async helper: if `shared["edge_server_down"]` is `True`, return immediately; otherwise issue `NUM_CLIENTS` concurrent `get_document` calls for `doc_id` against Edge Server using `asyncio.gather(return_exceptions=True)`; for each non-exception result assert the document is not None.
4. Define `client_worker(client_id)` as an async coroutine. Each worker initialises `doc_counter` at 1 and loops until 6 hours have elapsed.
5. For each iteration in `client_worker`: set `doc_id` to `cc{client_id}_doc_{doc_counter}`; randomly choose `cycle` and `operations`.
6. **If cycle is `sync_gateway`:**
   * Create document `doc_id` via Sync Gateway in `db-1`; verify create succeeds; wait 1–5 seconds
   * If not `edge_server_down`: get document from Edge Server; verify it exists with matching `id` and `_rev`; append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`; capture `rev_id` from created doc
   * If `operations` includes update: update via Sync Gateway with `changed: "yes"` and `rev_id`; verify update succeeds; if not `edge_server_down`, get document from Edge Server and verify revision changed; update `rev_id` from updated doc
   * If `operations` includes delete and not `edge_server_down`: delete via Edge Server; verify delete response has `ok: true`; verify get from Edge Server raises `CblEdgeServerBadResponseError`; wait 2 seconds; verify get from Sync Gateway raises `CblSyncGatewayBadResponseError`
7. **If cycle is `edge_server` and not `edge_server_down`:**
   * Create document `doc_id` via Edge Server in `db`; verify create succeeds; wait 5 seconds
   * Get document from Sync Gateway; verify it exists with matching `id` and `_rev`; capture `rev_id`; append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`
   * If `operations` includes update: update via Edge Server with `changed: "yes"` and `rev_id`; verify update succeeds; get from Sync Gateway and verify revision changed; update `rev_id`
   * If `operations` includes delete: delete via Sync Gateway using `rev_id`; wait 2 seconds; verify get from Edge Server raises `CblEdgeServerBadResponseError`
8. Increment `doc_counter`; repeat from step 5.
9. Launch all 4 `client_worker` coroutines and `chaos_controller` concurrently with `asyncio.gather` (5 total tasks); all run simultaneously for the full 6-hour window.
10. **Final reconciliation:** Get all documents from Sync Gateway and Edge Server; verify counts are equal.
