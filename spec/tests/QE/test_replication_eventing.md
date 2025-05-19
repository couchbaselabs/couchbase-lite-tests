# Test Cases

## #1 test_push_replication_for_20mb_doc

### Description
Test push replication of a large document (>20MB) from Couchbase Lite to Sync Gateway, and verify that an error is thrown for oversized documents.

### Steps
1. Reset Sync Gateway and load the `posts` dataset.
2. Reset the local database and load the `posts` dataset.
3. Create a large document in Couchbase Lite.
4. Attempt to replicate the large document to Sync Gateway using push replication.
5. Verify that an error is thrown and the document is not replicated to Sync Gateway.

## #2 test_delta_sync_verification

### Description
Verify that delta sync only processes changed documents during replication, ensuring bandwidth savings and correct document processing.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial replication to ensure all documents are present.
4. Modify a subset of documents in Couchbase Lite.
5. Start replication again and verify that only the modified documents are processed due to delta sync.
6. Ensure the total document count remains unchanged after replication. 