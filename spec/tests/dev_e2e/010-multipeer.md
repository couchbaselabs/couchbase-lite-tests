# Test Cases

## test_medium_mesh_sanity

### Description

Test that if populating data on one device in a mesh, it replicates to all others.

### Steps

1. Reset local database and load `empty` dataset on all devices
2. Add 10 docs to the database on device 1
    - docID: doc<1-10>
    - body: {"random": <random-num>}
3. Start a multipeer replicator on all devices
    - peerGroupID: “com.couchbase.testing”
    - identity: anonymous
    - authenticator: accept-all (null)
    - collections: default collection
4. Wait for idle status on all devices except device 1
5. Check that all databases on devices other than 1 have identical content to the database on device 1

## test_medium_mesh_consistency

### Description

Test that if populating data on all devices in a mesh setup, all devices end up with the same data

### Steps

1. Reset local database and load `empty` dataset on all devices
2. Add 10 docs to the database on all devices
    - docID: doc<1-x> (10 per device)
    - body: {"random": <random-num>}
3. Start a multipeer replicator on all devices
    - peerGroupID: “com.couchbase.testing”
    - identity: anonymous
    - authenticator: accept-all (null)
    - collections: default collection
4. Wait for idle status on all devices
5. Check that all device databases have the same content

## test_rapid_availability_changes

### Description

Test that rapidly starting and stopping a multipeer replicator doesn't corrupt it, and
leaves it in an expected state

### Steps

`mode` = [start, stop]

1. Reset local database and load `empty` dataset on two devices
2. Start a multipeer replicator on each device
    - peerGroupID: “com.couchbase.testing”
    - identity: anonymous
    - authenticator: accept-all (null)
    - collections: default collection
3. Stop multipeer replicator 2 after 5 seconds
4. Start multipeer replicator 2 after 5 seconds
5. Repeat the above two steps 5 times
6. (If `mode` is stop) stop multipeer replicator 2 after 5 seconds
7. 
    a. If `mode` is `start`, verify that peer 2 is visible to peer 1
    b. If `mode` is `stop`, verify that peer 2 is not visible to peer 1
