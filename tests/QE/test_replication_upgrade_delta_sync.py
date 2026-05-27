from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import (
    DocumentUpdateEntry,
    PutDatabasePayload,
    SyncGateway,
)
from shared.upgrade_test_helpers import (
    DocSnapshot,
    do_upgrade_replication_test,
    setup_upgrade_env,
)

# A real delta send is only distinguishable from a full-body fallback by a
# per-rev "deltas sent" counter under syncgateway.per_db.<db>.delta_sync;
# session-level counters increment even when SGW falls back to a full body.
_DELTAS_SENT_KEYS: tuple[str, ...] = ("deltas_sent", "delta_sent", "deltas_sent_count")


def _deltas_sent(stats: dict) -> int | None:
    for key in _DELTAS_SENT_KEYS:
        value = stats.get(key)
        if isinstance(value, int):
            return value
    return None


async def _assert_delta_sync_participated(
    sg: SyncGateway, db_name: str, deltas_sent_before: int | None
) -> None:
    """Assert SGW sent the revision as a delta, not a full-body fallback."""
    deltas_sent_after = _deltas_sent(await sg.get_delta_sync_stats(db_name))
    assert deltas_sent_after is not None, (
        f"No per-rev delta counter in SGW expvar (tried {_DELTAS_SENT_KEYS})."
    )
    assert deltas_sent_after - (deltas_sent_before or 0) > 0, (
        "SGW fell back to a full-body send instead of a delta."
    )


_DELTA_SYNC_UPGRADE_CONFIG: dict = {
    "bucket": "upgrade",
    "num_index_replicas": 0,
    "scopes": {
        "_default": {
            "collections": {
                "_default": {
                    "sync": (
                        "function(doc, oldDoc, meta) {"
                        "  if (doc._deleted) { channel(oldDoc.channels); }"
                        "  else { channel(doc.channels || 'upgrade'); }"
                        "}"
                    )
                }
            }
        }
    },
    "import_docs": True,
    "enable_shared_bucket_access": True,
    "delta_sync": {"enabled": True},
}


@pytest.mark.sgw
@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestUpgradeDeltaSync(CBLTestClass):
    async def _prepare_sg_with_delta_sync(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        payload = PutDatabasePayload(_DELTA_SYNC_UPGRADE_CONFIG)

        self.mark_test_step(
            "Create SG 'upgrade' database with delta_sync enabled and import from bucket"
        )
        try:
            await sg.put_database("upgrade", payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise
            await sg.delete_database("upgrade")
            try:
                await sg.put_database("upgrade", payload)
            except CblSyncGatewayBadResponseError as e2:
                if e2.code != 412:
                    raise
        await sg.wait_for_db_up("upgrade")

        self.mark_test_step(
            "Verify delta_sync is actually enabled on SGW 'upgrade' database"
        )
        config = await sg.get_database_config("upgrade")
        delta_sync = config.get("delta_sync") or {}
        assert delta_sync.get("enabled") is True, (
            "Prerequisite failed: SGW 'upgrade' database does not have "
            f"delta_sync.enabled=True. Active config: {config!r}"
        )

        self.mark_test_step("Create user1 for replication")
        collection_access = sg.create_collection_access_dict(
            {"_default._default": ["*"]}
        )
        await sg.add_user("upgrade", "user1", "pass", collection_access)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_history_pull_post_upgrade_sgw_mutation(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        doc_id = "nonconflict_3"
        db = await setup_upgrade_env(
            self, cblpytest, dataset_path, reset_expired_ttl=True
        )
        await self._prepare_sg_with_delta_sync(cblpytest)
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step(
            f"Mutate '{doc_id}' on 4.x SGW to create a new revtree leaf + HLV."
        )
        current = await sg.get_document("upgrade", doc_id)
        assert current is not None, f"Expected '{doc_id}' imported from bucket"
        assert current.revid is not None, f"Expected '{doc_id}' to have a revid"
        deltas_sent_before = _deltas_sent(await sg.get_delta_sync_stats("upgrade"))
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    current.revid,
                    body={**current.body, "updated_by": "delta_sync_history_test"},
                )
            ],
        )

        def validator(pre: DocSnapshot, post: DocSnapshot) -> None:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Pre local expected revtree-only: revid={pre.local.revid}, hlv={pre.local.cv}"
            )
            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Pre remote expected revtree+HLV: revid={pre.remote.revid}, hlv={pre.remote.cv}"
            )
            assert not pre.remote.cv.endswith("@Revision+Tree+Encoding"), (
                f"Pre remote expected canonical HLV, got RTE-encoded: {pre.remote.cv}"
            )
            assert post.local.revid is None, (
                f"Post local expected HLV-only, got revid={post.local.revid}"
            )
            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"Post HLV mismatch: local={post.local.cv}, remote={post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id=doc_id,
            replicator_type=ReplicatorType.PULL,
            compare_docs=True,
            validator=validator,
        )

        self.mark_test_step("Confirm SGW sent the revision as a delta.")
        await _assert_delta_sync_participated(sg, "upgrade", deltas_sent_before)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_history_pull_pre_upgrade_sgw_two_revs(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        doc_id = "nonconflict_2"
        db = await setup_upgrade_env(
            self, cblpytest, dataset_path, reset_expired_ttl=True
        )
        await self._prepare_sg_with_delta_sync(cblpytest)
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step(
            f"Mutate '{doc_id}' on 4.x SGW to create a new revtree leaf + HLV."
        )
        current = await sg.get_document("upgrade", doc_id)
        assert current is not None, f"Expected '{doc_id}' imported from bucket"
        assert current.revid is not None, f"Expected '{doc_id}' to have a revid"
        deltas_sent_before = _deltas_sent(await sg.get_delta_sync_stats("upgrade"))
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    current.revid,
                    body={**current.body, "updated_by": "delta_sync_history_test"},
                )
            ],
        )

        def validator(pre: DocSnapshot, post: DocSnapshot) -> None:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Pre local expected revtree-only: revid={pre.local.revid}, hlv={pre.local.cv}"
            )
            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Pre remote expected revtree+HLV: revid={pre.remote.revid}, hlv={pre.remote.cv}"
            )
            assert pre.local.revid < pre.remote.revid, (
                f"Pre expected local revid < remote revid: "
                f"local={pre.local.revid}, remote={pre.remote.revid}"
            )
            assert post.local.revid is None, (
                f"Post local expected HLV-only, got revid={post.local.revid}"
            )
            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"Post HLV mismatch: local={post.local.cv}, remote={post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id=doc_id,
            replicator_type=ReplicatorType.PULL,
            compare_docs=True,
            validator=validator,
        )

        self.mark_test_step("Confirm SGW sent the revision as a delta.")
        await _assert_delta_sync_participated(sg, "upgrade", deltas_sent_before)
