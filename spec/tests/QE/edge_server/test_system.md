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
   * *Creating a database on Edge Server with replication to Sync Gateway.* — create `db` from `test_e2e_empty_database.json` with replication source set to SG `db-1`
   * *Verifying that Sync Gateway has 10 documents.* — wait until SG has imported 10 documents
   * *Verifying that Edge Server has 10 documents.* — wait until ES has those 10 documents
2. Set `doc_counter = 11`; run loop until 6 hours have elapsed.
3. For each iteration: set `doc_id = doc_{doc_counter}`; randomly pick `cycle` from `["sync_gateway", "edge_server"]` and `operations` from `["create", "create_update_delete", "create_delete"]`.
   * *Cycle: doc {doc_id} via {cycle}, operations: {operations}*
4. **If cycle is `sync_gateway`:**
   * *Creating {doc_id} on Sync Gateway.* — POST to `db-1` with standard body; verify create succeeds
   * *Verifying {doc_id} on Edge Server.* — wait until the doc on `db` has the body written; capture revision
   * If `operations` includes update:
     * *Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and captured revision; verify update succeeds
     * *Verifying {doc_id} update on Edge Server.* — wait until the doc on `db` has `changed: "yes"`; update captured revision
   * If `operations` includes delete:
     * *Deleting {doc_id} on Edge Server.* — DELETE using captured revision; assert response `ok: true`; assert subsequent GET on Edge Server raises `CblEdgeServerBadResponseError`
     * *Verifying {doc_id} deleted on Sync Gateway.* — wait until `db-1` shows it as deleted
5. **If cycle is `edge_server`:**
   * *Creating {doc_id} on Edge Server.* — PUT to `db` with standard body; verify create succeeds
   * *Verifying {doc_id} on Sync Gateway.* — wait until the doc on `db-1` has the body written; capture revision
   * If `operations` includes update:
     * *Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and captured revision; verify update succeeds
     * *Verifying {doc_id} update on Sync Gateway.* — wait until the doc on `db-1` has `changed: "yes"`; update captured revision
   * If `operations` includes delete:
     * *Deleting {doc_id} on Sync Gateway.* — DELETE using captured revision
     * *Verifying {doc_id} deleted on Edge Server.* — wait until `db` shows it as deleted
6. Increment `doc_counter`; repeat from step 3.

## test_system_one_client_chaos

Test that replication and document counts remain consistent when the Edge Server is periodically killed and restarted (40% chance per iteration, 1-minute down window), with random create/update/delete operations over an extended period.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Initialise `edge_server_down = False` and chaos window end (far future). Set `doc_counter = 11`.
2. Run loop until 6 hours have elapsed.
3. **Chaos recovery:** If `edge_server_down` and current time is past the chaos window end:
   * *Restarting Edge Server after chaos window.* — start ES; set `edge_server_down = False`
   * *Verifying doc counts match after Edge Server restart.* — wait until ES has every document SG has; assert SG and ES doc counts are equal
4. Set `doc_id = doc_{doc_counter}`; randomly pick `cycle` and `operations` as in `test_system_one_client_l`.
   * *Cycle: doc {doc_id} via {cycle}, operations: {operations}*
5. **Chaos trigger:** If `not edge_server_down` and `random.random() <= 0.4`:
   * *Triggering chaos: killing Edge Server.* — kill ES; set chaos window end to now + 1 minute; set `edge_server_down = True`
6. **If cycle is `sync_gateway`:**
   * *Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds
   * If `not edge_server_down`:
     * *Verifying {doc_id} on Edge Server.* — wait until the doc on `db` has the body written
   * Capture `rev_id` from created doc.
   * If `operations` includes update:
     * *Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * If `not edge_server_down`:
       * *Verifying {doc_id} update on Edge Server.* — wait until the doc on `db` has `changed: "yes"`
     * Update `rev_id` from updated doc.
   * If `operations` includes delete and `not edge_server_down`:
     * *Deleting {doc_id} on Edge Server.* — DELETE using `rev_id`; assert response `ok: true`; assert subsequent GET raises `CblEdgeServerBadResponseError`
     * *Verifying {doc_id} deleted on Sync Gateway.* — wait until `db-1` shows it as deleted
