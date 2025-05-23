# Test Cases

## #1 test_delta_sync_replication

### Description
Verify push/pull replication works with large data and delta sync. Ensures that only changed documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial pull replication to ensure all documents are present.
4. Modify a document in Couchbase Lite.
5. Start push-pull replication and verify the document is updated in Sync Gateway.
6. Update documents in Sync Gateway (with and without attachment).
7. Start push-pull replication and verify only the updated documents are processed due to delta sync.
8. Check delta sync stats for number of docs updated.

### Key Assertions
- The number of processed documents after modification matches the number of changed documents.
- No unnecessary documents are replicated.
- The document IDs of updated documents match the expected set.
- The document count in the database remains consistent before and after delta sync replication.

## #2 test_delta_sync_nested_doc

### Description
Verify delta sync works with nested documents. Ensures that only changed nested documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial pull replication to ensure all documents are present.
4. Modify a document in Couchbase Lite to include nested fields.
5. Start push-pull replication and verify the nested document is updated in Sync Gateway.
6. Update the nested document in Sync Gateway.
7. Start push-pull replication and verify only the updated nested document is processed due to delta sync.
8. Check delta sync stats for number of docs updated.

### Key Assertions
- The number of processed documents after modification matches the number of changed documents.
- No unnecessary documents are replicated.
- The document IDs of updated documents match the expected set.
- The document count in the database remains consistent before and after delta sync replication.

## #3 test_delta_sync_utf8_strings

### Description
Verify delta sync works with documents containing large UTF-8 strings. Ensures that delta sync can handle multi-byte and non-ASCII data efficiently.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial replication.
4. Create a document in Couchbase Lite with a large UTF-8 string field.
5. Push the document to Sync Gateway.
6. Update the document in Sync Gateway with a new UTF-8 string value.
7. Pull the changes to Couchbase Lite.
8. Verify that only the delta is transferred (bytes transferred < doc size).

### Key Assertions
- The document is replicated successfully with UTF-8 content.
- The bytes transferred for the delta are less than the full document size.

## #4 test_delta_sync_enabled_disabled

### Description
Verify delta sync behavior when toggling delta sync enabled/disabled. Ensures that full documents are transferred when delta sync is disabled and deltas are used when enabled.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Create and update documents in Couchbase Lite.
4. Replicate and record bytes transferred (delta sync enabled).
5. Reset Sync Gateway and load the `posts` dataset with delta sync disabled.
6. Reset the local database and load the `posts` dataset.
7. Create and update documents in Couchbase Lite.
8. Replicate and record bytes transferred (delta sync disabled).
9. Compare bytes transferred in both cases.

### Key Assertions
- When delta sync is enabled, bytes transferred for updates are less than the full doc size.
- When delta sync is disabled, bytes transferred are close to the full doc size.

## #5 test_delta_sync_within_expiry

### Description
Verify delta sync behavior within and after the delta revision expiry window. Ensures that deltas are used before expiry and full docs are sent after expiry.

### Steps
1. Reset Sync Gateway and load a dataset with short delta sync expiry.
2. Create and update documents in Couchbase Lite.
3. Replicate to Sync Gateway and record bytes transferred.
4. Update the document in Sync Gateway.
5. Wait for the delta revision to expire.
6. Replicate back to Couchbase Lite and record bytes transferred.
7. Compare bytes transferred before and after expiry.

### Key Assertions
- Before expiry, delta sync is used (bytes transferred < doc size).
- After expiry, a full document is transferred (bytes transferred ≈ doc size).

## #6 test_delta_sync_with_no_deltas

### Description
Test the case where an update does not produce any changes (empty delta). Ensures that no unnecessary data is transferred and document content remains consistent.

### Steps
1. Create new documents in Couchbase Lite and/or Sync Gateway.
2. Replicate documents between CBL and SGW.
3. Update a document with the same value as the previous revision (no actual change).
4. Replicate again and verify no unnecessary data is transferred.
5. Ensure document content matches between CBL and SGW.

### Key Assertions
- No unnecessary data is transferred for empty delta updates.
- Document content is consistent between CBL and SGW after all updates.

## #7 test_delta_sync_larger_than_doc

### Description
Verify delta sync behavior when the delta is larger than the document itself. Ensures that Sync Gateway falls back to sending the full document in such cases.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Create and replicate a document in Couchbase Lite.
3. Update the document in Sync Gateway with a very large change (delta > doc size).
4. Replicate the document to Couchbase Lite.
5. Record and compare bytes transferred.

### Key Assertions
- When the delta is larger than the document, a full document is transferred.
- The bytes transferred are close to the full document size, not the delta size. 