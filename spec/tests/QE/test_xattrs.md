# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to SG and SDK channels
4. Write 1000 docs via Sync Gateway
5. Verify all SG docs were created successfully
6. Stop Sync Gateway
7. Update 1000 SG docs via SDK
8. Write 1000 new docs via SDK
9. Restart Sync Gateway (recreate database endpoint)
10. Verify all docs are accessible via Sync Gateway
11. Verify all expected documents are present
12. Verify document revisions are correct
13. Verify document contents for sample documents

