# ISGR Behind a Load Balancer Tests

Regression coverage for CBG-5867. A CBL client replicating through a load balancer in front of two Sync Gateways (SG1
and SG2, kept in sync by a continuous bidirectional ISGR link from SG1) uses one checkpoint ID for both, because the ID
comes from the replication config, not from the backend that answers. ISGR never copies checkpoints, so the expected
behavior is a one-time full resync on each backend's first contact, no redundant resync after that, and no lost
documents. These tests pin each replication to one backend with the load balancer's `X-Backend` header (`sg-0` is SG1,
`sg-1` is SG2) and check that this keeps holding.

A transfer count can't show a needless resync: ISGR gives both backends identical revisions, so CBL already holds every
document a backend proposes. Each pinned replication is instead judged by a Sync Gateway counter read before and after
it: `num_pull_repl_since_zero` for a pull, `propose_change_count` for a push. Two more checks make sure a change in that
counter came from CBL:

- SG1's ISGR connect-attempt count must not change, since an ISGR reconnect can move the same counters. For the same
  reason, setup returns only after a channel-less document has crossed the link in each direction, so both ISGR legs
  have made their first connection before anything is measured.
- The backend that was not pinned must not move, so a wrong `sg-0`/`sg-1` order fails as a pin-mapping error.

A CBL-observed document-transfer count alone cannot prove "no redundant resync happened" on a
repeat contact: ISGR gives both backends an identical revision for every document, so the puller
already holds it either way, and a backend wrongly re-running a from-scratch proposal would look
exactly like one that genuinely had nothing new -- both read zero transferred documents. Each
backend's own `cbl_replication_pull.num_pull_repl_since_zero` expvar (via
`SyncGateway.get_pull_repl_since_zero_count()`) closes that gap: it increments only when that
backend actually served a pull from `/_changes?since=0`, independent of what the puller already
held, so it is the signal that actually distinguishes an incremental continuation from a repeated
full resync. This stat is a cumulative, node-wide counter, so a before/after delta around each
pinned pull isolates that one call -- but note it is not scoped to CBL-client traffic specifically:
if the continuous SG1-to-SG2 ISGR link itself ever reconnects from scratch during the test, that
would also bump the target backend's counter. The suite doesn't guard against that explicitly
beyond the final ISGR-health check in step 11, since a reconnect there would be its own, separately
surfaced failure.

## test_checkpoint_divergence_behind_load_balancer

A CBL client pulling through the load balancer, alternating between both backends, resyncs once per backend and never
again. Skipped on SGW 4.0.0-4.0.7 and 4.1.0-4.1.1 (including 4.1.0.1): the ISGR channel-loss bug covered by
`test_isgr_pull_preserves_channel_set` leaves SG2 without the seed document, and 4.0.7 was seen restarting a repeat pull
from since=0.

