# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Configure Sync Gateway database endpoint
2. Create user 'vipul' with access to SG and SDK channels
3. Bulk create 1000 docs via Sync Gateway
4. Verify all SG docs were created successfully and store revisions, versions
5. Stop Sync Gateway
6. Update all SG docs via SDK
7. Write 1000 new docs via SDK
8. Restart Sync Gateway (recreate database endpoint)
9. Verify revisions, versions and contents of all documents

## test_purge

Test purging functionality with XATTR-based documents created via both Sync Gateway and SDK.

1. Configure Sync Gateway database endpoint
2. Create user 'vipul' with access to channels
3. Bulk create 1000 docs via Sync Gateway
4. Bulk create 1000 docs via SDK
5. Get all docs via Sync Gateway and save revisions
6. Store original version vectors for SG docs (optional)
7. Get all docs via SDK and verify count
8. Delete half of the docs randomly via Sync Gateway
9. Verify deleted docs visible in changes feed with new revision
10. Verify non-deleted docs still accessible
11. Verify new version vectors for deleted docs (optional)
12. Purge all docs via Sync Gateway
13. Verify SG can't see any docs after purge
14. Verify XATTRS are gone using changes feed
15. Verify SDK can't see any docs after purge

## test_sg_sdk_interop_unique_docs

Test Sync Gateway and SDK interoperability with unique documents and multiple updates.

1. Configure Sync Gateway with default sync function
2. Create user 'vipul' with access to SDK and SG channels
3. Bulk create 10 docs via SDK
4. Bulk create 10 docs via Sync Gateway
5. Verify SDK sees all docs
6. Verify user 'vipul' sees all docs via _changes (public API)
7. Bulk update sdk docs 10 times via SDK
8. Verify SDK docs don't contain _sync metadata
9. Bulk update sg docs 10 times via Sync Gateway
10. Verify SDK sees all doc updates
11. Verify 'vipul' sees all doc updates via _all_docs (public API)
12. Verify SDK docs still don't contain _sync after updates
13. Bulk delete sdk docs via SDK
14. Bulk delete sg docs via Sync Gateway
15. Verify SDK sees all docs as deleted
16. Verify 'vipul' sees all docs as deleted via _changes (public API)

## test_sg_sdk_interop_shared_docs

Test concurrent updates and deletes from both Sync Gateway and SDK on shared documents.

1. Configure Sync Gateway with default sync function
2. Create user 'vipul' with access to shared channel
3. Bulk create 10 docs via SDK with tracking properties
4. Bulk create 10 docs via SG with tracking properties
5. Verify SDK sees all docs
6. Verify 'vipul' sees all docs via _all_docs (public API)
7. Perform concurrent updates (10 per doc) from SDK and SG
8. Verify all documents have correct update counts
9. Perform concurrent deletes from SDK and SG
10. Verify all docs deleted from SDK side
11. Verify 'vipul' sees all docs as deleted via _changes (public API)

## test_sync_xattrs_update_concurrently

Test concurrent xattr updates and xattr-based channel assignment.

1. Configure Sync Gateway with custom sync function using xattrs
2. Create users 'vipul', 'lupiv' with access to 'abc', 'xyz'
3. Create 20 docs via SDK with xattr 'channel1=abc'
4. Wait for SG to import all docs (as admin)
5. Verify user 'vipul' can see all docs in channel 'abc'
6. Concurrently update xattrs to 'xyz' while querying docs
7. Delete _sync xattrs to force complete re-processing
8. Restart Sync Gateway to force re-import with updated xattrs
9. Verify user 'lupiv' can now see all docs
10. Verify user 'vipul' can no longer see any docs
