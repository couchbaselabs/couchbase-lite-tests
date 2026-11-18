# Test Users and Channels

## test_single_user_multiple_channels

Tests that a single user with access to multiple channels can correctly view and access documents distributed across those channels in a **multi-node Sync Gateway** setup. Documents are written in round-robin fashion across multiple SGW nodes (all pointing to a shared bucket) to verify proper distribution and replication.

### Steps

1. Configure database 'db' on all 3 SGW nodes (pointing to shared bucket)
2. Create user 'vipul' with access to ['ABC', 'CBS', 'NBC', 'FOX'] (stored in shared bucket)
3. Bulk create 5000 documents in 50 batches of 100 docs using **round-robin across SGW nodes** (documents distributed across channels)
4. Wait for the user changes feed on the first SGW to show all 5000 docs
5. Verify user can retrieve all documents via _all_docs from one SGW node
6. Verify all documents have correct revision format (generation 1)
7. Verify all documents have correct version vector format (SGW 4.0+, optional)
8. Verify all documents are accessible from each SGW node independently
