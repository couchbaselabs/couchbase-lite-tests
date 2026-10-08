# Session Replication Tests (Edge Server)

## test_basic_auth_push_pull

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Create 5 local docs, and replicate as `rw` with basic auth.
3. Verify the 5 docs are on Edge Server and the seeded doc was pulled.

## test_session_auth_push_pull

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Create 5 local docs, and replicate with a session as `rw`.
3. Verify the 5 docs are on Edge Server and the seeded doc was pulled.

## test_session_auth_continuous_live_changes

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Start a continuous replicator with a session as `rw`, and wait for idle.
3. Write a doc on Edge Server and a doc locally.
4. Verify both docs cross while the replicator stays error-free.

## test_one_time_false_gives_no_session

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Verify POST /travel/_session?one_time=false as `rw` is rejected with 400.
3. Create a local doc, and replicate with no credentials.
4. Verify the replicator is refused and nothing crossed in either direction.

## test_reused_session_rejected

### Steps

1. Start Edge Server, seed one doc per collection, and reset local databases `db1` and `db2`.
2. Replicate `db1` with a session as `rw`.
3. Create a local doc in `db2`, and replicate `db2` with the same session.
4. Verify the replicator is refused and nothing crossed in either direction.
5. Verify `db2` replicates with a new session, and its doc is pushed.

## test_session_for_other_database_rejected

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Replicate `travel` with a session for `names` as `admin_user`.
3. Verify the replicator is refused and nothing was pulled.
4. Create a local doc, and push it to `names` with the same session.
5. Verify the push succeeded.

## test_invalid_session_rejected

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Create a local doc, and replicate with the case's session.
3. Verify the replicator is refused and nothing crossed in either direction.

## test_restart_revokes_sessions

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Mint a session as `rw`, then restart Edge Server.
3. Verify a replicator with the session is refused and nothing was pulled.

## test_second_replicator_needs_its_own_session

### Steps

1. Start Edge Server, seed one doc per collection, and reset local databases `db1` and `db2`.
2. Start a continuous replicator on `db1` with a session as `rw`, and wait for idle.
3. Verify a replicator on `db2` with the same session is refused.
4. Write a doc on Edge Server, and verify the first replicator still pulls it without error.

## test_read_only_session_cannot_push

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Create 3 local docs, and push and pull with a session as read-only `ro`.
3. Verify the replicator is refused as pull-only (403) and none of the docs reached Edge Server.

## test_read_only_session_can_pull

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Pull with a session as read-only `ro`.
3. Verify the pull succeeded and the seeded doc was pulled.

## test_collection_grants_apply_to_session

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Pull both collections with a session as `coll`, and verify both seeded docs arrive.
3. Push a doc to `travel.hotels` with a new session, and verify it lands.
4. Push a doc to `travel.airlines` with a new session, and verify it does not land.

## test_admin_session_has_full_access

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Create a local doc in each collection, and replicate both with a session as `admin_user`.
3. Verify the replicator succeeded and both collections synced both ways.

## test_session_limited_to_granted_database

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Verify `other_db` is refused a session for `travel` with 403.
3. Create a local doc, and push it to `names` with a session as `other_db`.
4. Verify the push succeeded, and the doc is on `names` and not on `travel`.

## test_no_access_user_gets_no_session

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Verify `none` is refused a session for `travel` with 403.
3. Verify replicating as `none` with basic auth fails, and nothing was pulled.

## test_write_only_session_cannot_sync

### Steps

1. Start Edge Server, seed one doc per collection, and reset the local database.
2. Mint a session as write-only `wo`, which may be refused with 403.
3. Create a local doc, and push and pull with the session.
4. Verify the replicator is refused and nothing crossed in either direction.