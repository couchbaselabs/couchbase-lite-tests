# Authentication Tests (Sync Gateway)

This document describes authentication tests between Couchbase Lite and Sync Gateway,
covering every credential mode the CBL JS replicator supports: Basic, Bearer (JWT/OIDC),
Session ID, legacy cookie mode, and anonymous/GUEST. The suite is written against CBL JS but the assertions fork on server variant,
so it runs unchanged on the native platforms.

The tests are split across two classes:

* **`TestSessionSyncGateway`** drives Sync Gateway's session API directly. It carries no
  `min_test_servers` marker, so it runs in any topology with a Sync Gateway and can
  catch session regressions before the JS SDK's session support lands.
* **`TestSessionAuthReplication`** exercises the CBL replicator and requires a test
  server.

## TestSessionSyncGateway

## test_admin_session_creation

Create a session for an existing user via the admin API.

1. Reset SG and load the `names` dataset.
2. Create a session for `user1` via `POST /{db}/_session` on the admin port.
3. Verify a non-empty `session_id` is returned.
4. Verify `cookie_name` is `SyncGatewaySession`.
5. Revoke the session.

## test_public_login_valid_credentials

Exchange valid credentials for a session on the public port.

1. Reset SG and load the `names` dataset.
2. Create `user1` with access to all channels.
3. Log in via `POST /{db}/_session` on the public port.
4. Verify a non-empty `session_id` is returned.
5. Verify `GET /{db}/_session` resolves `userCtx.name` to `user1`.

## test_public_login_invalid_credentials

Verify that all three failing credential shapes return 401.

1. Reset SG and load the `names` dataset.
2. Create `user1`.
3. Attempt public login with a wrong password and verify 401.
4. Attempt public login as a nonexistent user and verify 401 — specifically not 404,
   which would leak whether the account exists.
5. Attempt public login with no credentials and verify 401.

## test_logout_invalidates_session

Verify a session resolves to its owner, and stops doing so after logout.

1. Reset SG and load the `names` dataset.
2. Create `user1` and mint a session.
3. Verify `GET /{db}/_session` resolves `userCtx.name` to `user1`.
4. Log out via `DELETE /{db}/_session`.
5. Verify the session is now rejected with 401.

## test_session_dies_with_user

Verify deleting a user invalidates the sessions issued to them.

1. Reset SG and load the `names` dataset.
2. Create user `doomed` and mint a session for them.
3. Delete the user.
4. Verify the orphaned session is rejected with 401.

## test_session_reflects_current_grants

Verify a session carries the user's grants as of use time, not as of issue time.

If Sync Gateway snapshotted channel access into the session, revoking a channel would
not take effect until the session expired — a real authorization hole, and worth an
explicit test rather than an assumption.

1. Reset SG and load the `names` dataset.
2. Create `user1` with access to `channel-a` and `channel-b`, and mint a session.
3. Verify the session reports `channel-b`.
4. Revoke `channel-b` from the user.
5. Verify the existing session no longer reports `channel-b`.

## test_malformed_session_token

Verify garbage in the session cookie is a clean 401, never a 500.

Covers a non-token string, an empty value, a path-traversal attempt, and a 4096-character
value.

1. Reset SG and load the `names` dataset.
2. For each malformed value, present it as the session cookie.
3. Verify each is rejected with 401 — specifically not 500, which would mean Sync Gateway
   crashed on a bad token rather than rejecting it.

## test_session_revocation

Verify sessions can be revoked individually and per user.

1. Reset SG and load the `names` dataset.
2. Create three sessions for `user1` and verify all three IDs are distinct.
3. Revoke the first by ID via `DELETE /{db}/_session/{sid}`.
4. Verify the first is rejected and the other two still resolve to `user1`.
5. Revoke the rest via `DELETE /{db}/_user/{name}/_session`.
6. Verify all three are now rejected with 401.

## test_session_is_database_scoped

Verify a session minted against one database is not accepted by another.

1. Reset SG and load the `names` and `travel` datasets.
2. Create a session for `user1` against `names`.
3. Verify the session is accepted by `names`.
4. Verify the same session is rejected by `travel` with 401.

## TestSessionAuthReplication

## test_replicate_with_session_auth

Verify one-shot replication succeeds on a session token, in each direction.

Parametrized over `push`, `pull` and `pushAndPull`.

1. Reset SG and load the `travel` dataset.
2. Reset the local database and load the `travel` dataset.
3. Create a session for `user1`.
4. Start a replicator:
   * endpoint: `/travel`
   * collections: `travel.airlines`
   * type: the parametrized type
   * continuous: false
   * credentials: session token for `user1`
5. Wait for the replicator to stop and verify there is no error.
6. Verify all documents replicated correctly.
7. Revoke the session.

## test_replicate_with_invalid_session

