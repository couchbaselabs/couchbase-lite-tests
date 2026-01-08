# Blob Tests (Edge Server)

This document describes the tests for blob/attachment operations in Couchbase Lite Edge Server.

## test_blob_get_nonexistent

Test that retrieving a nonexistent blob from a document returns an error.

1. Create a document `doc_updation` in Edge Server database `db`.
2. Attempt to retrieve a nonexistent blob `missing_blob.png` from the document.
3. Verify that the operation fails with an error.

## test_blob_delete_nonexistent

Test that deleting a nonexistent blob from a document returns an error.

1. Create a document `doc_deletion` in Edge Server database `db`.
2. Retrieve the document to get the latest revision ID.
3. Attempt to delete a nonexistent blob `missing_blob.png` from the document.
4. Verify that the operation fails with an error.

## test_blob_update_incorrect_rev

Test that updating a blob with an incorrect revision ID returns an error.

1. Create a document `doc_updation` in Edge Server database `db`.
2. Retrieve the document to get the latest revision ID.
3. Add a blob `test.png` to the document using the correct revision ID.
4. Attempt to update the blob with an incorrect revision ID.
5. Verify that the operation fails with an error.

## test_blob_put_nonexistent_doc

Test that adding a blob to a nonexistent document returns an error.

1. Attempt to add a blob `test.png` to a nonexistent document `doc_blob` with a fabricated revision ID.
2. Verify that the operation fails with an error.

## test_multiple_blobs_same_doc

Test adding multiple blobs to the same document.

1. Create a document `doc_blob` in Edge Server database `db`.
2. Retrieve the document to get the latest revision ID.
3. Add first blob `test.png` to the document.
4. Retrieve the document again to get the updated revision ID.
5. Add second blob `test2.png` to the document.
6. Verify both blob additions succeed.

## test_blob_exceeding_maxsize

Test that adding a blob exceeding the maximum allowed size returns an HTTP 413 error.

1. Create a document `doc_blob` in Edge Server database `db`.
2. Retrieve the document to get the latest revision ID.
3. Attempt to add a large blob `20mb.jpg` (exceeds max size) to the document.
4. Verify that the operation fails with HTTP 413 status code.
