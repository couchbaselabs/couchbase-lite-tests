import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from cbltest.api.couchbaseserver import CouchbaseServer
    from cbltest.api.syncgateway import SyncGateway


# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "..", "dataset", "sg")


async def cleanup_test_resources(
    sgs: "list[SyncGateway] | SyncGateway",
    cbs_servers: "list[CouchbaseServer] | CouchbaseServer",
    bucket_names: list[str] | None = None,
) -> None:
    """
    Clean up all databases from SGW(s) and specified buckets from CBS(s).

    Args:
        sgs: Single SyncGateway or list of SyncGateways to clean up
        cbs_servers: Single CouchbaseServer or list of CouchbaseServers for bucket cleanup
        bucket_names: Optional list of bucket names to drop from each CBS
    """
    # Handle both single SGW and list of SGWs
    sg_list = sgs if isinstance(sgs, list) else [sgs]

    for sg in sg_list:
        await wait_for_admin_ready(sg)

        db_names = await sg.get_all_database_names()
        for db_name in db_names:
            db_status = await sg.get_database_status(db_name)
            if db_status is not None:
                await sg.delete_database(db_name)

        retries = 10
        for db_name in db_names:
            for _ in range(retries):
                db_status = await sg.get_database_status(db_name)
                if db_status is None:
                    break
                await asyncio.sleep(6)
            else:
                raise TimeoutError(f"Database {db_name} did not delete after 1min")

    if bucket_names:
        cbs_list = cbs_servers if isinstance(cbs_servers, list) else [cbs_servers]
        for cbs in cbs_list:
            for bucket_name in bucket_names:
                cbs.drop_bucket(bucket_name)


async def wait_for_admin_ready(
    sg: "SyncGateway", retries: int = 10, delay: float = 1.0
) -> None:
    for _ in range(retries):
        try:
            await sg.get_version()
            return
        except Exception:
            await asyncio.sleep(delay)
    raise TimeoutError("Sync Gateway admin API did not become ready")
