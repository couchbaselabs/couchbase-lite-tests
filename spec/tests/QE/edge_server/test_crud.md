# CRUD Tests (Edge Server)

This document describes the tests for basic CRUD and information retrieval operations in Couchbase Lite Edge Server.

## test_basic_information_retrieval

Test retrieving basic server information from Edge Server.

1. Get a reference to the first Edge Server instance.
2. Retrieve the server version information.
3. Log the raw version string.

## test_database_config

Test retrieving database configuration and information from Edge Server.

1. Get a reference to the first Edge Server instance.
2. Fetch all databases from the Edge Server.
3. Select the first database from the list.
4. Fetch detailed database information for the selected database.
5. Verify that database information is returned.

## test_single_doc_crud

Test basic CRUD operations for a single document.

1. Get a reference to the first Edge Server instance.
2. Create a document with an auto-generated ID in database `db`.
3. Fetch the created document and verify the body and revision.
4. Create a document with a fixed ID.
5. Update the document with a new body and verify the updated fields.
6. Delete the document and verify retrieval fails.

## test_sub_doc_crud

Test CRUD operations on sub-documents.

1. Get a reference to the first Edge Server instance.
2. Create a document with an auto-generated ID in database `db`.
3. Insert a sub-document at key `test_key` with a sample value.
4. Fetch the sub-document and verify the stored value.
5. Delete the sub-document and verify retrieval fails.

## test_single_doc_crud_ttl

Test CRUD operations with document expiry (TTL).

1. Get a reference to the first Edge Server instance.
2. Create a document with TTL=20 seconds and verify retrieval fails after expiry.
3. Create a document with TTL=50 seconds, update it with TTL=20 seconds, and verify retrieval fails after expiry.
4. Create a document with TTL=60 seconds and delete it, then verify retrieval fails.
