# Peer-to-Peer Tests

This document describes the test cases for Couchbase Lite peer-to-peer URLEndpointListener replication, covering concurrent updates, various topology setups (one-to-many, many-to-one), multiple databases, and server failure/restart scenarios.

## test_peer_to_peer_concurrent_replication

Test peer-to-peer replication between a listener and a client, including concurrent document updates on both devices while replication is active.

1. Reset local databases and create `db1` on Device-1 and Device-2.
2. Start listener on Device-1:
   * database: `db1`
   * collections: `["_default._default"]`
   * port: 59840
3. Add `num_of_docs` documents to `db1` on Device-2.
4. Setup and start a replicator on Device-2:
   * endpoint: Device-1's listener URL
   * collections: `["_default._default"]`
   * type: `replicator_type`
   * continuous: `continuous`
5. Wait for replication to complete (Target activity: IDLE if continuous, STOPPED if not).
6. Check that all documents are replicated correctly and both databases have the same content.
7. Perform concurrent updates to documents on both the listener (Device-1) and the client (Device-2).
8. Wait for replication to complete after the updates.
9. Check that all updated documents are replicated correctly and databases match.
10. Stop the listener on Device-1.

## test_peer_to_peer_oneClient_toManyServers

Test a peer-to-peer topology where a single client device replicates concurrently to multiple listener servers (one-to-many).

1. Reset local databases and create `db1` on Device-1, Device-2, and Device-3.
2. Add `num_of_docs` documents to `db1` on Device-1.
3. Start listeners on Device-2 and Device-3 (database: `db1`, collections: `["_default._default"]`, port: 59840).
4. Setup and start Replicator 1 on Device-1 pointing to Device-2's listener endpoint.
5. Setup and start Replicator 2 on Device-1 pointing to Device-3's listener endpoint.
6. Wait for both Replicator 1 and Replicator 2 to complete replication.
7. Check that all documents are replicated correctly across all three databases.
8. Stop the listeners on Device-2 and Device-3.

## test_peer_to_peer_oneServer_toManyClients

Test a peer-to-peer topology where multiple client devices replicate concurrently from a single listener server (many-to-one).

1. Reset local databases and create `db1` on Device-1, Device-2, and Device-3.
2. Add `num_of_docs` documents to `db1` on Device-1.
3. Start a listener on Device-1 (database: `db1`, collections: `["_default._default"]`, port: 59840).
4. Setup and start a Replicator on Device-2 pointing to Device-1's listener endpoint.
5. Setup and start a Replicator on Device-3 pointing to Device-1's listener endpoint.
6. Wait for both replicators on Device-2 and Device-3 to complete.
7. Check that all documents are replicated correctly across all three databases.
8. Stop the listener on Device-1.

## test_peer_to_peer_oneServer_twoClients_on_single_db

Test peer-to-peer replication behavior when multiple distinct replication sessions are established from a single client database to the same listener endpoint.

1. Reset local databases and create `db1` on Device-1 and Device-2.
2. Add `num_of_docs` documents to `db1` on Device-1.
3. Start a listener on Device-1 (database: `db1`, collections: `["_default._default"]`, port: 59840).
4. Setup and start three separate replicator sessions on Device-2, all using Device-2's `db1` and pointing to Device-1's listener endpoint.
5. Wait for replication to complete on all 3 sessions.
6. Check that all documents are replicated correctly and both databases match.
7. Stop the listener on Device-1.

## test_peer_to_peer_replication_with_multiple_dbs

Test concurrent peer-to-peer replication scaling across multiple databases (DB1, DB2, DB3) on two devices.

1. Create and reset 3 local databases (`db1`, `db2`, `db3`) on Device-1 and Device-2.
2. Add `num_of_docs` documents to each of the 3 databases on Device-1.
3. Start 3 listeners on Device-2, one for each database:
   * `db1` on port 59840
   * `db2` on port 59841
   * `db3` on port 59842
4. Setup and start 3 separate replicators on Device-1 corresponding to each database, pointing to their respective listener endpoints on Device-2.
5. Wait for replication to complete on all 3 replicator sessions.
6. Check that all documents are replicated correctly across all database pairs (Device-1 DBs match Device-2 DBs).
7. Stop all 3 listeners on Device-2.

## test_peer_to_peer_with_server_down

Test the resilience of peer-to-peer replication when the listener server goes offline and is restarted during active client database updates.

1. Reset local databases and create `db1` on Device-1 and Device-2.
2. Add `num_of_docs` documents to `db1` on Device-2.
3. Start a listener on Device-1 (database: `db1`, collections: `["_default._default"]`, port: 59840).
4. Setup and start a replicator on Device-2 pointing to Device-1's listener endpoint.
5. Asynchronously execute the following actions concurrently:
   * Stop the listener on Device-1.
   * Start a new listener on Device-1 on the same port, re-using the previous TLS identity.
   * Perform document updates on Device-2.
6. Restart the replicator on Device-2 if necessary, and wait for replication to complete.
7. Check that all updated documents are successfully replicated to Device-1 despite the listener restart.
8. Stop the new listener on Device-1.