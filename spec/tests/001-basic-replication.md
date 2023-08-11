# Test Cases

## test_replicate_non_existing_sg_collections

### Description

Test that the replicator will stop with the `WebSocket 10404 NotFound` error when the replicator is configured with non-existing SG collections.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * endpoint: `/names`
    * collections : `travel.airlines`
    * type: push
    * continuos: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the replicator's error CBL/10404 error.

## test_push

### Description

Test single shot push replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * endpoint: `/travel`
    * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
    * type: push
    * continuos: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_pull

### Description

Test single shot pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
   * type: pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_push_and_pull

### Description

Test single shot push-and-pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
   * type: push-and-pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_continuous_push

### Description

Test continuous push replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
   * endpoint: `/travel`
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`
   * type: push
   * continuos: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Wait until the replicator is idle.
5. Check that all docs are replicated correctly.
6. Clear current document replication events.
7. Update documents in the local database.
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
8. Wait until receiving all document replication events.
9. Check that all updates are replicated correctly.

## test_continuous_pull

### Description

Test continuous pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.routes`, `travel.landmarks`, `travel.hotels`
   * type: pull
   * continuos: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Wait until the replicator is idle.
5. Check that all docs are replicated correctly.
6. Clear current document replication events.
7. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
8. Wait until receiving all document replication events.
9. Check that all updates are replicated correctly.

## test_continuous_push_and_pull

### Description

Test continuous push and pull replication with multiple collections.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.airlines`, `travel.airports`, `travel.hotels`, `travel.landmarks`, `travel.routes`
   * type: push-and-pull
   * continuos: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Wait until the replicator is idle.
5. Check that all docs are replicated correctly.
6. Clear current document replication events.
7. Update documents in the local database.
   * Add 2 airports in `travel.airports`.
   * Update 2 new airlines in `travel.airlines`.
   * Remove 2 hotels in `travel.hotels`.
8. Update documents on SG.
   * Add 2 routes in `travel.routes`.
   * Update 2 landmarks in `travel.landmarks`.
   * Remove 2 hotels in `travel.hotels`.
9. Wait until receiving all document replication events.
10. Check that all updates are replicated correctly.

## test_push_default_collection

### Description

Test push replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
   * endpoint: `/names`
   * collections : `_default._default`
   * type: push
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
   * endpoint: `/names`
   * collections : `_default._default` 
   * type: push
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_push_and_pull_default_collection

### Description

Test pull replication with the default collection.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
   * endpoint: `/names`
   * collections : `_default._default`
   * type: push_and_pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.

## test_reset_checkpoint_push

### Description

Test that when the push replicator starts with its checkpoint reset, the push replication starts from the beginning again.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.airlines`
   * type: push
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Purge an airline doc from `travel.airlines` on SG.
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check that the purged airline doc doesn't exist on SG.
10. Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`.
11. Wait until the replicator is stopped.
12. Check that the purged airline doc is pushed back to SG

## test_reset_checkpoint_pull

### Description

Test that when the pull replicator starts with its checkpoint reset, the pull replication starts from the beginning again.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.airports`
   * type: pull
   * continuos: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Purge an airport doc from `travel.airports` in the local database.
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check that the purged airport doc doesn't exist in CBL database.
10. Start the replicator with the same config as the step 3 BUT with `reset checkpoint set to true`.
11. Wait until the replicator is stopped.
12. 12. Check that the purged airport doc is pulled back in CBL database.
