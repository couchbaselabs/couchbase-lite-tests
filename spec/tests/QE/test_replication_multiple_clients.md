# Test Cases

## test_replication_with_multiple_client_dbs_and_single_sync_gateway_db

Test continuous bidirectional replication from multiple Couchbase Lite client databases to a single Sync Gateway database. This test verifies that multiple CBL clients can simultaneously replicate to the same SG database, and that documents from each client are properly replicated to SG and then distributed to all other clients.

### Steps
1. Create two client databases (db1 and db2)
2. Setup continuous push-pull replication from db1 to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push-and-pull
   * continuous: true
   * credentials: user1/pass
3. Setup continuous push-pull replication from db2 to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push-and-pull
   * continuous: true
   * credentials: user1/pass
4. Wait for both replicators to reach idle state
5. Add 100 documents to db1 with prefix 'ls_db1'
6. Add 100 documents to db2 with prefix 'ls_db2'
7. Wait for replicators to sync all documents
8. Verify all documents are present in Sync Gateway:
   * Should have: 100 docs from db1 + 100 docs from db2 = 200 total
9. Verify all documents have correct revision format
10. Verify all documents have correct version vector format (SGW 4.0+)
11. Verify documents in changes feed for Sync Gateway
12. Cleanup: delete Sync Gateway database
13. Cleanup: delete test server databases

## test_replication_with_10_attachments

Test continuous push replication of documents with multiple large attachments (2MB each) from Couchbase Lite to Sync Gateway. This test verifies that documents with many attachments can be successfully replicated and that all attachments are correctly transferred.

### Steps
1. Reset SG and configure database
2. Create client database
3. Start continuous push replication to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push
   * continuous: true
   * credentials: user1/pass
4. Wait for initial replication to reach idle state
5. Create 10 documents with multiple 2MB attachments each:
   * Each document has 20 attachments
   * Mix of small (s1-s10) and large (l1-l10) blobs
6. Verify documents were created in local database
7. Wait for replication to push all documents to Sync Gateway
8. Verify all documents are present in Sync Gateway
9. Verify all documents have correct revision format
10. Verify all documents have correct version vector format (SGW 4.0+)
11. Verify documents in Sync Gateway changes feed
12. Verify document content in Sync Gateway
13. Cleanup: delete Sync Gateway database
14. Cleanup: delete test server databases

