# Test Cases

## test_push_document_ids_filter

### Description

Test that the replicator will push only the docs specified in the document ids filter.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : 
      * `travel.airlines`
         * documentIDs : `airline_10`, `airline_20`, `airline_1000`
      * `travel.routes`
         * documentIDs : `route_10`, `route_20`
    * endpoint: `/travel`
    * type: push
    * continuous: false
    * credentials: user1/pass
3. Wait until the replicator is stopped.
4. Check that only docs specified in the documentIDs filters are replicated except `travel.airline`.`airline_1000`
5. Update docs in the local database
   * Add `airline_1000` in `travel.airlines`
   * Update `airline_10` in `travel.airlines`
   * Remove `route_10` in `travel.routes`
6. Start the replicator with the same config as the step 3.
7. Check that only docs specified in the documentIDs filters are replicated.

## test_pull_document_ids_filter

### Description

Test that the replicator will pull only the docs specified in the document ids filter.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : 
      * `travel.airports`
         * documentIDs : `airport_10`, `airport_20`, `airport_1000`
      * `travel.landmarks`
         * documentIDs : `landmark_10`, `landmark_20`
    * endpoint: `/travel`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that only docs specified in the documentIDs filters are replicated except `travel.airports`.`airport_1000`.
6. Update docs on SG
   * Add `airport_1000` in `travel.airports`
   * Update `airport_10` in `travel.airports`
   * Remove `landmark_10`, in `travel.landmarks`
7. Start the replicator with the same config as the step 3.
8. Check that only changes for docs in the specified documentIDs filters are replicated.

## test_pull_channels_filter

### Description

Test that the replicator will pull only the docs specified in the channels filter.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : 
      * `travel.airports`
         * channels : `United States`, `France`
      * `travel.landmarks`
         * channels : `France`
    * endpoint: `/travel`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that only docs in the filtered channels are pulled.
6. Update docs on SG
   * Add `airport_1000` with channels = ["United States"], `airport_2000` with channels = ["France"] and `airport_3000` with channels = ["United Kingdom"] in `travel.airports`
   * Update `airport_airport_11` with channels = ["United States"], `airport_1` with channels = ["France"], `airport_17` with channels = ["United Kingdom"] in `travel.airports`
   * Remove `landmark_1` channels = ["United States"], `landmark_2001` channels = ["France"] in `travel.landmarks`
7. Start the replicator with the same config as the step 3.
8. Check that only changes in the filtered channels are pulled.

## test_replicate_public_channel

### Description

Test that the replicator will pull only the docs specified in the channels filter.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `empty` dataset.
3. Add a document to SG
   * id: test_public
   * channels: `!`
   * body: `{"hello": "world"}`
4. Start a replicator: 
    * endpoint: `/names`
    * type: pull
    * continuous: false
    * credentials: user2/pass
5. Wait until the replicator is stopped.
6. Check that only test_public was pulled
7. Verify test_public contents
8. Update test_public locally
   * body: `{"see you later": "world"}`
9. Start a replicator: 
    * endpoint: `/names`
    * type: push
    * continuous: false
    * credentials: user2/pass
10. Wait until the replicator is stopped.
11. Verify that the document on Sync Gateway was updated

## test_custom_push_filter

### Description

Test that the replicator will push only the docs that are passed from the push filter function.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator: 
    * collections : 
      * `_default._default`
         * pushFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/names`
    * type: push
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that no docs are replicated.
6. Update docs in the local database
   * Add `name_10000`
   * Remove `name_10` and `name_20`
7. Start the replicator with the same config as the step 3.
8. Check that only changes passed the push filters are replicated.

## test_custom_pull_filter

### Description

Test that the replicator will pull only the docs that are passed from the pull filter function.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator: 
    * collections : 
      * `_default._default`
         * pullFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/names`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that no docs are replicated.
6. Update docs on SG
   * Add `name_10000`
   * Remove `name_10` and `name_20`
7. Start the replicator with the same config as the step 3.
8. Check that only changes passed the pull filters are replicated.
