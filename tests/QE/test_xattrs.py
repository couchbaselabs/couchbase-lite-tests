import asyncio
import random
from collections.abc import Collection
from typing import Any

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    IndexConfig,
    ScopeConfig,
    SyncGateway,
    SyncGatewayUserClient,
)
from couchbase.exceptions import CasMismatchException, DocumentNotFoundException


class _StillUpdating(Exception):
    """Tells the retry loop that documents are still short of their update quota.

    A dedicated type rather than AssertionError, so an assertion raised anywhere inside the
    loop body is a failure rather than being read as progress.
    """


@tenacity.retry(
    wait=tenacity.wait_fixed(2),
    stop=tenacity.stop_after_delay(60),
    reraise=True,
    retry=tenacity.retry_if_exception_type(AssertionError),
)
async def wait_for_purged_documents(
    sg: SyncGateway,
    db_name: str,
    doc_ids: Collection[str],
    scope: str = "_default",
    collection: str = "_default",
) -> None:
    """Poll the changes feed until a purge has emptied it of the documents.

    A purge takes the documents out of the bucket, but the changes feed is not guaranteed to
    have caught up by the time the purge calls return.
    """
    changes = await sg.get_changes(db_name, scope, collection, doc_ids=sorted(doc_ids))
    remaining = sorted({entry.id for entry in changes.results})
    assert not remaining, f"Expected 0 docs in changes feed after purge, found {remaining}"


