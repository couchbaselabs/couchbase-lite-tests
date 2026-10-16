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

The test runs once with each replicator type in the last step: `pull` and `pushAndPull`.

Requirements:

* Couchbase Lite 4.0.0 or later.
* Sync Gateway 4.0.9 or a later 4.0 release, or 4.1.3 or later. Sync Gateway 4.1.0 to 4.1.2 do not
  have the fix, and the test is skipped on them.

### Steps

1. Reset SG and load `names` dataset.
2. Reset empty local database.
3. Pull through the hostname URL:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Update `name_101` on SG, then pull it through the IP address URL:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
5. Update `name_101` locally, and update it again on SG.
6. Start a continuous replicator through the hostname URL, and wait for it to go idle:
    * endpoint: `/names`
    * collections: `_default._default`
    * type: pull / pushAndPull
    * continuous: true
    * credentials: user1/pass
7. Check that the replicator goes idle in 30 seconds with no error, and that its progress is
   complete.
