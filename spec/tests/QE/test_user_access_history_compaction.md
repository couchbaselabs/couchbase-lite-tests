# Test User Access History Compaction

Covers the `GET`/`POST /{db}/_user/{name}/_access_history[/compact]` Sync Gateway admin
endpoints (added in #491): a user's channel *access history* (channels they used to have
access to but no longer do) and the ability to compact (prune) old entries out of it.

Compaction happens entirely Sync-Gateway-side. Tests verify both SGW's own bookkeeping
(via the admin API) and, where the case calls for it, the consequence from a connected
client's point of view (the user's own public-facing view over its Sync Gateway session),
since that is what compaction is ultimately for: keeping the record of "what a client used
to be able to see" from growing unbounded, without disturbing what it can currently see.

## Implementation notes (confirmed against a live SGW 4.2.0 run)

- **Response shape**: `get_user_access_history`/`compact_user_access_history` return
  `scope -> collection -> [channel names]` (plain channel-name strings, not per-channel
  `{start_seq, end_seq}` objects). A collection with no history entries comes back as JSON
  `null` for that key, not an empty list or an absent key — code reading these responses
  must treat `None` as empty, not just a missing key.
- **Single scope per database**: Sync Gateway only supports one scope per database config.
  A database cannot combine the `_default` scope with a separately-named scope (confirmed:
  attempting to do so returns 400 `"only one named scope is supported"`). Any test needing
  a second collection alongside `_default._default` must add it as an extra collection
  *within* the `_default` scope (`_default.<name>`), not as a distinct named scope.

## test_new_user_access_history_is_empty

### Description
A user who has never had a channel revoked has an empty access history.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'newuser' with access to channel 'A' (never changed since).
3. Get the user's access history.
4. Check that the history is empty.

## test_history_for_nonexistent_user_returns_404

### Description
Requesting the access history of a user that does not exist on the database returns 404.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Get the access history for a user that was never created.
3. Check that the request fails with a 404 status.

## test_grant_then_revoke_channel_appears_in_history

### Description
Granting a user a channel and then revoking it records the channel in the user's access
history.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'alice' with access to channel 'A'.
3. Update user 'alice' to remove access to channel 'A' (revoke).
4. Get the user's access history.
5. Check that channel 'A' appears in the `_default._default` history.

## test_compact_removes_channel_entry_without_touching_live_access

### Description
Compacting a specific channel out of a user's history removes it from subsequent GETs,
while the user's actual current (live) channel access is provably unaffected.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'bob' with access to channels 'A' and 'B'.
3. Update user 'bob' to remove access to channel 'A' only (revoke 'A', keep 'B').
4. Get the user's access history and check that channel 'A' is present.
5. Create a document in channel 'B'.
6. Compact channel 'A' out of the user's access history.
7. Check that the compact response reports channel 'A' as compacted.
8. Get the user's access history again and check that channel 'A' is gone.
9. As user 'bob', fetch all documents and check that the channel-'B' document is still
   visible (current access to 'B' was never touched by the compaction).

## test_compact_channel_not_in_history_is_idempotent_noop

### Description
Compacting a channel name that was never revoked (so never entered the history) is a
harmless no-op, and repeating it produces the same empty result.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'carol' with no channel access.
3. Compact a channel name that was never granted or revoked for 'carol'.
4. Check that nothing was reported as compacted.
5. Repeat the same compact call.
6. Check that the result is still empty (idempotent).

## test_compact_multiple_collections_independently

### Description
A single compact request naming channels in more than one collection trims each
independently, and only the channels actually named are affected.

### Steps
1. Create a bucket and configure a Sync Gateway database with an extra named collection
   (`_default.other`) in addition to `_default._default`.
2. Create user 'dave' with access to channel 'A' in `_default._default` and channel 'X' in
   `_default.other`.
3. Update user 'dave' to revoke both channel 'A' and channel 'X'.
4. Compact only channel 'A' in `_default._default` (omit `_default.other` from the
   request).
5. Check that the compact response only reports `_default._default` as trimmed.
6. Get the user's access history and check that channel 'A' is gone from
   `_default._default` while channel 'X' is still present in `_default.other`.

## test_default_and_named_collection_history_roundtrip

### Description
Grant/revoke/compact round-trips correctly for both the default collection and a named
collection in the same test, guarding the two independent internal code paths.

### Steps
1. Create a bucket and configure a Sync Gateway database with an extra named collection
   (`_default.other`) in addition to `_default._default`.
2. Create user 'erin' with access to channel 'A' in `_default._default` and channel 'X' in
   `_default.other`.
