# Test Cases

## #1 test_resync_simple

### Description

Runs a resync operation against a small, bucket-backed database using a
scope1.col1 collection. Parametrized on whether the sync function is changed
before the resync (`changed_sync_function` / `unchanged_sync_function`). Checks
that the resync completes with no errors and processes every document in both
cases.

### Steps

1. Create a bucket-backed database using a scope1.col1 collection, and load a
   small number of documents.
2. Take the database offline. For the changed_sync_function case, write the new
   sync function in the same config write.
3. Start a resync operation, discarding any previous progress.
4. Wait until the resync operation completes.
5. Check that the resync processed all documents with no errors.

## #2 test_resync_stop_resume

### Description

Runs against a 3-node Sync Gateway cluster sharing one Couchbase Server bucket.
Reproduces a reported issue where stopping a resync operation and then checking
its status returns "completed" instead of "stopped" on a multi-node cluster.
Also reproduces a related issue where resuming a stopped resync, without
resetting it, can later report "completed" despite having permanently skipped
some documents. Skipped here means that the resync processed fewer documents
than the database actually contains. This test currently fails until the
underlying Sync Gateway bugs are fixed.

Step 6 needs work left over at the moment the resync is stopped. Sync Gateway
honors a stop only once the resync's sharded DCP feed is up, about 20 seconds
in, so a small database finishes first and leaves nothing to resume. The test
buys time with a deliberately slow sync function. Sync Gateway runs sync
functions in otto, which exposes no sleep, so the sync function spins on
Date.now() instead, timed in milliseconds so that it holds on a faster machine.

That is a best effort, not a guarantee: resync processes documents
concurrently, so the delay per document does not become wall clock one for one.
When the resync finishes anyway, the test skips the resume steps. It does not
fail them, because setting up a partial resync is a precondition here rather
than the behavior under test.

### Steps

1. Create a bucket-backed database using a scope1.col1 collection, load
   documents, then take the database offline and write the slow sync function in
   the same config write.
2. Start a resync operation, discarding any previous progress.
3. Check that the resync status is "running" on the node that started it.
   Resync status is node-local until CBG-5817. Skip the rest when the resync
   finished first.
4. Stop the resync operation.
5. Check that the resync status is "stopped".
6. Check that the resync has work left to resume. Skip the rest when it does
   not.
7. Resume the resync operation, without discarding progress.
8. Wait until the resumed resync operation completes.
9. Check that the completed resync actually processed every document.
