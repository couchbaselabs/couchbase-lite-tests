# Test Cases

These tests cover delta-sync PULL replication across a simulated 3.x → 4.x SGW
upgrade. The pre-upgrade state is materialised by restoring the prebuilt
`upgrade` CBS backup (revtree-only docs, no HLV xattrs) and resetting the CBL
local DB from the matching `upgrade` cblite2 file; both binaries run 4.x
throughout. Delta sync is enabled on the SGW `upgrade` database.

The bucket is restored with expired old-revision backup bodies (`_sync:rev:*`)
re-enabled (their captured TTL has long lapsed), so SGW can compute a delta
against a legacy ancestor revision instead of falling back to a full body.

Both tests assert that SGW actually sends the revision **as a delta** (via the
per-rev `deltas_sent` expvar counter), and that the document converges on the
client. The SGW delta-sync `history`-field defect is a wire-level issue that is
not observable from end-state and is verified separately; asserting on it from
the test is tracked as future work.

## #1 test_delta_sync_history_pull_post_upgrade_sgw_mutation

### Description

PULL replication of a doc whose new revision is created on 4.x SGW (so SGW
holds both a revtree leaf and an HLV) by a client that holds the **direct
revtree parent**. Uses doc `nonconflict_3`; the new revision is created in-test
by mutating the doc on 4.x SGW, which adds an HLV in parallel with the new
revtree leaf.

```
+-------------------+-------------------------------+-------------------------------+
|                   |             CBL               |              SGW              |
|                   +---------------+---------------+---------------+---------------+
|                   |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+-------------------+---------------+---------------+---------------+---------------+
| After restore     |     2-abc     |     none      |     2-abc     |     none      |
| After SGW mutate  |     2-abc     |     none      | 3-xxx, 2-abc  |   [N@SGW]     |
| Expected post-PULL|     none      |   [N@SGW]     | 3-xxx, 2-abc  |   [N@SGW]     |
+-------------------+---------------+---------------+---------------+---------------+
```

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset, re-enabling expired
   old-revision backup bodies.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Create SG 'upgrade' database with delta_sync enabled and import from bucket.
   On 412 (already exists), force-recreate by `delete_database` + `put_database`.
6. Verify delta_sync is actually enabled on SGW 'upgrade' database.
7. Create user `user1` with full access to `_default._default`.
8. Mutate `nonconflict_3` on 4.x SGW to create a new revtree leaf + HLV.
9. Start a replicator:
   * endpoint: `/upgrade`
   * collections: `_default._default`
   * type: pull
   * document_ids: `['nonconflict_3']`
   * continuous: False
   * credentials: user1/pass
10. Wait until the replicator is stopped.
11. Check that the doc is replicated correctly.
12. Validate revid and HLV of local and remote doc:
    * Pre: local has revid + no HLV; SGW has revid + canonical (non-RTE) HLV.
    * Post: local has no revid (4.x CBL is HLV-only); local HLV equals SGW HLV.
13. Confirm SGW sent the revision as a delta (`deltas_sent` incremented).

### Expected Outcome

CBL ingests the delta and ends up HLV-only with an HLV matching SGW; the
`deltas_sent` counter confirms a delta (not a full body) was sent.

---

## #2 test_delta_sync_history_pull_pre_upgrade_sgw_two_revs

### Description

PULL replication of a **legacy, pre-upgrade** second revision. Uses doc
`nonconflict_2`: after restore the client is at rev 1 and SGW is at rev 2, both
revtree-only with **no HLV** (rev 2 was created pre-upgrade on 3.x, so it never
got an HLV). There is **no in-test mutation**. SGW sends the existing rev 2 as a
**revID-identified (legacy) delta** computed against the client's rev 1 — which
requires rev 1's old-revision backup body, made available by the TTL rescue at
restore. This is the distinguishing case from #1: the delta is of a revtree-only
rev with no HLV, not a 4.x HLV-bearing rev.

```
+-------------------+-------------------------------+-------------------------------+
|                   |             CBL               |              SGW              |
|                   +---------------+---------------+---------------+---------------+
|                   |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+-------------------+---------------+---------------+---------------+---------------+
| After restore     |     1-abc     |     none      | 2-def, 1-abc  |     none      |
| Expected post-PULL| 2-def, 1-abc  |     none      | 2-def, 1-abc  |     none      |
+-------------------+---------------+---------------+---------------+---------------+
```

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset, re-enabling expired
   old-revision backup bodies.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Create SG 'upgrade' database with delta_sync enabled and import from bucket.
   On 412 (already exists), force-recreate by `delete_database` + `put_database`.
6. Verify delta_sync is actually enabled on SGW 'upgrade' database.
7. Create user `user1` with full access to `_default._default`.
8. Start a replicator:
   * endpoint: `/upgrade`
   * collections: `_default._default`
   * type: pull
   * document_ids: `['nonconflict_2']`
   * continuous: False
   * credentials: user1/pass
9. Wait until the replicator is stopped.
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc:
    * Pre: both sides have revid and no HLV; local revid < SGW revid.
    * Post: local and SGW share the same revid; neither has an HLV (the legacy
      rev carries no HLV and PULL doesn't touch SGW).
12. Confirm SGW sent the revision as a delta (`deltas_sent` incremented).

### Expected Outcome

SGW sends rev 2 as a revID-identified legacy delta (no HLV) computed against the
client's rev 1; CBL applies it and ends up revtree-only at rev 2; the
`deltas_sent` counter confirms a delta (not a full body) was sent.
