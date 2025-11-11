from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload


@pytest.mark.sgw
@pytest.mark.min_test_servers(0)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestDbOnlineOffline(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_db_offline_on_bucket_deletion(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["ABC"]
        username = "vipul"
        password = "pass"

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
        if await sg.database_exists(sg_db):
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to {channels}")
        sg_user = await sg.create_user_client(sg, sg_db, username, password, channels)

        self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        for i in range(num_docs):
            sg_docs.append(
                DocumentUpdateEntry(
                    f"{sg_db}_doc_{i}",
                    None,
                    body={"type": "test_doc", "index": i, "channels": channels},
                )
            )
        await sg.update_documents(sg_db, sg_docs, "_default", "_default")

        self.mark_test_step("Verify database is online - REST endpoints work")
        endpoints_tested, errors_403 = await sg.scan_rest_endpoints(
            sg_db, expected_online=True
        )
        assert errors_403 == 0, (
            f"DB is online but {errors_403}/{endpoints_tested} endpoints returned 403"
        )

        self.mark_test_step("Delete bucket to sever connection")
        cbs.drop_bucket(bucket_name)
        await sg.wait_for_database_to_be_offline(sg_db)

        self.mark_test_step("Verify database is offline - REST endpoints return 403")
        endpoints_tested, errors_403 = await sg.scan_rest_endpoints(
            sg_db, expected_online=False
        )
        assert endpoints_tested > 0, "No endpoints were tested"
        assert errors_403 == endpoints_tested, (
            f"DB is offline but only {errors_403}/{endpoints_tested} endpoints returned 403"
        )

        await sg_user.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_dbs_bucket_deletion(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10

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
            if await sg.database_exists(db_name):
                await sg.delete_database(db_name)
            await sg.put_database(db_name, db_payload)
            db_configs[i][4] = await sg.create_user_client(
                sg, db_name, username, "pass", [channel]
            )

            self.mark_test_step(f"Create {num_docs} docs via Sync Gateway")
            sg_docs: list[DocumentUpdateEntry] = []
            for j in range(num_docs):
                sg_docs.append(
                    DocumentUpdateEntry(
                        f"{db_name}_doc_{j}",
                        None,
                        body={"db": db_name, "index": j, "channels": [channel]},
                    )
                )
            await sg.update_documents(db_name, sg_docs, "_default", "_default")

        self.mark_test_step("Verify all databases are online")
        for [db_name, _, _, _, _] in db_configs:
            endpoints_tested, errors_403 = await sg.scan_rest_endpoints(
                db_name, expected_online=True
            )
            assert errors_403 == 0, (
                f"{db_name} should be online but got {errors_403} 403 errors"
            )

        self.mark_test_step("Delete buckets for db1 and db3")
        cbs.drop_bucket("data-bucket-1")
        cbs.drop_bucket("data-bucket-3")
        await sg.wait_for_database_to_be_offline("db1")
        await sg.wait_for_database_to_be_offline("db3")

        self.mark_test_step("Verify db2 and db4 remain online")
        for db_name in ["db2", "db4"]:
            endpoints_tested, errors_403 = await sg.scan_rest_endpoints(
                db_name, expected_online=True
            )
            assert errors_403 == 0, (
                f"{db_name} should be online but got {errors_403} 403 errors"
            )

        self.mark_test_step("Verify db1 and db3 are offline (return 403)")
        for db_name in ["db1", "db3"]:
            endpoints_tested, errors_403 = await sg.scan_rest_endpoints(
                db_name, expected_online=False
            )
            assert errors_403 == endpoints_tested, (
                f"{db_name}: Expected all {endpoints_tested} endpoints to return 403, got {errors_403}"
            )

        for [db_name, bucket_name, _, _, user_client] in db_configs:
            await user_client.close()
            await sg.delete_database(db_name)
            cbs.drop_bucket(bucket_name)
