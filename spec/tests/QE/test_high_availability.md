# SGW High Availability Tests

## test_sgw_high_availability

Test that Sync Gateway maintains high availability when one node goes offline during concurrent SDK writes.

1. Create shared bucket for all SGW nodes
2. Configure database on all 3 SGW nodes (pointing to shared bucket)
3. Wait for all SGW nodes to be ready
4. Start concurrent SDK writes (100 docs) in background
5. Wait for some docs to be written
6. Delete database on sg2 to simulate node being offline
7. Verify sg2 database is offline
8. Get current doc count from sg1 and sg3 (sg2 offline)
9. Wait for all SDK writes to complete
10. Check if sg1 and sg3 database is still online
11. Wait for documents to be imported by sg1 and sg3 (with retry logic)
12. Bring sg2 back online and verify it catches up (with retry logic)
13. Verify revision ID consistency between all three nodes
14. Verify version vector consistency between all three nodes (SGW 4.0+)
