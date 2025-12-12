# Multiple Couchbase Server Tests

## test_rebalance_sanity

Test that Sync Gateway handles Couchbase Server cluster rebalancing correctly during concurrent document updates.

1. Create bucket on CBS cluster
2. Configure database on SGW with distributed indexing enabled
3. Create user with specific channels
4. Create user client for SGW access
5. Add 100 docs to Sync Gateway
6. Verify all docs were created and store original revisions and version vectors
7. Start concurrent updates (100 updates per doc) and rebalance CBS cluster
8. Rebalance OUT cbs_two from cluster
9. Add cbs_two back to cluster
10. Rebalance IN cbs_two to cluster
11. Wait for all updates to complete
12. Verify all docs are present and revisions/version vectors changed
13. Cleanup: Delete database and bucket

## test_server_goes_down_sanity

Test that Sync Gateway continues to function when a Couchbase Server node fails over.

1. Clean up and setup test environment (bucket and database)
2. Create user with specific channels
3. Add 50 docs to Sync Gateway before failover
4. Verify all docs were created
5. Failover CBS node 2 to simulate server failure
6. Rebalance cluster (without ejecting failed node)
7. Wait for cluster to become healthy
8. Verify original docs are still accessible with node 2 failed over
9. Add 50 NEW docs while node 2 is down
10. Verify new docs added during failover are accessible
11. Recover CBS node 2 (or add back if needed)
12. Wait for cluster to become healthy after recovery
13. Verify all 100 docs are accessible after recovery
14. Cleanup: Delete database and bucket

## test_isgr_explicit_collection_mapping

Test Inter-Sync Gateway Replication (ISGR) with explicit collection mapping between different buckets.

1. Clean up any leftover state from all Sync Gateways
2. Create 3 buckets on single CBS cluster (isgr_bucket1, isgr_bucket2, isgr_bucket3)
3. Create collections in _default scope for each bucket:
   - bucket1: collection1, collection2, collection3
   - bucket2: collection4, collection5
   - bucket3: collection6, collection7, collection8, collection9
4. Configure SG1 with bucket1 (db1), SG2 with bucket2 (db2), SG3 with bucket3 (db3)
5. Upload 3 docs to each collection in SG1 (collection1, collection2, collection3)
6. Start one-shot push ISGR from SG1 to SG2 with collection remapping:
   - _default.collection1 -> _default.collection4
   - _default.collection2 -> _default.collection5
7. Start one-shot pull ISGR from SG1 to SG3 with collection remapping:
   - _default.collection1 -> _default.collection6
   - _default.collection2 -> _default.collection7
   - _default.collection3 -> _default.collection8
8. Wait for both ISGR replications to complete (status: stopped)
9. Verify docs replicated to SG2:
   - collection4 should have docs from collection1
   - collection5 should have docs from collection2
10. Verify docs replicated to SG3:
    - collection6 should have docs from collection1
    - collection7 should have docs from collection2
    - collection8 should have docs from collection3
