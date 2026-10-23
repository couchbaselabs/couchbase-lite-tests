# Test Cases

Authentication between CBL and Sync Gateway for each replicator credential mode: session ID,
bearer token (JWT), and anonymous/GUEST. Bearer token tests run only on CBL JS, because only the
JS test server implements bearer auth. All other tests run on every platform.

## #1 test_replicate_with_session_auth

### Description
One-shot replication succeeds on a session ID, for each replicator type.

### Steps
1. Reset SG and load `travel` dataset
2. Reset local database and load `travel` dataset
3. Write `session-doc` to the local `travel.airports` collection
4. Create a session for `user1`
5. Start a replicator
   * endpoint: `/travel`
   * collections: `travel.airports`
   * type: push / pull / pushAndPull
   * continuous: false
   * credentials: session for `user1`
6. Wait until the replicator stops and check there is no error
7. Check that all documents are replicated correctly

## #2 test_replicate_with_invalid_session

### Description
A session ID that Sync Gateway never issued is rejected.

### Steps
1. Reset SG and load `travel` dataset
2. Reset local database and load `travel` dataset
3. Start a pull replicator with a session ID Sync Gateway never issued
4. Check the replicator stops with an auth error

## #3 test_concurrent_session_identities

### Description
Two sessions for users with disjoint channel access replicate at the same time without
either receiving the other's documents. The replicators have no channel filter, so only
each session's identity decides what it receives.

### Steps
1. Reset SG and load `names` dataset
2. Create `alice` with access to `alice-only` and `bob` with access to `bob-only`
3. Write `alice-doc` to `alice-only` and `bob-doc` to `bob-only` on SG
4. Reset two empty local databases, `db_alice` and `db_bob`
5. Start a pull replicator per user, each on its own session, with no channel filter
   * collections: `_default._default`
6. Wait until both replicators stop and check there is no error
7. Check `db_alice` holds only `alice-doc` and `db_bob` holds only `bob-doc`

## #4 test_replicate_with_bearer_token

### Description
One-shot replication succeeds on a JWT validated by a `local_jwt` provider.

### Steps
1. Create an empty SG `travel` database with a `local_jwt` provider and its user
2. Reset local database with an empty `travel.airports` collection
3. Write `jwt-doc` on SG
4. Start a pull replicator with a valid JWT
5. Wait until the replicator stops and check there is no error
6. Check that all documents are replicated correctly

## #5 test_replicate_with_bad_bearer_token

### Description
A JWT that is wrong in exactly one way is rejected. Parametrized over: expired, wrong
issuer, signed with an unpublished key, unsigned (`alg: none`), and not a JWT at all.

### Steps
1. Create an empty SG `travel` database with a `local_jwt` provider and its user
2. Reset local database with an empty `travel.airports` collection
3. Start a pull replicator with a JWT that is wrong in exactly one way
4. Check the replicator stops with an auth error

## #6 test_anonymous_replication_rejected

### Description
A replicator with no authenticator is rejected when the GUEST user is disabled.

### Steps
1. Reset SG and load `travel` dataset
2. Disable the GUEST user
3. Reset local database and load `travel` dataset
4. Start a pull replicator with no authenticator
5. Check the replicator stops with an auth error

## #7 test_guest_replication_allowed

### Description
A replicator with no authenticator syncs when the GUEST user is enabled, and receives only
the documents in the GUEST user's channel. The positive counterpart to #6.

### Steps
1. Reset SG and load `travel` dataset
2. Enable the GUEST user with access to the `United States` channel
3. Reset local database and load `travel` dataset
4. Start a replicator
   * endpoint: `/travel`
   * collections: `travel.airports`
   * type: pull
   * continuous: false
   * credentials: none
5. Wait until the replicator stops and check there is no error
6. Check `db1` holds exactly the `travel.airports` documents SG serves to the GUEST user

## #8 test_session_revoked_during_continuous_replication

### Description
Deleting a session does not disturb a replication already established on it, because Sync
Gateway authenticates at connect time. The deletion is confirmed separately, so continued
replication cannot be explained by a no-op delete.

### Steps
1. Reset SG and load `travel` dataset
2. Reset local database and load `travel` dataset
3. Start a continuous push-and-pull replicator on a session for `user1`
4. Wait until the replicator is idle
5. Delete the session and check SG rejects it for new requests
6. Write `post-revocation-doc` on SG
7. Check the document arrives and the replicator stays idle

## #9 test_jwt_user_revoked_during_continuous_replication

### Description
Deleting the user a JWT maps to stops that identity receiving documents on an established
replication. A signed JWT cannot be revoked, so deleting the user is the only way to
withdraw access before the token expires.

### Steps
1. Create an empty SG `travel` database with a `local_jwt` provider and its user
2. Reset local database with an empty `travel.airports` collection
3. Start a continuous push-and-pull replicator with a valid JWT
4. Wait until the replicator is idle
5. Delete the user the JWT maps to and write `post-jwt-revocation-doc` on SG
6. Check the replicator stops on an auth error and the document never arrives

## #10 test_expired_jwt_then_fresh_token

### Description
An expired JWT is rejected, and a fresh JWT then replicates on the same database.

### Steps
1. Create an empty SG `travel` database with a `local_jwt` provider and its user
2. Reset local database with an empty `travel.airports` collection
3. Start a one-shot push-and-pull replicator with an expired JWT
4. Check the replicator stops with an auth error
5. Write `jwt-doc` on SG
6. Start a new continuous push-and-pull replicator with a fresh JWT
7. Check the replicator pulls `jwt-doc`

## #11 test_sgw_restart_during_replication

### Description
A continuous replicator reconnects on the same credentials after Sync Gateway restarts:
an outage must not be treated as an auth failure. Parametrized over a session and a JWT,
since sessions are stored in the bucket while a JWT is checked against the provider config
on every connection. Requires the shell2http sidecar; skipped without it.

### Steps
1. Create the SG `travel` database and session / jwt credentials
   * session: load the `travel` dataset and create a session for `user1`
   * jwt: create an empty `travel` database with a `local_jwt` provider and its user
2. Reset local database with an empty `travel.airports` collection
3. Start a continuous push-and-pull replicator and wait until it is idle
4. Stop SG and wait until the replicator is offline
5. Start SG and write `post-restart-session` / `post-restart-jwt` on it
6. Check the replicator reconnects on the same credentials and the document arrives