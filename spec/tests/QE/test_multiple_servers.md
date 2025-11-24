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

