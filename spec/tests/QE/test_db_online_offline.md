# Database Online/Offline Tests

## test_db_offline_on_bucket_deletion

Test that database goes offline when its bucket is deleted.

This test verifies that when the Couchbase Server bucket backing a Sync Gateway database is deleted, the database properly enters offline state and all REST API endpoints return 503 (Service Unavailable).

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to ['ABC']
4. Create 10 docs via Sync Gateway
5. Verify database is online - REST endpoints work
6. Delete bucket to sever connection
7. Verify database is offline - REST endpoints return 403

## test_multiple_dbs_bucket_deletion

Test that deleting specific buckets causes only those databases to go offline.

This test creates 4 databases with unique buckets, deletes 2 buckets, and verifies that only those 2 databases go offline while the other 2 remain online.

1. Create buckets and configure databases
2. Create 10 docs via Sync Gateway
3. Verify all databases are online
4. Delete buckets for db1 and db3
5. Verify db2 and db4 remain online
6. Verify db1 and db3 are offline (return 403)
