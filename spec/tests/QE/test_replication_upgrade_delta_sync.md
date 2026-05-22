# Test Cases

These tests cover delta-sync replication behavior across a simulated 3.x → 4.x
SGW upgrade. The pre-upgrade state is materialised by restoring the prebuilt
`upgrade` CBS backup (revtree-only docs, no HLV xattrs) and resetting the CBL
local DB from the matching `upgrade` cblite2 file; both binaries run 4.x
throughout. Delta sync is enabled on the SGW `upgrade` database.

## #1 test_delta_sync_history_pull_post_upgrade_sgw_mutation

### Description

PULL replication of a doc whose 2nd revision was created on 4.x SGW (so SGW
holds both a revtree and an HLV) by a client that still holds the revtree-only
ancestor. With delta sync enabled, SGW must populate the rev message's
`history` field with the revtree predecessors so the client can ingest the
delta. The current build sends an empty `history` here — this test is the
regression marker for the fix, and is marked `xfail(strict=True)` until the
SGW fix lands.

Uses doc `nonconflict_3` from the prebuilt `upgrade` dataset. The 2nd
revision is created in-test by mutating the doc on 4.x SGW, which adds an HLV
in parallel with the new revtree leaf (4.x SGW always writes both).

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| After restore    |     2-abc     |     none      |     2-abc     |     none      |
| After SGW mutate |     2-abc     |     none      | 3-xxx, 2-abc  |   [N@SGW]     |
| Expected post-PULL|     none     |    [N@SGW]    | 3-xxx, 2-abc  |   [N@SGW]     |
+------------------+---------------+---------------+---------------+---------------+
```

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Create SG 'upgrade' database with delta_sync enabled and import from bucket.
   On 412 (already exists), force-recreate by `delete_database` + `put_database`.
6. Verify delta_sync is actually enabled on SGW 'upgrade' database by fetching
   the live config; fail with the active config dumped if not enabled.
7. Create user `user1` with full access to `_default._default`.
8. Mutate `nonconflict_3` on 4.x SGW to produce a new revtree leaf + fresh HLV.
9. Start a replicator:
   * endpoint: `/upgrade`
   * collections: `_default._default`
   * type: pull
   * document_ids: `['nonconflict_3']`
   * continuous: False
   * credentials: user1/pass
10. Wait until the replicator is stopped.
11. Validate revid and HLV of local and remote doc:
    * Pre: local has revid + no HLV; SGW has revid + canonical HLV (not
      RTE-encoded).
    * Post: local has no revid (4.x CBL is HLV-only); local HLV equals SGW HLV.

### Expected Outcome

✅ **With SGW fix**: CBL ingests the delta, ends up HLV-only with HLV matching SGW.
❌ **Without SGW fix** (current build): rev message's `history` field is empty,
client cannot ingest → test fails the postcondition. The `xfail(strict=True)`
marker makes this an expected failure today and an `XPASS` (CI failure) the
day the fix lands, forcing the developer landing the fix to remove the marker.

---

## #2 test_delta_sync_history_pull_pre_upgrade_sgw_two_revs

### Description

PULL replication of a doc whose 2nd revision was created on 3.x SGW (so both
sides have revtree-only state, no HLV anywhere) by a client that holds the
revtree-only ancestor. With delta sync enabled, the client must pull the
newer revtree-only rev and generate an HLV locally using the
Revision-Tree-Encoding (RTE) format. This case is expected to work on the
current build (via the pre-fix code path) and serves as a forward regression
marker once the SGW fix lands.

Uses doc `nonconflict_2` from the prebuilt `upgrade` dataset — its baked-in
state already matches the required pre-state, so no in-test SGW mutation is
needed.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| After restore    |    1-abc      |     none      | 2-def, 1-abc  |     none      |
| Expected post-PULL|    none      | [2def@RTE]    | 2-def, 1-abc  |     none      |
+------------------+---------------+---------------+---------------+---------------+
```

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Create SG 'upgrade' database with delta_sync enabled and import from bucket.
   On 412 (already exists), force-recreate by `delete_database` + `put_database`.
6. Verify delta_sync is actually enabled on SGW 'upgrade' database by fetching
   the live config; fail with the active config dumped if not enabled.
7. Create user `user1` with full access to `_default._default`.
8. Start a replicator:
   * endpoint: `/upgrade`
   * collections: `_default._default`
   * type: pull
   * document_ids: `['nonconflict_2']`
   * continuous: False
   * credentials: user1/pass
9. Wait until the replicator is stopped.
10. Validate revid and HLV of local and remote doc:
    * Pre: both sides have revid and no HLV; CBL revid < SGW revid.
    * Post: local has no revid (4.x CBL is HLV-only); local HLV ends with
      `@Revision+Tree+Encoding`; SGW HLV is still None (PULL doesn't touch SGW).

### Expected Outcome

✅ **Today** (pre-fix): the existing code path correctly pulls the
revtree-only rev and the client generates an RTE-encoded HLV. Test passes.
✅ **After fix lands**: same path, same outcome. Test continues to pass.
This is the forward regression marker confirming the fix doesn't break the
symmetric, revtree-only case.
