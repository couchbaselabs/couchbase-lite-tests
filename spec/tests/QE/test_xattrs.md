# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to SG and SDK channels
4. Bulk create 1000 docs via Sync Gateway
5. Verify all SG docs were created successfully and store revisions, versions
6. Stop Sync Gateway
7. Update all SG docs via SDK
8. Write 1000 new docs via SDK
9. Restart Sync Gateway (recreate database endpoint)
10. Verify revisions, versions and contents of all documents

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

## test_sg_sdk_interop_unique_docs

Test Sync Gateway and SDK interoperability with unique documents and multiple updates.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to sdk and sg channels
4. Bulk create 10 docs via SDK
5. Bulk create 10 docs via Sync Gateway
6. Verify SDK sees all docs
7. Verify SG sees all docs via _all_docs
8. Verify SG sees all docs via _changes
9. Bulk update sdk docs 10 times via SDK
10. Verify SDK docs don't contain _sync metadata
11. Bulk update sg docs 10 times via Sync Gateway
12. Verify SDK sees all doc updates
13. Verify SG sees all doc updates via _all_docs
14. Verify SDK docs still don't contain _sync after updates
15. Bulk delete sdk docs via SDK
16. Bulk delete sg docs via Sync Gateway
17. Verify SDK sees all docs as deleted
18. Verify SG sees all docs as deleted via _changes
