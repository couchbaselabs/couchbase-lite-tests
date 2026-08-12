import asyncio

import pytest_asyncio
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.logging import cbl_info, cbl_trace


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_buckets(cblpytest):
    """
    Remove all Couchbase Server buckets and Sync Gateway databases.

    This runs at the start of each test (rather than as a teardown) to ensure a
    clean slate even if a previous test run was interrupted and left behind a
    dirty environment.

    No-ops when no Sync Gateway is configured (e.g. framework unit/smoke tests),
    since there is nothing to clean up and `SyncGatewayCluster` requires at least
    one node.
    """
    if not cblpytest.sync_gateways:
        return

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup started")

    await asyncio.gather(*(delete_all_databases(sg) for sg in cblpytest.sync_gateways))

    await asyncio.gather(
        *(delete_all_buckets(cbs) for cbs in cblpytest.couchbase_servers)
    )

    cbl_info("🧹 Waiting for Sync Gateway databases to be fully removed")

    await SyncGatewayCluster(cblpytest.sync_gateways).wait_for_no_databases()

    cbl_info("🧹 Couchbase Server and Sync Gateway cleanup finished")


async def delete_all_databases(sg: SyncGateway) -> None:
    """
    Delete every database on the given Sync Gateway node, along with its backing
    Rosmar bucket if the node is using Rosmar (Rosmar bucket data is not deleted
    by removing the database that uses it).
    """
    dbs = await sg.get_all_databases_verbose()
    cbl_trace(f"🧹 SGW {sg}: found databases {list(dbs)}, deleting...")

    await asyncio.gather(*(sg.delete_database(db_name) for db_name in dbs))

    if sg.using_rosmar:
        bucket_names = {entry.bucket for entry in dbs.values()}
        cbl_trace(f"🧹 SGW {sg}: dropping Rosmar buckets {bucket_names}...")
        await asyncio.gather(
            *(sg.drop_rosmar_bucket(bucket_name) for bucket_name in bucket_names)
        )


async def delete_all_buckets(cbs: CouchbaseServer) -> None:
    """
    Delete every bucket on the given Couchbase Server node, and wait for them to be gone.
    """
    bucket_names = cbs.get_bucket_names()
    cbl_trace(f"🧹 CBS {cbs}: found buckets {bucket_names}, deleting...")

    for bucket_name in bucket_names:
        cbs.drop_bucket(bucket_name)

    cbl_trace(f"🧹 CBS {cbs}: waiting for all buckets to be deleted...")
    await cbs.wait_for_no_buckets()
