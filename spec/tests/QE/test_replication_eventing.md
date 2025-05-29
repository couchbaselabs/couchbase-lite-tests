# Test Cases

## #1 test_push_replication_for_20mb_doc

### Description
Test push replication of a large document (>20MB) from Couchbase Lite to Sync Gateway, and verify that an error is thrown for oversized documents.

### Steps
1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start push-pull replication.
4. Wait for replication to complete.
5. Create document with a large attachment (20MB).
6. Verify document was created successfully.
7. Verify document content.
8. Start push one-shot replication to SGW.
9. Wait until the replicator is stopped.
10. Verify document was not replicated.
