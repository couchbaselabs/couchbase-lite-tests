# Test Cases

## #1 test_replication_complex_doc_encryption

### Description
Test replication of documents with deeply nested encrypted fields, ensuring encrypted values are present and correctly handled during replication.

### Steps
1. Reset Sync Gateway and load the `posts` dataset.
2. Reset the local database and load the `posts` dataset.
3. Replicate from SGW to CBL and verify initial documents.
4. Create a document in CBL with an encrypted value at the 15th level of nesting.
5. Replicate to SGW and verify the encrypted field is present in SGW.

## #2 test_delta_sync_with_encryption

### Description
Verify that delta sync does not work when an encryption callback hook is present, and that documents with encrypted fields are not editable in SGW.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial replication.
4. Create a document with an encrypted field in CBL and replicate to SGW.
5. Update documents in both CBL and SGW.
6. Replicate using pull replication and verify bandwidth is saved for other documents.

## #3 test_delta_sync_replication

### Description
Verify push/pull replication works with large data, including updates with and without attachments, and that delta sync stats show bandwidth saving and correct document processing.

### Steps
1. Reset Sync Gateway and load the `travel` dataset with delta sync enabled.
2. Reset the local database and load the `travel` dataset.
3. Start a replicator and perform initial replication.
4. Modify documents in CBL and replicate changes.
5. Update documents in SGW with and without attachments.
6. Perform push/pull replication and verify only updated documents are processed. 