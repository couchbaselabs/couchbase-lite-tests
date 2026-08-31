"""
Return the backend to a clean slate between tests: every Couchbase Server bucket and
Sync Gateway database removed, and every Edge Server reset to its provisioned state.

Failures are never swallowed: running against a half-cleaned environment fails later in a
much harder way to diagnose.
"""

import asyncio
from collections.abc import Sequence

import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info, cbl_trace


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cluster_cleanup(cblpytest: CBLPyTest) -> None:
    """
    Reset Edge Servers and remove all Couchbase Server buckets and Sync Gateway databases.

    This runs at the start of each test (rather than as a teardown) to ensure a
    clean slate even if a previous test run was interrupted and left behind a
    dirty environment.

    Tests that reuse a shared database/bucket across multiple test functions
    (e.g. `TestQueryConsistency`) can shadow this fixture with a class-scoped
    override that calls `perform_cleanup` once for the whole class instead of
    once per test.
    """
    await perform_cleanup(cblpytest)


async def perform_cleanup(cblpytest: CBLPyTest) -> None:
    """
    Reset every Edge Server, then remove all Sync Gateway databases and Couchbase
    Server buckets.

    Each part no-ops when the corresponding component is absent, so this is safe for
    framework unit/smoke tests (nothing configured), for an Edge Server topology with
    no cluster at all, and for a cluster with no Edge Servers.
    """
    if not cblpytest.clusters and not cblpytest.edge_servers:
        return

    cbl_info("🧹 Backend cleanup started")

    # Edge Servers are reset first. Their provisioned config declares no replications,
    # so once they restart nothing is pulling from the Sync Gateway databases that the
    # next phase deletes.
    await reset_all_edge_servers(cblpytest.edge_servers)

    # Databases are deleted before their backing buckets are dropped, so a failure in
    # the first phase stops the second rather than pulling a bucket out from under a
    # Sync Gateway database that is still configured to use it.
    async with asyncio.TaskGroup() as group:
        for cluster in cblpytest.clusters:
            group.create_task(delete_all_databases(cluster.sync_gateway_cluster))

    async with asyncio.TaskGroup() as group:
        for cluster in cblpytest.clusters:
            group.create_task(delete_all_buckets(cluster))

    cbl_info("🧹 Backend cleanup finished")


async def reset_all_edge_servers(edge_servers: Sequence[EdgeServer]) -> None:
    """
    Reset every Edge Server to its provisioned state, in parallel.

    Unlike Sync Gateway and Couchbase Server, an Edge Server is reconfigured by the
    tests themselves -- swapped onto TLS/users-less configs, killed by the chaos
    tests, firewalled -- and none of that is undone when a test fails partway. Without
    this, one failing test can strand the host for every test after it.
    """
    if not edge_servers:
        return

    cbl_trace(f"🧹 resetting {len(edge_servers)} edge server(s)...")
    async with asyncio.TaskGroup() as group:
        for edge_server in edge_servers:
            group.create_task(edge_server.reset_to_initial_state())


async def delete_all_databases(cluster: SyncGatewayCluster) -> None:
    """
    Delete every database on every node of the given Sync Gateway cluster, in parallel.

    Each node is asked for its own list, since a node that never learned about a database
    is not covered by deleting it elsewhere.  Once this returns no node serves any
    database, so the backing buckets are safe to drop.
    """
    async with asyncio.TaskGroup() as group:
        for sg in cluster.sync_gateways:
            group.create_task(delete_all_databases_on_node(sg))


async def delete_all_databases_on_node(sg: SyncGateway) -> None:
    """
    Delete every database on a single Sync Gateway node, along with its backing Rosmar
    bucket if the node is using Rosmar (Rosmar bucket data is not deleted by removing
    the database that uses it).
    """
    dbs = await sg.get_all_databases_verbose()
    cbl_trace(f"🧹 {sg}: found databases {list(dbs)}, deleting...")

    async with asyncio.TaskGroup() as group:
        for db_name in dbs:
            group.create_task(sg._delete_database(db_name))

    if sg.using_rosmar:
        bucket_names = {entry.bucket for entry in dbs.values()}
        cbl_trace(f"🧹 {sg}: dropping Rosmar buckets {bucket_names}...")
        async with asyncio.TaskGroup() as group:
            for bucket_name in bucket_names:
                group.create_task(sg.drop_rosmar_bucket(bucket_name))


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
    if not bucket_names:
        cbl_trace(f"🧹 {cbs}: no buckets to delete")
        return

    cbl_trace(f"🧹 {cbs}: found buckets {bucket_names}, deleting...")
    for bucket_name in bucket_names:
        cbs.drop_bucket(bucket_name)

    cbl_trace(f"🧹 {cbs}: waiting for all buckets to be deleted...")
    await cbs.wait_for_no_buckets()
