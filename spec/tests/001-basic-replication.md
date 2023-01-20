# Test Cases

## test_replicate_non_existing_sg_collections

### Description

Test that the replicator will stop with the `WebSocket 404 NotFound` error when the replicator is configured with non-existing SG collections.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : `inventory.airline`, `inventory.carrental`, `inventory.hotel`
    * endpoint: `/travel-sample-inventory`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that the replicator's error status is the WebSocket 404 NotFound error.

## test_push

### Description

Test single shot push replication with multiple collections.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : `inventory.airline`, `inventory.airport`, `inventory.hotel`
    * endpoint: `/travel-sample-inventory`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update docs in the local database (NEED_API)
   * Add 2 airports in `inventory.airport`.
   * Update 2 new airlines in `inventory.airline`.
   * Remove 2 hotels in `inventory.hotel`.
9. Start the replicator with the same config as the step 2.
10. Wait until the replicator is stopped.
11. Check that all changes are replicated correctly.

## test_pull

### Description

Test single shot pull replication with multiple collections.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator:
   * collections : `inventory.route`, `inventory.landmark`, `inventory.hotel`
   * endpoint: `/travel-sample-inventory`
   * type: pull
   * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update documents on SG.
   * Add 2 routes in `inventory.routes`.
   * Update 2 landmarks in `inventory.landmark`.
   * Remove 2 hotels in `inventory.hotel`.
9. Start the replicator with the same config as the step 2.
10. Wait until the replicator is stopped.
11. Check that all changes are replicated correctly.

## test_push_and_pull

### Description

Test single shot push-and-pull replication with multiple collections.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator:
   * collections : `inventory.airline`, `inventory.airport`, `inventory.hotel`, `inventory.landmark`, `inventory.route`
   * endpoint: `/travel-sample-inventory`
   * type: push-and-pull
   * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update documents in the local database.
   * Add 2 airports in `inventory.airport`.
   * Update 2 new airlines in `inventory.airline`.
   * Remove 2 hotels in `inventory.hotel`.
9. Update documents on SG.
   * Add 2 routes in `inventory.routes`.
   * Update 2 landmarks in `inventory.landmark`.
   * Remove 2 hotels in `inventory.hotel`.
10. Start the replicator with the same config as the step 2.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_continuous_push

### Description

Test continuous push replication with multiple collections.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator: 
   * collections : `inventory.airline`, `inventory.airport`, `inventory.hotel`
   * endpoint: `/travel-sample-inventory`
   * type: push
   * continuos: true
3. Wait until the replicator is idle.
4. Check that all docs are replicated correctly.
5. Update documents in the local database.
   * Add 2 airports in `inventory.airport`.
   * Update 2 new airlines in `inventory.airline`.
   * Remove 2 hotels in `inventory.hotel`.
9. Wait until the replicator is idle.
10. Check that all updates are replicated correctly.

## test_continuous_pull

### Description

Test continuous pull replication with multiple collections.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator:
   * collections : `inventory.route`, inventory.landmark, inventory.hotel
   * endpoint: /travel-sample-inventory
   * type: pull
   * continuos: true
3. Wait until the replicator is idle.
4. Check that all docs are replicated correctly.
5. Update documents on SG.
   * Add 2 routes in inventory.routes.
   * Update 2 landmarks in inventory.landmark.
   * Remove 2 hotels in inventory.hotel.
6. Wait until the replicator is idle.
7. Check that all updates are replicated correctly.

## test_continuous_push_and_pull

### Description

Test continuous push and pull replication with multiple collections.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator:
   * collections : `inventory.airline`, `inventory.airport`, `inventory.hotel`, `inventory.landmark`, `inventory.route`
   * endpoint: `/travel-sample-inventory`
   * type: push-and-pull
   * continuos: true
3. Wait until the replicator is idle.
4. Check that all docs are replicated correctly.
5. Update documents in the local database.
   * Add 2 airports in `inventory.airport`.
   * Update 2 new airlines in `inventory.airline`.
   * Remove 2 hotels in `inventory.hotel`.
6. Update documents on SG.
   * Add 2 routes in `inventory.routes`.
   * Update 2 landmarks in `inventory.landmark`.
   * Remove 2 hotels in `inventory.hotel`.
7. Wait until the replicator is idle.
8. Check that all updates are replicated correctly.

## test_push_default_collection

### Description

Test push replication with the default collection.

### Steps

1. Load `name-100` dataset.
2. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/default_empty`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update docs in the local database (NEED_API)
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
9. Start the replicator with the same config as the step 2.
10. Wait until the replicator is stopped.
11. Check that all changes are replicated correctly.

## test_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Reset and create a database without loading a dataset.
2. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/name-100`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update docs on SG
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
9. Start the replicator with the same config as the step 2.
10. Wait until the replicator is stopped.
11. Check that all changes are replicated correctly.

## test_push_and_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Load `name-100` dataset.
2. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/name-100`
    * type: push_and_pull
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Start the replicator with the same config as the step 2.
6. Wait until the replicator is stopped.
7. Check that there is no docs replicated (NEED_API)
8. Update docs in the local database (NEED_API)
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
9. Update docs on SG
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
10. Start the replicator with the same config as the step 2.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_reset_checkpoint

### Description

Test that when the replicator starts with its checkpoint reset, the replication starts from the beginning again.

### Steps

1. Load `travel-sample` dataset.
2. Start a replicator:
    * collections : `inventory.airline`, `inventory.airport`
    * endpoint:` /travel-sample-inventory`
    * type: push-and-pull
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that all docs are replicated correctly.
5. Purge an airline from `inventory.airline` in the local database (NEED_API).
6. Purge an airport from `inventory.airport` on SG.
7. Start the replicator with the same config as the step 2.
8. Wait until the replicator is stopped.
9. Check that the purged airline still doesn't exist in CBL database, and the purged airport still doesn't exist on SG.
10. Start the replicator with the same config as the step 2 BUT with `reset checkpoint set to true`.
11. Wait until the replicator is stopped.
12. Check that the purged airline is back in CBL database, and the purged airport is also back on SG.
