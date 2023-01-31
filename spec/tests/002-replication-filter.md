# Custom Filters

{Need API Update}

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

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `inventory.airline`
         * documentIDs : `airline_10`, `airline_22`, `airline_1x`
      * `inventory.route`
         * documentIDs : `route_10000`, `route_10001`
    * endpoint: `/travel-sample-inventory`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that only docs specified in the documentIDs filters are replicated except `inventory.airline`.`airline_1x`
5. Update docs in the local database (NEED_API)
   * Add `airline_1x` and `airline_2x` in `inventory.airline`
   * Update `airline_10`, `airline_22`, `airline_210` in `inventory.airline`
   * Remove `route_10000`, `route_10001`, and `route_10010` in `inventory.route`
6. Start the replicator with the same config as the step 2.
7. Check that only docs specified in the documentIDs filters are replicated.

## test_pull_document_ids_filter

### Description

Test that the replicator will pull only the docs specified in the document ids filter.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `inventory.airport`
         * documentIDs : `airport_1254`, `airport_1260`, `airport_1x`
      * `inventory.landmark`
         * documentIDs : `landmark_10019`, `landmark_10156`
    * endpoint: `/travel-sample-inventory`
    * type: pull
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that only docs specified in the documentIDs filters are replicated except `inventory.airport`.`airport_1x`.
5. Update docs on SG
   * Add `airport_1x` and `airport_2x` in `inventory.airport`
   * Update `airport_1254`, `airport_1260`, `airport_1280` in `inventory.airport`
   * Remove `landmark_10019`, `landmark_10156`, and `landmark_10622` in `inventory.landmark`
6. Start the replicator with the same config as the step 2.
7. Check that only docs specified in the documentIDs filters are replicated.

## test_pull_channels_filter

### Description

Test that the replicator will pull only the docs specified in the channels filter.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `inventory.airport`
         * channels : `United States`, `France`
      * `inventory.landmark`
         * channels : `France`
    * endpoint: `/travel-sample-inventory`
    * type: pull
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that only docs in the specified channels are pulled.
5. Update docs on SG
   * Add `airport_1x` (United States), `airport_2x` (France) and `airport_3x` (United Kingdom) in `inventory.airport`
   * Update `airport_3411` (United States), `airport_1254` (France), `airport_4346` (United Kingdom) in `inventory.airport`
   * Remove `landmark_10144` (United States), `landmark_1006` (France) in `inventory.landmark`
6. Start the replicator with the same config as the step 2.
7. Check that only docs in the channels filters are replicated.

## test_custom_push_filter

### Description

Test that the replicator will push only the docs that are passed from the push filter function.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `inventory.airline`
         * pushFilter:
            * name: `documentIDs`
            * params: `{ "documentIDs": { "inventory.airline": "airline_10", "airline_22", "airline_1x"} }`
      * `inventory.route`
         * pushFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/travel-sample-inventory`
    * type: push
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that only docs passed the push filters are replicated.
5. Update docs in the local database (NEED_API)
   * Add `airline_1x` and `airline_2x` in `inventory.airline`
   * Update `airline_10`, `airline_22`, `airline_210` in `inventory.airline`
   * Remove `route_10000`, `route_10001`, and `route_10010` in `inventory.route`
6. Start the replicator with the same config as the step 2.
7. Check that only changes passed the push filters are replicated.

## test_custom_pull_filter

### Description

Test that the replicator will pull only the docs that are passed from the pull filter function.

### Steps

1. Load `travel-sample` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `inventory.airport`
         * pullFilter:
            * name: `documentIDs`  
            * params : `{ "documentIDs": {"inventory.airport": "airport_1254", "airport_1260", "airport_1x"} }`
      * `inventory.landmark`
         * pullFilter:  
            * name: `deletedDocumentsOnly`
            * params: `{}`
    * endpoint: `/travel-sample-inventory`
    * type: pull
    * continuos: false
3. Wait until the replicator is stopped.
4. Check that only docs passed the pull filters are replicated.
5. Update docs on SG
   * Add `airport_1x` and `airport_2x` in `inventory.airport`
   * Update `airport_1254`, `airport_1260`, `airport_1280` in `inventory.airport`
   * Remove `landmark_10019`, `landmark_10156`, and `landmark_10622` in `inventory.landmark`
6. Start the replicator with the same config as the step 2.
7. Check that only changes passed the pull filters are replicated.
