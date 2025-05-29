# Test Cases

## #1 test_delta_sync_replication

### Description
Verify push/pull replication works with large data and delta sync. Ensures that only changed documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Modify docs in CBL with and without attachment
7. Do push_pull replication
8. Wait until the replicator stops.
9. Record the bytes transferred
10. Verify the new document is present in SGW
11. Update docs in SGW  with and without attachment
12. Do push_pull replication
13. Wait until the replicator stops.
14. Record the bytes transferred
15. Verify delta sync bytes transferred is less than doc size.

## #2 test_delta_sync_nested_doc

### Description
Verify delta sync works with nested documents. Ensures that only changed nested documents are processed and replicated, and that delta sync bandwidth savings are realized.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Modify docs in CBL with nested docs
7. Do push_pull replication
8. Wait until the replicator stops.
9. Record the bytes transferred
10. Verify the nested document is present in SGW
11. Update docs in SGW with nested docs
12. Do push_pull replication
13. Wait until the replicator stops.
14. Record the bytes transferred
15. Verify delta sync bytes transferred is less than doc size.

## #3 test_delta_sync_utf8_strings

### Description
Verify delta sync works with documents containing large UTF-8 strings. Ensures that delta sync can handle multi-byte and non-ASCII data efficiently.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator
4. Wait until the replicator stops.
5. Check that all docs are replicated correctly.
6. Create docs in CBL
7. Do push replication to SGW
8. Wait until the replicator stops.
9. Update docs in SGW/CBL with utf8 strings
10. Do pull replication
11. Wait until the replicator stops.
12. Record the bytes transferred
13. Verify only delta is updated.

## #4 test_delta_sync_enabled_disabled

### Description
Verify delta sync behavior when toggling delta sync enabled/disabled. Ensures that full documents are transferred when delta sync is disabled and deltas are used when enabled.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled
2. Reset local database, and load `travel` dataset.
3. Start a replicator
4. Wait until the replicator stops.
5. Verify docs are replicated correctly
6. Create docs in CBL
7. Start replication
8. Wait until the replicator stops.
9. Record the bytes transferred
10. Update doc on SGW
11. Do pull replication
12. Wait until the replicator stops.
13. Record the bytes transferred
14. Verify delta transferred is less than doc size.
15. Reset SG and load `posts` dataset with delta sync disabled
16. Reset local database, and load `posts` dataset.
17. Start a replicator
18. Wait until the replicator stops.
19. Verify docs are replicated correctly
20. Create docs in CBL
21. Start replication
22. Wait until the replicator stops.
23. Record the bytes transferred
24. Update doc on SGW
25. Do pull replication
26. Wait until the replicator stops.
27. Record the bytes transferred
28. Verify delta transferred equivalent to doc size.

## #5 test_delta_sync_within_expiry

### Description
Verify delta sync behavior within and after the delta revision expiry window. Ensures that deltas are used before expiry and full docs are sent after expiry.

### Steps
1. Reset SG and load `short_expiry` dataset with delta sync enabled.
2. Reset local database, and load `short_expiry` dataset.
3. Create docs in CBL.
4. Push replicate to SGW.
5. Wait until the replicator stops.
6. Record the bytes transferred.
7. Verify doc body in SGW matches the updates from CBL.
8. Update docs in SGW.
9. Wait for 60 seconds for delta revision to expire.
10. Pull replicate back to CBL.
11. Wait until the replicator stops.
12. Record the bytes transferred post expiry.
13. Verify the doc in SGW and CBL have same content.

## #6 test_delta_sync_with_no_deltas

### Description
Test the case where an update does not produce any changes (empty delta). Ensures that no unnecessary data is transferred and document content remains consistent.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Do initial push_pull replication.
4. Wait until the replicator stops.
5. Verify docs are replicated correctly.
6. Update doc on CBL.
7. Replicate to SGW.
8. Wait until the replicator stops.
9. Update doc on SGW with same body.
10. Update doc on SGW again to have same value as previous rev.
11. Replicate docs with continuous replication.
12. Wait until the replicator idles.
13. Update doc on CBL again to have same value as previous rev.
14. Wait until the replicator idles.
15. Verify doc body matches between SGW and CBL.

## #7 test_delta_sync_larger_than_doc

### Description
Verify delta sync behavior when the delta is larger than the document itself. Ensures that Sync Gateway falls back to sending the full document in such cases.

### Steps
1. Reset SG and load `travel` dataset with delta sync enabled.
2. Reset local database, and load `travel` dataset.
3. Setup a push-pull replicator.
4. Wait until the replicator stops.
5. Verify docs are replicated correctly
6. Update doc on CBL.
7. Push replicate to SGW.
8. Wait until the replicator stops.
9. Get delta stats.
10. Update doc on SGW with larger body.
11. Pull replicate to CBL.
12. Wait until the replicator stops.
13. Get delta stats.
14. Verify full doc is replicated.
15. Verify delta size at step 7 is >= step 4. 