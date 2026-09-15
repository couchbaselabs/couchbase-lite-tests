"""
Return the backend to a clean slate between tests: every Edge Server reset to its
provisioned state, every Sync Gateway database removed, and every Couchbase Server bucket
emptied.

``--bucketpool`` decides how a bucket is emptied: ``delete`` drops it, ``purge`` empties it
in place.

Failures are never swallowed: running against a half-cleaned environment fails later in a
much harder way to diagnose.
"""

import asyncio
from collections.abc import Sequence

import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info, cbl_trace


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cluster_cleanup(cblpytest: CBLPyTest) -> None:
    """
    Reset every Edge Server, then remove all Sync Gateway databases and empty all Couchbase
    Server buckets.

    This runs at the start of each test (rather than as a teardown) to ensure a
    clean slate even if a previous test run was interrupted and left behind a
    dirty environment.

    Tests that reuse a shared database/bucket across multiple test functions
    (e.g. `TestQueryConsistency`) can shadow this fixture with a class-scoped
    override that calls `perform_cleanup` once for the whole class instead of
    once per test. Such a class keeps its Edge Servers between tests too.
    """
    # Edge Servers first: their provisioned config declares no replications, so nothing
    # pulls from the Sync Gateway databases the next phase deletes.
    await reset_all_edge_servers(cblpytest.edge_servers)
    await perform_cleanup(cblpytest)


async def reset_all_edge_servers(managers: Sequence[EdgeServerManager]) -> None:
    """Reset every Edge Server to its provisioned state, in parallel."""
    if not managers:
        return

    cbl_trace(f"🧹 resetting {len(managers)} edge server(s)...")
    async with asyncio.TaskGroup() as group:
        for manager in managers:
            group.create_task(manager.reset_to_initial_state())


async def perform_cleanup(cblpytest: CBLPyTest) -> None:
    """
    Remove all Sync Gateway databases and empty all Couchbase Server buckets.

    No-ops when no Sync Gateway is configured (e.g. framework unit/smoke tests),
    since there is nothing to clean up and `SyncGatewayCluster` requires at least
    one node.
    """
    if not cblpytest.clusters:
        return

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup started")

    # Databases are deleted before their backing buckets are emptied, so a failure in
    # the first phase stops the second rather than purging data out from under a
    # Sync Gateway database that is still configured to use it.
    async with asyncio.TaskGroup() as group:
        for cluster in cblpytest.clusters:
            group.create_task(delete_all_databases(cluster.sync_gateway_cluster))

    async with asyncio.TaskGroup() as group:
        for cluster in cblpytest.clusters:
            group.create_task(clean_all_buckets(cluster))

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup finished")


async def delete_all_databases(cluster: SyncGatewayCluster) -> None:
    """
    Delete every database the given Sync Gateway cluster serves.

    Each node is asked for its own list, since a node that never learned about a database
    is not covered by deleting it elsewhere.  Each database is then deleted on one node
    only: Sync Gateway keeps a single registry document per bucket, and deleting the same
    database from every node at once makes those writes collide on it, which fails the
    delete after five attempts.  The other nodes drop the database when they next re-read
    the config, which is what the wait below is for.

    Each database deletes and then waits in its own task, so one slow delete does not hold
    up the waits for the others, and every node is polled at once.

    Once this returns no node serves any database, so the backing buckets are safe to empty.
    """
    node_databases = await asyncio.gather(*(sg.get_all_databases_verbose() for sg in cluster.sync_gateways))

    # Databases in different buckets have separate registries, so deleting them at the
    # same time does not contend.
    owners: dict[str, SyncGateway] = {}
    rosmar_buckets: dict[SyncGateway, set[str]] = {}
    for sg, databases in zip(cluster.sync_gateways, node_databases, strict=True):
        cbl_trace(f"🧹 {sg}: found databases {list(databases)}")
        for db_name, entry in databases.items():
            owners.setdefault(db_name, sg)
            if sg.using_rosmar:
                rosmar_buckets.setdefault(sg, set()).add(entry.bucket)

    async def delete_and_wait(db_name: str, sg: SyncGateway) -> None:
        """Delete one database, then wait for the nodes that did not take the write."""
        await sg._delete_database(db_name)
        await cluster.wait_for_no_database(db_name)

    if owners:
        cbl_trace(f"🧹 deleting databases {sorted(owners)}...")
        async with asyncio.TaskGroup() as group:
            for db_name, sg in owners.items():
                group.create_task(delete_and_wait(db_name, sg))

    # Rosmar bucket data outlives the database that used it, and each node has its own.
    for sg, bucket_names in rosmar_buckets.items():
        cbl_trace(f"🧹 {sg}: dropping Rosmar buckets {bucket_names}...")
        async with asyncio.TaskGroup() as group:
            for bucket_name in bucket_names:
                group.create_task(sg.drop_rosmar_bucket(bucket_name))


async def clean_all_buckets(cluster: CouchbaseCluster) -> None:
    """
    Empty every bucket in the given cluster, the way the server's cleanup mode asks for.

    Purging keeps the bucket, so the next test reuses its collections and indexes instead of
    paying to rebuild them, and the bucket pool caps how many are kept.  It removes every
    document and every xattr, including the Sync Gateway tombstones that a query cannot see.
    Deleting drops the bucket instead, and the next test creates a new one.

    Buckets are cluster-wide, so the work is issued against a single node. No-ops for a
    cluster with no Couchbase Server nodes (e.g. Rosmar).
    """
    if not cluster.couchbase_servers:
        return

    cbs = cluster.couchbase_servers[0]
    bucket_names = cbs.get_bucket_names()
    if not bucket_names:
        cbl_trace(f"🧹 {cbs}: no buckets to clean")
        return

    cbl_trace(f"🧹 {cbs}: found buckets {bucket_names}, cleaning ({cbs.cleanup_mode})...")
    async with asyncio.TaskGroup() as group:
        for bucket_name in bucket_names:
            group.create_task(cbs.clean_bucket(bucket_name))
