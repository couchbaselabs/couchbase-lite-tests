import asyncio
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload, SyncGateway
from conftest import cleanup_test_resources


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestDbOnlineOffline(CBLTestClass):
    async def scan_rest_endpoints(
        self,
        sg: SyncGateway,
        db_name: str,
        expected_online: bool,
        num_docs: int = 10,
    ) -> tuple[int, int]:
        """
        Scans multiple REST endpoints to verify database online/offline state.
        """
        endpoints_tested = 0
        errors_403 = 0

        test_operations = [
            (
                "GET /{db}/_all_docs",
                lambda: sg.get_all_documents(db_name, "_default", "_default"),
            ),
            (
                "GET /{db}/_changes",
                lambda: sg.get_changes(db_name, "_default", "_default"),
            ),
            (
                "GET /{db}/{doc}",
                lambda: sg.get_document(db_name, "doc_0", "_default", "_default"),
            ),
            (
                "POST /{db}/_bulk_docs",
                lambda: sg.update_documents(
                    db_name,
                    [DocumentUpdateEntry("test_doc", None, {"foo": "bar"})],
                    "_default",
                    "_default",
                ),
            ),
        ]

        for _, test_func in test_operations:
            try:
                await test_func()
                endpoints_tested += 1
            except (CblSyncGatewayBadResponseError, JSONDecodeError) as e:
                endpoints_tested += 1
                if isinstance(e, CblSyncGatewayBadResponseError):
                    if e.code in [403, 503]:
                        errors_403 += 1
                    elif e.code != 404:  # 404 is OK
                        raise e
                elif isinstance(e, JSONDecodeError):
                    errors_403 += 1

        return (endpoints_tested, errors_403)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_db_offline_on_bucket_deletion(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        sg_db = "db_offline_single"
        bucket_name = "bucket-offline-single"
        channels = ["ABC"]
        await cleanup_test_resources(sg, cbs, [bucket_name])

        self.mark_test_step("Create bucket and default collection")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        db_status = await sg.get_database_status(sg_db)
        if db_status is not None:
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs):
            sg_docs.append(
                DocumentUpdateEntry(
                    f"doc_{i}",
                    None,
                    body={"type": "test_doc", "index": i, "channels": channels},
                )
            )
        await sg.update_documents(sg_db, sg_docs, "_default", "_default")

        self.mark_test_step("Verify database is online - REST endpoints work")
        endpoints_tested, errors_403 = await self.scan_rest_endpoints(
            sg, sg_db, expected_online=True
        )
        assert errors_403 == 0, (
            f"DB is online but {errors_403}/{endpoints_tested} endpoints returned 403"
        )

        self.mark_test_step("Delete bucket to sever connection")
        cbs.drop_bucket(bucket_name)
        db_status = await sg.get_database_status(sg_db)
        while db_status is not None and db_status.state == "Online":
            db_status = await sg.get_database_status(sg_db)
            await asyncio.sleep(10)

        self.mark_test_step("Verify database is offline - REST endpoints return 403")
        endpoints_tested, errors_403 = await self.scan_rest_endpoints(
            sg, sg_db, expected_online=False
        )
        assert endpoints_tested > 0, "No endpoints were tested"
        assert errors_403 == endpoints_tested, (
            f"DB is offline but only {errors_403}/{endpoints_tested} endpoints returned 403"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_dbs_bucket_deletion(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        await cleanup_test_resources(
            sg,
            cbs,
            ["data-bucket-1", "data-bucket-2", "data-bucket-3", "data-bucket-4"],
        )

        db_configs: list[list[Any]] = [
            ["db1", "data-bucket-1", "ABC", "vipul", None],
            ["db2", "data-bucket-2", "CBS", "lupiv", None],
            ["db3", "data-bucket-3", "ABC", "vipul", None],
            ["db4", "data-bucket-4", "CBS", "lupiv", None],
        ]

        self.mark_test_step("Create buckets and configure databases")
        for i, [db_name, bucket_name, channel, username, _] in enumerate(db_configs):
            cbs.drop_bucket(bucket_name)
            cbs.create_bucket(bucket_name)

            db_config = {
                "bucket": bucket_name,
                "index": {"num_replicas": 0},
                "scopes": {"_default": {"collections": {"_default": {}}}},
            }
            db_payload = PutDatabasePayload(db_config)
            db_status = await sg.get_database_status(db_name)
            if db_status is not None:
                await sg.delete_database(db_name)
            await sg.put_database(db_name, db_payload)
            db_configs[i][4] = await sg.create_user_client(
                db_name, username, "pass", [channel]
            )

            self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
            sg_docs: list[DocumentUpdateEntry] = []
            for j in range(num_docs):
                sg_docs.append(
                    DocumentUpdateEntry(
                        f"doc_{j}",
                        None,
                        body={"db": db_name, "index": j, "channels": [channel]},
                    )
                )
            await sg.update_documents(db_name, sg_docs, "_default", "_default")

        self.mark_test_step("Verify all databases are online")
        for [db_name, _, _, _, _] in db_configs:
            status = await sg.get_database_status(db_name)
            assert status is not None, f"{db_name} database doesn't exist"
            assert status.state == "Online", (
                f"{db_name} should be online, but state is: {status.state}"
            )

        self.mark_test_step(
            "Delete buckets for db1 and db3 and wait for databases to go offline"
        )
        cbs.drop_bucket("data-bucket-1")
        cbs.drop_bucket("data-bucket-3")
        for db_name in ["db1", "db3"]:
            db_status = await sg.get_database_status(db_name)
            while db_status is not None and db_status.state == "Online":
                db_status = await sg.get_database_status(db_name)
                await asyncio.sleep(10)

        self.mark_test_step("Verify db2 and db4 remain online")
        for db_name in ["db2", "db4"]:
            endpoints_tested, errors_403 = await self.scan_rest_endpoints(
                sg, db_name, expected_online=True
            )
            assert errors_403 == 0, (
                f"{db_name} should be online but got {errors_403} 403 errors"
            )

        self.mark_test_step("Verify db1 and db3 are offline (return 403)")
        for db_name in ["db1", "db3"]:
            endpoints_tested, errors_403 = await self.scan_rest_endpoints(
                sg, db_name, expected_online=False
            )
            assert errors_403 == endpoints_tested, (
                f"{db_name}: Expected all {endpoints_tested} endpoints to return 403, got {errors_403}"
            )

        # Close user clients (cleanup of DBs and buckets handled by cleanup_test_resources)
        for [_, _, _, _, user_client] in db_configs:
            if user_client is not None:
                await user_client.close()
