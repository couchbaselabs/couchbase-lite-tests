# Test Cases

## test_pull_non_blob_changes_with_delta_sync_and_compact

### Description

CBSE-14861 : Blobs are deleted after re-sync and compact

Test that after pulling non-blob changes to a document with delta sync enabled doesn't cause the blobs in the document 
to get deleted from the database after performing database compaction.

### Steps

1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections : `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * enableDocumentListener: true
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Update hotel_1 on SG but not touching the image key which contains a blob.
7. Snapshot document hotel_1.
8. Start the replicator with the same config as the step 3.
9. Wait until the replicator is stopped.
10. Perform compact on the database.
11. Verify that the document was updated correctly and the blob file of the image key still exists.
