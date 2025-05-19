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

## Purpose
This test verifies delta sync functionality in Couchbase Lite and Sync Gateway. It ensures that only changed documents are processed and replicated, and that delta sync bandwidth savings are realized.

## Test Steps
1. **Setup**: Reset Sync Gateway and load the required dataset with delta sync enabled.
2. **Database Initialization**: Reset the local database and load the dataset.
3. **Initial Replication**: Start a replicator and perform initial replication to ensure all documents are present.
4. **Document Modification**: Modify a subset of documents in Couchbase Lite.
5. **Delta Sync Replication**: Start replication again and verify that only the modified documents are processed due to delta sync.
6. **Assertions**:
   - Only the changed documents are processed during the second replication.
   - The total document count remains unchanged.
   - Delta sync is enabled and functioning as expected.

## Key Assertions
- The number of processed documents after modification matches the number of changed documents.
- No unnecessary documents are replicated.
- The document IDs of updated documents match the expected set.
- The document count in the database remains consistent before and after delta sync replication. 