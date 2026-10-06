# Test Cases

## #1 test_delta_sync_replication

### Description
Verify push/pull replication works with large data and delta sync. Ensures that only changed documents are processed and replicated, and that delta sync bandwidth savings are realized.

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
6. Record the delta sync stats before update
7. Update existing document in SGW:
   * Modify hotel_400 with new name to test delta sync, keeping the rest of the body
8. Start the same replicator again to pull the update
9. Wait until the replicator stops.
10. Verify SGW sent the update as a small delta
   * The bytes pulled are under 10% of the original document size.
11. Verify the document was updated correctly in CBL

## #2 test_delta_sync_nested_doc

### Description
Verify delta sync works with nested documents. Ensures that only changed nested documents are processed and replicated, and that delta sync bandwidth savings are realized.

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
6. Record the delta sync stats before update
7. Update docs in SGW:
   * Update nested fields in existing document, keeping the rest of the body
8. Start the same replicator again:
9. Wait until the replicator stops.
10. Verify the document was updated correctly in CBL
11. Verify SGW sent the update as a small delta
   * The bytes pulled are under 10% of the original document size.

## #3 test_delta_sync_utf8_strings

### Description
Verify delta sync works with documents containing large UTF-8 strings. Ensures that delta sync can handle multi-byte and non-ASCII data efficiently.

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
6. Record the delta sync stats before update
7. Update docs in SGW:
   * Update document with UTF-8 content to test delta sync with multi-byte characters, keeping the rest of the body
8. Start the same replicator again.
9. Wait until the replicator stops.
10. Verify the document was updated correctly in CBL
11. Verify SGW sent the update as a small delta
   * The bytes pulled are under 10% of the original document size.

## #4 test_delta_sync_enabled_disabled

### Description
Verify delta sync behavior when toggling delta sync enabled/disabled. Ensures that full documents are transferred when delta sync is disabled and deltas are used when enabled.

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
5. Verify docs are replicated correctly
6. Record the delta sync stats before update
7. Update docs in SGW:
   * Modify only the key `name`: `SGW`, keeping the rest of the body.
8. Start the same replicator again.
9. Wait until the replicator stops.
10. Verify the document was updated correctly in CBL
11. Verify SGW sent the update as a small delta
   * The bytes pulled are under 10% of the original document size.
12. Reset SG and load `posts` dataset with delta sync disabled
13. Reset local database, and load `posts` dataset without delta sync.
14. Start a replicator:
    * endpoint: `/posts`
    * collections: `_default.posts`
    * type: pull
    * continuous: false
    * credentials: user1/pass
15. Wait until the replicator stops.
16. Verify docs are replicated correctly.
17. Record the bytes transferred.
18. Get existing document size for comparison
19. Update docs in SGW:
    * Modify the `name` field of the new doc.
20. Start the same replicator again.
21. Wait until the replicator stops.
22. Verify the document was updated correctly in CBL
23. Record the bytes transferred
24. Verify delta transferred equivalent to doc size (full doc transfer).

## #5 test_delta_sync_within_expiry

### Description
Verify that after revision expiry, any document update (even a small change) results in a full document transfer since delta sync should not be possible against an expired revision.

### Steps
1. Reset SG and load `short_expiry` dataset with delta sync enabled.
   * has a `old_rev_expiry_seconds` of 10 seconds.
   * has a rev_cache size of 1.
2. Verify SGW config has correct revision expiry settings
3. Reset local database.
4. Start a replicator:
   * endpoint: `/short_expiry`
   * collections: `_default._default`
   * type: pull
   * continuous: false
   * credentials: user1/pass
5. Wait until the replicator stops.
6. Record the bytes transferred.
7. Get the current document state and revision before update.
8. Verify old revision body is accessible before expiry through public API.
9. Update docs in SGW:
   * Modify content in document "doc1": `"name": "SGW"` (small change)
10. Wait for 12 seconds to ensure delta rev expires.
11. Verify old revision is not accessible through public API.
12. Start the same replicator again.
13. Wait until the replicator stops.
14. Record the bytes transferred post expiry.
    * SGW sent no delta.
15. Verify:
    * The transferred bytes are approximately equal to the full document size (>3000 bytes)
    * This indicates SGW correctly sent the full document after revision expiry
    * The small change forced a full document transfer due to expired revision

## #6 test_delta_sync_with_no_deltas

### Description
Test the case where an update does not produce any changes (empty delta). Ensures that SGW sends the update as an empty delta, not as a full body.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Record the delta sync stats before update
6. Verify docs are replicated correctly.
7. Update docs in SGW:
   * Update the same hotel document with identical content (no real change)
8. Start the same replicator again.
9. Wait until the replicator stops.
10. Verify SGW sent the update as a delta

## #7 test_delta_sync_larger_than_doc

### Description
Verify delta sync behavior when the update is much larger than the original document. Ensures that Sync Gateway sends the update as a delta.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify docs are replicated correctly
6. Record the delta sync stats before update
7. Update docs in SGW:
   * Update the same hotel document with much larger content (>2x original size)
8. Start the same replicator again.
9. Wait until the replicator stops.
10. Verify SGW sent the update as a delta
11. Verify document is replicated correctly. 