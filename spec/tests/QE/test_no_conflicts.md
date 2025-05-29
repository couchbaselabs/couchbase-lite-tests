# Test Cases

## #1 test_sg_cbl_updates_concurrently_with_push_pull

### Description
Test concurrent updates to the same document in both Sync Gateway and Couchbase Lite, and verify that conflicts are resolved and changes are replicated correctly.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset
3. Pull replication (continuous) to CBL
4. Wait until the replicator is idle
5. Create docs in SG
6. Update docs in SGW and CBL
7. Start Push Pull replication between SGW and CBL (continuous)
8. Wait until the replicator is idle
9. Verify updated doc count in CBL
10. Verify updated doc body in SGW and CBL
11. Update docs through CBL
12. Wait until the replicator is idle
13. Verify docs got replicated to SGW with CBL updates

## #2 test_multiple_cbls_updates_concurrently_with_push

### Description
Test concurrent updates and replication across three Couchbase Lite databases, simulating a multi-device scenario, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset on all 3 CBLs
3. Create docs in CBL DB1, DB2, DB3 associated with its own channel
4. Replicate docs from CBL DB1 to DB2 with push pull and continous
5. Wait until the replicator is idle
6. Replicate docs from CBL DB1 to DB3
7. Wait until the replicator is idle
8. Update docs on CBL DB1, DB2, DB3
9. Wait until the replicators are idle
10. Replicate docs from CBL DB3 to SGW with push pull and continous
11. Wait until the replicator is idle
12. Verify all docs replicated to sync-gateway

## #3 test_multiple_cbls_updates_concurrently_with_pull

### Description
Test concurrent updates and replication across three Couchbase Lite databases, starting with a pull from SGW, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset on all 3 CBLs
3. Create docs in SG
4. Do Pull replication to 3 CBLs
5. Wait until the replicators stop
6. Verify docs replicated to all 3 CBLs
7. Update docs in SGW and all 3 CBLs
8. Do PUSH and PULL replication to 3 CBLs
9. Wait until the replicators are idle
10. Verify docs replicated to all 3 CBLs
11. Update docs through all 3 CBLs
12. Wait until the replicators are idle
13. Verify docs updated through all 3 CBLs 