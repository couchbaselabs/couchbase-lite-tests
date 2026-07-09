import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.syncgateway import SyncGateway
from cbltest.utils import verify_lfs_checkout

# Markers identifying SGW-focused tests; a session that ran none of these
# (e.g. a CBL-focused platform run) skips SGW log collection (for now).
SGW_LOG_MARKERS = ("sgw", "upg_sgw")


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    verify_lfs_checkout()
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "dataset", "sg")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def collect_sgw_logs(cblpytest, request):
    """
    After the last test of the session, run sgcollect_info on every SGW node
    (in parallel) and download the zips next to this file, where the pipeline
    teardown's move_artifacts places them in the Jenkins artifacts directory.

    Runs while the environment is still up (pytest exits before teardown.sh),
    and only when the session executed at least one SGW-focused test (for now),
    so CBL-focused runs are unaffected. Never fails the session.
    """
    yield

    if not any(
        item.get_closest_marker(marker)
        for item in request.session.items
        for marker in SGW_LOG_MARKERS
    ):
        print("🧾 SGW log collection skipped: no SGW-marked tests in this session")
        return

    try:
        repo_root = str(Path(__file__).resolve().parents[2])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from environment.aws.sg_collect import main as sg_collect_main

        hostnames = [sg.hostname for sg in cblpytest.sync_gateways]
        if not hostnames:
            print("🧾 SGW log collection skipped: no Sync Gateways available in this session")
            return
        ok = await asyncio.to_thread(
            sg_collect_main,
            None,
            output_dir=os.path.dirname(os.path.abspath(__file__)),
            timeout=1800,
            sgw_hosts=hostnames,
        )
        if not ok:
            print(
                "🧾 SGW log collection finished with failures (non-fatal); see logs above."
            )
    except Exception as e:
        print(f"🧾 SGW log collection failed (non-fatal): {e}")


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_after_test(cblpytest, request):
    """
    Automatically clean up all test resources after each SGW test function completes.
    This fixture only runs for tests marked with @pytest.mark.sgw.
    """
    test_name = request.node.name
    try:
        yield  # test runs here
    finally:
        try:
            if request.node.get_closest_marker("sgw"):
                print(
                    "\n================== 🧹 CLEANUP FIXTURE STARTED =================="
                )
                await cleanup_all_test_resources(
                    cblpytest.sync_gateways, cblpytest.couchbase_servers
                )
                print(
                    f"🧹 CLEANUP FIXTURE: Cleanup completed successfully for {test_name}"
                )
            else:
                print(f"🧹 CLEANUP FIXTURE: Skipping non-SGW test: {test_name}")
        except Exception as e:
            print(f"🧹 CLEANUP FIXTURE: Cleanup failed for {test_name}: {e}")
        await asyncio.sleep(2)  # Let all the metadata dust settle down after cleanup


async def cleanup_all_test_resources(
    sync_gateways: list[SyncGateway] | SyncGateway,
    couchbase_servers: list[CouchbaseServer] | CouchbaseServer,
) -> None:
    """
    Clean up ALL databases from ALL SGW instances and test buckets from ALL CBS instances.

    This automatic cleanup runs after each SGW test to prevent resource accumulation.
    Includes robust error handling to avoid interfering with test execution.
    """
    # Handle both single and list inputs
    sg_list = sync_gateways if isinstance(sync_gateways, list) else [sync_gateways]
    cbs_list = (
        couchbase_servers
        if isinstance(couchbase_servers, list)
        else [couchbase_servers]
    )

    # Clean up Sync Gateway databases
    for i, sg in enumerate(sg_list):
        print(f"\t🧹 Processing SGW {i + 1}/{len(sg_list)}")
        try:
            # Get all databases and delete them
            db_names = await sg.get_all_database_names()
            print(f"\t\t🧹 Found {len(db_names)} databases: {db_names}")

            for db_name in db_names:
                try:
                    await sg.delete_database(db_name)
                except Exception as e:
                    print(f"🧹 Failed to delete database {db_name}: {e}")

            # Wait for all databases to be deleted
            for db_name in db_names:
                try:
                    await sg.wait_for_db_gone_clusterwide(sg_list, db_name)
                except Exception as e:
                    print(f"🧹 Failed to wait for database {db_name}: {e}")
        except Exception as e:
            print(f"🧹 Failed to clean up SG {sg}: {e}")

    # Clean up Couchbase Server buckets
    for i, cbs in enumerate(cbs_list):
        print(f"\t🧹 Processing CBS {i + 1}/{len(cbs_list)}")
        try:
            bucket_names = cbs.get_bucket_names()
            print(f"\t\t🧹 Found {len(bucket_names)} buckets: {bucket_names}")

            deleted_buckets = []
            for bucket_name in bucket_names:
                try:
                    cbs.drop_bucket(bucket_name)
                    deleted_buckets.append(bucket_name)
                except Exception as e:
                    print(f"🧹 Failed to drop bucket {bucket_name}: {e}")

            print(
                f"\t\t🧹 Will wait for {len(deleted_buckets)} buckets to be deleted: {deleted_buckets}"
            )
            for bucket_name in deleted_buckets:
                try:
                    await cbs.wait_for_bucket_deleted(bucket_name)
                except Exception as e:
                    print(f"🧹 Failed to wait for bucket {bucket_name}: {e}")
        except Exception as e:
            print(f"🧹 Failed to clean up CBS {cbs}: {e}")
