# Test Users and Channels

## test_single_user_multiple_channels

Tests that a single user with access to multiple channels can correctly view and access documents distributed across those channels in a **multi-node Sync Gateway** setup. Documents are written in round-robin fashion across multiple SGW nodes (all pointing to a shared bucket) to verify proper distribution and replication.

### Steps

1. Create single shared bucket for all SGW nodes
2. Configure database 'db' on all 3 SGW nodes (pointing to shared bucket)
3. Create user 'vipul' with access to ['ABC', 'CBS', 'NBC', 'FOX'] (stored in shared bucket)
4. Bulk create 5000 documents in 5 batches using **round-robin across SGW nodes** (documents distributed across channels)
5. Wait for documents to propagate across all SGW nodes
6. Verify user sees all 5000 docs via changes feed from first SGW
7. Verify no duplicate documents in changes feed
8. Verify all expected document IDs are present
9. Verify user can retrieve all documents via _all_docs from any SGW node
10. Verify all documents have correct revision format (generation 1)
11. Verify all documents have correct version vector format (SGW 4.0+, optional)
12. Verify all documents are accessible from each SGW node independently
