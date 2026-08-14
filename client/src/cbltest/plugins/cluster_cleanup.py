import asyncio

import pytest_asyncio
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info, cbl_trace


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cluster_cleanup(cblpytest):
    """
    Remove all Couchbase Server buckets and Sync Gateway databases.

    This runs at the start of each test (rather than as a teardown) to ensure a
    clean slate even if a previous test run was interrupted and left behind a
    dirty environment.

    Tests that reuse a shared database/bucket across multiple test functions
    (e.g. `TestQueryConsistency`) can shadow this fixture with a class-scoped
    override that calls `perform_cleanup` once for the whole class instead of
    once per test.
    """
    await perform_cleanup(cblpytest)


async def perform_cleanup(cblpytest) -> None:
    """
    Remove all Couchbase Server buckets and Sync Gateway databases.

    No-ops when no Sync Gateway is configured (e.g. framework unit/smoke tests),
    since there is nothing to clean up and `SyncGatewayCluster` requires at least
    one node.
    """
    if not cblpytest.clusters:
        return

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup started")

    await asyncio.gather(*(delete_all_databases(cluster.sync_gateway_cluster) for cluster in cblpytest.clusters))

    await asyncio.gather(*(delete_all_buckets(cluster) for cluster in cblpytest.clusters))

    cbl_info("🧹 Waiting for Sync Gateway databases to be fully removed")

    await asyncio.gather(*(cluster.sync_gateway_cluster.wait_for_no_databases() for cluster in cblpytest.clusters))

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup finished")


async def delete_all_databases(cluster: SyncGatewayCluster) -> None:
    """
    Delete every database in the given Sync Gateway cluster, along with its backing
    Rosmar bucket if the cluster is using Rosmar (Rosmar bucket data is not deleted
    by removing the database that uses it).

    Databases are cluster-wide, so the deletes are issued against a single node.
    """
    sg = cluster.round_robin_node
    dbs = await sg.get_all_databases_verbose()
    cbl_trace(f"🧹 SGW {sg}: found databases {list(dbs)}, deleting...")

    await asyncio.gather(*(sg.delete_database(db_name) for db_name in dbs))

    if sg.using_rosmar:
        bucket_names = {entry.bucket for entry in dbs.values()}
        cbl_trace(f"🧹 SGW {sg}: dropping Rosmar buckets {bucket_names}...")
        await asyncio.gather(*(sg.drop_rosmar_bucket(bucket_name) for bucket_name in bucket_names))


async def delete_all_buckets(cluster: CouchbaseCluster) -> None:
    """
    Delete every bucket in the given cluster, and wait for them to be gone.

    Buckets are cluster-wide, so the deletes are issued against a single node. No-ops
    for a cluster with no Couchbase Server nodes (e.g. Rosmar).
    """
    if not cluster.couchbase_servers:
        return

    cbs = cluster.couchbase_servers[0]
    bucket_names = cbs.get_bucket_names()
    cbl_trace(f"🧹 CBS {cbs}: found buckets {bucket_names}, deleting...")

    for bucket_name in bucket_names:
        cbs.drop_bucket(bucket_name)

    cbl_trace(f"🧹 CBS {cbs}: waiting for all buckets to be deleted...")
    await cbs.wait_for_no_buckets()
