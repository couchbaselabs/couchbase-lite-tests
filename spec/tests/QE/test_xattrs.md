# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to SG and SDK channels
4. Bulk create 1000 docs via Sync Gateway
5. Verify all SG docs were created successfully and store revisions
6. Stop Sync Gateway
7. Update 1000 SG docs via SDK
8. Write 1000 new docs via SDK
9. Restart Sync Gateway (recreate database endpoint)
10. Wait for Sync Gateway to import all documents
11. Verify SG doc revisions changed after SDK update
12. Verify SDK doc count is correct
13. Verify document contents for all documents
14. Verify version vectors for updated SG documents (optional)

## test_purge

Test purging functionality with XATTR-based documents created via both Sync Gateway and SDK.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to channels
4. Bulk create 1000 docs via Sync Gateway
5. Bulk create 1000 docs via SDK
6. Get all docs via Sync Gateway and save revisions
7. Store original version vectors for SG docs (optional)
8. Get all docs via SDK and verify count
9. Delete half of the docs randomly via Sync Gateway
10. Verify deleted docs visible in changes feed with new revision
11. Verify non-deleted docs still accessible
12. Verify new version vectors for deleted docs (optional)
13. Purge all docs via Sync Gateway
14. Verify SG can't see any docs after purge
15. Verify XATTRS are gone using changes feed
16. Verify SDK can't see any docs after purge
