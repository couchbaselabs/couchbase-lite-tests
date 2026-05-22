from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import DocumentUpdateEntry, PutDatabasePayload
from cbltest.api.upgrade_test_helpers import (
    DocSnapshot,
    do_upgrade_replication_test,
    setup_upgrade_env,
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
            # in case DB already exits, force-recreate, so our delta_sync
            # config is rather than running against the previous config
            await sg.delete_database("upgrade")
            await sg.put_database("upgrade", payload)
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
        strict=True,
        reason=(
            "SGW delta-sync history bug: when SGW sends a delta of a "
            "revtree+HLV rev to a client holding the revtree-only ancestor, "
            "the rev message's `history` field is empty. Fix pending."
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
            f"Mutate '{doc_id}' on 4.x SGW to produce a new revtree leaf + fresh HLV"
        )
        current = await sg.get_document("upgrade", doc_id)
        assert current is not None, f"Expected '{doc_id}' imported from bucket"
        assert current.revid is not None, (
            f"Expected '{doc_id}' to have a revid pre-mutation, got None"
        )
        new_body = {**current.body, "updated_by": "delta_sync_history_test"}
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
            compare_docs=False,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_history_pull_pre_upgrade_sgw_two_revs(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        doc_id = "nonconflict_2"
        db = await setup_upgrade_env(self, cblpytest, dataset_path)
        await self._prepare_sg_with_delta_sync(cblpytest)

        def validator(pre: DocSnapshot, post: DocSnapshot) -> None:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition invalid: RevID={pre.local.revid}, "
                f"HLV={pre.local.cv} (expected revtree-only)"
            )
            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition invalid: RevID={pre.remote.revid}, "
                f"HLV={pre.remote.cv} (expected revtree-only, no HLV)"
            )
            assert pre.local.revid < pre.remote.revid, (
                f"Pre-condition: expected local revid < remote revid, "
                f"got local={pre.local.revid}, remote={pre.remote.revid}"
            )

            assert post.local.revid is None, (
                f"Expected post-pull local doc to be HLV-only, "
                f"got revid={post.local.revid}"
            )
            assert post.local.cv and post.local.cv.endswith(
                "@Revision+Tree+Encoding"
            ), (
                f"Expected post-pull local HLV to be RTE-encoded from the "
                f"pulled revtree-only rev, got {post.local.cv}"
            )
            assert post.remote.cv is None, (
                f"Expected SGW HLV unchanged (none) after PULL, got {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id=doc_id,
            replicator_type=ReplicatorType.PULL,
            compare_docs=False,
            validator=validator,
        )
