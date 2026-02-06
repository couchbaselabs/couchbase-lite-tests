# Blob Tests (Edge Server)

This document describes the tests for blob/attachment operations in Couchbase Lite Edge Server.

## test_blobs_create_delete

Test that adding a blob to a document on Edge Server replicates to Sync Gateway and that deleting the blob removes it from Sync Gateway.

1. Create a bucket on Couchbase Server and add 2 documents to the bucket; create a database on Sync Gateway and add role and user; create database `db` on Edge Server with replication from Sync Gateway; wait for idle.
2. Verify Sync Gateway and Edge Server each have 2 documents.
3. Retrieve document `doc_2` from Edge Server to get the latest revision ID.
4. Add blob `test.png` to the document using the revision ID.
5. Retrieve document `doc_2` from Sync Gateway and verify `_attachments` and document body contain the blob with correct metadata.
6. Delete blob `test.png` from the document on Edge Server using the revision ID from before the add.
7. Retrieve document `doc_2` from Sync Gateway and verify `_attachments` is not present.

## test_empty_blob

Test that an empty blob (zero-length body) can be added to a document and retrieved correctly.

1. Create a database `db` on Edge Server using config `test_edge_server_with_multiple_rest_clients.json`.
2. Create a document `doc_empty_blob` in Edge Server database `db`.
3. Retrieve the document to get the latest revision ID.
4. Add an empty blob with attachment name `test.png` to the document.
5. Retrieve the blob from the document and verify the blob body equals the empty bytes.

## test_blob_update

Test that adding a blob to a document on Edge Server replicates to Sync Gateway with correct blob metadata.

1. Create a bucket on Couchbase Server and add 2 documents; create a database on Sync Gateway and add role and user; create database `db` on Edge Server with replication from Sync Gateway; wait for idle.
2. Verify Sync Gateway and Edge Server each have 2 documents.
3. Retrieve document `doc_2` from Edge Server to get the latest revision ID.
4. Add blob `test.png` to the document using the revision ID.
5. Retrieve document `doc_2` from Sync Gateway and verify `_attachments` and document body contain the blob with content_type, digest, and length.

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

## test_blob_special_characters

Test that a blob with a special-character name can be added on Edge Server and replicates to Sync Gateway with correct metadata.

1. Create a bucket on Couchbase Server and add 2 documents; create a database on Sync Gateway and add role and user; create database `db` on Edge Server with replication from Sync Gateway; wait for idle.
2. Verify Sync Gateway and Edge Server each have 2 documents.
3. Retrieve document `doc_2` from Edge Server to get the latest revision ID.
4. Add a blob with attachment name `im@g#e$%&*().png` to the document using the revision ID.
5. Retrieve document `doc_2` from Sync Gateway and verify `_attachments` and document body contain the blob with correct metadata.
