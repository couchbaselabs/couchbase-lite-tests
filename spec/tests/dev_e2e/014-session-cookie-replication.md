# Test Cases

These tests validate Edge Server (ES) &rarr; Sync Gateway (SGW) replication using
session-cookie authentication (`auth.session_cookie`), covering a bare session id,
an already-prefixed value, and a revoked session.

Session ids are minted through SGW's admin API (`POST /{db}/_session`) via
`SyncGateway.create_session()`. The SGW user must already exist before a session is
created: SGW answers 404 for an unknown user and 400 for GUEST. Each test therefore
adds the user `session_user` before minting its session.

ES sends the configured value on the replication WebSocket upgrade request as a
`Cookie: SyncGatewaySession=<id>` header. ES prepends `SyncGatewaySession=` when the
configured value does not already start with it, and leaves the value alone when it
does; both forms are covered because a user who copies a cookie out of browser dev
tools gets the prefixed form.

Each test asserts on the specific document ids it seeded rather than on a document
count. The pre-loaded `travel.cblite2` dataset ships 150 documents, so a count-based
assertion such as `>= 150` passes even when nothing replicates at all — it would be
reading the local seeded database rather than verifying authentication. The seeded
ids exist only on SGW, so their presence on ES proves the documents crossed an
authenticated connection.

Note on scope: authentication happens once, on the WebSocket upgrade. Once that
handshake succeeds the connection is an open, already-authenticated BLIP stream that
SGW does not re-validate per message, so revoking a session does not stop a
replication that is already connected. The revocation test below therefore revokes
before ES connects, which is the behaviour that can actually be asserted.

## test_session_cookie_replication

### Description

Test that ES can replicate with SGW using a bare session id in
`auth.session_cookie`, with ES supplying the `SyncGatewaySession=` prefix.

### Steps

1. Create the SGW `travel` database (creating its backing CBS bucket and the `travel.airlines` collection) with a sync function assigning `doc.channels`.
2. Add the SGW user `session_user` with `["*"]` channel access to `travel.airlines`.
3. Insert 5 documents into CBS (`session_cookie_airline_1..5`) with `channels=["*"]`.
4. Wait until SGW has imported all 5 documents from CBS.
5. Create a session for `session_user` via the SGW admin API and keep the returned session id.
6. Verify the session authenticates against the SGW REST API (`GET /travel/` with `Cookie: SyncGatewaySession=<id>` returns 200). This sends the same header ES will put on the handshake, so a failure here isolates the fault to the session rather than to ES.
7. Configure and start ES with the **bare** session id in `auth.session_cookie`.
8. Verify the replicator was created (`/_replicate` is non-empty), then wait until it is idle. An empty list means the replication config was rejected outright.
9. Verify all 5 seeded document ids are present on ES.
10. Fetch one document from ES and verify it is retrievable and has a `name` field.

## test_session_cookie_already_prefixed

### Description

Test that ES can replicate when the configured value already carries the
`SyncGatewaySession=` prefix, and that ES does not double the prefix. Sending
`SyncGatewaySession=SyncGatewaySession=<id>` is rejected by SGW.

### Steps

1. Create the SGW `travel` database (creating its backing CBS bucket and the `travel.airlines` collection) with a sync function assigning `doc.channels`.
2. Add the SGW user `session_user` with `["*"]` channel access to `travel.airlines`.
3. Insert 5 documents into CBS (`session_cookie_prefixed_airline_1..5`) with `channels=["*"]`.
4. Wait until SGW has imported all 5 documents from CBS.
5. Create a session for `session_user` via the SGW admin API.
6. Verify the prefixed value `SyncGatewaySession=<id>` authenticates against the SGW REST API (`GET /travel/` returns 200).
7. Configure and start ES with the **already-prefixed** value in `auth.session_cookie`.
8. Verify the replicator was created, then wait until it is idle.
9. Verify all 5 seeded document ids are present on ES.

## test_revoked_session_cannot_start_replication

### Description

Test that a revoked session cannot establish replication. Without this, a regression
in which the cookie is sent but SGW falls through to guest access would still pass
the two tests above.

### Steps

1. Create the SGW `travel` database (creating its backing CBS bucket and the `travel.airlines` collection) with a sync function assigning `doc.channels`.
2. Add the SGW user `session_user` with `["*"]` channel access to `travel.airlines`.
3. Insert 5 documents into CBS (`session_cookie_revoke_airline_1..5`) with `channels=["*"]`.
4. Wait until SGW has imported all 5 documents from CBS.
5. Create a session for `session_user` via the SGW admin API.
6. Revoke the session (`DELETE /{db}/_session/{sessionid}`) **before** ES connects, so the handshake itself is what must be rejected.
7. Verify SGW rejects the revoked session (`GET /travel/` with the revoked cookie returns 401). If SGW were allowing guest access this test could not prove anything.
8. Configure and start ES with the revoked session id in `auth.session_cookie`.
9. Wait 20s to give replication a window in which it could incorrectly pull documents.
10. Verify **none** of the 5 seeded document ids are present on ES. ES holds only the 150 pre-loaded documents.
