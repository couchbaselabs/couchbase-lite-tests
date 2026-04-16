import dataclasses
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import (
    DocumentUpdateEntry,
    PutDatabasePayload,
    SyncGateway,
)


@dataclasses.dataclass
class DatabaseConfig:
    bucket_name: str
    channel: str
    username: str


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
class TestDbOnlineOffline(CBLTestClass):
    async def scan_rest_endpoints(
        self,
        sg: SyncGateway,
        db_name: str,
        expected_online: bool,
        num_docs: int = 10,
    ):
        """
        Scans multiple REST endpoints to verify database online/offline state.
        """

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

        for test_name, test_func in test_operations:
            try:
                await test_func()
            except CblSyncGatewayBadResponseError as e:
                if expected_online:
                    assert e is not None, (
                        f"Expected endpoint {test_name} but got exception: {e}"
                    )
                else:
                    # 404 is true for Sync Gateway 4.0.4+ CBG-5156
                    # 403 will occur if Sync Gateway < 4.0.4 or using rosmar
                    assert e.code in [403, 404], (
                        f"Expected 403 or 404 for endpoint {test_name} but got {e.code}"
                    )
                    return
            assert expected_online, (
                f"Expected endpoint {test_name} to fail with 404 if offline, but it succeeded with 200"
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_db_offline_on_bucket_deletion(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        cloud = cblpytest.simple_cloud()
        sg = cloud.sync_gateway
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["ABC"]

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        await cloud.create_database(sg_db, PutDatabasePayload(db_config))

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
        await sg.update_documents(sg_db, sg_docs)

        self.mark_test_step("Verify database is online - REST endpoints work")
        await self.scan_rest_endpoints(sg, sg_db, expected_online=True)
        self.mark_test_step("Delete bucket to sever connection")
        await cloud.drop_bucket(bucket_name)
        await sg.wait_for_no_databases(bucket_name)

        self.mark_test_step("Verify database is offline - REST endpoints return 403")
        await self.scan_rest_endpoints(sg, sg_db, expected_online=False)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_dbs_bucket_deletion(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
    ) -> None:
        cloud = cblpytest.simple_cloud()
        sg = cloud.sync_gateway
        num_docs = 10

        db_configs: dict[str, DatabaseConfig] = {
            "db1": DatabaseConfig("data-bucket-1", "ABC", "vipul"),
            "db2": DatabaseConfig("data-bucket-2", "CBS", "vipul"),
            "db3": DatabaseConfig("data-bucket-3", "ABC", "vipul"),
            "db4": DatabaseConfig("data-bucket-4", "CBS", "lupiv"),
        }

        self.mark_test_step("Create buckets and configure databases")
        for db_name, config in db_configs.items():
            await cloud.create_database(
                db_name,
                PutDatabasePayload(
                    {
                        "bucket": config.bucket_name,
                        "index": {"num_replicas": 0},
                        "scopes": {"_default": {"collections": {"_default": {}}}},
                    }
                ),
            )
            async with sg.create_user_client(
                db_name, config.username, "pass", [config.channel]
            ) as client:
                self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
                sg_docs: list[DocumentUpdateEntry] = []
                for j in range(num_docs):
                    sg_docs.append(
                        DocumentUpdateEntry(
                            f"doc_{j}",
                            None,
                            body={
                                "db": db_name,
                                "index": j,
                                "channels": [config.channel],
                            },
                        )
                    )
                await client.update_documents(db_name, sg_docs, "_default", "_default")

        self.mark_test_step("Verify all databases are online")
        for db_name in db_configs:
            status = await sg.get_database_status(db_name)
            assert status is not None, f"{db_name} database doesn't exist"
            assert status.state == "Online", (
                f"{db_name} should be online, but state is: {status.state}"
            )

        self.mark_test_step(
            "Delete buckets for db1 and db3 and wait for databases to go offline"
        )
        await cloud.drop_bucket("data-bucket-1", wait_for_deleted=True)
        await cloud.drop_bucket("data-bucket-3", wait_for_deleted=True)

        await sg.wait_for_no_databases("data-bucket-1")
        await sg.wait_for_no_databases("data-bucket-3")

        self.mark_test_step("Verify db2 and db4 remain online")
        for db_name in ["db2", "db4"]:
            await self.scan_rest_endpoints(sg, db_name, expected_online=True)

        self.mark_test_step("Verify db1 and db3 are offline (return 403)")
        for db_name in ["db1", "db3"]:
            await self.scan_rest_endpoints(sg, db_name, expected_online=False)
