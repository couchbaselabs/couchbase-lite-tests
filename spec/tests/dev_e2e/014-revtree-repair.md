# Test Cases

## #1 test_revtree_repaired_after_upgrade

### Description

End to end in one test: build a rev tree corrupted by CBG-5713 using a real Couchbase Lite client
against a Sync Gateway that predates the fix, then restart the Sync Gateway under test over the same
bucket and check it repairs the tree on read and on write.

The test starts the older Sync Gateway itself. It keeps a copy of the binary that is in place, builds
or reuses one from the commit before the CBG-5713 fix, restarts Sync Gateway on it, builds the
corruption, then puts the original binary back. Couchbase Server and the test server are left running
throughout, so the corruption in the bucket and the client's local database both survive the restart —
which is what lets the repair be checked against a client that still holds a pre-repair revision.

```
+------------------------+--------------------------+---------------------------------------+
| Stage                  | Sync Gateway             | Rev tree on Sync Gateway              |
+------------------------+--------------------------+---------------------------------------+
| after the client pushes| built before the fix     | 1-…, 2-…, 3-a, 3-b, 3-c, 3-d  (bad)   |
| after the repair       | the binary under test    | 1-…, 2-…, 3-a, 4-b, 5-c, 6-d  (fixed) |
+------------------------+--------------------------+---------------------------------------+
```

It skips unless Sync Gateway is a local process started from source by `environment/local/start_local.py`,
since it has to restart it. That keeps it inert in CI, where Sync Gateway is a provisioned host.

Two documents are used, one per repair trigger, because the first read or write of a document repairs
it. Both are documents whose client-side legacy revision sits on the same branch as Sync Gateway's, so
the client's pushes are accepted rather than rejected as conflicts:

| Document | Pre-upgrade state | Repair triggered by |
|---|---|---|
| `nonconflict_3` | client and Sync Gateway hold the same legacy revision, neither has an HLV | a read |
| `nonconflict_1` | client is one revision ahead of Sync Gateway on that same branch | a write |

### Steps

1. Keep a copy of the Sync Gateway under test, then start one from before the CBG-5713 fix.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait for SG to bring the restored database online.
4. Reset local database, and load `upgrade` dataset.
5. Check the client holds a legacy revision — a rev tree ID and no HLV — for each document.
6. Update each document 4 times, pushing each revision separately.
7. Check every document's rev tree now has a parent link that does not increase generation.
8. Check Sync Gateway cannot encode the corrupt history for a pre-4.0 client.
9. Restart the Sync Gateway under test over the same bucket.
10. Check `nonconflict_1` is still corrupt, reading it through `_raw` so the read does not repair it.
11. Update `nonconflict_1` through the Sync Gateway admin API.
12. Wait for the written document's rev tree to be repaired.
13. Check generations strictly increase for the written document too.
14. Record the corrupt state of `nonconflict_3` through `_raw`, which does not repair it.
15. Read `nonconflict_3` through the Sync Gateway admin API.
16. Wait for the rev tree to be repaired.
17. Check generations strictly increase from the root of the branch to its leaf.
18. Check the repair renumbered the existing revisions rather than replacing them.
19. Check the repair left the document body alone.
20. Check the repair took a new sequence, so it reaches the changes feed.
21. Check the repaired revision actually reaches the changes feed.
22. Check Sync Gateway counted the invalid rev tree.
23. Check Sync Gateway can now encode the history for a pre-4.0 client.
24. Update `nonconflict_3` on the client on top of the revision it held before the repair, and push it.
25. Check the document converged, and that the rev tree is still well formed.
26. Update `nonconflict_3` again, this time on top of the repaired revision, and push it.
27. Check the second update converged and kept the rev tree well formed.
28. Pull `nonconflict_1` and check the client accepts the repaired revision.
29. Check the pulled document converged and its history is well formed on the client.
30. Update `nonconflict_1` on the client on top of the pulled revision and push it back.
31. Check the round trip converged and left the rev tree well formed.

