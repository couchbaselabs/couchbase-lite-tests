# System Tests (Edge Server)

This document describes the long-running system tests for Couchbase Lite Edge Server replication and resilience. Tests cover both single-client and multi-client (4 concurrent async clients) scenarios, each in two modes: a stability run with steady CRUD traffic, and a chaos run that periodically kills and restarts the Edge Server.

> Each *italicised* bullet phrase is the exact string passed to `mark_test_step` in the code, in the same order. Trailing text after the em-dash describes what happens at that step.

## test_system_one_client_l

Test that create, update, and delete operations replicate correctly between Sync Gateway and Edge Server over an extended period (up to 6 hours), with cycle (sync_gateway or edge_server) and operations (create, create_update_delete, or create_delete) randomly chosen per document.

**Steps:**
1. **Setup:**
   * *Creating a bucket on server.* — create `bucket-1` on Couchbase Server
   * *Adding 10 documents to bucket.* — upsert `doc_1` through `doc_10` (each with `id`, `channels: ["public"]`, `timestamp`)
   * *Creating a database on Sync Gateway.* — create `db-1` with bucket `bucket-1`, sync function `function(doc){channel(doc.channels);}`, `num_index_replicas: 0`
   * *Adding role and user to Sync Gateway.* — add role `stdrole` and user `sync_gateway` with collection access `_default._default: ["public"]`
   * *Creating a database on Edge Server with replication to Sync Gateway.* — create `db` from `test_e2e_empty_database.json` with replication source set to SG `db-1`; wait for replication idle
   * *Verifying that Sync Gateway has 10 documents.*
   * *Verifying that Edge Server has 10 documents.*
2. Set `doc_counter = 11`; run loop until 6 hours have elapsed.
3. For each iteration: set `doc_id = doc_{doc_counter}`; randomly pick `cycle` from `["sync_gateway", "edge_server"]` and `operations` from `["create", "create_update_delete", "create_delete"]`.
   * *Cycle: doc {doc_id} via {cycle}, operations: {operations}*
4. **If cycle is `sync_gateway`:**
   * *Creating {doc_id} on Sync Gateway.* — POST to `db-1` with standard body; verify create succeeds; sleep 1–5s for replication
   * *Verifying {doc_id} on Edge Server.* — GET from `db`; assert exists, `id` matches, `_rev` present; capture revision
   * If `operations` includes update:
     * *Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and captured revision; verify update succeeds
     * *Verifying {doc_id} update on Edge Server.* — GET from `db`; assert revision differs; update captured revision
   * If `operations` includes delete:
     * *Deleting {doc_id} on Edge Server.* — DELETE using captured revision; assert response `ok: true`; assert subsequent GET on Edge Server raises `CblEdgeServerBadResponseError`; sleep 2s
     * *Verifying {doc_id} deleted on Sync Gateway.* — assert GET from `db-1` raises `CblSyncGatewayBadResponseError`
5. **If cycle is `edge_server`:**
   * *Creating {doc_id} on Edge Server.* — PUT to `db` with standard body; verify create succeeds; sleep 5s for replication
   * *Verifying {doc_id} on Sync Gateway.* — GET from `db-1`; assert exists, `id` matches, `_rev` present; capture revision
   * If `operations` includes update:
     * *Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and captured revision; verify update succeeds
     * *Verifying {doc_id} update on Sync Gateway.* — GET from `db-1`; assert revision differs; update captured revision
   * If `operations` includes delete:
     * *Deleting {doc_id} on Sync Gateway.* — DELETE using captured revision; sleep 2s
     * *Verifying {doc_id} deleted on Edge Server.* — assert GET from `db` raises `CblEdgeServerBadResponseError`
6. Increment `doc_counter`; repeat from step 3.

## test_system_one_client_chaos

Test that replication and document counts remain consistent when the Edge Server is periodically killed and restarted (40% chance per iteration, 1-minute down window), with random create/update/delete operations over an extended period.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Initialise `edge_server_down = False` and chaos window end (far future). Set `doc_counter = 11`.
2. Run loop until 6 hours have elapsed.
3. **Chaos recovery:** If current time is past the chaos window end:
   * *Restarting Edge Server after chaos window.* — start ES; sleep 10s; set `edge_server_down = False`
   * *Verifying doc counts match after Edge Server restart.* — assert SG and ES doc counts are equal
