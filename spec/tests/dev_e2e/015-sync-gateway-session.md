# Test Cases

The class creates one database, and every test uses it:

1. Create database session_db with a `channel(doc.channels)` sync function.
2. Write doc_a to channel A and doc_b to channel B.

Each test creates users of its own, with random names. A user has access to channel A, or to the
channels that the test names. Because of this, no test changes the state that another test sees.

A test gets a session in one of two ways:

- `admin`: `POST /{db}/_session` on the admin port, with the user name.
- `public`: `POST /{db}/_session` on the public port, with the user's basic auth. The session id
  comes from the `SyncGatewaySession` cookie that Sync Gateway sets.

A test marked "for each source" runs once for each way. A session client sends only the
`SyncGatewaySession` cookie to the public port. It sends no `Authorization` header, and it keeps no
cookie that a response sets.

Some tests below fail on Sync Gateway 4.2. Each one names the defect that it finds.

## #1 test_session_authenticates_as_user

### Description

Checks that a session authenticates as its user, with the channel access of that user. This runs for
each source.

### Steps

1. Create a user.
2. Create a session for the user.
3. Read doc_a, which is in the user's channel.
4. Read doc_b, which is outside the user's channels, and get 403.
5. List all docs and see doc_a but not doc_b.
6. Write a document through the session.
7. Read the document back through the admin API.

## #2 test_unknown_session_is_rejected

### Description

Checks that Sync Gateway rejects a session id that it never created.

### Steps

1. Read doc_a with a session id that was never created, and get 401.

## #3 test_deleted_session_is_rejected

### Description

Checks that a deleted session logs out a client that uses it. This runs for each source, and for a
delete through each API: `DELETE /{db}/_session/{id}` on the admin port, or `DELETE /{db}/_session`
with the session cookie on the public port.

### Steps

1. Create a user.
2. Create a session for the user, and read doc_a with it.
3. Delete the session.
4. Read doc_a with the deleted session, and get 401.
5. Delete the session again through the admin API, and get 404.

## #4 test_sessions_are_independent

### Description

Checks that a second session for a user does not replace the first. It also checks that a logout
from one session leaves the other session working.

### Steps

1. Create a user.
2. Create one session for the user through each API.
3. Read doc_a with both sessions.
4. Log out of the public session.
5. Read doc_a with the public session and get 401, but the admin one still works.

## #5 test_deleting_user_invalidates_session

### Description

Checks that deleting a user logs out the open sessions of that user. This runs for each source.

### Steps

1. Create a user.
2. Create a session for the user, and read doc_a with it.
3. Delete the user.
4. Read doc_a with the session, and get 401.

## #6 test_recreated_user_does_not_inherit_session

### Description

Checks that a new user with the same name cannot use the session of the deleted user. This runs for
each source.

### Steps

1. Create a user.
2. Create a session for the user.
3. Delete and recreate the user.
4. Read doc_a with the old session, and get 401.

## #7 test_session_follows_channel_access_changes

### Description

Checks that a change to the channel access of a user applies to an open session at once. The user
does not log in again. This runs for each source.

### Steps

1. Create a user.
2. Create a session for the user.
3. Read doc_b, and get 403.
4. Grant the user access to channel B without recreating the user.
5. Read doc_b with the same session.

## #8 test_create_session_rejects_invalid_users

### Description

Checks that neither API creates a session for a user that cannot have one.

### Steps

1. Create a user.
2. Create a session through the admin API for a user that does not exist, and get 404.
3. Create a session through the admin API for the GUEST user, and get 400.
4. Log in through the public API as a user that does not exist, and get 401.
5. Log in through the public API as the user with a wrong password, and get 401.

## #9 test_tampered_session_ids_are_rejected

### Description

Checks that a session id that is close to a real one does not authenticate. The ids are the real id
truncated, extended or in upper case, an empty id, the key of the user document, and a relative
path.

### Steps

1. Create a user.
2. Create a session for the user.
3. Read doc_a with each tampered session id, and get 401.

