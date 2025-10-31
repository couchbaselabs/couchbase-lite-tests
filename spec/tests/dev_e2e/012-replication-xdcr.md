# Test Cases

## #1 test_push_and_pull_with_xdcr

### Description

Test push and pull replication and ensure that the documents are replicated between 
two SG clusters.

### Steps

1. Prepare clusters and start XDCR.
2. Stop XDCR between cluster 1 and cluster 2 if they are active.
3. Reset SGs in cluster 1 and 2, and load dataset.
4. Start XDCR between cluster 1 and cluster 2.
5. Wait 5 secs to ensure that clusters are ready.
6. Reset local database, and load `names` dataset.
7. Start a replicator to SG1 via load balancer:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push_and_pull
    * continuous: true
8. Wait until the replicator is idle.
9. Wait 5 secs to ensure that the docs are sync between two SGs.
10. Check that all docs are replicated correctly at SG1.
11. Check that all docs are replicated correctly at SG2.
12. Update documents in the local database.
    * Add 1 docs in default collection.
    * Update 1 docs in default collection.
    * Remove 1 docs in default collection.
13. Update documents on SG2.
    * Add 1 docs in default collection.
    * Update 1 docs in default collection.
    * Remove 1 docs in default collection.
14. Wait until the replicator is idle.
15. Wait 5 secs to ensure that the docs are sync between two SGs.
16. Check that all updated docs are replicated correctly at SG1.
17. Check that all updated docs are replicated correctly at SG2.

## #2 test_fail_over

### Description

Tests replication failover and recovery between SG clusters via a load balancer to ensure 
data sync continues when one SG node goes offline.

### Steps

1.	Prepare clusters and start XDCR.
2.	Stop XDCR between cluster 1 and cluster 2 if active.
3.	Reset SGs in cluster 1 and 2, and load the dataset.
4.	Start XDCR between cluster 1 and 2.
5.	Wait 5 seconds to ensure clusters are ready.
6.	Reset local database and load `names` dataset.
7.	Start a replicator to SG1 via load balancer:
	* endpoint: /names
	* collections: _default._default
	* type: push_and_pull
	* continuous: false
8.	Wait until the replicator is stopped.
9.	Wait 5 seconds to ensure docs are synced between SGs.
10.	Check that all docs are replicated correctly at SG1.
11.	Check that all docs are replicated correctly at SG2.
12.	Update documents in the local database:
	* Add 1 doc in default collection
	* Update 1 doc in default collection
	* Remove 1 doc in default collection
13.	Update documents on SG2:
	* Add 1 doc in default collection
	* Update 1 doc in default collection
	* Remove 1 doc in default collection
14.	Start the replicator with header X-Backend=sg-1 to tell the load balancer to switch to SG2.
15.	Wait until the replicator is stopped.
16.	Check that all updated docs are replicated correctly at SG2.