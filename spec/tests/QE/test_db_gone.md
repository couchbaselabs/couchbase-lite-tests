# Database Gone Tests

Note: "offline" has a specific meaning in Sync Gateway (a database administratively
taken offline via the admin API — see the Sync Gateway "Take Databases Offline"
docs). These tests cover a different situation: the Couchbase Server bucket backing
a database is deleted, so the database is *gone* — it no longer exists and all REST
API endpoints reject requests.

## test_db_gone_on_bucket_deletion

Test that a database is gone when its bucket is deleted.

This test verifies that when the Couchbase Server bucket backing a Sync Gateway database is deleted, the database becomes unavailable (“gone” from a client perspective) and REST API endpoints reject requests (typically 403; sometimes 503).

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create 10 docs via Sync Gateway
4. Verify database is available - REST endpoints work
5. Delete bucket to sever connection
6. Verify database is gone - REST endpoints reject requests (403/503)

## test_multiple_dbs_bucket_deletion

Test that deleting specific buckets makes only those databases go away.

This test creates 4 databases with unique buckets, deletes 2 buckets, and verifies that only those 2 databases are gone while the other 2 remain available.

1. Create buckets and configure databases
2. Create 10 docs via Sync Gateway
3. Verify all databases are online
4. Delete buckets for db1 and db3 and wait for those databases to be gone
5. Verify db2 and db4 remain available
6. Verify db1 and db3 are gone (return 403/503)
