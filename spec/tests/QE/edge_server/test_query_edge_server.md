# Query Tests (Edge Server)

This document describes query and validation tests for Couchbase Lite Edge Server.

## test_named_queries

Test execution of a parameterized named query.

1. Configure Edge Server with the `names` dataset and named queries config.
2. Execute the `user_by_email` named query with a valid parameter.
3. Verify the response contains the expected user and a single result.

## test_adhoc_queries

Test execution of an ad-hoc parameterized query.

1. Configure Edge Server with the `names` dataset and named queries config.
2. Execute a parameterized ad-hoc query with filters and ordering.
3. Verify the first result matches the expected record fields.

## test_negative_scenarios

Test error handling for invalid query usage.

1. Configure Edge Server with ad-hoc queries disabled.
2. Execute a named query without required parameters and verify it fails.
3. Execute an ad-hoc query with ad-hoc disabled and verify it returns a forbidden error.

## test_query_on_expired_doc

Test named query behavior on expired documents.

1. Configure Edge Server with the `names` dataset and named queries config.
2. Create a document with a TTL of 30 seconds.
3. Wait for expiry and execute the `user_by_email` named query.
4. Verify the query returns no results.

## test_adhoc_queries_incorrect_field

Test ad-hoc query with an incorrect field selection.

1. Configure Edge Server with the `names` dataset and named queries config.
2. Execute an ad-hoc query selecting an incorrect field path.
3. Verify the response still matches the expected result fields.