3. Update user 'erin' to revoke both channels.
4. Get the user's access history and check that both channel 'A' (`_default._default`) and
   channel 'X' (`_default.other`) are present.
5. Compact both channels in the same request.
6. Get the user's access history again and check that both are now gone.

## test_role_inherited_channel_not_reachable_via_user_compact_endpoint

### Description
A channel a user gains only through role membership is not recorded on the user's own
access history when the role subsequently loses it, and the user compact endpoint cannot
reach it. There is also no equivalent `/_role/{name}/_access_history/compact` endpoint.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create role 'myrole' with access to channel 'ROLE_CHAN'.
3. Create user 'frank' assigned to role 'myrole', with no direct channel access of their
   own.
4. Update role 'myrole' to remove access to channel 'ROLE_CHAN'.
5. Get user 'frank's access history and check that channel 'ROLE_CHAN' is absent (the
   history lives on the role's own principal record, not the user's).
6. Compact channel 'ROLE_CHAN' via the user endpoint for 'frank' and check that nothing is
   reported as compacted.
7. Attempt to call a role-scoped access-history-compact endpoint directly and check that it
   does not exist (404) — confirming there is no way to compact a role's own history via
   this feature.

## test_same_channel_name_two_collections_isolated

### Description
The same channel name revoked in two different collections for the same user is tracked
and compacted independently; compacting one must not affect the other. Also serves as
regression coverage for a `_setup_db` helper bug: an extra collection named under the
`_default` scope was being added to the Sync Gateway database config without first being
physically created in the Couchbase Server bucket, and separately, the collection's
`ScopeConfig` was being constructed before that extra collection was merged into it — a
real class of failure seen in a live run (a named collection referenced by Sync Gateway
before it actually exists on the Sync Gateway side).

### Steps
1. Create a bucket and configure a Sync Gateway database with an extra named collection
   (`_default.other`) in addition to `_default._default`.
2. Create user 'grace' with access to channel 'SHARED' in both `_default._default` and
   `_default.other`.
3. Update user 'grace' to revoke channel 'SHARED' from both collections.
4. Compact channel 'SHARED' only in `_default._default`.
5. Get the user's access history and check that channel 'SHARED' is gone from
   `_default._default` but still present in `_default.other`.

## test_concurrent_double_compact_clean_conflict

### Description
Two concurrent compact requests for the same user/channel do not corrupt the history —
either both succeed cleanly, or the loser gets a well-formed error response, never a
silent inconsistency.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'henry' with access to channel 'A'.
3. Update user 'henry' to revoke channel 'A'.
4. Issue two concurrent compact requests for channel 'A' on user 'henry'.
5. Check that at least one request succeeds, and that any request that fails does so with
   a well-formed Sync Gateway error response (not a crash or malformed body).
6. Get the user's access history afterward and check that channel 'A' is gone and the
   response is still well-formed.

## test_compact_during_live_replication_no_disconnect_no_recompute

### Description
Compacting a user's access history while that user has a continuously-connected pull
replicator does not disrupt the replicator — no forced disconnect, and current channel
visibility is unaffected. Uses a real continuous CBL replicator against the required
test-server topology, since a one-shot admin/public-API call cannot exercise or verify
live-session/no-disconnect behavior (there is no session or connection to keep alive
between one-shot calls in the first place).

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'iris' with access to channel 'B', and revoke channel 'A' to give her some
   access history.
3. Reset a local database and start a continuous pull replicator for user 'iris', waiting
   for it to reach idle.
4. While that replicator is still continuously connected, compact channel 'A' out of user
   'iris's access history.
5. Check that the replicator is still running normally afterward, with no error and no
   forced disconnect.
6. Create a document in channel 'B' and confirm the still-connected replicator pulls it
   down without needing to reconnect or resync (current access to 'B' was never touched).

## test_partial_multi_channel_compact_only_found_removed

### Description
A compact request naming several channels, only some of which are actually present in the
history, succeeds and reports only the channels that were actually found — not an
all-or-nothing failure.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'jack' with access to channel 'A'.
3. Update user 'jack' to revoke channel 'A' (channel 'NEVER_GRANTED' was never granted at
   all).
4. Compact both channel 'A' and channel 'NEVER_GRANTED' in the same request.
5. Check that the response reports channel 'A' as compacted and does not report
   'NEVER_GRANTED'.

## test_compact_with_duplicate_channel_names_matches_deduplicated_request

