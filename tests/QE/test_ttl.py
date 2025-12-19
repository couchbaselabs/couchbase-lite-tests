import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from conftest import cleanup_test_resources


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestTTL(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_document_expiry_unix_timestamp(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db_ttl_unix"
        bucket_name = "bucket-ttl-unix"
        channels = ["NBC", "ABC"]
        username = "vipul"
        password = "pass"
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

        self.mark_test_step(f"Create user '{username}' with access to {channels}")
        sg_user = await sg.create_user_client(sg_db, username, password, channels)

        self.mark_test_step("Create documents with different expiry times")
        current_time = datetime.now()
        expire_5s = int((current_time + timedelta(seconds=5)).timestamp())
        expire_years = int((current_time + timedelta(days=365)).timestamp())
        await sg.update_documents(
            sg_db,
            [
                DocumentUpdateEntry(
                    "exp_5",
                    None,
                    body={
                        "type": "test_doc",
                        "channels": channels,
                        "_exp": str(expire_5s),
                    },
                )
            ],
            "_default",
            "_default",
        )
        await sg.update_documents(
            sg_db,
            [
                DocumentUpdateEntry(
                    "exp_years",
                    None,
                    body={
                        "type": "test_doc",
                        "channels": channels,
                        "_exp": str(expire_years),
                    },
                )
            ],
            "_default",
            "_default",
        )

        self.mark_test_step("Verify both documents exist initially")
        doc_exp_5 = await sg_user.get_document(sg_db, "exp_5", "_default", "_default")
        doc_exp_years = await sg_user.get_document(
            sg_db, "exp_years", "_default", "_default"
        )
        assert doc_exp_5 is not None, "exp_5 should exist"
        assert doc_exp_years is not None, "exp_years should exist"

        self.mark_test_step("Wait for exp_5 document to expire")
        await asyncio.sleep(10)

        self.mark_test_step("Verify exp_5 document is expired (not accessible)")
        try:
            expired_doc = await sg_user.get_document(
                sg_db, "exp_5", "_default", "_default"
            )
            if expired_doc is not None:
                pytest.fail("exp_5 should be expired/inaccessible")
        except CblSyncGatewayBadResponseError as e:
            assert e.code in [403, 404], (
                f"Expected 403/404 for expired doc, got {e.code}"
            )
        sdk_doc = cbs.get_document(bucket_name, "exp_5", "_default", "_default")
        assert sdk_doc is None, "exp_5 should be purged"

        self.mark_test_step("Verify exp_years document is still accessible")
        doc_still_valid = await sg_user.get_document(
            sg_db, "exp_years", "_default", "_default"
        )
        assert doc_still_valid is not None, "exp_years should still be accessible"
        assert doc_still_valid.id == "exp_years"

        await sg_user.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_string_expiry_as_iso_8601_date(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db_ttl_iso"
        bucket_name = "bucket-ttl-iso"
        channels = ["NBC", "ABC"]
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
        db_status = await sg.get_database_status(sg_db)
        if db_status is not None:
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to {channels}")
        sg_user = await sg.create_user_client(sg_db, username, password, channels)

        self.mark_test_step("Create documents with ISO-8601 expiry dates")
        current_time = datetime.now().astimezone()
        expire_5s_iso = (current_time + timedelta(seconds=5)).isoformat()
        expire_years_iso = (current_time + timedelta(days=365)).isoformat()

        await sg.update_documents(
            sg_db,
            [
                DocumentUpdateEntry(
                    "exp_5",
                    None,
                    body={
                        "type": "test_doc",
                        "channels": channels,
                        "_exp": expire_5s_iso,
                    },
                )
            ],
            "_default",
            "_default",
        )
        await sg.update_documents(
            sg_db,
            [
                DocumentUpdateEntry(
                    "exp_years",
                    None,
                    body={
                        "type": "test_doc",
                        "channels": channels,
                        "_exp": expire_years_iso,
                    },
                )
            ],
            "_default",
            "_default",
        )

        self.mark_test_step("Verify both documents exist initially")
        doc_exp_5 = await sg_user.get_document(sg_db, "exp_5", "_default", "_default")
        doc_exp_years = await sg_user.get_document(
            sg_db, "exp_years", "_default", "_default"
        )
        assert doc_exp_5 is not None, "exp_5 should exist"
        assert doc_exp_years is not None, "exp_years should exist"

        self.mark_test_step("Wait for exp_5 document to expire")
        await asyncio.sleep(10)

        self.mark_test_step("Verify exp_5 document is expired (not accessible)")
        try:
            expired_doc = await sg_user.get_document(
                sg_db, "exp_5", "_default", "_default"
            )
            if expired_doc is not None:
                pytest.fail("exp_5 should be expired/inaccessible")
        except CblSyncGatewayBadResponseError as e:
            assert e.code in [403, 404], (
                f"Expected 403/404 for expired doc, got {e.code}"
            )
        sdk_doc = cbs.get_document(bucket_name, "exp_5", "_default", "_default")
        assert sdk_doc is None, "exp_5 should be purged from bucket"

        self.mark_test_step("Verify exp_years document is still accessible")
        doc_still_valid = await sg_user.get_document(
            sg_db, "exp_years", "_default", "_default"
        )
        assert doc_still_valid is not None, "exp_years should still be accessible"
        assert doc_still_valid.id == "exp_years"

        await sg_user.close()
