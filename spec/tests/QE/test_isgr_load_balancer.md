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

## test_checkpoint_divergence_behind_load_balancer

A CBL client pulling through the load balancer, alternating between both backends, resyncs once per backend and never
again. Skipped on SGW 4.0.0-4.0.7 and 4.1.0-4.1.1 (including 4.1.0.1): the ISGR channel-loss bug covered by
`test_isgr_pull_preserves_channel_set` leaves SG2 without the seed document, and 4.0.7 was seen restarting a repeat pull
from since=0.

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