### Description
A compact request whose channel-name list contains a repeated name produces the same
outcome as the equivalent deduplicated list — no duplicate entries in the response, and
the same end state. The REST handler passes the raw channel-name list straight through
with no dedup/validation of its own (`rest/admin_api.go:2602-2649` in Sync Gateway), so
this guards against a caller-supplied duplicate producing a duplicated or inconsistent
response.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create users 'mona' and 'nora', each with access to channels 'ch1' and 'ch2', then
   revoke both for each.
3. Compact 'mona' with a channel list containing a repeated name (`['ch1', 'ch1', 'ch2']`),
   and compact 'nora' with the equivalent deduplicated list (`['ch1', 'ch2']`).
4. Check that the duplicated request's response has no duplicate entries and matches the
   deduplicated request's response.
5. Get both users' access history afterward and check the end state is identical for both.

## test_same_username_different_databases_isolated

### Description
The same username existing independently on two different Sync Gateway databases has
fully separate access history; compacting in one database must not affect the other.

### Steps
1. Create two buckets and configure two separate Sync Gateway databases, one on each.
2. Create a user with the same name on both databases, each with access to channel 'A'.
3. Revoke channel 'A' for that user on both databases.
4. Compact channel 'A' for that user on the first database only.
5. Get the user's access history on the second database and check that channel 'A' is
   still present there (untouched by the first database's compaction).

## test_rbac_read_only_can_get_but_not_compact

**Status: SKIPPED — pending test infrastructure.** There is currently no helper anywhere in
the `cbltest` framework for provisioning a Sync Gateway/Couchbase Server RBAC credential
scoped to a specific admin role (e.g. "Application Read Only" vs "Application"), so this
case cannot be written without first adding that support. Tracked as a follow-up; not
built here per the standing no-scope-creep-into-`client/`-without-sign-off policy.

### Description
A caller authenticated with the "Application Read Only" Sync Gateway RBAC role can GET a
user's access history but gets 403 attempting to compact it.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'kelly' with access to channel 'A', then revoke it.
3. As a caller with the "Application Read Only" role, get the user's access history and
   check that it succeeds.
4. As the same caller, attempt to compact the history and check that it fails with 403.

## test_compact_while_client_offline_leaves_stale_access_undetected

This is the flagship scenario for this endpoint pair (mirrors the "Bob" offline-revoke
case from a user-history angle). Uses the shared `backfill_after_offline` helper
(`tests/shared/backfill_after_offline.py`) to simulate the offline window for both the
initial sync and the reconnect.

**Status: confirmed as expected/documented behavior, not a product bug.** A live run
against SGW 4.2.0 showed the reconnect replicator receiving zero document-update events
at all (not even a normal update, let alone one flagged access-removed) after the offline
revoke-then-compact window, even though the revoke and compact steps themselves both
completed successfully. This was cross-checked directly with the Sync Gateway team: both
`compact_user_access_history` and `compact_document_channel_history` operate purely on an
explicit, caller-supplied identifier (a channel-name list for the user-history endpoint;
a sequence cutoff scoped to that one document for the doc-history endpoint) and only ever
remove closed/historical entries -- never a user or role's current, active access. Neither
endpoint checks whether a still-offline client might resume needing the very history being
removed; the caller is fully trusted to know that history is truly no longer needed by
anyone, including long-offline replicators. Compacting a channel's access-history entry
before an affected client has had a chance to reconnect is exactly this scenario, and the
resulting silence on reconnect is the documented risk working as designed, not a defect.
The test below asserts that this risk reproduces, rather than asserting it doesn't.

### Description
A client that is offline when its access to a channel is revoked, and reconnects only
after that revocation's history entry has been compacted, receives no notification at all
about the now-inaccessible document and keeps the stale document on-device -- this is the
documented risk of compacting access history a still-offline client may depend on, not a
guarantee the endpoint provides protection against.

### Steps
1. Create a bucket and configure a Sync Gateway database on it.
2. Create user 'leo' with access to channel 'A'.
3. Create a document assigned to channel 'A'.
4. Reset a local database and pull as user 'leo' so the document replicates to the device.
5. While offline, revoke user 'leo's access to channel 'A', then compact channel 'A' out
   of user 'leo's access history before the client reconnects.
6. Bring the client back online: start a new pull replicator for the same user.
7. Check that the device received no notification about 'doc_a' at all -- compacting the
   user's access history for channel 'A' before the client resumed left Sync Gateway with
   no history to compute the revocation against, which is the documented risk of
   compacting history a still-offline client may still depend on.
8. Check that the now-inaccessible channel-'A' document is still present on the client --
   the documented risk outcome of compacting access history the client's reconnect needed.
