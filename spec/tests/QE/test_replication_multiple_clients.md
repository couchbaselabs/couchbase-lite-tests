# Test Cases

## test_replication_with_multiple_client_dbs_and_single_sync_gateway_db

Test continuous bidirectional replication from multiple Couchbase Lite client databases (on separate test servers) to a single Sync Gateway database. This test verifies that multiple CBL clients running on different test servers can simultaneously replicate to the same SG database, and that documents from each client are properly replicated to SG and then distributed to all other clients.

### Steps
1. Create client database on test server 1
2. Create client database on test server 2
3. Setup continuous push-pull replication from db1 (test server 1) to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push-and-pull
   * continuous: true
   * credentials: user1/pass
4. Setup continuous push-pull replication from db2 (test server 2) to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push-and-pull
   * continuous: true
   * credentials: user1/pass
5. Wait for both replicators to reach idle state
6. Add 100 documents to db1 (test server 1) with prefix 'ls_db1'
7. Add 100 documents to db2 (test server 2) with prefix 'ls_db2'
8. Wait for replicators to sync all documents
9. Verify all documents are present in Sync Gateway:
   * Should have: 100 docs from db1 + 100 docs from db2 = 200 total
10. Verify all documents have correct revision format
11. Verify all documents have correct version vector format (SGW 4.0+)
12. Verify documents in changes feed for Sync Gateway

## test_replication_with_10_attachments

Test continuous push replication of documents with multiple large attachments (2MB each) from multiple Couchbase Lite clients (on separate test servers) to Sync Gateway. This test verifies that multiple clients can push documents with many attachments to the same SG database and that all attachments are correctly transferred.

### Steps
1. Create client database on test server 1
2. Create client database on test server 2
3. Start continuous push replication from db1 (test server 1) to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push
   * continuous: true
   * credentials: user1/pass
4. Start continuous push replication from db2 (test server 2) to Sync Gateway:
   * endpoint: `/names`
   * collections: `_default._default`
   * type: push
   * continuous: true
   * credentials: user1/pass
5. Wait for both replicators to reach idle state
6. Create 5 documents with multiple 2MB attachments in db1 (test server 1):
   * Each document has 20 attachments
   * Use small blobs (s1-s10)
7. Create 5 documents with multiple 2MB attachments in db2 (test server 2):
   * Each document has 20 attachments
   * Use large blobs (l1-l10)
8. Verify documents were created in db1 (test server 1)
9. Verify documents were created in db2 (test server 2)
10. Wait for replication to push all documents to Sync Gateway
11. Verify all documents are present in Sync Gateway:
    * Should have: 5 docs from db1 + 5 docs from db2 = 10 total
12. Verify all documents have correct revision format
13. Verify all documents have correct version vector format (SGW 4.0+)
14. Verify documents in Sync Gateway changes feed
15. Verify document content in Sync Gateway
