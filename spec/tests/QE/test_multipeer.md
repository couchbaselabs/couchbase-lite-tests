# Multipeer Tests

This document describes the multipeer replication tests for Couchbase Lite, testing multipeer replication functionality with multiple devices.

## test_large_mesh_sanity

Test basic multipeer mesh replication sanity with a small number of documents.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Add 20 documents to the database on device 1:
   * Documents named: `doc1`, `doc2`, ..., `doc20`
   * Each document contains a random integer value
4. Start multipeer replicator on all devices:
   * peer_id: `"mesh-test"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
5. Wait for idle status on all devices:
   * timeout: 60 seconds
   * Verify no replicator errors
6. Check that all device databases have the same content:
   * All databases should have identical documents
7. Stop multipeer replicator on all devices.

## test_large_mesh_consistency

Test multipeer mesh replication consistency with documents added on all devices.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Add 50 documents to the database on all devices:
   * Each device adds documents with naming pattern: `device{device_idx}-doc{doc_num}`
   * Each document contains a random integer value
   * Total documents across all devices: 50 * number_of_devices
4. Start multipeer replicator on all devices:
   * peer_id: `"mesh-test"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
5. Wait for idle status on all devices:
   * timeout: 300 seconds
   * Verify no replicator errors
6. Check that all device databases have the same content:
   * All databases should have identical documents from all devices
7. Stop multipeer replicator on all devices.

## test_scalable_conflict_resolution

Test scalable conflict resolution using merge conflict resolver in multipeer mesh replication.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Insert conflict1 on each device with its unique key in 'counter':
   * Document ID: `conflict1`
   * Format: `{"counter": {"deviceX": X}}`
   * Each device adds its own device key with device number as value
4. Start multipeer replication with merge conflict resolver:
   * peer_id: `"couchtest"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
   * conflict_resolver: `merge-dict` with property `counter`
5. Wait for idle status on all devices:
   * timeout: 60 seconds
   * Verify no replicator errors
6. Verify conflict1 is resolved identically on all devices with all device keys:
   * All devices should have the same document with all device keys merged
   * Each key's value must match the device_id
   * Retry up to 5 times if revision IDs don't match initially
7. Stop multipeer replicator on all devices.

## test_network_partition

Test network partition scenarios with peer groups in multipeer mesh replication.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Verify we have 6-15 devices for this test.
4. Dynamically split devices into 3 groups:
   * Group 1: first portion of devices
   * Group 2: middle portion of devices
   * Group 3: remaining devices
5. Add unique documents to each peer group:
   * Group 1: documents named `group1-doc1`, `group1-doc2`, ... (100 docs total)
   * Group 2: documents named `group2-doc1`, `group2-doc2`, ... (100 docs total)
   * Group 3: documents named `group3-doc1`, `group3-doc2`, ... (100 docs total)
   * Documents distributed across devices in each group
6. Start multipeer replicators with different peer groups:
   * Group 1 replicators: peer_id `"group1"`
   * Group 2 replicators: peer_id `"group2"`
   * Group 3 replicators: peer_id `"group3"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
7. Wait for initial replication within each group:
   * timeout: 300 seconds
   * Verify no replicator errors
8. Verify groups are isolated from each other:
   * Each group should only see peers within its own group
   * Group 1 should only see Group 1 peers
   * Group 2 should only see Group 2 peers
   * Group 3 should only see Group 3 peers
9. Verify each group can see its own documents:
   * Group 1 devices should have 100 documents (group1-doc*)
   * Group 2 devices should have 100 documents (group2-doc*)
   * Group 3 devices should have 100 documents (group3-doc*)
10. Stop group 2 replicators and restart with group 1's peer ID:
    * Stop all group 2 replicators
    * Restart group 2 replicators with peer_id `"group1"`
11. Wait for replication between group 1 and group 2:
    * timeout: 300 seconds
    * Verify no replicator errors
12. Verify group 1 and group 2 devices have combined documents:
    * Combined group should have 200 documents (100 from group1 + 100 from group2)
13. Stop group 3 replicators and restart with group 1's peer ID:
    * Stop all group 3 replicators
    * Restart group 3 replicators with peer_id `"group1"`
14. Wait for replication across all groups:
    * timeout: 300 seconds
    * Verify no replicator errors
15. Verify all devices have all documents:
    * All devices should have 300 documents total (100 from each group)
    * All databases should have identical content
16. Stop all multipeer replicators.

## test_dynamic_peer_addition_removal

Test dynamic peer addition and removal during active replication in multipeer mesh.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Verify we have at least 6 devices for this test.
4. Calculate device distribution:
   * Initial devices: at least 3, up to half of total devices
   * Additional devices: up to 3 additional devices
   * Devices to remove: 1-2 devices
5. Add documents to initial devices:
   * Each device adds 20 documents
   * Documents named: `device{device_idx}-doc{doc_num}`
6. Start multipeer replicator on initial devices:
   * peer_id: `"dynamic-mesh"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
7. Wait for some initial replication progress:
   * Wait for at least half of initial devices to reach idle
   * timeout: 300 seconds
   * Verify no replicator errors
8. Add additional devices to the mesh:
   * Add 20 documents to each additional device
   * Documents named: `device{device_idx}-doc{doc_num}`
9. Start replicators on additional devices:
   * peer_id: `"dynamic-mesh"` (same as initial devices)
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
10. Wait a short time for replication to start (2 seconds).
11. Remove random devices from the mesh while replication is active:
    * Randomly select 1-2 devices to remove (mix of initial and additional)
    * Stop replicators on selected devices
12. Wait for remaining devices to stabilize after removal:
    * timeout: 300 seconds
    * Verify no replicator errors
13. Verify remaining devices achieve full data consistency:
    * All remaining devices should have the same document count
    * All databases should have identical content
14. Stop all remaining multipeer replicators.

## test_large_document_replication

Test multipeer mesh replication with large documents containing blobs.

1. Verify CBL version >= 3.3.0 on all test servers.
2. Reset local database and load `empty` dataset on all devices.
3. Add 10 large documents with xl1.jpg blob to the database on device 1:
   * Documents named: `large_doc1`, `large_doc2`, ..., `large_doc10`
   * Each document contains a blob: `{"image": "xl1.jpg"}`
4. Start multipeer replicator on all devices:
   * peer_id: `"large-doc-mesh"`
   * database: `db1` (on each device)
   * collections: `["_default._default"]`
5. Wait for idle status on all devices:
   * timeout: 200 seconds
   * Verify no replicator errors
6. Check that all device databases have the same content:
   * Each device should have exactly 10 documents
   * All databases should have identical content including blobs
7. Stop multipeer replicator on all devices.