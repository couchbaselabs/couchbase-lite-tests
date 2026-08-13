# Test Cases

## #1 test_database_visible_across_sync_gateways

### Description

Tests that a Sync Gateway database created on one node of a 3-node Sync Gateway
cluster (all nodes sharing the same Couchbase Server bucket) becomes visible,
along with its documents, on the other two nodes without any additional setup.
Also tests that a resync operation, run after taking the database offline,
completes successfully and reprocesses the existing documents.

### Steps

1. Create a bucket on Couchbase Server with a scope1.col1 collection, and
   configure a Sync Gateway database endpoint backed by it on the first Sync
   Gateway.
2. Wait until the database is online on the first Sync Gateway.
3. Create a document via the first Sync Gateway.
4. Wait until the database is online on the second Sync Gateway.
5. Wait until the database is online on the third Sync Gateway.
6. Check that the document is visible via the second Sync Gateway.
7. Check that the document is visible via the third Sync Gateway.
8. Take the database offline via the first Sync Gateway.
9. Start a resync operation via the first Sync Gateway.
10. Wait until the resync operation completes, and check that the document was
    processed with no errors.
11. Bring the database back online via the first Sync Gateway.
12. Delete the database configuration via the first Sync Gateway.
13. Wait until the database is gone from all three Sync Gateways.

## #2 test_resync_simple

### Description

Runs a resync operation against a small, bucket-backed database using a
scope1.col1 collection. Parametrized on whether the sync function is changed
before the resync (`changed_sync_function` / `unchanged_sync_function`),
verifying the resync completes with no errors and processes every document in
both cases.

### Steps

1. Create a bucket-backed database using a scope1.col1 collection, and load a
   small number of documents.
2. (changed_sync_function only) Update the sync function.
3. Take the database offline.
4. Start a resync operation.
5. Wait until the resync operation completes.
6. Check that the resync processed all documents with no errors.

## #3 test_resync_stop_resume

### Description

Runs against a 3-node Sync Gateway cluster sharing one Couchbase Server
bucket. Reproduces a reported issue where stopping a resync operation and then
checking its status returns "completed" instead of "stopped" on a multi-node
cluster. Also reproduces a related issue where resuming a stopped resync
(without resetting it) can later report "completed" despite having
permanently skipped some documents (i.e. processed fewer documents than the
database actually contains). This test currently fails until the underlying
Sync Gateway bugs are fixed.

### Steps

1. Create a bucket-backed database using a scope1.col1 collection, with a large
   number of documents, update the sync function, and take the database
   offline.
2. Start a resync operation.
3. Check that the resync status is "running".
4. Stop the resync operation.
5. Check that the resync status is "stopped", and that it stopped before
   processing every document.
6. Resume the resync operation, without resetting it.
7. Wait until the resumed resync operation completes.
8. Check that the completed resync actually processed every document.
