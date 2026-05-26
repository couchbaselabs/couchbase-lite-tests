import json
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
from cbltest.logging import cbl_info
from shared.upgrade_test_helpers import (
    DocSnapshot,
    do_upgrade_replication_test,
    setup_upgrade_env,
)

# ~10KB padding added during the SGW mutation step so the doc body is
# big enough that SGW's delta-sync code path is exercised on pull, and the
# pre/post bytes_transferred delta gives a measurable signal.
_LARGE_PADDING: str = "x" * 10_240


def _delta_counter_total(stats: dict) -> int:
    """Sum the counters in an SGW per-db ``delta_sync`` expvar dict.

    SGW exposes a handful of delta-related counters under
    ``syncgateway.per_db.<db>.delta_sync`` (e.g. ``deltas_sent``,
    ``delta_pull_replication_count``). We sum whichever integer counters
    are present so we don't have to hard-code a specific key name that
    might shift between SGW versions — any positive delta over a pull means
    delta-sync participated.
    """
    return sum(v for v in stats.values() if isinstance(v, int))


async def _assert_delta_sync_participated(
    sg: SyncGateway,
    db_name: str,
    bytes_before: int,
    delta_stats_before: dict,
    new_body_size: int,
) -> None:
    """Verify SGW's delta-sync path actually served the pull.

    Two independent signals are checked; the test passes if either one
    fires (both should fire when delta-sync engages, but we accept either
    so we're resilient to SGW expvar schema drift):

    1. ``delta_sync`` counters in ``/_expvar`` incremented across the pull.
    2. Bytes written by SGW over BLIP for this pull are meaningfully less
       than the full new body — i.e. SGW actually compressed.
    """
    bytes_after, _ = await sg.bytes_transferred(db_name)
    bytes_for_pull = bytes_after - bytes_before

    delta_stats_after = await sg.get_delta_sync_stats(db_name)
    counter_before = _delta_counter_total(delta_stats_before)
    counter_after = _delta_counter_total(delta_stats_after)
    counter_increment = counter_after - counter_before

    cbl_info(
        f"Delta-sync participation check: "
        f"bytes_for_pull={bytes_for_pull}, new_body_size={new_body_size}, "
        f"delta_counter_increment={counter_increment}, "
        f"delta_stats_before={delta_stats_before}, "
        f"delta_stats_after={delta_stats_after}"
    )

    counter_signal = counter_increment > 0
    bytes_signal = 0 < bytes_for_pull < new_body_size

    assert counter_signal or bytes_signal, (
        "Delta-sync did not appear to participate in this pull. "
        f"bytes_for_pull={bytes_for_pull} (expected 0 < x < new_body_size="
        f"{new_body_size}); delta counters delta={counter_increment} "
        f"(before={delta_stats_before}, after={delta_stats_after}). "
        "Either SGW fell back to sending the full body (delta path not "
        "exercised, so the history-field bug cannot manifest), or the "
        "expvar schema we're polling has changed."
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
            # DB already exists. Try to force-recreate so our delta_sync
            # config is applied. delete_database silently swallows 403
            # internally (config-managed DBs), so the delete may be a no-op
            # and the retry put may also 412. Tolerate that — the
            # verify-config assertion below is the real backstop and will
            # dump the active config if delta_sync is not enabled.
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
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "SGW delta-sync history bug: when SGW sends a delta of a "
            "revtree+HLV rev to a client holding the revtree-only ancestor, "
            "the rev message's `history` field is empty. Fix pending. "
            "NOTE: non-strict — the bug currently does not surface through "
            "end-state revid/HLV/body comparison (likely a BLIP wire-level "
            "issue only). When the SGW fix lands, flip strict=True so an "
            "XPASS becomes a loud signal to remove this decorator."
        ),
    )
    async def test_delta_sync_history_pull_post_upgrade_sgw_mutation(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        doc_id = "nonconflict_3"
        db = await setup_upgrade_env(self, cblpytest, dataset_path)
        await self._prepare_sg_with_delta_sync(cblpytest)
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step(
            f"Mutate '{doc_id}' on 4.x SGW with a large body so delta-sync "
            "engages on the subsequent pull. The new rev gets revtree + HLV."
        )
        current = await sg.get_document("upgrade", doc_id)
        assert current is not None, f"Expected '{doc_id}' imported from bucket"
        assert current.revid is not None, (
            f"Expected '{doc_id}' to have a revid pre-mutation, got None"
        )
        # New body: keep the original fields (so client's ancestor body overlaps
        # with the new rev — gives delta-sync something meaningful to compress),
        # plus a substantial padding field to make the new body large enough
        # that "bytes transferred < new body size" is a clean signal.
        new_body = {
            **current.body,
            "updated_by": "delta_sync_history_test",
            "large_payload": _LARGE_PADDING,
        }
        new_body_size = len(json.dumps(new_body).encode("utf-8"))

        self.mark_test_step(
            "Snapshot SGW bytes-transferred and delta_sync expvar counters "
            "before the pull, so we can verify delta-sync participated."
        )
        bytes_before, _ = await sg.bytes_transferred("upgrade")
        delta_stats_before = await sg.get_delta_sync_stats("upgrade")

        self.mark_test_step(f"Apply the large-body mutation to '{doc_id}' on SGW")
        await sg.update_documents(
            "upgrade",
            [DocumentUpdateEntry(doc_id, current.revid, body=new_body)],
        )

        def validator(pre: DocSnapshot, post: DocSnapshot) -> None:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition invalid: RevID={pre.local.revid}, "
                f"HLV={pre.local.cv} (expected revtree-only)"
            )
            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition invalid: RevID={pre.remote.revid}, "
                f"HLV={pre.remote.cv} (expected revtree + HLV after 4.x mutation)"
            )
            assert not pre.remote.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected canonical HLV on SGW after 4.x write, got RTE-encoded: "
                f"{pre.remote.cv}"
            )

            assert post.local.revid is None, (
                f"Expected post-pull local doc to be HLV-only, "
                f"got revid={post.local.revid}"
            )
            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"Expected post-pull local HLV to match SGW HLV. "
                f"Local={post.local.cv}, Remote={post.remote.cv}"
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

        self.mark_test_step(
            "Confirm delta-sync actually participated in this pull "
            "(otherwise the history-field bug we're targeting can't manifest)."
        )
        await _assert_delta_sync_participated(
            sg,
            "upgrade",
            bytes_before,
            delta_stats_before,
            new_body_size,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_history_pull_pre_upgrade_sgw_two_revs(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        # Same template as Test 1, but using nonconflict_2 — client starts at
        # rev 1 (revtree-only) while SGW's dataset state is already at rev 2
        # (revtree-only legacy). After the 4.x SGW mutation below, SGW is at
        # rev 3 (revtree + HLV). The client is therefore TWO revs behind, with
        # rev 1 as the only common ancestor — and per the senior's wire-level
        # investigation, the legacy-rev backup body for rev 1 isn't seeded in
        # the bucket, so SGW is expected to fall back to a full body send and
        # the delta-sync participation check should fail. That failure is the
        # signal that the TDK upgrade dataset needs backup-rev seeding.
        doc_id = "nonconflict_2"
        db = await setup_upgrade_env(self, cblpytest, dataset_path)
        await self._prepare_sg_with_delta_sync(cblpytest)
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step(
            f"Mutate '{doc_id}' on 4.x SGW with a large body so delta-sync "
            "engages on the subsequent pull. The new rev gets revtree + HLV."
        )
        current = await sg.get_document("upgrade", doc_id)
        assert current is not None, f"Expected '{doc_id}' imported from bucket"
        assert current.revid is not None, (
            f"Expected '{doc_id}' to have a revid pre-mutation, got None"
        )
        new_body = {
            **current.body,
            "updated_by": "delta_sync_history_test",
            "large_payload": _LARGE_PADDING,
        }
        new_body_size = len(json.dumps(new_body).encode("utf-8"))

        self.mark_test_step(
            "Snapshot SGW bytes-transferred and delta_sync expvar counters "
            "before the pull, so we can verify delta-sync participated."
        )
        bytes_before, _ = await sg.bytes_transferred("upgrade")
        delta_stats_before = await sg.get_delta_sync_stats("upgrade")

        self.mark_test_step(f"Apply the large-body mutation to '{doc_id}' on SGW")
        await sg.update_documents(
            "upgrade",
            [DocumentUpdateEntry(doc_id, current.revid, body=new_body)],
        )

        def validator(pre: DocSnapshot, post: DocSnapshot) -> None:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition invalid: RevID={pre.local.revid}, "
                f"HLV={pre.local.cv} (expected revtree-only)"
            )
            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition invalid: RevID={pre.remote.revid}, "
                f"HLV={pre.remote.cv} (expected revtree + HLV after 4.x mutation)"
            )
            assert not pre.remote.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected canonical HLV on SGW after 4.x write, got RTE-encoded: "
                f"{pre.remote.cv}"
            )
            assert pre.local.revid < pre.remote.revid, (
                f"Pre-condition: expected local revid < remote revid, "
                f"got local={pre.local.revid}, remote={pre.remote.revid}"
            )

            assert post.local.revid is None, (
                f"Expected post-pull local doc to be HLV-only, "
                f"got revid={post.local.revid}"
            )
            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"Expected post-pull local HLV to match SGW HLV. "
                f"Local={post.local.cv}, Remote={post.remote.cv}"
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

        self.mark_test_step(
            "Confirm delta-sync actually participated in this pull. "
            "Expected to FAIL today: legacy backup rev for rev 1 isn't seeded "
            "in the bucket, so SGW falls back to full body. Becomes a PASS "
            "once the TDK dataset is regenerated with backup revs included."
        )
        await _assert_delta_sync_participated(
            sg,
            "upgrade",
            bytes_before,
            delta_stats_before,
            new_body_size,
        )
