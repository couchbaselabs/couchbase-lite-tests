# Test Cases

## #1 test_replicate_after_doc_synced_through_two_endpoints

### Description

Checks that a replicator still syncs a document that the local database has pulled through two
different endpoint URLs and then changed. This is the case in CBG-5978.

Couchbase Lite gives each endpoint URL its own remote ID. If a document is pulled through two URLs
and then changed locally, Couchbase Lite replies to a later `changes` message with three known revs:
its local version, then the version that it has from each remote. Sync Gateway versions without the
fix reject this reply as an invalid known rev format. The replicator then never gets the revision,
or any revision after it.

The test reaches one Sync Gateway through two URLs: one with its hostname, and one with the IP address
that the hostname resolves to. The test is skipped if Sync Gateway is configured by IP address,
because then there is no second URL.

The test runs once with each replicator type in the last step: `pull` and `pushAndPull`. Steps 3
and 4 always pull: pushing through each URL there changes what Couchbase Lite records for each
remote, and the later reply to `changes` no longer has three known revs. Every
replication is one-shot and uses the `remote-wins` conflict resolver, so the local edit in step 5
conflicts with the SG edit in a predictable way. Each step checks the local document itself, not
just that the replicator stopped, because a replicator also stops when the changes feed says it has
caught up, which can happen before an SG write reaches the feed.

Requirements:

* Sync Gateway 4.0.9 or a later 4.0 release, or 4.1.3 or later. Sync Gateway 4.1.0 to 4.1.2 do not
  have the fix, and the test is skipped on them.

### Steps

1. Reset SG and load `names` dataset.
2. Reset empty local database.
3. Create `doc1` on SG with `{"write": 1}`, and wait for it to reach the changes feed. Then pull it
   through the hostname URL, and check that the local `doc1` is `{"write": 1}`:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * conflictResolver: `remote-wins`
    * credentials: user1/pass
4. Update `doc1` on SG to `{"write": 2}`, using the revision from step 3, and wait for it to reach
   the changes feed. Then pull it through the IP address URL, and check that the local `doc1` is
   `{"write": 2}`:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * conflictResolver: `remote-wins`
    * credentials: user1/pass
5. Update `doc1` locally to `{"write": "local"}`. Update it on SG to `{"write": 3}`, using the
   revision from step 4, and wait for it to reach the changes feed.
6. Replicate through the hostname URL, and check that the replicator stops with no error and that
   the local `doc1` is `{"write": 3}`:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull / pushAndPull
    * continuous: false
    * conflictResolver: `remote-wins`
    * credentials: user1/pass
