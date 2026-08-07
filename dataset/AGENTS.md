# Test Datasets — `dataset/`

Binary and JSON fixtures consumed by `tests/dev_e2e/`, `tests/QE/`, and `client/smoke_tests/` via the `dataset_path` fixture. Couchbase Server backup archives (`dataset/couchbase-server/*.zip`) and Sync Gateway data/config pairs (`dataset/sg/*-sg.json` + `*-sg-config.json`) are tracked via Git LFS.

## `upgrade` dataset (`dataset/couchbase-server/upgrade.zip`)

This is a `cbbackupmgr` backup archive of a bucket that was populated by an older Sync Gateway version, used by `tests/shared/upgrade_test_helpers.py` to exercise SGW upgrade paths against pre-existing metadata.

### Creating or regenerating this archive

Producing this fixture is four steps. Only step 1 (producing the source bucket) differs depending on whether you're generating from scratch or regenerating from the existing archive — steps 2–4 (cleanup, validation, backup) are identical either way. Skipping any step below reintroduces a bug that's already bitten this fixture once.

#### Step 1: produce the source bucket

**Option A — generate from scratch** (new doc/history shapes, or targeting a different Sync Gateway version):

1. Point the target-version Sync Gateway at a fresh, empty bucket and create the `upgrade` database (matching the sync function and `delta_sync.enabled` setting this dataset needs).
2. Create and mutate documents through *that* Sync Gateway's REST API to produce the exact revision-tree shape each test case needs — e.g. write then update a doc for a 2-revision non-conflict history, or push conflicting branches for a `conflict_N` doc. This must go through a real Sync Gateway of that version, not hand-crafted `_sync` xattrs: its own rev-tree, conflict-resolution, and old-rev-backup (`_sync:rev:*`) logic is exactly what the upgrade tests need to see.
3. Stop that Sync Gateway — the bucket is now a static "pre-upgrade" snapshot.

**Option B — regenerate from a previous archive** (only fixture plumbing changed — indexes, cleanup, config — and the existing doc set/history is still valid): restore the *previous* `upgrade.zip`, then immediately do a **second, filtered restore pass** from the same archive to reset TTL on just the delta-sync backup bodies:

```sh
cbbackupmgr restore -a <archive> -c <cluster> -r upgrade -u Administrator -p password \
  --auto-create-buckets --disable-gsi-indexes --disable-ft-indexes
cbbackupmgr restore -a <archive> -c <cluster> -r upgrade -u Administrator -p password \
  --filter-keys '^_sync:rev:' --replace-ttl expired --replace-ttl-with 0 --force-updates
```

`_sync:rev:*` docs are old-revision backup bodies that SGW needs to compute a delta against a legacy ancestor revision (`tests/QE/test_replication_upgrade_delta_sync.py`). Their TTL is normally already expired at restore time, so the second pass must run immediately — once Couchbase Server's expiry pager tombstones an expired doc (can happen within seconds), the body is gone for good. `--force-updates` is required, or conflict resolution sees the doc as unchanged from pass one and skips the rewrite. **Don't** apply `--replace-ttl` to the first pass or to the whole bucket — any other doc's TTL should be left alone (or actually expire), not resurrected.

#### Step 2: delete `_sync:cfg*` and `_sync:dcp_ck*` docs

Needs a temporary primary index — drop it again before backing up.

```sql
DELETE FROM `upgrade` WHERE SUBSTR(META().id, 0, 9) = '_sync:cfg';
DELETE FROM `upgrade` WHERE SUBSTR(META().id, 0, 12) = '_sync:dcp_ck';
```

`_sync:cfg*` are cbgt/XDCR config-tracking docs (`_sync:cfgindexDefs`, `_sync:cfgnodeDefs-known`, etc.) from the source cluster. `_sync:dcp_ck*` are DCP checkpoints, one per vbucket; left in place, they pin SGW's DCP stream to the source cluster's vbucket/seqno state, causing a rollback against the new one.

#### Step 3: verify `num_index_replicas`

Every `_sync:dbconfig:*` doc must have a **top-level** `num_index_replicas` field present and exactly `0` — missing is *not* safe.

```sql
-- Zero rows = pass. A MISSING field is a failure, so don't write this as
-- `NOT (num_index_replicas = 0)` — comparing MISSING evaluates to MISSING,
-- and NOT MISSING is also MISSING, which WHERE silently drops either way.
SELECT META().id, upgrade.num_index_replicas FROM `upgrade`
WHERE SUBSTR(META().id, 0, 15) = '_sync:dbconfig:'
  AND (upgrade.num_index_replicas IS MISSING OR upgrade.num_index_replicas != 0);

-- If that returns rows, patch directly (don't touch other fields, e.g. `version`):
UPDATE `upgrade` SET num_index_replicas = 0 WHERE SUBSTR(META().id, 0, 15) = '_sync:dbconfig:';
```

If `num_index_replicas` is missing, SGW falls back to a positive replica count for its own GSI indexes and fails to initialize them on any cluster with fewer than 2 index nodes (`Unable to create indexes with the specified number of replicas`) — the "upgrade" database then never comes online. Never bring up a live Sync Gateway against this bucket to fix it instead: a different SGW version than the one in the doc's `sg_version` field will refuse to touch the bucket, or will bump its version metadata and break the next SGW that tries.

#### Step 4: back up the cleaned bucket

```sh
cbbackupmgr config -a <new-archive> -r upgrade --disable-gsi-indexes
cbbackupmgr backup -a <new-archive> -c <cluster> -r upgrade -u Administrator -p password
```

`--disable-gsi-indexes` is needed if the cluster's index (GSI) service REST API isn't reachable (e.g. a Dockerized single-node dev cluster with only KV/N1QL ports host-mapped) — harmless either way, since SGW rebuilds whatever indexes it needs the next time it brings the database online.

Zip the resulting archive into `upgrade.zip` (top-level `upgrade/` folder containing the `cbbackupmgr` repo dir, `logs/`, `.backup`, `.tmp` — match the existing layout).
