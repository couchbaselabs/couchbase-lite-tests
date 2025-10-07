# Test Cases

## #1 test_sg_cbl_updates_concurrently_with_push_pull

### Description
Test concurrent updates to the same document in both Sync Gateway and Couchbase Lite, and verify that conflicts are resolved and changes are replicated correctly.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset
3. Start a replicator:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: pull
   * continuous: true
   * credentials: user1/pass
4. Wait until the replicator is idle
6. Update docs concurrently:
   * In SGW: `"title"`: `"SGW Update"`
   * In CBL: `"title"`: `"CBL Update"`
7. Start another replicator:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: push
   * continuous: true
   * credentials: user1/pass
8. Wait until the replicators are idle.
9. Verify updated doc count in CBL
10. Verify updated doc body in SGW and CBL.
11. Update docs through CBL:
    * `"title"`: `"CBL Update 2"`
12. Wait until the replicators are idle.
13. Verify docs got replicated to SGW with CBL updates.

## #2 test_multiple_cbls_updates_concurrently_with_push

### Description
Test concurrent updates and replication across three Couchbase Lite databases (3 dbs, 1/device), with a multi-device scenario (3 devices) and a SGW, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset on all 3 CBLs
3. Create docs in CBL DB1, DB2, DB3:
   * In DB1:
     * Add doc in "group1"
   * In DB2:
     * Add doc in "group1"
   * In DB3:
     * Add doc in "group2"
4. Start a replicator between DB1 and DB2:
   * endpoint: DB2 URL
   * collections: `_default.posts`
   * type: push-and-pull
   * continuous: true
5. Wait until the replicator is idle
6. Start a replicator between DB1 and DB3:
   * endpoint: DB3 URL
   * collections: `_default.posts`
   * type: push-and-pull
   * continuous: false
7. Wait until the replicator is idle
8. Update docs concurrently:
   * In DB1: `"CBL1 Update 1"`
   * In DB2: `"CBL2 Update 1"`
   * In DB3: `"CBL3 Update 1"`
9. Wait until the replicators are idle
10. Start a replicator between DB3 and SGW:
    * endpoint: `/posts`
    * collections: `_default.posts`
    * type: push-and-pull
    * continuous: true
    * enableDocumentListener: true
    * credentials: user1/pass
11. Wait until the replicator is idle
12. Verify replication was successful and document content in SGW.

## #3 test_multiple_cbls_updates_concurrently_with_pull

### Description
Test concurrent updates and replication across three Couchbase Lite databases, starting with a pull from SGW, and verify that all changes are synchronized and conflicts are resolved.

### Steps
1. Reset SG and load `posts` dataset
2. Reset local database and load `posts` dataset on all 3 CBLs
3. Create a new doc in SG: `post_1000`.
4. Start replicators for all 3 CBLs:
   * For each CBL (DB1, DB2, DB3):
     * endpoint: `/posts`
     * collections: `_default.posts`
     * type: pull
     * continuous: false
     * credentials: user1/pass
5. Wait until the replicators stop
6. Verify docs replicated to all 3 CBLs
7. Update docs concurrently:
   * In SGW: `"title": "SGW Update 1"`
   * In DB1: `"title": "CBL1 Update 1"`
   * In DB2: `"title": "CBL2 Update 1"`
   * In DB3: `"title": "CBL3 Update 1"`
8. Start replicators for all 3 CBLs:
   * For each CBL (DB1, DB2, DB3):
     * endpoint: `/posts`
     * collections: `_default.posts`
     * type: push-and-pull
     * continuous: true
     * credentials: user1/pass
9. Wait until the replicators are idle
10. Verify docs replicated to all 3 CBLs:
    * Check doc bodies are consistent across all 3 CBLs and SGW
11. Update docs concurrently through all 3 CBLs:
    * In DB1: `"title": "CBL1 Update 2"`
    * In DB2: `"title": "CBL2 Update 2"`
    * In DB3: `"title": "CBL3 Update 2"`
12. Wait until the replicators are idle
13. Verify docs updated through all 3 CBLs:
    * Check doc bodies are consistent across all 3 CBLs and SGW