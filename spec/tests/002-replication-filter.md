# Custom Filters

These are the list of the predefined custom push/pull filters used in the test cases.

### documentIDs

The filter that only allows the specified document IDs the to pass.

**name** : `documentIDs`

**params** :

| Key        | Value       |
| :--------- | ----------- |
| documentIDs| `{ <collection-name> : [Array of document-ids>]` |

## deletedDocumentsOnly

The filter that only allows only deleted documents to pass.

**name** : `deletedDocumentsOnly`

**params** : `None`

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
    * endpoint: `/travel
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

## test_custom_push_filter

### Description

Test that the replicator will push only the docs that are passed from the push filter function.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : 
      * `travel.routes`
         * pushFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/travel`
    * type: push
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that no docs are replicated.
6. Update docs in the local database (NEED_API)
   * Add `route_10000` in `travel.routes`
   * Remove `route_10` and `route_20` in `travel.routes`
7. Start the replicator with the same config as the step 3.
8. Check that only changes passed the push filters are replicated.

## test_custom_pull_filter

### Description

Test that the replicator will pull only the docs that are passed from the pull filter function.

### Steps

1. Reset SG and load `travel` dataset.
2. Reset local database, and load `travel` dataset.
3. Start a replicator: 
    * collections : 
      * `travel.landmarks`
         * pullFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/travel`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that no docs are replicated.
6. Update docs on SG
   * Add `landmark_10000`in `travel.landmarks`
   * Remove `landmark_10` and `landmark_20` in `travel.landmarks`
7. Start the replicator with the same config as the step 3.
8. Check that only changes passed the pull filters are replicated.
