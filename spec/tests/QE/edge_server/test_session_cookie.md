# Session Cookie Replication Tests (Edge Server)

## test_session_cookie_bidirectional_replication

1. Create the SGW `travel` database: guest disabled, the `requireUser(doc.owner)` sync function, `travel.airlines` and `travel.hotels`.
2. Add SGW user `session_user` with access to `session_ch` only, in both collections.
3. Verify SGW rejects an unauthenticated request (`GET /travel/` returns 401).
4. Seed 3 documents in `session_ch` and 2 in `restricted_ch` into each collection through CBS, and wait for SGW to import all 10.
5. Create a session for `session_user` and verify SGW accepts it (`GET /travel/` with `Cookie: SyncGatewaySession=<id>` returns 200).
6. Configure ES with the session given in the parameter's form and start it.
7. Wait for the replicator to exist, report no error, and be `Idle`.
8. Verify the 6 `session_ch` documents are on ES, across both collections.
9. Verify none of the 4 `restricted_ch` documents are on ES.
10. On ES, write `<prefix>_foreign` to `travel.airlines` with `owner: other_user`, then `<prefix>_owned` to both collections with `owner: session_user`.
11. Wait for both `<prefix>_owned` documents to reach SGW, and verify SGW holds `owner: session_user` for each.
12. Verify `<prefix>_foreign` is not on SGW: `requireUser` rejected it, so the push was made as `session_user`.

## test_session_cookie_across_restart_revoke_and_rotate

1. Create the SGW database and user, and verify guest is rejected, as in steps 1&ndash;3 above.
2. Seed 3 `session_ch` documents per collection (phase 1) through CBS and wait for SGW to import them.
3. Create session A, verify SGW accepts it, and start ES with session A as a bare `auth.session_cookie`.
4. Wait for the replicator to be `Idle` and verify the phase 1 documents are on ES.
5. Restart ES on the same config and database.
6. Seed phase 2 documents through CBS and wait for SGW to import them.
7. Wait for the replicator to be `Idle` and verify the phase 2 documents are on ES.
8. Stop ES, revoke session A, and verify SGW rejects it (`GET /travel/` returns 401).
9. Seed phase 3 documents through CBS and wait for SGW to import them.
10. Start ES on the same config and database.
11. Wait for ES to give up on the replicator: removed, or `Stopped`/`Offline` with a 401 error.
12. Verify none of the phase 3 documents are on ES.
13. On ES, write `lifecycle_offline_write` to `travel.airlines` with `owner: session_user` while the replicator is down.
14. Create session B, verify SGW accepts it, and restart ES with session B in the config and the same database.
15. Wait for the replicator to be `Idle` and verify the phase 3 documents are on ES.
16. Wait for `lifecycle_offline_write` to reach SGW.

## test_invalid_session_cookie_rejected

1. Create the SGW database and user, and verify guest is rejected, as in steps 1&ndash;3 of the first test.
2. Seed 3 `session_ch` documents per collection through CBS and wait for SGW to import them.
3. Obtain the parameter's session. For `expired`, create it with a 5 s ttl and wait 10 s without using it.
4. Verify SGW rejects the session (`GET /travel/` returns 401).
5. Start ES with the session as a bare `auth.session_cookie`.
6. Wait for ES to give up on the replicator: removed, or `Stopped`/`Offline` with a 401 error.
7. Verify none of the seeded documents are on ES.