7. **If cycle is `edge_server` and `not edge_server_down`:**
   * *Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds
   * *Verifying {doc_id} on Sync Gateway.* — wait until the doc on `db-1` has the body written; capture `rev_id`
   * If `operations` includes update:
     * *Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * *Verifying {doc_id} update on Sync Gateway.* — wait until the doc on `db-1` has `changed: "yes"`; update `rev_id`
   * If `operations` includes delete:
     * *Deleting {doc_id} on Sync Gateway.* — DELETE using `rev_id`
     * *Verifying {doc_id} deleted on Edge Server.* — wait until `db` shows it as deleted
8. Increment `doc_counter`; repeat from step 2.

## test_system_multi_client_concurrent

Test that 4 concurrent async client coroutines can independently perform create, update, and delete operations via both Sync Gateway and Edge Server over an extended period (up to 6 hours) without interference, and that document counts reconcile correctly at the end.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Set `NUM_CLIENTS = 4`.
2. Define `client_worker(client_id)` as an async coroutine. Each worker initialises `doc_counter = 1` and loops until 6 hours have elapsed.
3. For each iteration in `client_worker`: set `doc_id = c{client_id}_doc_{doc_counter}`; randomly pick `cycle` and `operations`.
   * *[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}*
4. **If cycle is `sync_gateway`:**
   * *[Client {client_id}] Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds
   * *[Client {client_id}] Verifying {doc_id} on Edge Server.* — wait until the doc on `db` has the body written; capture revision
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and revision; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Edge Server.* — wait until the doc on `db` has `changed: "yes"`; update revision
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Edge Server.* — DELETE using revision; assert response `ok: true`
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server and Sync Gateway.* — assert GET from `db` raises `CblEdgeServerBadResponseError`; wait until `db-1` shows it as deleted
5. **If cycle is `edge_server`:**
   * *[Client {client_id}] Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds
   * *[Client {client_id}] Verifying {doc_id} on Sync Gateway.* — wait until the doc on `db-1` has the body written; capture revision
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and revision; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Sync Gateway.* — wait until the doc on `db-1` has `changed: "yes"`; update revision
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Sync Gateway.* — DELETE using revision
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server.* — wait until `db` shows it as deleted
6. Increment `doc_counter`; repeat from step 3.
7. Launch all 4 `client_worker` coroutines concurrently in an `asyncio.TaskGroup`; all run simultaneously for the full 6-hour window, and a failure in one cancels the rest.
8. **Final reconciliation:**
   * *Verifying final doc counts match between SG and Edge Server.* — assert SG and ES doc counts are equal

## test_system_multi_client_chaos

Test that 4 concurrent async client coroutines continue to operate correctly while a dedicated `chaos_controller` coroutine kills and restarts the Edge Server at random intervals (every 5–20 minutes, with a 1-minute down window), verifying document count consistency after each restart and at the end of the 6-hour run.

**Steps:**
1. **Setup:** Same as `test_system_one_client_l` step 1. Set `NUM_CLIENTS = 4`. Initialise `shared = {"edge_server_down": False, "outages": 0, "paused": False, "active": 0}`, an `asyncio.Condition` that guards `paused` and `active`, `recent_docs = []`, and `interrupted = {}`.
2. Define `chaos_controller()` as an async coroutine that loops until 6 hours have elapsed. Each iteration:
   * `await asyncio.sleep(random.uniform(300, 1200))` — random quiet period of 5–20 minutes
   * Exit if 6-hour window has expired
   * *Triggering chaos: killing Edge Server.* — set `shared["edge_server_down"] = True` and increment `shared["outages"]`, then kill ES at once. Workers are not paused, so ES can go down partway through a worker's step.
   * `await asyncio.sleep(60)` — keep ES down for ~1 minute
   * *Restarting Edge Server after chaos window.* — start ES; set `shared["edge_server_down"] = False`
   * Set `paused` so that no worker starts a new cycle, and wait until `active` (the number of cycles in progress) is 0. Then *Verifying doc counts match after Edge Server restart.* — poll (up to 60s) until SG and ES doc counts are equal. For each doc in `interrupted`, *Revalidating {doc_id}, interrupted by the outage.* — poll (up to 60s) until SG and ES hold the same body, or both lack the doc, and that state is one the cycle wrote. Clear `interrupted`, then clear `paused` to resume the workers.
