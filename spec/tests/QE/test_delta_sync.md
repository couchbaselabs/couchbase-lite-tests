# Test Cases

## #1 test_delta_sync_replication

### Description
Verify push/pull replication works with large data and delta sync. Ensures that only changed documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.airlines`, `travel.airports`, `travel.hotels`
   * type: pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Modify docs in CBL:
   * Update a doc in `travel.airlines` with text content
   * Add attachments to another doc in `travel.airports`
7. Start another replicator:
   * endpoint: `/travel`
   * collections: `travel.airlines`, `travel.airports`, `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
   * enable_document_listener: True
8. Wait until the replicator stops.
9. Record the bytes transferred
10. Verify the new document is present in SGW
11. Update docs in SGW:
    * Update 2 airlines in `travel.airlines` with different text content
    * Modify attachments in 2 airports in `travel.airports`
12. Start the same replicator again.
13. Wait until the replicator stops.
14. Record the bytes transferred
15. Verify delta sync bytes transferred is less than doc size.

## #2 test_delta_sync_nested_doc

### Description
Verify delta sync works with nested documents. Ensures that only changed nested documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a pull replicator:
   * endpoint: `/travel`
   * collections: `travel.airlines`, `travel.routes`
   * type: pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Modify docs in CBL:
   * Update nested schedule in `travel.routes`
7. Start another replicator:
   * endpoint: `/travel`
   * collections: `travel.airlines`, `travel.routes`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
8. Wait until the replicator stops.
9. Record the bytes transferred
10. Verify the nested document is present in SGW
11. Update docs in SGW:
    * Update nested fields in `travel.routes`
12. Start the same replicator again:
13. Wait until the replicator stops.
14. Record the bytes transferred
15. Verify delta sync bytes transferred is less than doc size.

## #3 test_delta_sync_utf8_strings

### Description
Verify delta sync works with documents containing large UTF-8 strings. Ensures that delta sync can handle multi-byte and non-ASCII data efficiently.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Create docs in CBL:
   * A `name` field : `CBL` and a `body` with large UTF-8 descriptions (Chinese, Japanese characters, emoji-rich descriptions)
7. Start the same replicator again.
8. Wait until the replicator stops.
9. Record the bytes transferred.
9. Update docs in SGW :
   * Keeping the body same but the `name` field changed to `SGW`.
10. Start the same replicator again.
11. Wait until the replicator stops.
12. Record the bytes transferred again this time.
13. Verify only delta is updated while replicating and updating that document to CBL with a new name and same body.

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
6. Create docs in CBL:
    * `name`: `CBL` and a big value for a key: `extra`.
7. Start another replicator this time:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
8. Wait until the replicator stops.
9. Record the bytes transferred.
10. Update docs in SGW:
    * Modify only the key `name`: `SGW`.
11. Start the same replicator again.
12. Wait until the replicator stops.
13. Record the bytes transferred.
14. Verify delta transferred is less than doc size.
15. Reset SG and load `posts` dataset with delta sync disabled
16. Reset local database, and load `posts` dataset without delta sync.
17. Start a replicator:
    * endpoint: `/posts`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
18. Wait until the replicator stops.
19. Verify docs are replicated correctly
20. Create docs in CBL:
    * Add a new doc.
21. Start a replicator:
    * endpoint: `/posts`
    * collections: `_default._default`
    * type: push-and-pull
    * continuous: false
    * credentials: user1/pass
22. Wait until the replicator stops.
23. Record the bytes transferred.
24. Update docs in SGW:
    * Modify the `name` field of the new doc.
25. Start the same replicator again.
26. Wait until the replicator stops.
27. Record the bytes transferred
28. Verify delta transferred equivalent to doc size.

## #5 test_delta_sync_within_expiry

### Description
Verify that after revision expiry, any document update (even a small change) results in a full document transfer since delta sync should not be possible against an expired revision.

### Steps
1. Reset SG and load `short_expiry` dataset with delta sync enabled.
   * has a `old_rev_expiry_seconds` of 10 seconds.
   * has a rev_cache size of 1.
2. Verify SGW config has correct revision expiry settings.
3. Reset local database, and load `short_expiry` dataset.
4. Create doc in CBL:
   * Add a new document with large text content:
     * `"name": "CBL"`
     * `"extra": "a" * 3000` (large content)
5. Start a replicator:
   * endpoint: `/short_expiry`
   * collections: `_default._default`
   * type: push
   * continuous: false
   * credentials: user1/pass
6. Wait until the replicator stops.
7. Record the bytes transferred.
8. Get the current document state and revision before update.
9. Verify old revision body is accessible before expiry through public API.
10. Update docs in SGW:
   * Modify content in document "doc_1": `"name": "SGW"` (small change)
11. Wait for 10 seconds to ensure delta rev expires.
12. Verify old revision is not accessible through public API.
13. Pull replicate back to CBL:
    * endpoint: `/short_expiry`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
14. Wait until the replicator stops.
15. Record the bytes transferred post expiry.
16. Verify:
    * The transferred bytes are approximately equal to the full document size (>3000 bytes)
    * This indicates SGW correctly sent the full document after revision expiry
    * The small change forced a full document transfer due to expired revision

## #6 test_delta_sync_with_no_deltas

### Description
Test the case where an update does not produce any changes (empty delta). Ensures that no unnecessary data is transferred and document content remains consistent.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify docs are replicated correctly.
6. Update doc in CBL:
   * Add a new doc with body: `"name": "CBL"`.
7. Start the same replicator again.
8. Wait until the replicator stops.
9. Update docs in SGW:
   * Update the same hotel document with identical content
10. Update docs in SGW again:
    * Update the same hotel document with same content as previous revision
11. Start a continuous replicator.
12. Wait until the replicator idles.
13. Update docs in CBL:
    * Update the same hotel document with identical content again
14. Wait until the replicator idles.
15. Verify doc body matches between SGW and CBL.

## #7 test_delta_sync_larger_than_doc

### Description
Verify delta sync behavior when the delta is larger than the document itself. Ensures that Sync Gateway falls back to sending the full document in such cases.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: push-and-pull
   * continuous: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify docs are replicated correctly
6. Update doc in CBL:
   * Modify a hotel document with small changes
7. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.hotels`
   * type: push
   * continuous: false
   * credentials: user1/pass
8. Wait until the replicator stops.
9. Get delta stats.
10. Update docs in SGW:
    * Update the same hotel document with much larger content (>2x original size)
11. Start a replicator:
    * endpoint: `/travel`
    * collections: `travel.hotels`
    * type: pull
    * continuous: false
    * credentials: user1/pass
12. Wait until the replicator stops.
13. Get delta stats.
14. Verify full doc is replicated.
15. Verify delta size at step 7 is >= step 4. 