@tenacity.retry(
    wait=tenacity.wait_fixed(2),
    stop=tenacity.stop_after_delay(60),
    reraise=True,
    retry=tenacity.retry_if_exception_type(AssertionError),
)
async def wait_for_update_count(
    sg_user: SyncGatewayUserClient,
    db_name: str,
    doc_ids: Collection[str],
    expected: int,
) -> None:
    """Poll each document until Sync Gateway reports the expected update count.

    A document Couchbase Server wrote reaches Sync Gateway through import, so a read can come
    back at a revision behind the one the SDK already sees.
    """
    for doc_id in doc_ids:
        doc = await sg_user.get_document(db_name, doc_id)
        actual = doc.body["content"]["updates"]
        assert actual == expected, f"SG doc {doc_id} should have {expected} updates, got {actual}"


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestXattrs(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_offline_processing_of_external_updates(self, cblpytest: CBLPyTest) -> None:
        cluster = cblpytest.clusters[0]
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 100
        username = "vipul"
        password = "pass"
        sg_db = "db"
        bucket_name = "data-bucket"

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cluster.create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user {username} with access to SG and SDK channels")
        async with sg.create_user_client(sg_db, username, password, ["SG", "SDK"]) as sg_user:
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

            await sg.update_documents(sg_db, sg_docs, scope="_default", collection="_default")

            self.mark_test_step("Verify all SG docs were created successfully and store revisions, versions")
            sg_all_docs = await sg_user.wait_for_document_count(sg_db, num_docs)
            sg_created_count = len([doc for doc in sg_all_docs.rows if doc.id.startswith("sg_")])
            assert sg_created_count == num_docs, f"Expected {num_docs} SG docs, but found {sg_created_count}"
            supports_version_vectors = await sg.supports_version_vectors()
            original_revisions = {row.id: row.revision for row in sg_all_docs.rows}
            if supports_version_vectors:
                original_vv = {row.id: row.cv for row in sg_all_docs.rows}

        self.mark_test_step("Delete the Sync Gateway database")
        await cluster.sync_gateway_cluster.delete_database(sg_db)

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

        self.mark_test_step("Restart Sync Gateway database")
        await cluster.sync_gateway_cluster.create_database(sg_db, db_payload)
        async with sg.create_user_client(sg_db, username, password, ["SG", "SDK"]):
            self.mark_test_step("Verify revisions, versions and contents of all documents")
            sgw_docs_now, sdk_docs_now = 0, 0
            content_errors = []
            for doc_id in sg_doc_ids + sdk_doc_ids:
                doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
                if doc.id.startswith("sg_"):
                    sgw_docs_now += 1
                    if doc.body.get("updated_by_sdk") is not True:
                        content_errors.append(f"SG doc {doc_id} missing 'updated_by_sdk' flag")
                    if doc.revid == original_revisions.get(doc.id):
                        content_errors.append(f"SG doc {doc_id} has incorrect revision")
                    if supports_version_vectors and doc.cv is not None and doc.cv == original_vv.get(doc.id):
                        content_errors.append(f"SG doc {doc_id} has incorrect version vector")
                elif doc.id.startswith("sdk_"):
                    sdk_docs_now += 1
                    if doc.body.get("created_by") != "sdk":
                        content_errors.append(f"SDK doc {doc_id} has incorrect 'created_by' value")
            assert sgw_docs_now == num_docs, f"Expected {num_docs} SG docs, got {sgw_docs_now}"
            assert sdk_docs_now == num_docs, f"Expected {num_docs} SDK docs, got {sdk_docs_now}"
            assert len(content_errors) == 0, (
                f"{len(content_errors)} documents didn't have correct content: {content_errors}"
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_purge(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 100
        username = "vipul"
        password = "pass"
        sg_db = "db"
        bucket_name = "data-bucket"
        channels = ["NASA"]

        self.mark_test_step("Configure Sync Gateway database endpoint")
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user {username} with access to channels")
        async with sg.create_user_client(sg_db, username, password, channels) as sg_user:
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

            await sg.update_documents(sg_db, sg_docs, scope="_default", collection="_default")

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
            sg_all_docs = await sg_user.wait_for_document_count(sg_db, num_docs * 2)
            assert len(sg_all_docs.rows) == num_docs * 2, (
                f"Expected {num_docs * 2} docs via SG, got {len(sg_all_docs.rows)}"
            )
            all_doc_revisions: dict[str, str] = {row.id: row.revision for row in sg_all_docs.rows}

            supports_version_vectors = await sg.supports_version_vectors()
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
            assert sdk_visible_count == num_docs * 2, f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"

            self.mark_test_step("Delete half of the docs randomly via Sync Gateway")
            random.shuffle(all_doc_ids)
            docs_to_delete = all_doc_ids[:num_docs]
            remaining_docs = all_doc_ids[num_docs:]

            for doc_id in docs_to_delete:
                sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
                assert sg_doc.revid is not None, f"SG doc {doc_id} has no revision to delete"
                await sg.delete_document(doc_id, sg_doc.revid, sg_db, "_default", "_default")

            self.mark_test_step("Verify deleted docs visible in changes feed with new revision")
            deleted_entries = await sg.wait_for_documents(sg_db, docs_to_delete, "_default", "_default", deleted=True)
            for doc_id, entry in deleted_entries.items():
                assert entry.changes[0] != all_doc_revisions.get(doc_id), (
                    f"Deleted doc {doc_id} should have a new revision, got {entry.changes[0]}"
                )

            remaining_entries = await sg.wait_for_documents(sg_db, remaining_docs, "_default", "_default")
            for doc_id, entry in remaining_entries.items():
                assert entry.changes[0] == all_doc_revisions.get(doc_id), (
                    f"Non-deleted doc {doc_id} should have the same revision, got {entry.changes[0]}"
                )

            self.mark_test_step("Verify non-deleted docs still accessible")
            for doc_id in remaining_docs:
                await sg.get_document(sg_db, doc_id, "_default", "_default")

            if supports_version_vectors:
                self.mark_test_step("Verify new version vectors for deleted docs (optional)")
                cv_entries = await sg.wait_for_documents(
                    sg_db, docs_to_delete, "_default", "_default", deleted=True, version_type="cv"
                )
                for doc_id, entry in cv_entries.items():
                    assert entry.changes[0] != all_doc_version_vectors.get(doc_id), (
                        f"Deleted doc {doc_id} should have different version vector. "
                        f"Original: {all_doc_version_vectors.get(doc_id)}, Current: {entry.changes[0]}"
                    )

            self.mark_test_step("Purge all docs via Sync Gateway")
            for doc_id in all_doc_ids:
                await sg.purge_document(doc_id, sg_db, "_default", "_default")

            self.mark_test_step("Verify XATTRS are gone using changes feed")
            await wait_for_purged_documents(sg, sg_db, all_doc_ids)

            self.mark_test_step("Verify SG can't see any docs after purge")
            sg_docs_after_purge = await sg_user.get_all_documents(sg_db)
            assert len(sg_docs_after_purge.rows) == 0, (
                f"Expected 0 docs after purge, got {len(sg_docs_after_purge.rows)}"
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sg_sdk_interop_unique_docs(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        num_updates = 10
        username = "vipul"
        password = "pass"
        sg_db = "db"
        bucket_name = "data-bucket"

        self.mark_test_step("Configure Sync Gateway with default sync function")
        # Default sync function reads doc.channels from document body
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to SDK and SG channels")
        async with sg.create_user_client(sg_db, username, password, ["sdk", "sg"]) as sg_user:
            self.mark_test_step(f"Bulk create {num_docs} docs via SDK")
            sdk_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"sdk_{i}"
                sdk_doc_ids.append(doc_id)
                doc_body = {
                    "content": {"foo": "bar", "updates": 1},
                    "channels": ["sdk"],
                }
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
                        body={
                            "content": {"foo": "bar", "updates": 1},
                            "channels": ["sg"],
                        },
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
            assert sdk_visible_count == num_docs * 2, f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"

            self.mark_test_step(f"Verify user '{username}' sees all docs via _changes (public API)")
            await sg_user.wait_for_documents(sg_db, all_doc_ids)

            self.mark_test_step(f"Bulk update sdk docs {num_updates} times via SDK")
            for _ in range(num_updates):
                for doc_id in sdk_doc_ids:
                    # Sync Gateway's import writes the _sync xattr, which moves the CAS, so even
                    # an uncontended write can lose the race and has to be reapplied
                    for attempt in tenacity.Retrying(
                        retry=tenacity.retry_if_exception_type(CasMismatchException),
                        stop=tenacity.stop_after_attempt(10),
                        reraise=True,
                    ):
                        with attempt:
                            sdk_doc, cas = cbs.get_document_with_cas(
                                bucket=bucket_name, doc_id=doc_id, scope="_default", collection="_default"
                            )
                            sdk_doc["content"]["updates"] += 1
                            cbs.update_document(
                                bucket=bucket_name,
                                doc_id=doc_id,
                                document=sdk_doc,
                                cas=cas,
                                scope="_default",
                                collection="_default",
                            )

            self.mark_test_step("Verify SDK docs don't contain _sync metadata")
            for doc_id in sdk_doc_ids:
                sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
                assert sdk_doc is not None, f"SDK doc {doc_id} should exist"
                assert "_sync" not in sdk_doc, f"SDK doc {doc_id} contains _sync"

            self.mark_test_step(f"Bulk update sg docs {num_updates} times via Sync Gateway")
            for _ in range(num_updates):
                sg_docs_to_update: list[DocumentUpdateEntry] = []
                for doc_id in sg_doc_ids:
                    sg_doc = await sg.get_document(sg_db, doc_id, "_default", "_default")
                    updated_body = sg_doc.body.copy()
                    updated_body["content"]["updates"] += 1
                    sg_docs_to_update.append(DocumentUpdateEntry(doc_id, sg_doc.revid, updated_body))
                await sg.update_documents(sg_db, sg_docs_to_update, "_default", "_default")

            self.mark_test_step("Verify SDK sees all doc updates")
            for doc_id in all_doc_ids:
                sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
                assert sdk_doc is not None, f"Doc {doc_id} should exist in SDK"
                assert sdk_doc["content"]["updates"] == num_updates + 1, (
                    f"SDK doc {doc_id} should have {num_updates + 1} updates, got {sdk_doc['content']['updates']}"
                )

            self.mark_test_step(f"Verify '{username}' sees all doc updates via the document API")
            await wait_for_update_count(sg_user, sg_db, all_doc_ids, num_updates + 1)

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
                assert sg_doc.revid is not None, f"SG doc {doc_id} has no revision to delete"
                await sg.delete_document(doc_id, sg_doc.revid, sg_db, "_default", "_default")

            self.mark_test_step("Verify SDK sees all docs as deleted")
            sdk_deleted_count = 0
            for doc_id in all_doc_ids:
                sdk_doc = cbs.get_document(bucket_name, doc_id, "_default", "_default")
                if sdk_doc is None or len(sdk_doc) == 0:
                    sdk_deleted_count += 1
            assert sdk_deleted_count == num_docs * 2, (
                f"Expected {num_docs * 2} docs to be deleted via SDK, got {sdk_deleted_count}"
            )

            self.mark_test_step(f"Verify '{username}' sees all docs as deleted via _changes (public API)")
            await sg_user.wait_for_documents(sg_db, all_doc_ids, deleted=True)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sg_sdk_interop_shared_docs(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 10
        num_updates = 10
        username = "vipul"
        password = "pass"
        sg_db = "db"
        bucket_name = "data-bucket"

        self.mark_test_step("Configure Sync Gateway with default sync function")
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(f"Create user '{username}' with access to shared channel")
        async with sg.create_user_client(sg_db, username, password, ["shared"]) as sg_user:
            self.mark_test_step(f"Bulk create {num_docs} docs via SDK with tracking properties")
            sdk_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"doc_set_one_{i}"
                sdk_doc_ids.append(doc_id)
                doc_body = {
                    "updates": 0,
                    "sg_updates": 0,
                    "sdk_updates": 0,
                    "channels": ["shared"],
                }
                cbs.upsert_document(bucket_name, doc_id, doc_body, "_default", "_default")

            self.mark_test_step(f"Bulk create {num_docs} docs via SG with tracking properties")
            sg_docs: list[DocumentUpdateEntry] = []
            sg_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"doc_set_two_{i}"
                sg_doc_ids.append(doc_id)
                sg_docs.append(
                    DocumentUpdateEntry(
                        doc_id,
                        None,
                        body={
                            "updates": 0,
                            "sg_updates": 0,
                            "sdk_updates": 0,
                            "channels": ["shared"],
                        },
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
            assert sdk_visible_count == num_docs * 2, f"Expected {num_docs * 2} docs via SDK, got {sdk_visible_count}"

            self.mark_test_step(f"Verify '{username}' sees all docs via _changes (public API)")
            await sg_user.wait_for_documents(sg_db, all_doc_ids)

            self.mark_test_step(f"Perform concurrent updates ({num_updates} per doc) from SDK and SG")

            # Each attempt advances one document; the retry ends once none are left short.
            def still_updating(docs_remaining: list[str]) -> None:
                if docs_remaining:
                    raise _StillUpdating(f"{len(docs_remaining)} docs still short of {num_updates} updates")

            async def update_from_sg() -> None:
                """Update documents from Sync Gateway side with conflict handling"""
                docs_remaining = list(all_doc_ids)
                async for attempt in tenacity.AsyncRetrying(
                    retry=tenacity.retry_if_exception_type(_StillUpdating),
                    stop=tenacity.stop_after_delay(300),
                    reraise=True,
                ):
                    with attempt:
                        doc_id = random.choice(docs_remaining)
                        try:
                            sg_doc = await sg.get_document(sg_db, doc_id)
                            assert sg_doc.revid is not None, f"SG doc {doc_id} has no revision to update from"
                            if sg_doc.body.get("sg_updates", 0) >= num_updates:
                                docs_remaining.remove(doc_id)
                            else:
                                updated_body = sg_doc.body.copy()
                                updated_body["sg_updates"] = updated_body.get("sg_updates", 0) + 1
                                updated_body["updates"] = updated_body.get("updates", 0) + 1
                                await sg.update_document(sg_db, doc_id, updated_body, sg_doc.revid)
                        except CblSyncGatewayBadResponseError as e:
                            if e.code != 409:  # 409 means someone wrote first, so re-read and try again
                                raise

                        await asyncio.sleep(0.01)  # Small delay to normalize rate
                        still_updating(docs_remaining)

            def update_from_sdk() -> None:
                """Update documents from SDK side with conflict handling"""
                docs_remaining = list(all_doc_ids)
                for attempt in tenacity.Retrying(
                    retry=tenacity.retry_if_exception_type(_StillUpdating),
                    stop=tenacity.stop_after_delay(300),
                    reraise=True,
                ):
                    with attempt:
                        doc_id = random.choice(docs_remaining)
                        sdk_doc, cas = cbs.get_document_with_cas(bucket=bucket_name, doc_id=doc_id)
                        if sdk_doc.get("sdk_updates", 0) >= num_updates:
                            docs_remaining.remove(doc_id)
                        else:
                            # Ensure no _sync metadata in SDK docs
                            assert "_sync" not in sdk_doc, f"SDK doc {doc_id} contains _sync"
                            sdk_doc["sdk_updates"] = sdk_doc.get("sdk_updates", 0) + 1
                            sdk_doc["updates"] = sdk_doc.get("updates", 0) + 1
                            try:
                                cbs.update_document(bucket=bucket_name, doc_id=doc_id, document=sdk_doc, cas=cas)
                            except CasMismatchException:  # Someone wrote first, so re-read and try again
                                pass

                        still_updating(docs_remaining)

            # Run concurrent updates
            await asyncio.gather(update_from_sg(), asyncio.to_thread(update_from_sdk))

            self.mark_test_step("Verify all documents have correct update counts")
            for doc_id in all_doc_ids:
                # Verify from SDK side
                sdk_doc = cbs.get_document(bucket_name, doc_id)
                assert sdk_doc is not None, f"Doc {doc_id} should exist in SDK"
                assert (
                    sdk_doc["updates"] == num_updates * 2
                    and sdk_doc["sg_updates"] == num_updates
                    and sdk_doc["sdk_updates"] == num_updates
                ), (
                    f"Doc {doc_id} should have {num_updates * 2} total updates via SDK, got {sdk_doc['updates']}, ie, SG: {sdk_doc['sg_updates']}, SDK: {sdk_doc['sdk_updates']}"
                )

                # Verify from SG side
                sg_doc = await sg.get_document(sg_db, doc_id)
                assert (
                    sg_doc.body["updates"] == num_updates * 2
                    and sg_doc.body["sdk_updates"] == num_updates
                    and sg_doc.body["sg_updates"] == num_updates
                ), (
                    f"Doc {doc_id} should have {num_updates * 2} total updates via SG, got {sg_doc.body['updates']}, ie, SDK: {sg_doc.body['sdk_updates']}, SG: {sg_doc.body['sg_updates']}"
                )

            self.mark_test_step("Perform concurrent deletes from SDK and SG")

            async def delete_from_sg() -> int:
                """Delete documents from Sync Gateway with conflict handling"""
                deleted_count = 0
                for doc_id in random.sample(all_doc_ids, len(all_doc_ids)):
                    try:
                        sg_doc = await sg.get_document(sg_db, doc_id)
                        if sg_doc.revid is not None:
                            await sg.delete_document(doc_id, sg_doc.revid, sg_db)
                            deleted_count += 1
                    except CblSyncGatewayBadResponseError as e:
                        # 404: the SDK deleted it first.
                        # 409: the SDK deleted it between the read and the delete
                        if e.code not in (404, 409):
                            raise

                    await asyncio.sleep(0.01)
                return deleted_count

            async def delete_from_sdk() -> int:
                """Delete documents from SDK with conflict handling"""
                deleted_count = 0
                for doc_id in random.sample(all_doc_ids, len(all_doc_ids)):
                    try:
                        cbs.delete_document(bucket_name, doc_id)
                        deleted_count += 1
                    except DocumentNotFoundException:  # Sync Gateway deleted it first
                        pass

                    await asyncio.sleep(0.01)
                return deleted_count

            sg_deleted, sdk_deleted = await asyncio.gather(delete_from_sg(), delete_from_sdk())

            assert sg_deleted > 0, f"SG should have deleted at least some documents, got {sg_deleted}"
            assert sdk_deleted > 0, f"SDK should have deleted at least some documents, got {sdk_deleted}"

            self.mark_test_step("Verify all docs deleted from SDK side")
            sdk_deleted_count = 0
            for doc_id in all_doc_ids:
                sdk_doc = cbs.get_document(bucket_name, doc_id)
                if sdk_doc is None or len(sdk_doc) == 0:
                    sdk_deleted_count += 1
            assert sdk_deleted_count == num_docs * 2, (
                f"Expected {num_docs * 2} docs deleted via SDK, got {sdk_deleted_count}"
            )

            self.mark_test_step(f"Verify '{username}' sees all docs as deleted via _changes (public API)")
            await sg_user.wait_for_documents(sg_db, all_doc_ids, deleted=True)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sync_xattrs_update_concurrently(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        num_docs = 20
        sg_db = "db"
        bucket_name = "data-bucket"
        user_custom_channel_xattr = "channel1"
        sg_channel1 = "abc"
        sg_channel2 = "xyz"
        username1 = "vipul"
        username2 = "lupiv"
        password = "password"

        self.mark_test_step("Configure Sync Gateway with custom sync function using xattrs")
        sync_function = f"""
        function(doc, oldDoc, meta) {{
            if (doc._deleted) {{
                return;
            }}
            if (meta.xattrs.{user_custom_channel_xattr} === undefined) {{
                channel("!");
            }} else {{
                channel(meta.xattrs.{user_custom_channel_xattr});
            }}
        }}
        """
        db_payload = DatabaseConfig(
            bucket=bucket_name,
            import_docs=True,
            user_xattr_key=user_custom_channel_xattr,
            index=IndexConfig(num_replicas=0),
            scopes={"_default": ScopeConfig(collections={"_default": {"sync": sync_function}})},
        )
        await cblpytest.clusters[0].create_database(sg_db, db_payload)

        self.mark_test_step(
            f"Create users '{username1}', '{username2}' with access to '{sg_channel1}', '{sg_channel2}'"
        )
        async with (
            sg.create_user_client(sg_db, username1, password, [sg_channel1]) as sg_user1,
            sg.create_user_client(sg_db, username2, password, [sg_channel2]) as sg_user2,
        ):
            self.mark_test_step(
                f"Create {num_docs} docs via SDK with xattr '{user_custom_channel_xattr}={sg_channel1}'"
            )
            sdk_doc_ids: list[str] = []
            for i in range(num_docs):
                doc_id = f"sdk_{i}"
                sdk_doc_ids.append(doc_id)
                doc_body = {
                    "type": "sdk_doc",
                    "index": i,
                }
                cbs.upsert_document(
                    bucket_name,
                    doc_id,
                    doc_body,
                    "_default",
                    "_default",
                    xattrs={user_custom_channel_xattr: sg_channel1},
                )

            self.mark_test_step("Wait for SG to import all docs (as admin)")
            await sg.wait_for_document_count(sg_db, num_docs)

            self.mark_test_step(f"Verify user '{username1}' can see all docs in channel '{sg_channel1}'")
            await sg_user1.wait_for_documents(sg_db, sdk_doc_ids)

            self.mark_test_step(f"Concurrently update xattrs to '{sg_channel2}' while querying docs")

            async def update_xattrs_and_docs() -> None:
                """Update xattrs to move every doc into the second channel"""
                for doc_id in sdk_doc_ids:
                    cbs.upsert_document_xattr(
                        bucket_name,
                        doc_id,
                        user_custom_channel_xattr,
                        sg_channel2,
                        "_default",
                        "_default",
                    )

            async def query_as_user2() -> None:
                """Read the changes feed as user2 while the xattrs are being rewritten"""
                for _ in range(20):
                    await sg_user2.get_changes(sg_db)
                    await asyncio.sleep(0.1)

            # The xattr writes still run to completion before the queries start: the Couchbase SDK
            # calls are synchronous, so these only truly interleave once that SDK is async.
            async with asyncio.TaskGroup() as tg:
                tg.create_task(update_xattrs_and_docs())
                tg.create_task(query_as_user2())

            self.mark_test_step("Delete _sync xattrs to force complete re-processing")
            for doc_id in sdk_doc_ids:
                cbs.delete_document_xattr(bucket_name, doc_id, "_sync", "_default", "_default")

            self.mark_test_step(f"Verify user '{username2}' can now see all docs")
            await sg_user2.wait_for_documents(sg_db, sdk_doc_ids)

            self.mark_test_step(f"Verify user '{username1}' can no longer see any docs")
            user1_changes_after = await sg_user1.get_changes(sg_db)
            still_visible = {e.id for e in user1_changes_after.results if e.id in sdk_doc_ids and not e.removed}
            assert not still_visible, (
                f"User '{username1}' should see 0 docs after xattr change to channel '{sg_channel2}', "
                f"got {sorted(still_visible)}"
            )
