# Session Tests (Edge Server)

This document describes tests for the Couchbase Lite Edge Server `_session` endpoint
(`POST`/`GET`/`DELETE /{db}/_session`), driven entirely over REST. Sessions exist so the CBL
JavaScript SDK can authenticate a `_blipsync` WebSocket upgrade, where the token is presented
as the subprotocol entry `SyncGatewaySession_<token>`. Token *use* at that upgrade is covered
by the CBL JS session tests, which require a browser; these tests cover what REST can observe.

All tests use the `admin_user` / `password` credentials and the `test_session.json` config,
which must declare users — otherwise the client sends no credentials and the authentication
tests pass without testing anything.

## test_create_session_both_modes

Test that both session modes mint a token under their own response key.

1. Configure Edge Server with the `names` dataset and the session config.
2. Create a one-time session by posting to `/{db}/_session?one_time=true` as the admin user,
   and verify a token is returned under `one_time_session_id`.
3. Create a reusable session by posting to `/{db}/_session?one_time=false` as the same user,
   and verify a token is returned under `session_id`.
4. Verify both tokens are non-empty strings with no surrounding whitespace.
5. Verify the two tokens differ from each other, confirming the `one_time` query parameter is
   not being ignored.
6. Revoke the session.

## test_tokens_are_unique

Test that every session creation yields a fresh token, sequentially and under concurrency.

1. Configure Edge Server with the `names` dataset and the session config.
2. Create three reusable sessions for the admin user, one after another.
3. Create ten more reusable sessions for the same user concurrently.
4. Verify all thirteen tokens are non-empty.
5. Verify all thirteen tokens are distinct. A sequential collision means tokens are reused
   outright; a collision only under concurrency indicates unsynchronised access to the
   in-memory session map.
6. Revoke the session.

## test_session_endpoints_reject_bad_credentials

Test that all three session verbs require valid credentials.

1. Configure Edge Server with the `names` dataset and the session config.
2. For each verb (`create`, `get`, `delete`), attempt the call with the admin username and an
   incorrect password, and verify it returns 401.
3. For each verb, attempt the call as a user that does not exist, and verify it returns 401
   rather than 404 — a distinct status for an unknown account would let a caller enumerate
   users.
4. For each verb, attempt the call with no credentials, and verify it returns 401. Anonymous
   `DELETE` matters most: the endpoint takes no token, so without authentication any caller
   could log out an arbitrary user.

## test_non_admin_can_create_own_session

Test that creating a session is not an administrative action.

1. Configure Edge Server with the `names` dataset and the session config.
2. Add a non-admin user through the Edge Server manager, which restarts the process.
3. Take a fresh admin client, since the previous one predates the restart.
4. Create a reusable session for the non-admin user with their own credentials.
5. Verify a non-empty token is returned. If this required admin rights, a browser client could
   never log itself in, which is the endpoint's whole purpose.
6. Revoke the non-admin user's session.

## test_session_endpoints_reject_unknown_database

Test that sessions are scoped to a database that exists.

1. Configure Edge Server with the `names` dataset and the session config.
2. For each verb (`create`, `get`, `delete`), attempt the call against `nosuchdb` with valid
   admin credentials.
3. Verify `create` and `get` fail with a client error (401, 403 or 404). A 2xx would mean
   tokens can be minted, or session state read, for a keyspace that does not exist.
4. Verify `delete` either fails with a client error or completes quietly, since the client
   deliberately swallows 404 so teardown never fails on an already-gone session.

## test_get_session_reports_authenticated_caller

Test that `GET /{db}/_session` reports the caller identified by Basic auth.

1. Configure Edge Server with the `names` dataset and the session config.
2. Add a second user through the Edge Server manager, before any session is created — the
   restart inside the add would otherwise drop them.
3. Take a fresh admin client, since the previous one predates the restart.
4. Create a reusable session for the admin user, and another for the second user.
5. Request `GET /{db}/_session` as the admin user and verify the response reports `ok` as true
   with `userCtx.name` equal to `admin_user`.
6. Request `GET /{db}/_session` as the second user and verify `userCtx.name` equals that user.
   Two users are checked because a single caller cannot distinguish a per-request identity
   from one global session echoed back to everyone.
7. Revoke both sessions.
