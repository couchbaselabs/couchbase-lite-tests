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