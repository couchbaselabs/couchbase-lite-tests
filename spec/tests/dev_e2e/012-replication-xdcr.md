# Test Cases

Both tests use two Sync Gateway clusters, SG1 and SG2. XDCR links the two clusters in both directions.
Each cluster loads the same dataset on its own. At its start, XDCR settles two versions of every
document. Sync Gateway then imports each XDCR write as a new version.

The tests compare documents by current version (CV) only, never by rev-tree ID:

- "Wait until both SGs have the same CV for every doc" reads the changes feeds of SG1 and SG2. It waits
  until both feeds list the same documents and tombstones with the same CVs. A replicator reads the
  changes feed. Thus a replication after this wait sees the settled versions.
- "Check that the local database has the same CV as SGn for every doc" reads the changes feed of that
  Sync Gateway. It waits until the local database holds exactly the live documents on the feed. Each
  local CV must match the CV on the feed. If the local database matches SG1 and SG1 matches SG2, the
  local database also matches SG2.
- The test server reports the local source of Couchbase Lite as `*`. A local CV that ends in `@*`
  matches a Sync Gateway CV with the same timestamp.

## #1 test_push_and_pull_with_xdcr

### Description

Test push and pull replication through a load balancer that is pinned to SG1. Make sure that the
documents reach both SG clusters.

### Steps

1. Prepare clusters and start XDCR.
2. If XDCR between cluster 1 and cluster 2 is active, stop it.
3. Reset SGs in cluster 1 and 2, and load dataset.
4. Start XDCR between cluster 1 and cluster 2.
5. Wait until both SGs have the same CV for every doc, through XDCR.
6. Reset local database, and load `names` dataset.
7. Put SG1 and SG2 behind the load balancer, and start a replicator pinned to SG1:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push_and_pull
    * continuous: true
8. Wait until the replicator is idle.
9. Wait until both SGs have the same CV for every doc, through XDCR.
10. Check that the local database has the same CV as SG1 for every doc.
11. Update documents in the local database.
    * Add 1 docs in default collection.
    * Update 1 docs in default collection.
    * Remove 1 docs in default collection.
12. Update documents on SG2.
    * Add 1 docs in default collection.
    * Update 1 docs in default collection.
    * Remove 1 docs in default collection.
13. Wait until the replicator is idle.
14. Wait until both SGs have the same CV for every doc, through XDCR.
15. Check that the local database has the same CV as SG1 for every doc, including the updates.

## #2 test_fail_over

### Description

Test that a client can move its replication from SG1 to SG2 through a load balancer. Make sure that
the documents stay in sync across both SG clusters.

### Steps

1.	Prepare clusters and start XDCR.
2.	If XDCR between cluster 1 and cluster 2 is active, stop it.
3.	Reset SGs in cluster 1 and 2, and load the dataset.
4.	Start XDCR between cluster 1 and 2.
5.	Wait until both SGs have the same CV for every doc, through XDCR.
6.	Reset local database and load `names` dataset.
7.	Put SG1 and SG2 behind the load balancer, and start a replicator pinned to SG1:
	* endpoint: /names
	* collections: _default._default
	* type: push_and_pull
	* continuous: false
8.	Wait until the replicator is stopped.
9.	Wait until both SGs have the same CV for every doc, through XDCR.
10.	Check that the local database has the same CV as SG1 for every doc.
11.	Update documents in the local database:
	* Add 1 doc in default collection.
	* Update 1 doc in default collection.
	* Remove 1 doc in default collection.
12.	Update documents on SG2:
	* Add 1 doc in default collection.
	* Update 1 doc in default collection.
	* Remove 1 doc in default collection.
13.	Start the replicator pinned to SG2, to switch the load balancer to SG2.
14.	Wait until the replicator is stopped.
15.	Check that the local database has the same CV as SG2 for every doc, including the updates.
