# Session Tests (Edge Server and Sync Gateway)

This document describes tests for the `_session` endpoint (`POST`/`GET`/`DELETE /{db}/_session`)
of Couchbase Lite Edge Server and of the Sync Gateway public API, driven entirely over REST.
Sessions exist so the CBL JavaScript SDK can authenticate a `_blipsync` WebSocket upgrade,
where the token is presented as the subprotocol entry `SyncGatewaySession_<token>`. Token *use* at that upgrade is covered
by the CBL JS session tests, which require a browser; these tests cover what REST can observe.

Every test runs once per backend:

- **Edge Server**: the `names` dataset and the `test_session.json` config. The primary user is
  `admin_user` / `password`. A user added through the Edge Server manager restarts the process,
  so the test then takes a fresh admin client.
- **Sync Gateway**: the `names` dataset. The primary user is `user1` / `pass` from
  `names-sg-config.json`, and a user is added through the admin API.

The backends differ in four ways that the tests account for:

- Sync Gateway returns a reusable session id in the `SyncGatewaySession` cookie, not under
  `session_id` in the body.
- Sync Gateway logs out only the session whose cookie the `DELETE` carries, so the client sends
  the cookie of the last reusable session it created.
- Sync Gateway answers an anonymous `GET` with 200 and a null `userCtx.name`, where Edge Server
  answers 401.
- Sync Gateway answers a repeat `DELETE` of a deleted session with 200, where Edge Server
  answers 404.

## test_create_session_both_modes

Test that both session modes mint a token under their own response key.

1. Configure the backend with the `names` dataset.
2. Create a one-time session by posting to `/{db}/_session?one_time=true` as the primary user,
   and verify a token is returned under `one_time_session_id`.
3. Create a reusable session by posting to `/{db}/_session?one_time=false` as the same user,
   and verify a token is returned (under `session_id`, or in the Sync Gateway cookie).
4. Verify both tokens are non-empty strings with no surrounding whitespace.
5. Verify the two tokens differ from each other, confirming the `one_time` query parameter is
   not being ignored.
6. Revoke the session.

## test_tokens_are_unique

Test that every session creation yields a fresh token, sequentially and under concurrency.

1. Configure the backend with the `names` dataset.
2. Create three reusable sessions for the primary user, one after another.
3. Create ten more reusable sessions for the same user concurrently.
4. Verify all thirteen tokens are non-empty.
5. Verify all thirteen tokens are distinct. A sequential collision means tokens are reused
   outright; a collision only under concurrency indicates unsynchronised access to the
   in-memory session map.
6. Revoke the session.

## test_session_endpoints_reject_bad_credentials

Test that all three session verbs require valid credentials.

1. Configure the backend with the `names` dataset.
2. For each verb (`create`, `get`, `delete`), attempt the call with the primary username and an
   incorrect password, and verify it returns 401.
3. For each verb, attempt the call as a user that does not exist, and verify it returns 401
   rather than 404 — a distinct status for an unknown account would let a caller enumerate
   users.
4. For each verb, attempt the call with no credentials, and verify it returns 401. Anonymous
   `DELETE` matters most: on Edge Server the endpoint takes no token, so without authentication
   any caller could log out an arbitrary user. On Sync Gateway, an anonymous `get` instead
   returns 200 with a null `userCtx.name`.

## test_non_admin_can_create_own_session

Test that creating a session is not an administrative action.

1. Configure the backend with the `names` dataset.
2. Add a non-admin user.
3. On Edge Server, take a fresh admin client, since the add restarted the process.
4. Create a reusable session for the non-admin user with their own credentials.
5. Verify a non-empty token is returned. If this required admin rights, a browser client could
   never log itself in, which is the endpoint's whole purpose.
6. Revoke the non-admin user's session.

## test_delete_already_deleted_session

Test that deleting a session a second time is handled cleanly.

1. Configure the backend with the `names` dataset.
2. Create a reusable session for the primary user, then delete it.
3. Delete the same session again. On Sync Gateway the client sends the cookie of the deleted
   session again.
4. On Edge Server, verify that the second delete returns 404. On Sync Gateway, verify that it
   returns 200. Any other result, for example a 5xx, means that the server did not keep track
   of the deleted session.

## test_session_endpoints_reject_unknown_database

Test that sessions are scoped to a database that exists.

1. Configure the backend with the `names` dataset.
2. For each verb (`create`, `get`, `delete`), attempt the call against `nosuchdb` with valid
   primary user credentials.
3. Verify `create` and `get` fail with a client error (401, 403 or 404). A 2xx would mean
   tokens can be minted, or session state read, for a keyspace that does not exist.
4. Verify `delete` either fails with a client error or completes quietly, since the client
   deliberately swallows 404 so teardown never fails on an already-gone session.

## test_get_session_reports_authenticated_caller

Test that `GET /{db}/_session` reports the caller identified by Basic auth.

1. Configure the backend with the `names` dataset.
2. Add a second user, before any session is created. On Edge Server the add restarts the
   process, which would otherwise drop the sessions.
3. On Edge Server, take a fresh admin client, since the previous one predates the restart.
4. Create a reusable session for the primary user, and another for the second user.
5. Request `GET /{db}/_session` as the primary user and verify the response reports `ok` as true
   with `userCtx.name` equal to that user.
6. Request `GET /{db}/_session` as the second user and verify `userCtx.name` equals that user.
   Two users are checked because a single caller cannot distinguish a per-request identity
   from one global session echoed back to everyone.
7. Revoke both sessions.
