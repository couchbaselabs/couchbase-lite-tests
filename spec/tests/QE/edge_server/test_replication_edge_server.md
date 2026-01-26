# Replication Tests (Edge Server)

This document describes replication tests between Edge Server and Sync Gateway, and Edge Server to Edge Server.

## test_edge_to_sgw_replication

Test Edge Server replication to Sync Gateway with validation and TTL behavior.

1. Configure the `travel` dataset on Sync Gateway and Couchbase Server.
2. Update Edge Server config to use SGW replication URL as the source.
3. Configure Edge Server with the `travel` database and wait for idle.
4. For each `travel` collection, verify document counts and IDs match SGW.
5. Update `airline_10000` via Edge Server with TTL=30 seconds.
6. Verify the update propagated to SGW.
7. Wait for TTL expiry and verify the document remains on SGW.
8. Verify the document is purged on Edge Server.
9. Stop replication.

## test_edge_to_edge_replication

Test Edge-to-Edge replication with validation and TTL behavior.

1. Configure Edge Server 1 with the `travel` dataset using primary config.
2. Configure Edge Server 2 to replicate from Edge Server 1.
3. Wait for replication to become idle.
4. For each `travel` collection, verify document counts and IDs match.
5. Update `airline_10000` via Edge Server 2 with TTL=30 seconds.
6. Verify the update propagated to Edge Server 1.
7. Wait for TTL expiry and verify the document remains on Edge Server 1.
8. Verify the document is purged on Edge Server 2.
9. Stop replication.
