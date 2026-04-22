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
    async def test_doc_body_size_boundary(self, cblpytest: CBLPyTest) -> None:
        """This test does not use a TS/CBL to replicate documents to SGW
        This is because the batch updater cannot handle such 20MB docs
        And returns 500 error then'n'there..."""
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        sg_db = "db"
        bucket_name = "large-doc-bucket"

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

        self.mark_test_step(
            "Create a 19.9 MB document via SGW admin API — expect acceptance."
        )
        under_limit_payload = _generate_payload(int(19.9 * SIZE_MB), channels=["test"])
        under_limit_doc = await sg.create_document(
            sg_db, "doc_19_9mb", under_limit_payload
        )
        assert under_limit_doc is not None, (
            "SGW should return a RemoteDocument for accepted 19.9 MB doc"
        )
        assert under_limit_doc.id == "doc_19_9mb", (
            f"Returned doc ID mismatch: expected 'doc_19_9mb', got '{under_limit_doc.id}'"
        )
        assert under_limit_doc.revid is not None or under_limit_doc.cv is not None, (
            "Accepted document must have a revision ID or CV assigned by SGW"
        )

        self.mark_test_step(
            "Verify the 19.9 MB document is retrievable from SGW with correct content."
        )
        retrieved_doc = await sg.get_document(
            sg_db, "doc_19_9mb", "_default", "_default"
        )
        assert retrieved_doc is not None, (
            "19.9 MB doc should be retrievable via GET after successful creation"
        )
        assert retrieved_doc.id == "doc_19_9mb", "Retrieved doc ID mismatch"
        assert "data" in retrieved_doc.body, (
            "Retrieved doc body must contain the 'data' field"
        )
        assert len(retrieved_doc.body["data"]) > 19 * SIZE_MB, (
            "Retrieved doc 'data' field should be approximately 19.9 MB"
        )

        self.mark_test_step("Verify 19.9 MB doc appears in _all_docs listing on SGW.")
        all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        all_doc_ids = {row.id for row in all_docs.rows}
        assert "doc_19_9mb" in all_doc_ids, (
            "Accepted 19.9 MB doc must appear in SGW _all_docs response"
        )

        self.mark_test_step(
            "Attempt to create a 20.1 MB document via SGW admin API — expect HTTP 413."
        )
        over_limit_payload = _generate_payload(int(20.1 * SIZE_MB), channels=["test"])
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.create_document(sg_db, "doc_20_1mb", over_limit_payload)

        assert exc_info.value.code == 413, (
            f"SGW should return HTTP 413 for oversized doc, got {exc_info.value.code}"
        )

        self.mark_test_step(
            "Verify the rejected 20.1 MB document does NOT exist in SGW."
        )
        try:
            rejected_doc = await sg.get_document(
                sg_db, "doc_20_1mb", "_default", "_default"
            )
            assert rejected_doc is None, (
                "Rejected 20.1 MB doc must NOT be retrievable from SGW"
            )
        except CblSyncGatewayBadResponseError as e:
            assert e.code == 404, (
                f"Expected 404 for non-existent rejected doc, got HTTP {e.code}"
            )

        self.mark_test_step("Verify rejected doc does NOT appear in _all_docs listing.")
        all_docs_after = await sg.get_all_documents(sg_db, "_default", "_default")
        all_doc_ids_after = {row.id for row in all_docs_after.rows}
        assert "doc_20_1mb" not in all_doc_ids_after, (
            "Rejected 20.1 MB doc must NOT appear in SGW _all_docs"
        )
        assert "doc_19_9mb" in all_doc_ids_after, (
            "Previously accepted 19.9 MB doc must still be in _all_docs after rejection"
        )

        self.mark_test_step(
            "Create a normal 1 KB document to confirm writes still work after rejection."
        )
        small_payload = _generate_payload(1024, channels=["test"])
        small_doc = await sg.create_document(sg_db, "doc_1kb_control", small_payload)
        assert small_doc is not None, (
            "SGW must accept a 1 KB doc after rejecting oversized one"
        )
        assert small_doc.id == "doc_1kb_control", (
            f"Control doc ID mismatch: expected 'doc_1kb_control', got '{small_doc.id}'"
        )

        self.mark_test_step(
            "Verify SGW endpoints are responsive — _config, _changes, _all_docs, database status."
        )
        db_config_resp = await sg.get_database_config(sg_db)
        assert db_config_resp is not None, "SGW _config endpoint must respond"
        assert db_config_resp.get("bucket") == bucket_name, (
            f"_config bucket mismatch: expected '{bucket_name}', got '{db_config_resp.get('bucket')}'"
        )

        changes = await sg.get_changes(sg_db, "_default", "_default")
        assert changes is not None, "SGW _changes endpoint must respond"
        change_doc_ids = {r.id for r in changes.results}
        assert "doc_19_9mb" in change_doc_ids, "19.9 MB doc must appear in _changes"
        assert "doc_1kb_control" in change_doc_ids, (
            "1 KB control doc must appear in _changes"
        )
        assert "doc_20_1mb" not in change_doc_ids, (
            "Rejected 20.1 MB doc must NOT appear in _changes"
        )

        final_all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        final_ids = {row.id for row in final_all_docs.rows}
        assert "doc_19_9mb" in final_ids, "19.9 MB doc must be in _all_docs"
        assert "doc_1kb_control" in final_ids, "1 KB control doc must be in _all_docs"
        assert "doc_20_1mb" not in final_ids, "20.1 MB doc must NOT be in _all_docs"

        db_status = await sg.get_database_status(sg_db)
        assert db_status is not None, "SGW database status endpoint must respond"
        assert db_status.state == "Online", (
            f"SGW database should be Online, got '{db_status.state}'"
        )

        self.mark_test_step(
            "Verify previously accepted 19.9 MB doc is still accessible."
        )
        final_check = await sg.get_document(sg_db, "doc_19_9mb", "_default", "_default")
        assert final_check is not None, (
            "Previously accepted 19.9 MB doc must remain accessible after boundary tests"
        )

        self.mark_test_step(
            "Verify CBS bucket — rejected doc must NOT exist. "
            "(Skipping CBS fetch for accepted large docs due to KV timeout on ~20 MB bodies.)"
        )
        cbs_over = cbs.get_document(bucket_name, "doc_20_1mb")
        assert cbs_over is None, "Rejected 20.1 MB doc must NOT exist in CBS bucket"

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
