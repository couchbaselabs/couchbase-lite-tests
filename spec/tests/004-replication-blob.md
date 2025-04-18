# Test Cases

## test_pull_non_blob_changes_with_delta_sync_and_compact

### Description

CBSE-14861 : Blobs are deleted after re-sync and compact

Test that after pulling non-blob changes twice to a document with delta sync enabled doesn't cause the blobs in the document 
to get deleted from the database after performing database compaction.

### Steps

1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Update hotel_1 on SG without changing the image key.
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check that all docs are replicated correctly.
10. Update hotel_1 on SG again without changing the image key.
11. Snapshot document hotel_1.
12. Start the replicator with the same config as the step 3.
13. Wait until the replicator is stopped.
14. Check that all docs are replicated correctly.
15. Perform compact on the database.
16. Verify updates to the snapshot from the step 11.

## test_blob_replication

### Description

Basic blob replication check to ensure that blobs will be included in a replication.

### Steps

1.  Reset SG and load `names` dataset
2.  Reset empty local database
3. Create a document with a blob on the property `watermelon` with the contents of s10.jpg
4. Start a replicator:
   * endpoint: `/names`
   * collections : `_default._default`
   * type: push
   * continuous: false
   * credentials: user1/pass
5. Wait until the replicator is stopped
6. Check that the document with the ID from step 3 contains a valid `watermelon` property
7. Check that the blob in the `watermelon` property has a corresponding attachment entry in SGW