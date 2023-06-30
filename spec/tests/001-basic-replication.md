# Test Cases

## test_replicate_non_existing_sg_collections

### Description

Test that the replicator will stop with the `WebSocket 404 NotFound` error when the replicator is configured with non-existing SG collections.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : `travel.airlines`
    * endpoint: `/names`
    * type: push
    * continuos: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the replicator's error status is the WebSocket 404 NotFound error.

## test_push

### Description

Test single shot push replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
    * endpoint: `/travel`
    * type: push
    * continuos: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update docs in the local database (NEED_API)
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
10. Start the replicator with the same config as the step 3.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_pull

### Description

Test single shot pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
   * endpoint: `/travel`
   * type: pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
10. Start the replicator with the same config as the step 3.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_push_and_pull

### Description

Test single shot push-and-pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
   * endpoint: `/travel`
   * type: push-and-pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update documents in the local database.
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
10. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
11. Start the replicator with the same config as the step 3.
12. Wait until the replicator is stopped.
13. Check that all changes are replicated correctly.

## test_continuous_push

### Description

Test continuous push replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
   * endpoint: `/travel`
   * type: push
   * continuos: true
   * credentials: user1/pass
4. Wait until the replicator is idle.
5. Check that all docs are replicated correctly.
6. Update documents in the local database.
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
7. Wait until the replicator is idle.
8. Check that all updates are replicated correctly.

## test_continuous_pull

### Description

Test continuous pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
   * endpoint: `/travel`
   * type: pull
   * continuos: true
   * credentials: user1/pass
3. Wait until the replicator is idle.
4. Check that all docs are replicated correctly.
5. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
6. Wait until the replicator is idle.
7. Check that all updates are replicated correctly.

## test_continuous_push_and_pull

### Description

Test continuous push and pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
   * endpoint: `/travel`
   * type: push-and-pull
   * continuos: true
   * credentials: user1/pass
4. Wait until the replicator is idle.
5. Check that all docs are replicated correctly.
6. Update documents in the local database.
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
7. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
8. Wait until the replicator is idle.
9. Check that all updates are replicated correctly.

## test_push_default_collection

### Description

Test push replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/names`
    * type: push
    * continuos: false
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update docs in the local database (NEED_API)
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
10. Start the replicator with the same config as the step 3.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/names`
    * type: push
    * continuos: false
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update docs on SG
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
10. Start the replicator with the same config as the step 3.
11. Wait until the replicator is stopped.
12. Check that all changes are replicated correctly.

## test_push_and_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
    * collections : `_default._default`
    * endpoint: `/names`
    * type: push_and_pull
    * continuos: false
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Start the replicator with the same config as the step 3.
7. Wait until the replicator is stopped.
8. Check that there is no docs replicated (NEED_API)
9. Update docs in the local database (NEED_API)
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
10. Update docs on SG
   * Add 2 new names in `_default._default`.
   * Update 2 names in `_default._default`.
   * Remove 2 names in `_default._default`.
11. Start the replicator with the same config as the step 3.
12. Wait until the replicator is stopped.
13. Check that all changes are replicated correctly.

## test_reset_checkpoint

### Description

Test that when the replicator starts with its checkpoint reset, the replication starts from the beginning again.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
    * collections : `travel.airlines`, `travel.airports`
    * endpoint: `/travel`
    * type: push-and-pull
    * continuos: false
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Purge an airline from `travel.airlines` in the local database (NEED_API).
7. Purge an airport from `travel.airports` on SG.
8. Start the replicator with the same config as the step 3.
9. Wait until the replicator is stopped.
10. Check that the purged airline still doesn't exist in CBL database, and the purged airport still doesn't exist on SG.
11. Start the replicator with the same config as the step 2 BUT with `reset checkpoint set to true`.
12. Wait until the replicator is stopped.
13. Check that the purged airline is back in CBL database, and the purged airport is also back on SG.
