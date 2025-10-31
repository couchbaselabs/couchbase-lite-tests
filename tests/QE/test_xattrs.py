import asyncio
import random
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from packaging.version import Version


@pytest.mark.sgw
@pytest.mark.min_test_servers(0)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestXattrs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_offline_processing_of_external_updates(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 1000
        sg_db = "db"
        bucket_name = "data-bucket"

        self.mark_test_step("Create bucket and default collection")
        cbs.drop_bucket(
            bucket_name
        )  # in case the bucket already exists, due to a previous failed test
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_config = {
            "bucket": bucket_name,
            "index": {
                "num_replicas": 0,
            },
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        try:
            await sg.put_database(sg_db, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if (
                e.code == 412
            ):  # in case the database already exists, delete it and try again
                await sg.delete_database(sg_db)
                await sg.put_database(sg_db, db_payload)
            else:
                raise

        self.mark_test_step("Create user 'vipul' with access to SG and SDK channels")
        await sg.add_user(
            sg_db,
            "vipul",
            password="pass",
            collection_access={
                "_default": {"_default": {"admin_channels": ["SG", "SDK", "*"]}}
            },
        )

        self.mark_test_step(f"Bulk create {num_docs} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        sg_doc_ids: list[str] = []
        for i in range(num_docs):
            doc_id = f"sg_{i}"
            sg_doc_ids.append(doc_id)
            sg_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    None,  # No revision for new docs
                    body={
                        "type": "sg_doc",
                        "index": i,
                        "channels": ["SG"],
                        "created_by": "sync_gateway",
                    },
                )
            )

        batch_size = 500
        for batch_start in range(0, num_docs, batch_size):
            batch_end = min(batch_start + batch_size, num_docs)
            await sg.update_documents(
                sg_db,
                sg_docs[batch_start:batch_end],
                scope="_default",
                collection="_default",
            )

        self.mark_test_step(
            "Verify all SG docs were created successfully and store revisions"
        )
        sg_all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        sg_created_count = len(
            [doc for doc in sg_all_docs.rows if doc.id.startswith("sg_")]
        )
        assert sg_created_count == num_docs, (
            f"Expected {num_docs} SG docs, but found {sg_created_count}"
        )
        sgw_version_obj = await sg.get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")
        original_revisions: dict[str, str] = {}
        original_vv: dict[str, str | None] = {}
        for row in sg_all_docs.rows:
            original_revisions[row.id] = row.revision
            if supports_version_vectors:
                original_vv[row.id] = row.cv

        self.mark_test_step("Stop Sync Gateway")
        await sg.delete_database(sg_db)

        self.mark_test_step(f"Update {num_docs} SG docs via SDK")
        for doc_id in sg_doc_ids:
            doc_body: dict[str, Any] = {
                "type": "sg_doc",
                "index": int(doc_id.split("_")[1]),
                "channels": ["SG"],
                "created_by": "sync_gateway",
                "updated_by_sdk": True,
            }
            cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

        self.mark_test_step(f"Write {num_docs} new docs via SDK")
        sdk_doc_ids: list[str] = []
        for i in range(num_docs):
            doc_id = f"sdk_{i}"
            sdk_doc_ids.append(doc_id)
            doc_body = {
                "type": "sdk_doc",
                "index": i,
                "channels": ["SDK"],
                "created_by": "sdk",
            }
            cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

        self.mark_test_step("Restart Sync Gateway (recreate database endpoint)")
        await sg.put_database(sg_db, db_payload)
        await sg.add_user(
            sg_db,
            "seth",
            password="pass",
            collection_access={
                "_default": {"_default": {"admin_channels": ["SG", "SDK", "*"]}}
            },
        )

        self.mark_test_step("Wait for Sync Gateway to import all documents")
        sg_check = await sg.get_all_documents(sg_db, "_default", "_default")
        for _ in range(10):
            if len(sg_check.rows) == num_docs * 2:
                break
            await asyncio.sleep(2)
            sg_check = await sg.get_all_documents(sg_db, "_default", "_default")
        assert len(sg_check.rows) == num_docs * 2, (
            f"Document import verification failed. Expected {num_docs * 2}, got {len(sg_check.rows)} after 10 attempts"
        )

        self.mark_test_step("Verify SG doc revisions changed after SDK update")
        unchanged_sg_docs = []
        sdk_doc_count = 0
        for row in sg_check.rows:
            if row.id.startswith("sg_") and row.revision == original_revisions.get(
                row.id
            ):
                unchanged_sg_docs.append(row.id)
            elif row.id.startswith("sdk_"):
                sdk_doc_count += 1
        assert len(unchanged_sg_docs) == 0, (
            f"{len(unchanged_sg_docs)} SG documents should have changed revisions after SDK update"
        )

        self.mark_test_step("Verify SDK doc count is correct")
        assert sdk_doc_count == num_docs, (
            f"Expected {num_docs} SDK docs imported, found {sdk_doc_count}"
        )

        self.mark_test_step("Verify document contents for all documents")
        content_errors = []
        for doc_id in sg_doc_ids + sdk_doc_ids:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            if doc is None:
                content_errors.append(f"SG doc {doc_id} not found")
            elif (
                doc.id.startswith("sg_") and doc.body.get("updated_by_sdk") is not True
            ):
                content_errors.append(f"SG doc {doc_id} missing 'updated_by_sdk' flag")
            elif doc.id.startswith("sdk_") and doc.body.get("created_by") != "sdk":
                content_errors.append(
                    f"SDK doc {doc_id} has incorrect 'created_by' value"
                )
        assert len(content_errors) == 0, (
            f"{len(content_errors)} documents didn't have correct content"
        )

        if supports_version_vectors:
            self.mark_test_step(
                "Verify version vectors for updated SG documents (optional)"
            )
            for doc in sg_check.rows:
                assert doc.cv != original_vv.get(doc.id), (
                    f"Document {doc.id} should have different version vector after SDK update. "
                    f"Original: {original_vv.get(doc.id)}, Current: {doc.cv}"
                )

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_purge(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 5
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["NASA"]

        self.mark_test_step("Create bucket and default collection")
        cbs.drop_bucket(bucket_name)
        cbs.create_bucket(bucket_name)

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_config = {
            "bucket": bucket_name,
            "index": {
                "num_replicas": 0,
            },
            "scopes": {"_default": {"collections": {"_default": {}}}},
        }
        db_payload = PutDatabasePayload(db_config)
        try:
            await sg.put_database(sg_db, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code == 412:
                await sg.delete_database(sg_db)
                await sg.put_database(sg_db, db_payload)
            else:
                raise

        self.mark_test_step("Create user 'vipul' with access to channels")
        await sg.add_user(
            sg_db,
            "vipul",
            password="pass",
            collection_access={"_default": {"_default": {"admin_channels": channels}}},
        )

        self.mark_test_step(f"Bulk create {num_docs} docs via Sync Gateway")
        sg_docs: list[DocumentUpdateEntry] = []
        sg_doc_ids: list[str] = []
        for i in range(num_docs):
            doc_id = f"sg_{i}"
            sg_doc_ids.append(doc_id)
            sg_docs.append(
                DocumentUpdateEntry(
                    doc_id,
                    None,
                    body={
                        "type": "sg_doc",
                        "index": i,
                        "channels": channels,
                    },
                )
            )

        batch_size = 500
        for batch_start in range(0, num_docs, batch_size):
            batch_end = min(batch_start + batch_size, num_docs)
            await sg.update_documents(
                sg_db,
                sg_docs[batch_start:batch_end],
                scope="_default",
                collection="_default",
            )

        self.mark_test_step(f"Bulk create {num_docs} docs via SDK")
        sdk_doc_ids: list[str] = []
        for i in range(num_docs):
            doc_id = f"sdk_{i}"
            sdk_doc_ids.append(doc_id)
            doc_body = {
                "type": "sdk_doc",
                "index": i,
                "channels": channels,
            }
            cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")
        all_doc_ids = sg_doc_ids + sdk_doc_ids

        self.mark_test_step("Get all docs via Sync Gateway and save revisions")
        sg_all_docs = await sg.get_all_documents(sg_db, "_default", "_default")
        assert len(sg_all_docs.rows) == num_docs * 2, (
            f"Expected {num_docs * 2} docs via SG, got {len(sg_all_docs.rows)}"
        )
        all_doc_revisions: dict[str, str] = {
            row.id: row.revision for row in sg_all_docs.rows
        }

        sgw_version_obj = await sg.get_version()
        sgw_version = Version(sgw_version_obj.version)
        supports_version_vectors = sgw_version >= Version("4.0.0")
        all_doc_version_vectors: dict[str, str | None] = {}
        if supports_version_vectors:
            self.mark_test_step("Store original version vectors for SG docs (optional)")
            all_doc_version_vectors = {row.id: row.cv for row in sg_all_docs.rows}

        self.mark_test_step("Get all docs via SDK and verify count")
        sdk_visible_count = 0
        for doc_id in all_doc_ids:
            doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if doc is not None:
                sdk_visible_count += 1
        assert sdk_visible_count == num_docs * 2, (
            f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"
        )

        self.mark_test_step("Delete half of the docs randomly via Sync Gateway")
        random.shuffle(all_doc_ids)
        docs_to_delete = all_doc_ids[:num_docs]
        remaining_docs = all_doc_ids[num_docs:]

        for doc_id in docs_to_delete:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            if doc and doc.revid:
                await sg.delete_document(
                    doc_id, doc.revid, sg_db, "_default", "_default"
                )

        self.mark_test_step(
            "Verify deleted docs visible in changes feed with new revision"
        )
        changes = await sg.get_changes(
            sg_db, "_default", "_default", version_type="rev"
        )
        deleted_revisions = 0
        for entry in changes.results:
            if entry.id in docs_to_delete and entry.deleted:
                assert entry.revisions[0] != all_doc_revisions.get(entry.id), (
                    f"Deleted doc {entry.id} should have a new revision, got {entry.revisions[0]}"
                )
                deleted_revisions += 1
        assert deleted_revisions == len(docs_to_delete), (
            f"Expected to find {len(docs_to_delete)} deleted docs in changes feed, found {deleted_revisions}"
        )

        self.mark_test_step("Verify non-deleted docs still accessible")
        for doc_id in remaining_docs:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            assert doc is not None, (
                f"Non-deleted doc {doc_id} should still be accessible"
            )

        if supports_version_vectors:
            self.mark_test_step(
                "Verify new version vectors for deleted docs (optional)"
            )
            changes = await sg.get_changes(
                sg_db, "_default", "_default", version_type="cv"
            )
            for entry in changes.results:
                if entry.id in docs_to_delete and entry.deleted:
                    assert entry.cv != all_doc_version_vectors.get(entry.id), (
                        f"Deleted doc {entry.id} should have a different version vector, got {entry.cv}"
                    )

        self.mark_test_step("Purge all docs via Sync Gateway")
        for doc_id in all_doc_ids:
            await sg.purge_document(doc_id, sg_db, "_default", "_default")

        self.mark_test_step("Verify SG can't see any docs after purge")
        sg_docs_after_purge = await sg.get_all_documents(sg_db, "_default", "_default")
        assert len(sg_docs_after_purge.rows) == 0, (
            f"Expected 0 docs after purge, got {len(sg_docs_after_purge.rows)}"
        )

        self.mark_test_step("Verify XATTRS are gone using changes feed")
        changes_after_purge = await sg.get_changes(
            sg_db, "_default", "_default", version_type="rev"
        )
        purged_doc_count = sum(
            1 for entry in changes_after_purge.results if entry.id in all_doc_ids
        )
        assert purged_doc_count == 0, (
            f"Expected 0 docs in changes feed after purge, found {purged_doc_count} (verifies _sync XATTR is removed)"
        )

        self.mark_test_step("Verify SDK can't see any docs after purge")
        sdk_visible_after_purge = 0
        for doc_id in all_doc_ids:
            doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if doc is not None:
                sdk_visible_after_purge += 1
        assert sdk_visible_after_purge == 0, (
            f"Expected 0 docs visible via SDK after purge, got {sdk_visible_after_purge}"
        )

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
