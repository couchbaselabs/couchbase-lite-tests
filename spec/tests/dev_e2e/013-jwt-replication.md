# Test Cases

These tests validate Edge Server (ES) ; Sync Gateway (SGW) replication using
JWT (OIDC) authentication, covering inline tokens, file-based tokens, and token
rotation (valid, invalid, and corrupt) while replication is active.

Each test signs its own RS256 JWTs with a locally generated RSA key pair (see
`jwt_helper.py`) and registers the matching public JWK with SGW's `local_jwt`
provider. The JWT `sub` claim maps to the SGW user `test-provider_user1`.

## test_jwt_replication_reconnect_false

### Description

Test that ES can replicate with SGW using a static JWT token provided inline in
the ES config (`reconnect_on_token_change=false`, no file watching).

### Steps

1. Clean up any `travel` database on SGW and `travel` bucket on CBS from prior runs.
2. Generate an RSA key pair and sign a JWT token (`sub=user1`, `exp=3600s`).
3. Create the `travel` bucket on CBS with the `travel.airlines` collection.
4. Create the SGW `travel` database with a `local_jwt` provider registering the public JWK
    (`issuer=test-issuer`, `client_id=edge-server`, `algorithms=[RS256]`, `register=true`).
5. Add the JWT user `test-provider_user1` with `["*"]` channel access to `travel.airlines`.
6. Insert 5 documents into CBS (`jwt_test_airline_1..5`) with `channels=["*"]`.
7. Wait until SGW has imported all 5 documents from CBS.
8. Verify the JWT token authenticates against the SGW REST API (`GET /travel/` with `Authorization: Bearer <token>` returns 200).
9. Configure and start ES with the inline JWT token in `auth.openid_token` and `reconnect_on_token_change=false`.
10. Verify the replicator was created (`/_replicate` is non-empty), then wait until it is idle.
11. Verify ES has replicated at least the expected documents (pre-loaded dataset + the 5 new docs).
12. Fetch one document from ES and verify it is retrievable and has a `name` field.

## test_replication_with_jwt_file

### Description

Test that ES can replicate with SGW using a JWT token read from a file on the ES
host (`auth.openid_token.path`), across all `travel` collections.

### Steps

1. Generate an RSA key pair and sign a JWT token (`sub=user1`, `exp=600s`).
2. Clean up any existing `travel` database on SGW and flush the CBS `travel` bucket.
3. Create the SGW `travel` database with a `local_jwt` provider registering the public JWK,
    with sync functions for all 5 collections (`airlines`, `airports`, `hotels`, `landmarks`, `routes`).
4. Add the JWT user `test-provider_user1` with `["*"]` channel access to all 5 collections.
5. Load the `travel` dataset into SGW.
6. Write the JWT token to a file on the ES host (`/home/ec2-user/cert/jwt.txt`).
7. Configure and start ES with `auth.openid_token.path` pointing at the JWT file, syncing all 5 collections.
8. Wait until replication is idle.
9. For each of the 5 collections, verify document parity between ES and SGW (equal row counts).

## test_token_rotation_reconnect

### Description

Test that ES detects a change to the JWT file (via file watching) and reconnects
with the new token when `reconnect_on_token_change=true`, so replication
continues uninterrupted.

### Steps

1. Generate two RSA key pairs (A and B) and sign Token-A (`kid=test-key-1`) and Token-B (`kid=test-key-2`), both `sub=user1`.
2. Clean up any existing `travel` database on SGW and drop the CBS `travel` bucket.
3. Create the `travel` bucket and `travel.airlines` collection on CBS.
4. Create the SGW `travel` database with a `local_jwt` provider registering both public JWKs (A and B).
5. Add the JWT user `test-provider_user1` with `["*"]` channel access to `travel.airlines`.
6. Insert 5 documents into CBS (`rotation_test_1..5`).
7. Write Token-A to the JWT file on the ES host.
8. Configure and start ES with `auth.openid_token.path` and `reconnect_on_token_change=true`, syncing `travel.airlines`.
9. Wait until the initial replication with Token-A is idle, and verify ES pulled at least 5 documents.
10. Rotate the token: overwrite the JWT file with Token-B.
11. Insert 5 more documents into CBS (`rotation_test_6..10`).
12. Poll ES until it has at least `initial_count + 5` documents, confirming replication reconnected and continued with Token-B.