## #10 test_oversized_session_id_is_rejected

### Description

Checks that a session id too long for a Couchbase Server document key gets the same answer as any
other unknown id.

Fails on Sync Gateway 4.2: an id of 237 characters or more gets a 500 from the cookie, the admin
GET and the admin DELETE. The body of the 500 shows the internal document key, the bucket, and the
Couchbase Server node address.

### Steps

1. Read doc_a with an oversized session id, and get 401.
2. Delete the oversized session id through the admin API, and get 404.

## #11 test_session_is_rejected_on_admin_port

### Description

Checks that a session does not authenticate on the admin port. This runs for each source.

### Steps

1. Create a user.
2. Create a session for the user.
3. Read doc_a on the admin port with only the session, and get 401.

## #12 test_basic_auth_takes_precedence_over_session

### Description

A request can carry the session of one user and the basic auth of another user. This test checks
which user the request acts as. Basic auth decides, and a wrong password fails the request even with
a valid session.

### Steps

1. Create a user with access to channel A, and a second user with access to channel B.
2. Log in as the first user through the public API.
3. Send the session of the first user with the basic auth of the second user, and read doc_b.
4. Read doc_a with the same headers, and get 403.
5. Send the session of the first user with a wrong password for the second user, and get 401.

## #13 test_disabled_user_session_is_rejected

### Description

Checks that disabling a user logs out the open sessions of that user. This runs for each source.

Fails on Sync Gateway 4.2: basic auth for the disabled user gets 401, but the old session still
reads and writes documents.

### Steps

1. Create a user.
2. Create a session for the user, and read doc_a with it.
3. Disable the user.
4. Read doc_a with basic auth for the user, and get 401.
5. Read doc_a with the session, and get 401.
6. Write a document with the session, and get 401.

## #14 test_password_change_invalidates_session

### Description

Checks that a new password for a user logs out the open sessions of that user. This runs for each
source.

### Steps

1. Create a user.
2. Create a session for the user, and read doc_a with it.
3. Change the password of the user.
4. Read doc_a with the session, and get 401.

## #15 test_delete_user_sessions_invalidates_every_session

### Description

Checks that `DELETE /{db}/_user/{name}/_session` logs out every session of the user, and that the
user can log in again after it.

### Steps

1. Create a user.
2. Create one session for the user through each API.
3. Delete every session of the user.
4. Read doc_a with each session, and get 401.
5. Log in again through the public API, and read doc_a with the new session.

## #16 test_session_expires_after_ttl

### Description

Checks that a session stops working after its ttl. Every use of a session can extend it, so the test
does not use the session during the wait.

### Steps

1. Create a user.
2. Create a session for the user with a ttl of 3 seconds.
3. Read doc_a with the session before it expires.
4. Wait 5 seconds without using the session.
5. Read doc_a with the session, and get 401.

## #17 test_session_in_use_is_extended

### Description

Checks that a session in use lives past its ttl. After the use stops, the session expires.

### Steps

1. Create a user.
2. Create a session for the user with a ttl of 3 seconds.
3. Read doc_a with the session every second for 9 seconds.
4. Wait 5 seconds without using the session.
5. Read doc_a with the session, and get 401.

## #18 test_create_session_rejects_invalid_ttl

### Description

Checks that the admin API refuses a ttl that is not a positive duration. The cases are 0, -1, and
two values that overflow in the conversion from seconds to int64 nanoseconds. The first overflow
becomes a negative duration. The second becomes a positive duration of a few years.

Fails on Sync Gateway 4.2 for the second overflow: Sync Gateway accepts the ttl and returns a wrong
expiry date.

### Steps

1. Create a user.
2. Create a session for the user with the ttl, and get 400.

## #19 test_create_session_rejects_disabled_user

### Description

Checks that neither API creates a session for a disabled user.

### Steps

1. Create a user.
2. Disable the user.
3. Create a session for the user through the admin API, and get 400.
4. Log in as the user through the public API, and get 401.
