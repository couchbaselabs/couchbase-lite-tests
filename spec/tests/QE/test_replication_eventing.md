# Test Cases

## #1 test_push_replication_for_20mb_doc

### Description
Test push replication of a large document (>20MB) from Couchbase Lite to Sync Gateway, and verify that an error is thrown for oversized documents.

### Steps
1. Reset SG and load `names` dataset.
2. Reset local database, and load `names` dataset.
3. Start a replicator:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
4. Wait for replication to complete.
5. Create document with a large attachment:
   * Create a new document with ID "large_doc"
   * Add text content and metadata
   * Attach a 20MB binary file
6. Verify document was created successfully:
   * Check document exists in local database
   * Verify attachment is accessible
7. Verify document content:
   * Check text content is correct
   * Verify metadata is present
   * Validate attachment size is 20MB
8. Start the same replicator again.
9. Wait until the replicator is stopped.
10. Verify document was not replicated:
    * Check replicator error indicates document size limit exceeded
    * Verify document is not present in Sync Gateway
    * Validate error message contains size limit information
