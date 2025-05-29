# Test Cases

## #1 test_replication_complex_doc_encryption

### Description
Test replication of documents with deeply nested encrypted fields, ensuring encrypted values are present and correctly handled during replication.

### Steps
1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Replicate to CBL from SGW
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Create document in CBL with encrypted value at the 15th level of nesting
7. Replicate to SGW from CBL
8. Wait until the replicator stops.
9. Check that the document is in SGW

## #2 test_delta_sync_with_encryption

### Description
Verify that delta sync does not work when an encryption callback hook is present, and that documents with encrypted fields are not editable in SGW.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a push-pull replicator (continuous).
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Create a document with encrypted field in CBL.
7. Replicate to SGW from CBL.
8. Wait until the replicator is idle.
9. Record the bytes transferred.
10. Verify the new document is present in SGW.
11. Update that document in CBL & SGW.
12. Replicate that document using pull replication.
13. Record the bytes transferred.
14. Verify bandwidth is saved for other documents.
