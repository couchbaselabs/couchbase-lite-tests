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
