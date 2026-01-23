# Database Configuration Tests (Edge Server)

This document describes database configuration validation tests for Couchbase Lite Edge Server.

## test_edge_server_incorrect_db_config

Test behavior when Edge Server is configured with an incorrect database config.

1. Configure Edge Server using an invalid DB config and verify version retrieval fails.
2. Update the config to create database `db` with collection `test`.
3. Reconfigure Edge Server and fetch database info for collection `test`.
4. Verify the collection is present in the response.
5. Attempt a REST write to the collection and verify it fails.
6. Reset the config to remove the invalid collection settings.