3. Define `fire_read_burst(doc_id)` as an async helper. If `shared["edge_server_down"]`, return immediately. Otherwise:
   * *Firing {NUM_CLIENTS} concurrent reads of {doc_id} on Edge Server.* — issue `NUM_CLIENTS` concurrent `get_document` calls via `asyncio.gather(return_exceptions=True)`; for each non-exception result assert it is not None
4. Define `client_worker(client_id)` as an async coroutine. Each worker initialises `doc_counter = 1` and loops until 6 hours have elapsed.
5. For each iteration in `client_worker`: wait until `paused` is clear, then increment `active` until the cycle ends. Set `doc_id = cc{client_id}_doc_{doc_counter}`; randomly pick `cycle` and `operations`. Record `edge_server_up = not shared["edge_server_down"]` once. The cycle uses this value for every Edge Server check, because ES can restart mid-cycle without the docs that the cycle wrote.
   * *[Client {client_id}] doc {doc_id} via {cycle}, ops: {operations}*
6. **If cycle is `sync_gateway`:**
   * *[Client {client_id}] Creating {doc_id} on Sync Gateway.* — POST to `db-1`; verify create succeeds
   * If `edge_server_up`:
     * *[Client {client_id}] Verifying {doc_id} on Edge Server.* — wait until the doc on `db` has the body written
     * Append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`
   * Capture `rev_id` from created doc.
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Sync Gateway.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * If `edge_server_up`:
       * *[Client {client_id}] Verifying {doc_id} update on Edge Server.* — wait until the doc on `db` has `changed: "yes"`
     * Update `rev_id` from updated doc.
   * If `operations` includes delete and `edge_server_up`:
     * *[Client {client_id}] Deleting {doc_id} on Edge Server.* — DELETE using `rev_id`; assert response `ok: true`; assert subsequent GET raises `CblEdgeServerBadResponseError`
     * *[Client {client_id}] Verifying {doc_id} deleted on Sync Gateway.* — wait until `db-1` shows it as deleted
7. **If cycle is `edge_server` and `edge_server_up`:**
   * *[Client {client_id}] Creating {doc_id} on Edge Server.* — PUT to `db`; verify create succeeds
   * *[Client {client_id}] Verifying {doc_id} on Sync Gateway.* — wait until the doc on `db-1` has the body written; capture `rev_id`
   * Append `doc_id` to `recent_docs` (evict oldest if list exceeds 10); call `fire_read_burst(doc_id)`
   * If `operations` includes update:
     * *[Client {client_id}] Updating {doc_id} on Edge Server.* — PUT with `changed: "yes"` and `rev_id`; verify update succeeds
     * *[Client {client_id}] Verifying {doc_id} update on Sync Gateway.* — wait until the doc on `db-1` has `changed: "yes"`; update `rev_id`
   * If `operations` includes delete:
     * *[Client {client_id}] Deleting {doc_id} on Sync Gateway.* — DELETE using `rev_id`
     * *[Client {client_id}] Verifying {doc_id} deleted on Edge Server.* — wait until `db` shows it as deleted
8. Sleep a random 1–5 seconds (jitter) before the next cycle, so that the workers do not run in lockstep or flood Sync Gateway while ES is down.
9. Before each write, the cycle records the state it writes: the body, or absent for a delete. The list starts with absent, since a create can fail before it lands. If the cycle started with Edge Server up and any step raises after `shared["outages"]` changed during the cycle, log *[Client {client_id}] {doc_id} interrupted by an Edge Server outage, revalidating later.*, add the doc and its recorded states to `interrupted`, and go on to the next cycle. The next post-restart check (step 2) revalidates it. Any other error fails the test.
10. Increment `doc_counter`; repeat from step 5.
11. Launch all 4 `client_worker` coroutines and `chaos_controller` concurrently in an `asyncio.TaskGroup` (5 total tasks); all run for the full 6-hour window, and a failure in one cancels the rest.
12. **Final reconciliation:**
    * *Verifying final doc counts match between SG and Edge Server.* — poll (up to 60s) until SG and ES doc counts are equal
