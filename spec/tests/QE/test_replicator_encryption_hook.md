# Test Cases

## #1 test_replication_complex_doc_encryption

### Description
Test replication of documents with deeply nested encrypted fields, ensuring encrypted values are present and correctly handled during replication.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database, and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Create document in CBL:
   * Create a new document with deeply nested structure:
     ```json
     {
       "level1": {
         "level2": {
           "level3": {
             // ... continue nesting ...
             "level15": {
               "encrypted_field": "sensitive_data"
             }
           }
         }
       }
     }
     ```
   * Apply encryption hook to "encrypted_field" at 15th level
7. Start the same replicator again
8. Wait until the replicator stops.
9. Check that the document is in SGW:
    * Verify document exists.
    * Verify the innermost field is properly encrypted.
    * Validate nested structure is preserved.

## #2 test_delta_sync_with_encryption

### Description
Verify that delta sync works correctly when an encryption callback hook is present.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
    * endpoint: `/travel`
    * collections: `travel.hotels`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Record baseline bytes before update
7. Get existing document for encryption test
8. Update existing document in SGW with encryption
9. Start the same replicator again to pull the update
10. Record the bytes transferred after delta sync.
11. Verify delta sync worked with encryption.
