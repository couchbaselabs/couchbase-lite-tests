# Test Cases

## #1 test_sg_cbl_updates_concurrently_with_push_pull

### Description
Test concurrent updates to the same document in both Sync Gateway and Couchbase Lite, and verify that conflicts are resolved and changes are replicated correctly.

### Steps
1. Reset Sync Gateway and load the `posts` dataset.
2. Reset the local database and load the `posts` dataset.
3. Perform a pull replication from SGW to CBL.
4. Add a new document in SGW and replicate to CBL.
5. Update the same document in both SGW and CBL concurrently.
6. Start a continuous push-pull replication between SGW and CBL.
7. Verify that the document is updated and conflicts are resolved as expected in both SGW and CBL.
8. Update the document again in CBL and verify the update is replicated to SGW.

## #2 test_multiple_cbls_updates_concurrently_with_push

### Description
Test concurrent updates and replication across three Couchbase Lite databases, simulating a multi-device scenario, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset Sync Gateway and load the `posts` dataset.
2. Reset and initialize three local CBL databases (`db1`, `db2`, `db3`).
3. Create documents in each CBL database, each associated with its own channel.
4. Start listeners on `db2` and `db3`.
5. Replicate documents from `db1` to `db2` and `db3` using continuous push-pull replication.
6. Update the same document concurrently in all three CBL databases.
7. Wait for replication to complete.
8. Replicate documents from `db3` to SGW using continuous push-pull replication.
9. Verify that all document updates are synchronized and conflicts are resolved across all databases and SGW.

## #3 test_multiple_cbls_updates_concurrently_with_pull

### Description
Test concurrent updates and replication across three Couchbase Lite databases, starting with a pull from SGW, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset Sync Gateway and load the `posts` dataset.
2. Reset and initialize three local CBL databases (`db1`, `db2`, `db3`).
3. Create a document in SGW.
4. Perform pull replication from SGW to all three CBL databases.
5. Update the same document concurrently in SGW and all three CBL databases.
6. Perform continuous push and pull replication from all CBL databases to SGW.
7. Update the document again in all three CBL databases.
8. Verify that all document updates are synchronized and conflicts are resolved across all databases and SGW. 