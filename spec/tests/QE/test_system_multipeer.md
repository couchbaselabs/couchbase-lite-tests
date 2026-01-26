# System Multipeer Tests

This document describes the system-level multipeer replication tests for Couchbase Lite.

## test_system

Test long-running multipeer replication with periodic CRUD and device restarts.

1. Verify CBL version >= 3.3.0 and Android/iOS platform on all devices.
2. Reset local database `db1` on all devices.
3. Generate 1,000 documents and insert them into device 1 in batches.
4. Start multipeer replicators on all devices:
   * peerGroupID: `couchtest`
   * identity: anonymous
   * authenticator: accept-all (null)
   * collections: `_default._default`
5. Run the test for 24 hours with a CRUD cycle every 5 minutes:
   * Randomly insert, update, delete documents on random devices.
   * Randomly stop and restart a subset of devices (up to 50%).
6. After each cycle, wait for all devices to reach idle without errors.
7. Verify all devices have identical document content after each cycle.
8. Stop all multipeer replicators.

## test_volume_with_blobs

Test large-scale multipeer replication with documents containing blobs.

1. Verify CBL version >= 3.3.0 and Android/iOS platform on all devices.
2. Reset local database `db1` on all devices.
3. Generate 100,000 documents and insert them into device 1 in batches.
4. Attach a random blob from the provided blob list to each document.
5. Start multipeer replicators on all devices:
   * peerGroupID: `couchtest`
   * identity: anonymous
   * authenticator: accept-all (null)
   * collections: `_default._default`
6. Wait for all devices to reach idle without errors (extended timeout).
7. Verify all devices have identical document content.
8. Stop all multipeer replicators.

## test_multipeer_end_to_end

Test end-to-end replication across Couchbase Server, Sync Gateway, and multipeer mesh.

1. Verify CBL version >= 3.3.0 and Android/iOS platform on all devices.
2. Reset SGW and load `names` dataset on two SGWs backed by two CB servers.
3. Reset local database `db1` on all devices (minimum 5 devices).
4. Start continuous push/pull replication:
   * Device 1 -> SGW1 (`/names`, `_default._default`)
   * Devices 4/5 -> SGW2 (`/names`, `_default._default`)
   * Use basic auth `user1/pass` and pinned SGW cert
5. Start multipeer replication among devices 1-4 using `couchtest` peer group.
6. Insert documents concurrently into:
   * Couchbase Server 1 and 2
   * Sync Gateway 1 and 2
   * Multiple CBL devices (batch updates)
   * Restart one multipeer device during operations
7. Wait for all replicators to reach idle without errors.
8. Verify all devices have identical document content.
9. Verify documents are replicated correctly to SGW1 and SGW2.
10. Stop all multipeer replicators and clean up test servers.
