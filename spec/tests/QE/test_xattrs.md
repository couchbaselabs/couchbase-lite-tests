# XATTR Tests

## test_offline_processing_of_external_updates

Test that documents written by Sync Gateway can be updated via SDK and successfully imported back into Sync Gateway upon restart.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to SG and SDK channels
4. Write 1000 docs via Sync Gateway
5. Verify all SG docs were created successfully
6. Store original version vectors for SG docs (optional)
7. Stop Sync Gateway
8. Update 1000 SG docs via SDK
9. Write 1000 new docs via SDK
10. Restart Sync Gateway (recreate database endpoint)
11. Wait for Sync Gateway to import SDK documents
12. Verify all docs are accessible via Sync Gateway
13. Verify all expected documents are present
14. Verify document revisions are correct
15. Verify document contents for sample documents
16. Verify version vectors for updated SG documents (optional)
17. Verify version vectors exist for SDK documents (optional)