Verify a well-formed but unissued session token is rejected with a 401.

The token used is legal as an HTTP token, so Sync Gateway will look it up and reject it
rather than the SDK refusing it locally.

1. Reset SG and load the `travel` dataset.
2. Reset the local database and load the `travel` dataset.
3. Start a pull replicator with a session token that was never issued.
4. Verify the replicator reaches `STOPPED` with a 401, and does not sit in `OFFLINE`
   retrying a credential that will never work.

## test_replicate_with_malformed_session

Verify a session ID that is not a legal WebSocket token is rejected locally, before any
network call.

CBL JS only. Parametrized over a comma, whitespace, a slash, and an empty string.

1. Reset SG and load the `travel` dataset.
2. Reset the local database and load the `travel` dataset.
3. Start a pull replicator with the malformed session ID.
4. Verify the replicator fails with **400**, not 401. A 401 would mean the malformed
   token was sent to Sync Gateway, and an unauthenticated request that looks like an
   auth failure is exactly the ambiguity these tests exist to remove.

## test_custom_cookie_name_unsupported

Verify CBL JS refuses a custom session cookie name with 501.

The cross-platform TDK spec has a `cookieName` field because the native platforms
implement SESSION as a `Cookie` header. A browser cannot set that header on a WebSocket
handshake, so CBL JS puts the session ID on the handshake subprotocol and has no cookie
to name. The test server refuses rather than silently ignoring the field — otherwise a
test asserting on a custom cookie name would pass without the name ever being honoured.

CBL JS only; the native platforms support custom cookie names.

1. Reset SG and load the `travel` dataset.
2. Reset the local database and load the `travel` dataset.
3. Mint a valid session, then pair it with the cookie name `MyAppSession`.
4. Verify `replicatorStart` is rejected with HTTP 501.

## test_replicate_with_bearer_token

Verify replication succeeds on a bearer token validated by a `local_jwt` provider.

Uses `local_jwt` rather than a full `oidc` provider so no external identity provider is
needed in the topology — the keypair is minted in-process by `shared/jwt_helper.py` and
its public JWK handed to Sync Gateway.

1. Reset SG and load the `travel` dataset.
2. Mint an RSA keypair and configure SG with a `local_jwt` provider using its public JWK.
3. Create the user the token's `sub` claim maps to.
4. Reset the local database and load the `travel` dataset.
5. Start a pull replicator with a `BEARER` authenticator carrying the signed JWT.
6. Verify the replicator stops with no error.

## test_replicate_with_bad_bearer_token

Verify every way a JWT can be wrong is rejected with a 401.

Parametrized over seven mutations, each changing exactly one claim or header so that a
rejection is attributable: expired, wrong issuer, wrong audience, bad signature (signed
with a key whose public half was never published), unknown `kid`, unsigned (`alg: none`),
and not a JWT at all.

1. Reset SG and load the `travel` dataset.
2. Configure SG with a `local_jwt` provider and create the mapped user.
3. Reset the local database and load the `travel` dataset.
4. Mint a token with the given mutation.
5. Start a pull replicator with it and verify a 401.

## test_anonymous_replication_rejected

Verify no authenticator against a guest-disabled database is rejected.

Note this is not the same as proving the connection was anonymous: in a browser an
existing session cookie on the origin can still ride along even with no credentials
configured. What this asserts is the outcome that matters — a database requiring auth
does not sync without it.

1. Reset SG and load the `travel` dataset with `guest.disabled` set to true.
2. Reset the local database and load the `travel` dataset.
3. Start a pull replicator with no authenticator.
4. Verify a 401.

## test_half_empty_basic_credentials_rejected

Guard the legacy cookie-mode boundary.

Only fully-empty Basic credentials select cookie mode; a half-empty credential still
sends a literal `Authorization: Basic` header with a blank half. The test server rejects
the half-empty case with 400 so that a test cannot think it is exercising the cookie path
when it is not.

CBL JS only.

1. Reset SG and load the `travel` dataset.
2. Reset the local database and load the `travel` dataset.
3. Start a pull replicator with `("user1", "")`, then with `("", "pass")`.
4. Verify `replicatorStart` is rejected with HTTP 400 in both cases.

## test_concurrent_session_identities

Verify two sessions with disjoint channel access replicate against the same endpoint
without leaking documents to each other.

This is the case that would catch a session token being cached or shared at the SDK or
transport layer — a plausible failure mode in a browser, where there is one cookie jar
per origin.

1. Reset SG and load the `names` dataset.
2. Create `alice` with access to `alice-only` and `bob` with access to `bob-only`.
3. Reset two local databases.
4. Create a session for each user.
5. Start both pull replicators against the same endpoint simultaneously, each filtered
   to its own channel.
6. Verify both replicators finish without an auth error.
