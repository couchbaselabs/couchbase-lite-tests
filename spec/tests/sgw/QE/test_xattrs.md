# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Configure Sync Gateway with test database
2. Create bucket and default collection
3. Configure Sync Gateway database endpoint
4. Create user 'seth' with access to SG and SDK channels
5. Write 1000 docs via Sync Gateway
6. Verify all SG docs were created successfully
7. Stop Sync Gateway
8. Update 1000 SG docs via SDK
9. Write 1000 new docs via SDK
10. Restart Sync Gateway (recreate database endpoint)
11. Verify all docs are accessible via Sync Gateway
12. Verify all expected documents are present
13. Verify document revisions are correct
14. Verify document contents for sample documents