The write path is checked before the read path deliberately. Repair happens whenever a document is
loaded from the bucket, so anything that reads every document — `compare_local_and_remote` at step 25,
for one — repairs `nonconflict_1` as a side effect. Checked in the other order, step 11 would be
writing to a tree that was already sound. Steps 10 and 14 assert each document is still corrupt for
exactly that reason.

Every check of a document's stored metadata goes through `GET /{db}/_raw/{doc}`, which serves the
`_sync` xattr and the body straight from the bucket via `GetRawDoc`. It is the one Sync Gateway
endpoint that does not go through `GetDocumentWithRaw`, so it is the only way to observe a corrupt
document without repairing the very thing being observed. Reading the bucket with the Couchbase SDK
would work equally well, but needs a second set of credentials and a second client to keep in step
with the collection the test is using.

### Expected Result

Steps 6–8 reproduce CBG-5713: each document's rev tree, walked from root to leaf, contains a revision
whose generation is not higher than its parent's, and `GET /{db}/{doc}?revs=true` returns a
`_revisions` list whose `start` is too low to number its ids.

Steps 11–13 are the repair on write. **The first write is expected to be rejected with a 409**: the
repair renames the revision the caller quoted, so the rev it supplied no longer exists. This mirrors
the read path, where asking for a renamed revision returns `ErrMissing`. The test retries against the
repaired revision and requires that to succeed. Note the write itself is not what was blocked — the
`RevTree.addRevision` guard only compares a new revision against its immediate parent, so even without
the repair the write lands on top of the corrupt branch and leaves the bad links in place.

Steps 16–23 are the repair on read. Generations strictly increase again, every revision keeps its
digest, and the leaf climbs by however many bad links the branch had rather than by exactly one:

```
1-e643a, 2-509dc, 3-24a2c, 3-268b5, 3-1d67e, 3-281f8
      ->  1-e643a, 2-509dc, 3-24a2c, 4-268b5, 5-1d67e, 6-281f8
```

The document body in the bucket is byte for byte what it was before — the repair is a metadata only
write. `invalid_rev_tree_count` under `syncgateway.per_db.<db>.database` rises, the document's
sequence increases, and the repaired revision shows up on `_changes` at that sequence. The last part
is the one worth stating separately: an entry's revision comes from the change cache, which is fed
from the mutation feed, so a repaired revision appearing there is the only proof the sequence the
repair allocated actually reached a client-visible feed. Without it a client already told about the
pre-repair revision would never hear about the repair.

Steps 24–27 are the case that matters most for a client caught mid-upgrade: the client still holds the
revision it pushed onto the pre-repair tree, and a repair that rebuilds the tree must not turn that
into a conflict. The push is accepted with no document error, and the client converges. Step 26 then
writes again from the repaired lineage, which is what every client write does from that point on, and
step 27 requires the winning generation to have climbed past the repaired revision and the history to
still be encodable for a pre-4.0 client.

Steps 28–31 are the pull side, and they use `nonconflict_1` because it is a revision behind: it was
repaired and then written through the admin API at step 11, so the client has to accept a revision
whose ancestors were renamed underneath it. It must apply that as a continuation of the branch it
already holds rather than fork a second one off it — so the pull reports no document error, the client
converges, the body it ends up with is the one the admin API wrote, and the rev tree history the client
holds has strictly increasing generations of its own. Steps 30–31 close the loop by writing on top of
what was pulled and pushing it back.

## Notes

### The bug

A 4.x Couchbase Lite client that holds a **legacy revision** — a rev tree ID with no HLV — keeps
sending that rev ID in its blip `history` on every push. Sync Gateway before the CBG-5713 fix parented
each new revision to its own current revision but took the generation from the incoming history, so
every push added another same-generation link:

```
1-e643a…  ->  2-509dc…  ->  3-24a2c…  ->  3-268b5…  ->  3-1d67e…  ->  3-281f8…
                                          ^^^^^^^^ generation stops increasing here
```

A branch like this cannot be encoded as a `_revisions` list, which requires `start` to be at least the
number of revision ids it has to number. Sync Gateway therefore answers a pre-4.0 pull with
`invalid revision history` and a `norev`, and the document becomes unreplicatable.

