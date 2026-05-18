# Chaos Tests (Edge Server)

This document describes the chaos and resilience tests for Couchbase Lite Edge Server.

## test_kill_sgw_mid_replication

Test replication behavior while Sync Gateway connectivity is interrupted mid-workload.

1. Configure the `travel` dataset in Sync Gateway and Couchbase Server.
2. Update the Edge Server config to use the SGW replication URL as the source.
3. Configure Edge Server with the `travel` database.
4. Wait for replication to become idle.
5. Delete all documents in `travel.hotels` on Edge Server using a bulk delete.
6. Verify `travel.hotels` is empty on both Edge Server and Sync Gateway.
7. Create 10,000 documents in `travel.hotels` via bulk create on Edge Server.
8. Wait for replication to become idle and verify counts match on Edge Server and SGW.
9. Update all documents and apply firewall deny rules to block SGW.
10. Perform another update while SGW is blocked, then allow SGW and wait for idle.
11. Verify document counts match and reset Edge Server firewall rules.

## test_3_edge_with_sync

Test multi-edge synchronization and recovery with chained replications.

1. Configure Edge Server 1 with the `travel` dataset.
2. Configure Edge Server 2 to replicate from Edge Server 1.
3. Configure Edge Server 3 to replicate from Edge Server 2.
4. Reconfigure Edge Server 1 to replicate from Edge Server 3 (loop).
5. Delete all documents in `travel.hotels` on Edge Server 1.
6. Verify `travel.hotels` is empty on Edge Servers 1, 2, and 3.
7. Create 1,000 documents in `travel.hotels` on Edge Server 1 and wait for idle.
8. Verify document counts match across Edge Servers 1, 2, and 3.
9. Kill Edge Server 1, update documents via Edge Servers 2/3, and verify replication.
10. Kill Edge Servers 1 and 3, update documents via Edge Server 2, and verify replication.

## test_edge_server_offline_sync_and_recovery

Test the offline synchronization and recovery capabilities of a chained Edge Server topology.

1. Configure Edge Server 1 to replicate from Sync Gateway for the `travel` dataset.
2. Configure Edge Server 2 to replicate from Edge Server 1.
3. Configure Edge Server 3 to replicate from Edge Server 2.
4. Wait for replication to become idle across all Edge Servers.
5. Delete all documents in the `travel.hotels` collection on Edge Server 3 using a bulk delete.
6. Wait for replication to become idle, then kill Edge Server 3.
7. Verify the documents are deleted in Edge Server 1, Edge Server 2, and Sync Gateway.
8. Restart Edge Server 3 and wait for it to come online.
9. Create 10,000 documents in `travel.hotels` via bulk create on Edge Server 3.
10. Verify documents are created on Edge Server 3 and wait for replication to become idle.
11. Kill Edge Server 3 again.
12. Verify the created documents propagated successfully to Edge Server 2, Edge Server 1, and Sync Gateway.

## test_edge_server_with_concurrent_rest_requests

Test the stability and consistency of Edge Server under a randomized concurrent REST CRUD workload.

1. Configure Edge Server with a database named `db`.
2. Seed the database with 10,000 documents using bulk create operations.
3. Verify the initial document load is successful and document counts match.
4. Run a randomized CRUD workload for 1,000 iterations containing a mix of create, update, delete, and read operations.
5. Perform final data consistency validation by verifying the documents on Edge Server match the expected state tracked locally.