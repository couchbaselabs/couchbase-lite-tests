import json
from datetime import timedelta

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from cbltest.api.syncgateway import PutDatabasePayload

SIZE_MB = 1024 * 1024  # A megabyte
SGW_MAX_DOC_SIZE_BYTES = 20 * SIZE_MB  # SGW rejects documents exceeding 20MB
CBS_MAX_XATTR_SIZE_BYTES = 1 * SIZE_MB  # CBS rejects a single XATTR value exceeding 1MB


def _generate_payload(size_bytes: int, *, channels: list[str] | None = None) -> dict:
    """Return a document body whose JSON encoding is approximately `size_bytes`.

    The `data` field is padded with ASCII 'x' characters so that
    ``len(json.dumps(doc))`` is close to the requested size.
    """
    base: dict = {"channels": channels or ["test"]}
    overhead = len(json.dumps({**base, "data": ""}))
    padding = max(0, size_bytes - overhead)
    base["data"] = "x" * padding
    return base


@pytest.mark.sgw
@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestLargeDocWorkloads(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_oversized_attachment_push(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        ts = cblpytest.test_servers[0]
        sg_db = "db"
        bucket_name = "large-blob-bucket"
        username = "blobuser"
        password = "pass"
        channels = ["test"]

        self.mark_test_step("Create bucket on Couchbase Server.")
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway database endpoint.")
        db_config = {
            "bucket": bucket_name,
            "index": {"num_replicas": 0},
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        await sg.put_database(sg_db, db_payload)
        await sg.wait_for_db_up(sg_db)

        self.mark_test_step(f"Create user '{username}' with channel access.")
        await sg.create_user_client(sg_db, username, password, channels)

        self.mark_test_step("Reset local database with empty collection.")
        dbs = await ts.create_and_reset_db(["db1"], collections=["_default._default"])
        db = dbs[0]

        self.mark_test_step(
            "Create a document with a 50 MB blob attachment (xl2.jpg) in CBL."
        )
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default",
                "oversized_blob_doc",
                new_blobs={"attachment": "xl2.jpg"},
            )

        self.mark_test_step("Verify the document and blob exist locally in CBL.")
        local_doc = await db.get_document(
            DocumentEntry("_default._default", "oversized_blob_doc")
        )
        assert local_doc is not None, (
            "Document with 50 MB blob not found in local CBL database"
        )
        assert "attachment" in local_doc.body, (
            "Blob 'attachment' field not present in local document body"
        )
        blob_meta = local_doc.body["attachment"]
        assert isinstance(blob_meta, dict), (
            "Blob attachment should be a dict (blob reference metadata)"
        )

        self.mark_test_step(
            "Also create a small control document to verify partial replication works."
        )
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default",
                "small_control_doc",
                new_properties=[{"type": "control", "channels": channels}],
            )

        local_control = await db.get_document(
            DocumentEntry("_default._default", "small_control_doc")
        )
        assert local_control is not None, "Control doc should exist locally"

        self.mark_test_step(
            "Push replicate to SGW — expect SGW to reject the 50 MB blob."
        )
        push_replicator = Replicator(
            db,
            sg.replication_url(sg_db),
            replicator_type=ReplicatorType.PUSH,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
            authenticator=ReplicatorBasicAuthenticator(username, password),
            pinned_server_cert=sg.tls_cert(),
        )
        await push_replicator.start()
        status = await push_replicator.wait_for(
            ReplicatorActivityLevel.STOPPED,
            timedelta(seconds=10),
            timedelta(seconds=300),
        )
        if status.error is not None:
            print(
                f"INFO: Replicator error (expected for 50 MB blob): "
                f"({status.error.domain} / {status.error.code}) {status.error.message}"
            )
        else:
            print("INFO: Replicator stopped without error despite 50 MB blob")

        self.mark_test_step("Verify SGW did NOT receive the oversized-blob document.")
        sgw_all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        sgw_doc_ids = {row.id for row in sgw_all_docs.rows}
        assert "oversized_blob_doc" not in sgw_doc_ids, (
            "SGW must reject document with 50 MB blob attachment (>20 MB limit)"
        )
        assert len(sgw_all_docs.rows) >= 1, (
            "SGW _all_docs should have at least the control document"
        )

        self.mark_test_step("Verify the oversized doc is not retrievable from SGW.")
        try:
            sgw_rejected = await sg.get_document(
                sg_db, "oversized_blob_doc", "_default", "_default"
            )
            assert sgw_rejected is None, "Oversized blob doc must NOT exist on SGW"
        except CblSyncGatewayBadResponseError as e:
            assert e.code == 404, (
                f"Expected 404 for rejected blob doc on SGW, got HTTP {e.code}"
            )

        self.mark_test_step(
            "Verify the small control document WAS successfully replicated."
        )
        assert "small_control_doc" in sgw_doc_ids, (
            "Small control doc should be replicated successfully "
            "even when another doc was rejected"
        )
        sgw_control = await sg.get_document(
            sg_db, "small_control_doc", "_default", "_default"
        )
        assert sgw_control is not None, "Control doc must be retrievable from SGW"
        assert sgw_control.body.get("type") == "control", (
            "Control doc body content mismatch on SGW"
        )

        self.mark_test_step(
            "Verify local CBL database integrity — blob doc still intact."
        )
        local_doc_after = await db.get_document(
            DocumentEntry("_default._default", "oversized_blob_doc")
        )
        assert local_doc_after is not None, (
            "Local blob doc must remain intact after failed push replication"
        )
        assert "attachment" in local_doc_after.body, (
            "Blob attachment must still be present in local doc after failed push"
        )

        self.mark_test_step("Verify local control doc also still intact.")
        local_control_after = await db.get_document(
            DocumentEntry("_default._default", "small_control_doc")
        )
        assert local_control_after is not None, (
            "Local control doc must remain intact after replication"
        )

        self.mark_test_step("Verify local database has exactly 2 documents.")
        local_all_docs = await db.get_all_documents("_default._default")
        local_doc_ids = {d.id for d in local_all_docs["_default._default"]}
        assert "oversized_blob_doc" in local_doc_ids, (
            "Oversized blob doc must still exist in local CBL database"
        )
        assert "small_control_doc" in local_doc_ids, (
            "Control doc must still exist in local CBL database"
        )
        assert len(local_doc_ids) == 2, (
            f"Expected exactly 2 local docs, found {len(local_doc_ids)}: {local_doc_ids}"
        )

        self.mark_test_step(
            "Verify CBS bucket — control doc present, blob doc NOT present."
        )
        cbs_control = cbs.get_document(bucket_name, "small_control_doc")
        assert cbs_control is not None, (
            "Control doc must exist in CBS bucket after successful replication"
        )
        cbs_blob = cbs.get_document(bucket_name, "oversized_blob_doc")
        assert cbs_blob is None, "Oversized blob doc must NOT exist in CBS bucket"

        await ts.cleanup()
