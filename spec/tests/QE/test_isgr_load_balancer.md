# ISGR Behind a Load Balancer Tests

Regression coverage for CBG-5867: a load balancer fronting two independently-replicating Sync
Gateway backends (kept in sync with continuous bidirectional ISGR) shares one checkpoint
identity across both, since a CBL checkpoint ID is derived from the replication config (the load
balancer's own URL, local db, direction, collections) and never from which physical backend
answers. The confirmed, expected behavior is: a checkpoint ID's first-ever contact with a given
backend forces a one-time full resync (that backend genuinely has no record of it, since ISGR
intentionally never replicates checkpoint docs between the two backends), every later contact
with an already-known backend converges with no redundant transfer, and documents stay correct
throughout. This suite asserts that mechanism keeps holding, not that it's a bug.

## test_checkpoint_divergence_behind_load_balancer

Test that a CBL client pulling through a round-robin load balancer in front of two
continuously-ISGR-linked Sync Gateway backends sees a bounded, self-healing resync pattern
(never an unbounded resync loop, never data loss), by forcing deterministic alternation between
both backends via the `X-Backend` pinning the load balancer already supports.

1. Create a same-named database on both SG1 and SG2 (separate buckets), and a matching user on
   both
2. Start a continuous, bidirectional ISGR link from SG1 to SG2
3. Add one seed document directly on SG1 (native) and wait for it to reach SG2 via ISGR and for
   the channel cache to catch up on both backends -- a document can satisfy a plain document-count
   check before the channel cache that a real pull actually reads from has indexed it, so this
   wait is required, not just the document-count one
4. Create an empty local CBL database and a reusable one-shot pull `Replicator` pointed at the
   load balancer, with its document listener enabled
5. Pull once pinned to SG1 (`X-Backend: sg-0`), then once pinned to SG2 (`X-Backend: sg-1`) --
   first-ever contact with each backend, expect a non-empty document transfer on both
6. Repeat the SG1 / SG2 pinned pulls with no new writes in between -- already-known backends,
   expect zero documents transferred on every one of these
7. Add one more document directly on SG1 and wait for it to reach SG2 via ISGR and for the
   channel cache to catch up on both backends, as in step 3
8. Pull once pinned to SG1, then once pinned to SG2 again -- each backend's next contact after
   the new write, expect a non-empty document transfer on both (and only these two)
9. Repeat the SG1 / SG2 pinned pulls once more with no further writes -- expect zero documents
   transferred again
10. Verify the local CBL database and both SG1 and SG2 (queried directly, bypassing the load
    balancer) all agree on the full document set -- an exact bidirectional comparison (matching
    document count both ways), not a one-directional subset check, so that a backend silently
    losing a document would be caught
11. Verify the SG1-to-SG2 ISGR link itself is still healthy (no error status)

## test_isgr_pull_preserves_channel_set

Regression test for a fixed bug (SGW 4.0.0-4.0.7, 4.1.0-4.1.1): an ISGR pull of a brand-new
document could leave its `_sync.channel_set` null on the receiving side, making the document
invisible on that side's `_changes` feed with no error raised anywhere. Confirmed fixed in
4.0.8 / 4.1.2; this asserts the fix holds on the current default Sync Gateway version.

1. Create a same-named database on both SG1 and SG2 (separate buckets), and a matching user on
   both
2. Start a continuous, bidirectional ISGR link from SG1 to SG2, with SG1 as the active side
3. Add one brand-new document with an explicit channel assignment directly on SG2 (native) --
   since SG1 is the active side of the link, this document reaches SG1 over SG1's own active
   *pull* leg, the direction this regression is actually about (writing on SG1 instead would
   only exercise its active *push* leg, never a pull)
4. Wait for the document to reach SG1 via ISGR, and for SG1's channel cache to catch up -- a
   document can satisfy a plain document-count check before the channel cache that both a
   channel-scoped `_changes` call and a real pull actually read from has indexed it
5. Verify the document is visible through a `request_plus`-consistent `_changes` call scoped to
   that channel on SG1
6. Pull the document through a real CBL client pinned to SG1 (`X-Backend: sg-0`), and verify the
   pull actually transferred it
7. Verify the document's channel assignment arrived intact at the CBL client
