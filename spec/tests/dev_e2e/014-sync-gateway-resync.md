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

