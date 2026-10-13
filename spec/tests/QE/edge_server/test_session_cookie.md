# Session Cookie Replication Tests (Edge Server)

These tests validate Edge Server (ES) &rarr; Sync Gateway (SGW) replication authenticated with an
SGW session through `auth.session_cookie` (CBL-8647).

Every test starts the same way:

1. Create the SGW `travel` database with guest disabled and the `requireUser` sync function.
2. Add `session_user` with access to `session_ch` in both collections.
3. Verify SGW rejects an unauthenticated request.

The database has the `travel.airlines` and `travel.hotels` collections. With guest disabled, a
document reaching ES can only have crossed an authenticated connection. The sync function is
`if (doc.owner) { requireUser(doc.owner); } channel(doc.channels);`, so a pushed document naming an
`owner` is accepted only when the push connection authenticated as that owner. Documents are seeded
through Couchbase Server, 3 per collection, and waited on until SGW has imported them.

ES health comes from `EdgeServer.wait_for_idle()`. It raises `CblEdgeServerBadResponseError` when
the replicator reports an error, carrying the code it reports, or with code 404 when ES no longer
lists it, which is how ES drops a replicator whose handshake was answered 401. A rejected session
must therefore fail with 401 or 404.

## test_session_cookie_bidirectional_replication

### Description

Test that ES replicates both ways as the session's user, for each way the session can be given:

| Parameter | Replication config |
|---|---|
| `bare` | `auth.session_cookie: <id>` |
| `prefixed` | `auth.session_cookie: SyncGatewaySession=<id>` |
| `with_unrelated_cookie_header` | `auth.session_cookie: <id>` plus `headers.Cookie: AWSALB=qe-sticky-session` |

`prefixed` checks that ES does not add the cookie name a second time. `with_unrelated_cookie_header`
models a load balancer's sticky-session cookie: the session cookie must not be clobbered by, or
clobber, a `Cookie` header the user configured.

### Steps

1. Seed `session_ch` and `restricted_ch` documents into both collections.
2. Create a session for `session_user` and verify SGW accepts it.
3. Start Edge Server replicating with the session.
4. Verify only the `session_ch` documents were pulled.
5. On Edge Server, write `foreign` (owner `other_user`), then `owned` (owner `session_user`).
6. Verify `owned` reached SGW in both collections.
7. Verify `foreign` was rejected by `requireUser`: the push was made as `session_user`.

## test_session_cookie_across_restart_revoke_and_rotate

### Description

Test the session over ES's lifecycle:

- ES sends the configured session on every connect, not just the first.
- A revoked session stops ES from reconnecting.
- A new session in the config restores replication both ways.

SGW checks a session only on the WebSocket upgrade, so revoking it does not drop a connection that
is already up. ES is therefore stopped before the session is revoked, and the next handshake is the
one that must fail. Documents are seeded while ES is stopped, so the next catch-up includes them and
`Idle` means they have arrived.

### Steps

1. Seed phase 1 documents, then start Edge Server with session A.
2. Stop Edge Server, seed phase 2 documents, and restart it on the same config.
3. Stop Edge Server, revoke session A, and verify SGW rejects it.
4. Seed phase 3 documents, restart Edge Server, and verify the replicator fails with a 401.
5. On Edge Server, write `offline_write` while the replicator is down.
6. Restart Edge Server with a new session B.
7. Verify phase 3 was pulled and `offline_write` was pushed.

## test_invalid_session_cookie_rejected

### Description

Test that ES does not replicate with a session SGW will not accept, and that the replicator fails
rather than hangs.

| Parameter | Session |
|---|---|
| `expired` | Created with a 5 s ttl, then left unused for 10 s |
| `never_issued` | A random 40-character hex id |

The expired session is not presented to SGW before it expires. SGW slides a session's expiry
forward each time it is used, so checking it early would keep it alive.

### Steps

1. Seed documents.
2. Obtain the parameter's session and verify SGW rejects it.
3. Start Edge Server with the session, and verify the replicator fails with a 401.
4. Verify none of the seeded documents were pulled.
