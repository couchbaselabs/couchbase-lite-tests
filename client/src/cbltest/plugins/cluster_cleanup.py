import asyncio
from collections.abc import Awaitable, Iterable, Sequence

import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info, cbl_trace


def _raise_if_failed(what: str, errors: Sequence[BaseException]) -> None:
    """
    Raise a single error describing every failure in errors, or return if there were
    none.

    Cleanup failures are never swallowed: a test that runs against a half-cleaned
    environment fails later in a way that is much harder to diagnose than failing here.

    .. note:: Once the Python floor is 3.11 this can become
        ``raise BaseExceptionGroup(what, errors)``, which keeps every sub-exception's
        traceback instead of flattening them into one message.
    """
    if not errors:
        return

    details = "; ".join(f"{type(e).__name__}: {e}" for e in errors)
    raise CblTestError(f"{what} failed ({len(errors)} error(s)): {details}") from errors[0]


async def _gather_all(what: str, coros: Iterable[Awaitable[None]]) -> None:
    """
    Await every coroutine to completion, then raise if any of them failed.

    `asyncio.gather` on its own propagates the first exception while leaving its
    siblings running detached.  The test event loop is session scoped, so those
    orphans keep running into the next test, racing its setup with a half-finished
    delete.  Collect the results instead, so that every deletion is attempted before
    this returns and every failure is reported.
    """
    results = await asyncio.gather(*coros, return_exceptions=True)
    errors = [r for r in results if isinstance(r, BaseException)]
    for error in errors:
        # Cancellation is control flow, not a cleanup failure, so let it through as-is
        if isinstance(error, asyncio.CancelledError):
            raise error

    _raise_if_failed(what, errors)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cluster_cleanup(cblpytest: CBLPyTest) -> None:
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


async def perform_cleanup(cblpytest: CBLPyTest) -> None:
    """
    Remove all Couchbase Server buckets and Sync Gateway databases.

    No-ops when no Sync Gateway is configured (e.g. framework unit/smoke tests),
    since there is nothing to clean up and `SyncGatewayCluster` requires at least
    one node.
    """
    if not cblpytest.clusters:
        return

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup started")

    # Databases are deleted before their backing buckets are dropped, so a failure in
    # the first phase stops the second rather than pulling a bucket out from under a
    # Sync Gateway database that is still configured to use it.
    await _gather_all(
        "Sync Gateway database cleanup",
        [delete_all_databases(cluster.sync_gateway_cluster) for cluster in cblpytest.clusters],
    )

    await _gather_all(
        "Couchbase Server bucket cleanup",
        [delete_all_buckets(cluster) for cluster in cblpytest.clusters],
    )

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup finished")


async def delete_all_databases(cluster: SyncGatewayCluster) -> None:
    """
    Delete every database on every node of the given Sync Gateway cluster, in parallel.

    A node that never learned about a database is not covered by deleting it elsewhere,
    so each node is asked for its own database list.  DELETE is synchronous, so once
    these return there is nothing left to wait for.
    """
    await _gather_all(
        "Deleting Sync Gateway databases",
        [delete_all_databases_on_node(sg) for sg in cluster.sync_gateways],
    )


async def delete_all_databases_on_node(sg: SyncGateway) -> None:
    """
    Delete every database on a single Sync Gateway node, along with its backing Rosmar
    bucket if the node is using Rosmar (Rosmar bucket data is not deleted by removing
    the database that uses it).
    """
    dbs = await sg.get_all_databases_verbose()
    cbl_trace(f"🧹 SGW {sg}: found databases {list(dbs)}, deleting...")

    await _gather_all(
        f"Deleting databases on SGW {sg}",
        [sg.delete_database(db_name) for db_name in dbs],
    )

    if sg.using_rosmar:
        bucket_names = {entry.bucket for entry in dbs.values()}
        cbl_trace(f"🧹 SGW {sg}: dropping Rosmar buckets {bucket_names}...")
        await _gather_all(
            f"Dropping Rosmar buckets on SGW {sg}",
            [sg.drop_rosmar_bucket(bucket_name) for bucket_name in bucket_names],
        )


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
        cbl_trace(f"🧹 CBS {cbs}: no buckets to delete")
        return

    cbl_trace(f"🧹 CBS {cbs}: found buckets {bucket_names}, deleting...")
    errors: list[BaseException] = []
    for bucket_name in bucket_names:
        try:
            cbs.drop_bucket(bucket_name)
        except Exception as e:
            errors.append(e)

    # Raise before waiting: a bucket whose drop failed is still there, so waiting on it
    # can only burn the full timeout before failing anyway.
    _raise_if_failed(f"Dropping buckets on CBS {cbs}", errors)

    cbl_trace(f"🧹 CBS {cbs}: waiting for all buckets to be deleted...")
    await cbs.wait_for_no_buckets()