4. Set `doc_id = doc_{doc_counter}`; randomly pick `cycle` and `operations` as in `test_system_one_client_l`.
   * *Cycle: doc {doc_id} via {cycle}, operations: {operations}*
5. **Chaos trigger:** If `not edge_server_down` and `random.random() <= 0.4`:
   * *Triggering chaos: killing Edge Server.* — kill ES; set chaos window end to now + 1 minute; sleep 10s; set `edge_server_down = True`
6. **If cycle is `sync_gateway`:**
   * *Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds; sleep 1–5s
   * If `not edge_server_down`:
     * *Verifying {doc_id} on Edge Server.* — GET from `db`; assert exists, `id` matches, `_rev` present
   * Capture `rev_id` from created doc.
   * If `operations` includes update:
     * *Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * If `not edge_server_down`:
       * *Verifying {doc_id} update on Edge Server.* — GET from `db`; assert revision differs
     * Update `rev_id` from updated doc.
   * If `operations` includes delete and `not edge_server_down`:
     * *Deleting {doc_id} on Edge Server.* — DELETE using `rev_id`; assert response `ok: true`; assert subsequent GET raises `CblEdgeServerBadResponseError`; sleep 2s
     * *Verifying {doc_id} deleted on Sync Gateway.* — assert GET from `db-1` raises `CblSyncGatewayBadResponseError`
7. **If cycle is `edge_server` and `not edge_server_down`:**
   * *Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds
   * *Verifying {doc_id} on Sync Gateway.* — GET from `db-1`; assert exists, `id` matches, `_rev` present; capture `rev_id`
   * If `operations` includes update:
     * *Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * *Verifying {doc_id} update on Sync Gateway.* — GET from `db-1`; assert revision differs; update `rev_id`
   * If `operations` includes delete:
     * *Deleting {doc_id} on Sync Gateway.* — DELETE using `rev_id`; sleep 2s
     * *Verifying {doc_id} deleted on Edge Server.* — assert GET from `db` raises `CblEdgeServerBadResponseError`
8. Increment `doc_counter`; repeat from step 2.

## test_system_multi_client_concurrent

Test that 4 concurrent async client coroutines can independently perform create, update, and delete operations via both Sync Gateway and Edge Server over an extended period (up to 6 hours) without interference, and that document counts reconcile correctly at the end.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Set `NUM_CLIENTS = 4`.
2. Define `client_worker(client_id)` as an async coroutine. Each worker initialises `doc_counter = 1` and loops until 6 hours have elapsed.
3. For each iteration in `client_worker`: set `doc_id = c{client_id}_doc_{doc_counter}`; randomly pick `cycle` and `operations`.
   * *[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}*
4. **If cycle is `sync_gateway`:**
   * *[Client {client_id}] Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds; `await asyncio.sleep(1–5)` for replication
   * *[Client {client_id}] Verifying {doc_id} on Edge Server.* — GET from `db`; assert exists, `id` matches, `_rev` present; capture revision
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and revision; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Edge Server.* — GET from `db`; assert revision differs; update revision
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Edge Server.* — DELETE using revision; assert response `ok: true`
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server and Sync Gateway.* — assert GET from `db` raises `CblEdgeServerBadResponseError`; sleep 2s; assert GET from `db-1` raises `CblSyncGatewayBadResponseError`
5. **If cycle is `edge_server`:**
   * *[Client {client_id}] Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds; `await asyncio.sleep(5)` for replication
   * *[Client {client_id}] Verifying {doc_id} on Sync Gateway.* — GET from `db-1`; assert exists, `id` matches, `_rev` present; capture revision
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and revision; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Sync Gateway.* — GET from `db-1`; assert revision differs; update revision
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Sync Gateway.* — DELETE using revision; sleep 2s
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server.* — assert GET from `db` raises `CblEdgeServerBadResponseError`
6. Increment `doc_counter`; repeat from step 3.
7. Launch all 4 `client_worker` coroutines concurrently with `asyncio.gather`; all run simultaneously for the full 6-hour window.
8. **Final reconciliation:**
   * *Verifying final doc counts match between SG and Edge Server.* — assert SG and ES doc counts are equal