<<<<<<< HEAD
1. Create a same-named database and user on SG1 and SG2 (separate clusters, with `sgr_tls_skip_verify` because both use
   the harness's private CA), start the ISGR link, and wait for a channel-less document to cross it each way
2. Add a seed document on SG1 and wait for its ID on SG2's changes feed. A timeout reports the ISGR link's status
3. Create an empty local database
4. Pull pinned to SG1, then to SG2, the first contact with each. Expect SG1 to transfer documents and both since-zero
   counts to grow by 1. SG2's transfer count isn't checked: CBL already holds the document from SG1, so it reads 0 even
   though SG2 resyncs
5. Twice, pull pinned to SG1 then SG2 with no new writes. Expect no transfer and no since-zero growth
6. Add a document on SG1 and wait for it on SG2, as in step 2
7. Pull pinned to SG1, then to SG2. Expect SG1 to transfer the new document and neither since-zero count to grow
8. Pull pinned to SG1 then SG2 once more. Expect no transfer and no since-zero growth
9. Verify the local database matches SG1 and SG2 exactly for the test's documents, reading both directly rather than
   through the load balancer
10. Verify the ISGR link is not in an error state

## test_push_checkpoint_divergence_behind_load_balancer

The push version of the test above. CBL keeps its push checkpoint on the backend too, so a backend's first push contact
proposes every local document again. Skipped on the same versions.

ISGR pushes into SG2 through the same endpoint that counts proposals. So every push to SG1 is followed by a wait for
its documents to reach SG2 before SG2 is read, and a push pinned to SG1 can't check that SG2 stayed quiet. A swapped pin
is still caught there, because SG1 would read 0 instead of 5 on the first push.

1. Create the database, user and ISGR link as in the pull test
2. Create an empty local database with 5 documents in the user's channel
3. Push pinned to SG1, the first contact: expect SG1's propose count to grow by 5. Wait for the 5 IDs to reach SG2
4. Push pinned to SG2, the first contact: expect SG2's propose count to grow by 5, though SG2 already holds them all
5. Twice, push pinned to SG1 then SG2 with no new writes. Expect neither propose count to grow
6. Add a local document. Push pinned to SG1 (expect +1), wait for it on SG2, then push pinned to SG2 (expect +1, not 6)
7. Verify the local database matches SG1 and SG2 exactly for the test's documents
=======
1. Create a same-named database on both SG1 and SG2 (separate buckets, each with
   `sgr_tls_skip_verify` set since both backends' HTTPS certificates are signed by the harness's
   own private CA, which neither side trusts by default), and a matching user on both
2. Start a continuous, bidirectional ISGR link from SG1 to SG2
3. Add one seed document directly on SG1 (native), confirm it landed on SG1 itself, then wait for
   it to reach SG2 via ISGR and for the channel cache to catch up on both backends -- a document
   can satisfy a plain document-count check before the channel cache that a real pull actually
   reads from has indexed it, so this wait is required, not just the document-count one. A
   propagation timeout attaches the SG1-to-SG2 ISGR link's own status to the failure, so a broken
   link surfaces directly instead of a bare doc-count mismatch
4. Create an empty local CBL database and a reusable one-shot pull `Replicator` pointed at the
   load balancer, with its document listener enabled
5. Pull once pinned to SG1 (`X-Backend: sg-0`) -- first-ever contact with SG1, local CBL db is
   genuinely empty, expect a non-empty document transfer, and expect SG1's own since-zero-pull
   count to increment by 1 (a genuine `/_changes?since=0` proposal). Then pull once pinned to SG2
   (`X-Backend: sg-1`) -- SG2 is also contacted for the first time: its since-zero-pull count is
   expected to increment by 1 too, confirming it genuinely ran its own from-scratch proposal (it
   has no checkpoint for this client either, the mechanism this suite exists to exercise), but no
   transfer-count assertion is made on it: ISGR already gave SG2 the identical revision the SG1
   pull just applied locally, so CBL recognizes it already holds that revision and skips
   re-fetching it -- a redundant-but-correct resync on SG2 is indistinguishable, from the transfer
   count alone, from SG2 having had nothing to offer. Confirmed live: this pull reads 0 transferred
   documents even though SG2 did run its own checkpoint-less proposal
6. Repeat the SG1 / SG2 pinned pulls with no new writes in between -- already-known backends,
   expect zero documents transferred AND no since-zero-pull increment on every one of these. The
   since-zero check is the one that actually catches a checkpoint regression here: the transfer
   count alone reads zero whether the backend is genuinely continuing incrementally or wrongly
   re-running a full resync of already-known content, so only the since-zero signal can tell those
   two apart
7. Add one more document directly on SG1 and wait for it to reach SG2 via ISGR and for the
   channel cache to catch up on both backends, as in step 3 (including the landed-on-SG1 check
   and the ISGR-status-on-timeout diagnostic)
8. Pull once pinned to SG1 -- both backends already hold a valid checkpoint for this client by
   now, so this is a genuine incremental diff containing only the new document, which CBL has
   never seen anywhere; expect a non-empty transfer and no since-zero-pull increment (an
   incremental continuation, not a reset). Then pull once pinned to SG2 -- same transfer-count
   caveat as step 5 applies here too (the SG1 pull moments earlier already gave CBL this same new
   document via an identical revision, so SG2's own contact is not asserted on transfer count), but
   its since-zero-pull count is still checked and expected not to increment
9. Repeat the SG1 / SG2 pinned pulls once more with no further writes -- expect zero documents
   transferred and no since-zero-pull increment again
10. Verify the local CBL database and both SG1 and SG2 (queried directly, bypassing the load
    balancer) all agree on the full document set -- an exact bidirectional comparison (matching
    document count both ways), not a one-directional subset check, so that a backend silently
    losing a document would be caught
11. Verify the SG1-to-SG2 ISGR link itself is still healthy (no error status)
>>>>>>> 2bd39838 (changed helper to catch full-resync cases in future regressiions, uses _changes/since=0)

## test_isgr_pull_preserves_channel_set

Regression test for a bug fixed in SGW 4.0.8 and 4.1.2: an ISGR pull of a new document could leave its
`_sync.channel_set` null on the receiving side, hiding the document from that side's `_changes` feed with no error.
Skipped on the affected versions (4.0.0-4.0.7, 4.1.0-4.1.1, including 4.1.0.1). It pulls from SG1 directly, not through
the load balancer, so it also runs on the JS test server.

1. Create the database, user and ISGR link as in the first test
2. Add a new document with a channel on SG2, so it reaches SG1 through SG1's ISGR pull, the direction the bug affects
3. Wait for its ID on SG1's changes feed. A timeout reports the ISGR link's status
4. Verify the channel-restricted user sees it on SG1's `request_plus` `_changes` feed, which needs the channel the bug
   lost
5. Pull it through CBL directly from SG1 as that user, and verify the pull transferred it