The document does, however, stay writable. The `RevTree.addRevision` guard added by the CBG-5713 fix
compares a new revision only against its immediate parent, so writing generation 4 on top of the
generation-3 leaf is accepted and the bad links simply stay where they are — leaving the branch
`1, 2, 3, 3, 3, 3, 4` and still unreplicatable. Repairing on write therefore means fixing the ancestry
when a write happens, not unblocking a write that would otherwise fail.

CBG-5718 adds automatic repair on read and on write. It is always on — there is no config flag to
enable, so this test does nothing to opt in.

### Why the pre-upgrade state comes from a fixture

The client must already hold a legacy revision before the corruption can be built, and it must be a 4.x
client for its pushes to carry an HLV. That state cannot be produced by having the client pull from the
older Sync Gateway this test starts: a 4.x client only offers `BLIP_3+CBMobile_4`, and a pre-4.0 Sync
Gateway answers `I only speak BLIP_3+CBMobile_3,BLIP_3+CBMobile_2` — so the two cannot replicate at
all. Sync Gateway must be upgraded before Couchbase Lite.

The `upgrade` dataset supplies both halves of that pre-upgrade state instead: a Couchbase Server bucket
written by a pre-4.0 Sync Gateway (`dataset/couchbase-server/upgrade.zip`) and a matching local database
in which the client already holds the same legacy revisions
(`dataset/server/dbs/4.0/upgrade.cblite2.zip`). The older Sync Gateway this test starts is a **4.x**
build from before the fix, which is the version that actually creates the corruption.

### Why there is no cleanup() call

Unlike most of dev_e2e, this test does not call `cleanup()`: it resets the test server, and the client's
local database has to survive the Sync Gateway restart in the middle of the test.
`test_replication_upgrade.py` leaves it out for the same reason.

### Running it

Sync Gateway is built from source, because the repair being developed lives in a working tree rather
than a downloadable build. Prerequisites on a fresh clone:

| Need | Why | Check |
|---|---|---|
| Git LFS | the `upgrade` fixture is an LFS object, and the `dataset_path` fixture refuses to run unless **every** LFS file is checked out | `git lfs install --local && git lfs pull` (~120 MB) |
| `uv` | runs everything | `uv --version` |
| Go | the test builds Sync Gateway from source | `go version` |
| CMake + a C/C++ toolchain | builds the Couchbase Lite C test server from source | `cmake --version` |
| A Couchbase Server the host can reach | Sync Gateway and the test both connect to it directly | `curl -u Administrator:password http://localhost:8091/pools` |

A native Couchbase Server install works out of the box. Docker works only if the ports are published to
the host — `start_local.py --start-cbs` (cbdinocluster) allocates a container on the bridge network,
whose IP is **not** routable from a macOS host, so Sync Gateway cannot reach it.

CMake is only needed because a prebuilt test server is downloaded from `latestbuilds`, which requires
the Couchbase VPN. On the VPN, drop `--build-testserver` and let it download instead. The version passed
to `--build-testserver` must be a released Couchbase Lite C version, since the library comes from
`packages.couchbase.com` (4.0.0, 4.0.2, 4.0.3 and 4.1.0 are all available).

Start the test server and your Sync Gateway, then run the test:

```bash
git lfs install --local && git lfs pull

# Test server (CBL C built from source) plus Sync Gateway from your working tree.
uv run environment/local/start_local.py --server cbs --connstr couchbase://127.0.0.1 \
    --repo-path <your sync_gateway checkout> --build-testserver 4.1.0

cd tests/dev_e2e
uv run pytest -s -v --no-header \
    --config "$(cat ../../environment/local/topology_config)" test_revtree_repair.py
```

On later runs only Sync Gateway needs restarting, so add `--skip-testserver` to the `start_local.py`
call. The test caches the pre-fix Sync Gateway build as `environment/local/sync_gateway.prefix`, so the
first run pays for that build (and for cloning the Sync Gateway repo under `environment/local`, if
`--git-tag` has not been used before) and later runs do not.

Against a Sync Gateway without the repair the test fails at step 12, naming the exact link that is
still wrong — e.g. `'3-268b5…' is not a higher generation than its parent '3-24a2c…'`.
