# Peer-to-Peer Topology Tests

This document describes the peer-to-peer topology tests for Couchbase Lite, testing legacy peer-to-peer functionality in different topology setups (mesh and loop) without Sync Gateway.

## test_peer_to_peer_topology_mesh

Test legacy peer-to-peer functionality with mesh topology setup where each peer replicates to all other peers in phases.

**Parameters:**
- `num_of_docs`: Number of documents to create (10 or 100)
- `continuous`: Whether replication is continuous (True or False)
- `replicator_type`: Type of replication (e.g., "push_pull")

<br>

**Steps:**
1. Verify CBL version >= 2.8.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. **PHASE 1**: Peer 1 -> Peers [2, 3]
   - Add `num_of_docs` documents to the database on peer 1:
     * Documents named: `phase1-peer1-doc1`, `phase1-peer1-doc2`, ..., `phase1-peer1-doc{num_of_docs}`
     * Each document contains a random integer value
   - Start listeners on peers 2 and 3:
     * database: `db1` (on each target peer)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicators from peer 1 to peers 2 and 3:
     * endpoint: replication URL for each target peer's listener
     * collections: `_default._default`
     * type: `replicator_type` (e.g., "push_pull")
     * continuous: `continuous`
   - Start replication from peer 1 to peers 2 and 3.
   - Wait for replication from peer 1 to complete:
     * Target activity: IDLE if continuous, otherwise STOPPED
   - Check that all device databases have the replicated documents after phase 1:
     * All databases should have the same content
   - Stop listeners after phase 1.
4. **PHASE 2**: Peer 2 -> Peers [1, 3]
   - Add `num_of_docs` documents to the database on peer 2:
     * Documents named: `phase2-peer2-doc1`, `phase2-peer2-doc2`, ..., `phase2-peer2-doc{num_of_docs}`
   - Start listeners on peers 1 and 3:
     * database: `db1` (on each target peer)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicators from peer 2 to peers 1 and 3.
   - Start replication from peer 2 to peers 1 and 3.
   - Wait for replication from peer 2 to complete.
   - Check that all device databases have the replicated documents after phase 2.
   - Stop listeners after phase 2.
5. **PHASE 3**: Peer 3 -> Peers [1, 2]
   - Add `num_of_docs` documents to the database on peer 3:
     * Documents named: `phase3-peer3-doc1`, `phase3-peer3-doc2`, ..., `phase3-peer3-doc{num_of_docs}`
   - Start listeners on peers 1 and 2:
     * database: `db1` (on each target peer)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicators from peer 3 to peers 1 and 2.
   - Start replication from peer 3 to peers 1 and 2.
   - Wait for replication from peer 3 to complete.
   - Check that all device databases have the replicated documents after phase 3.
   - Stop listeners after phase 3.

## test_peer_to_peer_topology_loop

Test legacy peer-to-peer functionality with loop topology setup where each peer replicates to the next peer in a circular chain.

**Parameters:**
- `num_of_docs`: Number of documents to create (10 or 100)
- `continuous`: Whether replication is continuous (True or False)
- `replicator_type`: Type of replication (e.g., "push_pull" or "pull")

<br>

**Steps:**
1. Verify CBL version >= 2.8.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. **PHASE 1**: Peer 1 -> Peer 2
   - Add `num_of_docs` documents to the database on peer 1:
     * Documents named: `phase1-peer1-doc1`, `phase1-peer1-doc2`, ..., `phase1-peer1-doc{num_of_docs}`
     * Each document contains a random integer value
   - Start listener on peer 2:
     * database: `db1` (on peer 2)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicator from peer 1 to peer 2:
     * endpoint: replication URL for peer 2's listener
     * collections: `_default._default`
     * type: `replicator_type` (e.g., "push_pull" or "pull")
     * continuous: `continuous`
   - Start replication from peer 1 to peer 2.
   - Wait for replication from peer 1 to peer 2 to complete:
     * Target activity: IDLE if continuous, otherwise STOPPED
   - Verify that peer 1 and peer 2 have the same content after phase 1:
     * Source and target databases should match
   - Stop listener after phase 1.
4. **PHASE 2**: Peer 2 -> Peer 3
   - Add `num_of_docs` documents to the database on peer 2:
     * Documents named: `phase2-peer2-doc1`, `phase2-peer2-doc2`, ..., `phase2-peer2-doc{num_of_docs}`
   - Start listener on peer 3:
     * database: `db1` (on peer 3)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicator from peer 2 to peer 3.
   - Start replication from peer 2 to peer 3.
   - Wait for replication from peer 2 to peer 3 to complete.
   - Verify that peer 2 and peer 3 have the same content after phase 2.
   - Stop listener after phase 2.
5. **PHASE 3**: Peer 3 -> Peer 1
   - Add `num_of_docs` documents to the database on peer 3:
     * Documents named: `phase3-peer3-doc1`, `phase3-peer3-doc2`, ..., `phase3-peer3-doc{num_of_docs}`
   - Start listener on peer 1:
     * database: `db1` (on peer 1)
     * collections: `["_default._default"]`
     * port: 59840
   - Setup replicator from peer 3 to peer 1.
   - Start replication from peer 3 to peer 1.
   - Wait for replication from peer 3 to peer 1 to complete.
   - Verify that peer 3 and peer 1 have the same content after phase 3.
   - Stop listener after phase 3.
6. Verify all device databases have converged to the same content after all phases:
   * All three peers should have identical content
   * All documents from all phases should be present on all peers