## test_invalid_token_rotation_causes_401_stop

### Description

Test that when the JWT file is overwritten mid-replication with an invalid token
(signed by a key not registered with SGW), ES reconnects, SGW rejects with 401,
and the replicator permanently stops (no retry, since 401 is not transient).

### Steps

1. Generate an RSA key pair and sign a valid token; generate a second key pair and sign an invalid token (`kid=unknown-key`) whose key is **not** registered with SGW.
2. Clean up any existing `travel` database on SGW.
3. Create the `travel` bucket and `travel.airlines` collection on CBS.
4. Create the SGW `travel` database with a `local_jwt` provider registering **only** the valid public JWK.
5. Add the JWT user `test-provider_user1` with `["*"]` channel access to `travel.airlines`.
6. Insert 3 documents into CBS (`disconnect_test_1..3`).
7. Write the valid token to the JWT file and start ES with `reconnect_on_token_change=true`.
8. Wait until replication is idle (confirming the valid token works).
9. Overwrite the JWT file with the invalid token.
10. Poll (up to 60s) the ES `/_replicate` list until the task is removed or its status becomes `Stopped`/`Offline`.
11. Verify the outcome: either the replicator task was removed (permanent stop after 401), or its status is `Stopped`/`Offline` with a 401 auth error.

## test_corrupt_token_file_content_mid_replication

### Description

Test ES behavior when the JWT file is overwritten mid-replication with corrupt
content (a single space, which is not a valid JWT). ES either stops replication
on reconnect (401) or keeps the existing connection alive if the file watcher
does not treat the content as a valid change.

### Steps

1. Generate an RSA key pair and sign a valid token.
2. Clean up any existing `travel` database on SGW.
3. Create the `travel` bucket and `travel.airlines` collection on CBS.
4. Create the SGW `travel` database with a `local_jwt` provider registering the public JWK.
5. Add the JWT user `test-provider_user1` with `["*"]` channel access to `travel.airlines`.
6. Insert 3 documents into CBS (`filedel_test_1..3`).
7. Write the valid token to the JWT file and start ES with `reconnect_on_token_change=true`.
8. Wait until replication is idle.
9. Overwrite the JWT file with invalid content (a single space).
10. Poll (up to 30s) the ES `/_replicate` list until the task is removed or its status becomes `Stopped`/`Offline`.
11. Verify the outcome: the task was removed or `Stopped`/`Offline` (corrupt token rejected), or `Idle` (ES kept the existing connection because the file watcher did not treat the change as a valid token). Any other status fails the test.

## test_valid_invalid_valid_token_cycle

### Description

Test the full lifecycle valid &rarr; invalid &rarr; valid. A valid token replicates;
an invalid token causes a permanent 401 stop (and destroys the file watcher);
writing a new valid token has no effect until replication is manually
re-triggered, after which it recovers.

### Steps

1. Generate key pairs A, C (valid) and one invalid key. Sign Token-A (`kid=test-key-1`), Token-C (`kid=test-key-3`), and an invalid token (`kid=bad-key`), all `sub=user1`.
2. Clean up any existing `travel` database on SGW and drop the CBS `travel` bucket.
3. Create the `travel` bucket and `travel.airlines` collection on CBS.
4. Create the SGW `travel` database with a `local_jwt` provider registering public JWKs A and C (not the invalid key).
5. Add the JWT user `test-provider_user1` with `["*"]` channel access to `travel.airlines`.
6. Insert 3 documents into CBS (`cycle_test_1..3`).
7. **Phase 1:** Write Token-A to the JWT file, start ES with `reconnect_on_token_change=true`, wait until idle, and verify at least 3 documents replicated.
8. **Phase 2:** Overwrite the JWT file with the invalid token. Poll (up to 60s) until the replicator is removed or `Stopped`/`Offline`, confirming a permanent 401 stop.
9. Insert 3 more documents into CBS (`cycle_test_4..6`) while replication is stopped, and verify ES still has only the original document count.
10. **Phase 3:** Write Token-C to the JWT file, then manually re-trigger replication (re-run `configure_dataset`, which calls `/_replicate`).
11. Wait until replication is idle and verify ES now has at least `initial_count + 3` documents (recovery succeeded with Token-C).