## test_system_multi_client_chaos

Test that 4 concurrent async client coroutines continue to operate correctly while a dedicated `chaos_controller` coroutine kills and restarts the Edge Server at random intervals (every 5–20 minutes, with a 1-minute down window), verifying document count consistency after each restart and at the end of the 6-hour run.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Set `NUM_CLIENTS = 4`. Initialise `shared = {"edge_server_down": False}` and `recent_docs = []`.
2. Define `chaos_controller()` as an async coroutine that loops until 6 hours have elapsed. Each iteration:
   * `await asyncio.sleep(random.uniform(300, 1200))` — random quiet period of 5–20 minutes
   * Exit if 6-hour window has expired
   * *Triggering chaos: killing Edge Server.* — kill ES; set `shared["edge_server_down"] = True`; `await asyncio.sleep(10)`
   * `await asyncio.sleep(60)` — keep ES down for ~1 minute
   * *Restarting Edge Server after chaos window.* — start ES; `await asyncio.sleep(10)`; set `shared["edge_server_down"] = False`
   * *Verifying doc counts match after Edge Server restart.* — assert SG and ES doc counts are equal
3. Define `fire_read_burst(doc_id)` as an async helper. If `shared["edge_server_down"]`, return immediately. Otherwise:
   * *Firing {NUM_CLIENTS} concurrent reads of {doc_id} on Edge Server.* — issue `NUM_CLIENTS` concurrent `get_document` calls via `asyncio.gather(return_exceptions=True)`; for each non-exception result assert it is not None
4. Define `client_worker(client_id)` as an async coroutine. Each worker initialises `doc_counter = 1` and loops until 6 hours have elapsed.
5. For each iteration in `client_worker`: set `doc_id = cc{client_id}_doc_{doc_counter}`; randomly pick `cycle` and `operations`.
   * *[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}*
6. **If cycle is `sync_gateway`:**
   * *[Client {client_id}] Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds; `await asyncio.sleep(1–5)`
   * If `not shared["edge_server_down"]`:
     * *[Client {client_id}] Verifying {doc_id} on Edge Server.* — GET from `db`; assert exists, `id` matches, `_rev` present
     * Append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`
   * Capture `rev_id` from created doc.
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * If `not shared["edge_server_down"]`:
       * *[Client {client_id}] Verifying {doc_id} update on Edge Server.* — GET from `db`; assert revision differs
     * Update `rev_id` from updated doc.
   * If `operations` includes delete and `not shared["edge_server_down"]`:
     * *[Client {client_id}] Deleting {doc_id} on Edge Server.* — DELETE using `rev_id`; assert response `ok: true`; assert subsequent GET raises `CblEdgeServerBadResponseError`; `await asyncio.sleep(2)`
     * *[Client {client_id}] Verifying {doc_id} deleted on Sync Gateway.* — assert GET from `db-1` raises `CblSyncGatewayBadResponseError`
7. **If cycle is `edge_server` and `not shared["edge_server_down"]`:**
   * *[Client {client_id}] Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds; `await asyncio.sleep(5)`
   * *[Client {client_id}] Verifying {doc_id} on Sync Gateway.* — GET from `db-1`; assert exists, `id` matches, `_rev` present; capture `rev_id`
   * Append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Sync Gateway.* — GET from `db-1`; assert revision differs; update `rev_id`
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Sync Gateway.* — DELETE using `rev_id`; `await asyncio.sleep(2)`
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server.* — assert GET from `db` raises `CblEdgeServerBadResponseError`
8. Increment `doc_counter`; repeat from step 5.
9. Launch all 4 `client_worker` coroutines and `chaos_controller` concurrently with `asyncio.gather` (5 total tasks); all run for the full 6-hour window.
10. **Final reconciliation:**
    * *Verifying final doc counts match between SG and Edge Server.* — assert SG and ES doc counts are equal
