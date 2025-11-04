import random
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
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
        if await sg.database_exists(sg_db):
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

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
            "Verify all SG docs were created successfully and store revisions, versions"
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
        original_revisions = {row.id: row.revision for row in sg_all_docs.rows}
        if supports_version_vectors:
            original_vv = {row.id: row.cv for row in sg_all_docs.rows}

        self.mark_test_step("Stop Sync Gateway")
        await sg.delete_database(sg_db)

        self.mark_test_step("Update all SG docs via SDK")
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

        self.mark_test_step("Verify revisions, versions and contents of all documents")
        sgw_docs_now, sdk_docs_now = 0, 0
        content_errors = []
        for doc_id in sg_doc_ids + sdk_doc_ids:
            doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            if doc is None:
                content_errors.append(f"SG doc {doc_id} not found")
            elif doc.id.startswith("sg_"):
                sgw_docs_now += 1
                if doc.body.get("updated_by_sdk") is not True:
                    content_errors.append(
                        f"SG doc {doc_id} missing 'updated_by_sdk' flag"
                    )
                if doc.revid == original_revisions.get(doc.id):
                    content_errors.append(f"SG doc {doc_id} has incorrect revision")
                if (
                    supports_version_vectors
                    and doc.cv is not None
                    and doc.cv == original_vv.get(doc.id)
                ):
                    content_errors.append(
                        f"SG doc {doc_id} has incorrect version vector"
                    )
            elif doc.id.startswith("sdk_"):
                sdk_docs_now += 1
                if doc.body.get("created_by") != "sdk":
                    content_errors.append(
                        f"SDK doc {doc_id} has incorrect 'created_by' value"
                    )
        assert sgw_docs_now == num_docs, (
            f"Expected {num_docs} SG docs, got {sgw_docs_now}"
        )
        assert sdk_docs_now == num_docs, (
            f"Expected {num_docs} SDK docs, got {sdk_docs_now}"
        )
        assert len(content_errors) == 0, (
            f"{len(content_errors)} documents didn't have correct content: {content_errors}"
        )

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_purge(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 1000
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
        if await sg.database_exists(sg_db):
            await sg.delete_database(sg_db)
        await sg.put_database(sg_db, db_payload)

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
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if sdk_doc is not None:
                sdk_visible_count += 1
        assert sdk_visible_count == num_docs * 2, (
            f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"
        )

        self.mark_test_step("Delete half of the docs randomly via Sync Gateway")
        random.shuffle(all_doc_ids)
        docs_to_delete = all_doc_ids[:num_docs]
        remaining_docs = all_doc_ids[num_docs:]

        for doc_id in docs_to_delete:
            sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            if sg_doc is not None and sg_doc.revid is not None:
                await sg.delete_document(
                    doc_id, sg_doc.revid, sg_db, "_default", "_default"
                )

        self.mark_test_step(
            "Verify deleted docs visible in changes feed with new revision"
        )
        rev_changes = await sg.get_changes(
            sg_db, "_default", "_default", version_type="rev"
        )
        deleted_revisions, remaining_revisions = 0, 0
        for entry in rev_changes.results:
            if entry.id in docs_to_delete and entry.deleted:
                assert entry.changes[0] != all_doc_revisions.get(entry.id), (
                    f"Deleted doc {entry.id} should have a new revision, got {entry.changes[0]}"
                )
                deleted_revisions += 1
            elif entry.id in remaining_docs:
                assert entry.changes[0] == all_doc_revisions.get(entry.id), (
                    f"Non-deleted doc {entry.id} should have the same revision, got {entry.changes[0]}"
                )
                remaining_revisions += 1
        assert deleted_revisions == len(docs_to_delete), (
            f"Expected to find {len(docs_to_delete)} deleted docs in changes feed, found {deleted_revisions}"
        )
        assert remaining_revisions == len(remaining_docs), (
            f"Expected to find {len(remaining_docs)} non-deleted docs in changes feed, found {remaining_revisions}"
        )

        self.mark_test_step("Verify non-deleted docs still accessible")
        for doc_id in remaining_docs:
            sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            assert sg_doc is not None, (
                f"Non-deleted doc {doc_id} should still be accessible"
            )

        if supports_version_vectors:
            self.mark_test_step(
                "Verify new version vectors for deleted docs (optional)"
            )
            cv_changes = await sg.get_changes(
                sg_db, "_default", "_default", version_type="cv"
            )
            for entry in cv_changes.results:
                if entry.id in docs_to_delete and entry.deleted and entry.changes:
                    assert entry.changes[0] != all_doc_version_vectors.get(entry.id), (
                        f"Deleted doc {entry.id} should have different version vector. "
                        f"Original: {all_doc_version_vectors.get(entry.id)}, Current: {entry.changes[0]}"
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sg_sdk_interop_unique_docs(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        num_updates = 10
        sg_db = "db"
        bucket_name = "data-bucket"

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

        self.mark_test_step("Create user 'vipul' with access to SDK and SG channels")
        await sg.add_user(
            sg_db,
            "vipul",
            password="pass",
            collection_access={
                "_default": {"_default": {"admin_channels": ["sdk", "sg"]}}
            },
        )

        self.mark_test_step(f"Bulk create {num_docs} docs via SDK")
        sdk_doc_ids: list[str] = []
        for i in range(num_docs):
            doc_id = f"sdk_{i}"
            sdk_doc_ids.append(doc_id)
            doc_body = {"content": {"foo": "bar", "updates": 1}, "channels": ["sdk"]}
            cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

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
                    body={"content": {"foo": "bar", "updates": 1}, "channels": ["sg"]},
                )
            )
        await sg.update_documents(sg_db, sg_docs, "_default", "_default")
        all_doc_ids = sdk_doc_ids + sg_doc_ids

        self.mark_test_step("Verify SDK sees all docs")
        sdk_visible_count = 0
        for doc_id in all_doc_ids:
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if sdk_doc is not None:
                sdk_visible_count += 1
        assert sdk_visible_count == num_docs * 2, (
            f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"
        )

        self.mark_test_step("Verify SG sees all docs via _all_docs")
        sg_check = await sg.get_all_documents(sg_db, "_default", "_default")
        assert len(sg_check.rows) == num_docs * 2, (
            f"Expected {num_docs * 2} docs via SG, got {len(sg_check.rows)}"
        )

        self.mark_test_step("Verify SG sees all docs via _changes")
        changes = await sg.get_changes(sg_db, "_default", "_default", version_type="cv")
        assert len(changes.results) == num_docs * 2, (
            f"Expected {num_docs * 2} changes via SG, got {len(changes.results)}"
        )

        self.mark_test_step(f"Bulk update sdk docs {num_updates} times via SDK")
        for _ in range(num_updates):
            for doc_id in sdk_doc_ids:
                sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
                if sdk_doc is not None:
                    sdk_doc["content"]["updates"] += 1
                    cbs.upsert_document(
                        bucket_name, doc_id, sdk_doc, "_default", "_default"
                    )

        self.mark_test_step("Verify SDK docs don't contain _sync metadata")
        for doc_id in sdk_doc_ids[:5]:
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if sdk_doc is not None:
                assert "_sync" not in sdk_doc, f"SDK doc {doc_id} contains _sync"

        self.mark_test_step(f"Bulk update sg docs {num_updates} times via Sync Gateway")
        for _ in range(num_updates):
            sg_docs_to_update: list[DocumentUpdateEntry] = []
            for doc_id in sg_doc_ids:
                sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
                if sg_doc is not None:
                    updated_body = sg_doc.body.copy()
                    updated_body["content"]["updates"] += 1
                    sg_docs_to_update.append(
                        DocumentUpdateEntry(doc_id, sg_doc.revid, updated_body)
                    )
            await sg.update_documents(sg_db, sg_docs_to_update, "_default", "_default")

        self.mark_test_step("Verify SDK sees all doc updates")
        for doc_id in all_doc_ids:
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if sdk_doc is not None:
                assert sdk_doc["content"]["updates"] == num_updates + 1, (
                    f"SDK doc {doc_id} should have {num_updates + 1} updates, got {sdk_doc['content']['updates']}"
                )

        self.mark_test_step("Verify SG sees all doc updates via _all_docs")
        all_docs_updated = await sg.get_all_documents(sg_db, "_default", "_default")
        for row in all_docs_updated.rows:
            sg_doc = await sg.get_document(sg_db, row.id, "_default", "_default")
            if sg_doc is not None:
                assert sg_doc.body["content"]["updates"] == num_updates + 1, (
                    f"SG doc {sg_doc.id} should have {num_updates + 1} updates, got {sg_doc.body['content']['updates']}"
                )

        self.mark_test_step("Verify SDK docs still don't contain _sync after updates")
        for doc_id in sdk_doc_ids:
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            assert sdk_doc is not None, f"SDK doc {doc_id} should not be None"
            assert "_sync" not in sdk_doc, f"SDK doc {doc_id} should not contain _sync"

        self.mark_test_step("Bulk delete sdk docs via SDK")
        for doc_id in sdk_doc_ids:
            cbs.delete_document(bucket_name, doc_id, "_default", "_default")

        self.mark_test_step("Bulk delete sg docs via Sync Gateway")
        for doc_id in sg_doc_ids:
            sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
            if sg_doc is not None and sg_doc.revid is not None:
                await sg.delete_document(
                    doc_id, sg_doc.revid, sg_db, "_default", "_default"
                )

        self.mark_test_step("Verify SDK sees all docs as deleted")
        sdk_deleted_count = 0
        for doc_id in all_doc_ids:
            sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
            if sdk_doc is None or len(sdk_doc) == 0:
                sdk_deleted_count += 1
        assert sdk_deleted_count == num_docs * 2, (
            f"Expected {num_docs * 2} docs to be deleted via SDK, got {sdk_deleted_count}"
        )

        self.mark_test_step("Verify SG sees all docs as deleted via _changes")
        changes_deleted = await sg.get_changes(sg_db, "_default", "_default")
        sg_deleted_count = sum(1 for entry in changes_deleted.results if entry.deleted)
        assert sg_deleted_count == num_docs * 2, (
            f"Expected {num_docs * 2} docs to be deleted via SG, got {sg_deleted_count}"
        )

        await sg.delete_database(sg_db)
        cbs.drop_bucket(bucket_name)
