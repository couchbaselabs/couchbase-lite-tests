# TTL and Expires Tests (Edge Server)

This document describes the tests for TTL (Time To Live) and document expiration features in Couchbase Lite Edge Server.

## test_ttl_5s

Test document expiration using TTL (relative seconds) format.

1. Create a document `ttl_doc` with TTL of 5 seconds in Edge Server database `db`.
2. Verify the document exists immediately after creation.
3. Wait 5 seconds for the document to expire.
4. Attempt to retrieve the document and verify it fails (document expired).

## test_expires_5s

Test document expiration using absolute Unix timestamp format.

1. Calculate expiration timestamp (current time + 5 seconds).
2. Create a document `ttl_doc` with the expires timestamp in Edge Server database `db`.
3. Verify the document exists immediately after creation.
4. Wait 5 seconds for the document to expire.
5. Attempt to retrieve the document and verify it fails (document expired).

## test_update_ttl

Test updating the TTL of an existing document.

1. Create a document `ttl` with TTL of 30 seconds in Edge Server database `db`.
2. Verify the document exists immediately after creation.
3. Retrieve the document to get the current revision ID.
4. Update the document with a new TTL of 5 seconds.
5. Wait 5 seconds for the document to expire.
6. Attempt to retrieve the document and verify it fails (document expired with updated TTL).

## test_ttl_expires

Test behavior when both TTL and expires are provided - the lower value should take precedence.

1. **Test Case 1: TTL < expires**
   * Create document `ttl_expires_doc` with TTL=10s and expires=current+30s
   * Verify document exists immediately
   * Wait 10 seconds
   * Verify document is expired (TTL took precedence)
2. **Test Case 2: expires < TTL**
   * Create document `ttl_expires_doc2` with TTL=60s and expires=current+10s
   * Verify document exists immediately
   * Wait 10 seconds
   * Verify document is expired (expires took precedence)

## test_ttl_non_existent_document

Test that updating TTL of a non-existent document returns an error.

1. Attempt to update a non-existent document `ttl_doc` with a fabricated revision ID and TTL of 5 seconds.
2. Verify that the operation fails with 404 Not Found.

## test_bulk_documents_ttl

Test TTL expiration behavior with multiple documents having different TTL values.

1. Create 100 documents concurrently with different TTL values:
   * 50 documents `ttl_doc_1` to `ttl_doc_50` with TTL: 10 seconds
   * 25 documents `ttl_doc_51` to `ttl_doc_75` with TTL: 30 seconds
   * 25 documents `ttl_doc_76` to `ttl_doc_100` with TTL: 60 seconds
2. Verify initial document count matches total successfully created documents.
3. After 10 seconds:
   * Verify 10s TTL documents are expired
   * Verify remaining count = 50 (25 @ 30s + 25 @ 60s)
4. After 30 seconds total:
   * Verify 30s TTL documents are expired
   * Verify remaining count = 25 (only 60s TTL documents)
5. After 60 seconds total:
   * Verify all documents are expired
   * Verify document count = 0
