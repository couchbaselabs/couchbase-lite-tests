from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator_types import (
    ReplicatorConflictResolver,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import DocumentUpdateEntry
from shared.upgrade_test_helpers import (
    DocSnapshot,
    do_upgrade_replication_test,
    setup_upgrade_env,
)


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationUpgrade(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_1(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication where CBL has a pre-upgrade mutation that hasn’t been
        replicated — a mutation made on CBL before the 4.x upgrade has not yet been pushed.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |  2-def, 1-abc |      none     |     1-abc     |      none     |
        | Expected Result  |  2-def, 1-abc |      none     |  2-def, 1-abc | Encoded 2-def |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

            assert post.remote.cv and post.remote.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected remote doc's HLV to end with '@Revision+Tree+Encoding', but got: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_1"],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_2(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication where SGW has a pre-upgrade mutation that hasn’t been
        replicated — a mutation made on SGW before the 4.x upgrade has not yet been pulled.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     1-abc     |      none     |  2-def,1-abc  |      none     |
        | Expected Result  |  2-def,1-abc  | Encoded 2-def |     2-def     |      none     |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

            assert post.remote.cv is None, f"Expected remote doc to have no HLV, but got: {post.remote.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_2"],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_3(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication where CBL has a pre-upgrade mutation that SGW
        already knows — a mutation made on CBL before the 4.x upgrade has not
        been pushed, but was already pushed earlier by another peer.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     2-abc     |      none     |     2-abc     |      none     |
        | Expected Result  |     2-abc     |      none     |     2-abc     |      none     |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid == pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be equals to remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

            assert post.remote.cv is None, f"Expected remote doc to have no HLV, but got: {post.remote.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_3"],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_4(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication where CBL has a pre-upgrade mutation that is already in
        SGW’s history and SGW includes post-upgrade mutations — a mutation made on CBL
        before the 4.x upgrade has not been pushed, but was previously pushed by
        another peer and already exists in SGW’s revision tree history.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
        | Expected Result  |      none     |  [100@SGW1]   |  3-ghi 2-def  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_4"],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_5(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        CBL pull of a post-upgrade mutation that shares a common ancestor with the
        CBL version — SGW has a new mutation with the CBL revTreeID as its ancestor,
        and CBL should recognize it as non-conflicting and pull the new revision.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
        | Expected Result  |      none     |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_5"],
            replicator_type=ReplicatorType.PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_6(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        CBL push of a post-upgrade mutation that shares a common ancestor with the
        SGW version — CBL has a post-upgrade mutation with the same revTreeID ancestor
        as the SGW version, and SGW should recognize it as non-conflicting and accept
        the pushed revision.
        +------------------+------------------------------------------------+-------------------------------+
        |                  |                       CBL                      |              SGW              |
        |                  +------------------------+------------------------+---------------+---------------+
        |                  |        Rev Tree        |         HLV            |   Rev Tree    |      HLV      |
        +------------------+------------------------+------------------------+---------------+---------------+
        | Initial State    | none (parent = 2-abc)  | [100@CBL1]             |     2-abc     |      none     |
        | Expected Result  |         none           | [100@CBL1]             |     3-def     |   [100@CBL1]  |
        +------------------+------------------------+------------------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["nonconflict_6"],
            replicator_type=ReplicatorType.PUSH,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_7(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Pull of a document that CBL does not have and that SGW still holds with a legacy
        (pre-upgrade) revision only, followed by a post-upgrade SGW mutation of the same
        document. The first pull stores the document with its legacy revID in the 4.x record
        format; the second pull must accept the new revision (CBL-8954).
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     none      |      none     |  2-def,1-abc  |      none     |
        | After first pull |     2-def     |      none     |  2-def,1-abc  |      none     |
        | After SGW update |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
        | Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        """
        doc_id = "nonconflict_2"
        db = await setup_upgrade_env(self, cblpytest, dataset_path, empty_local_db=True)
        sg = cblpytest.sync_gateways[0]

        def first_pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert not pre.local_exists, f"Local precondition is invalid, the doc exists: RevID: {pre.local.revid}"

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

        # First pull: CBL has no doc, SGW has the legacy revision only.
        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            validator=first_pull_validator,
        )

        remote_doc = await sg.get_document("upgrade", doc_id)
        self.mark_test_step(f"Update `{doc_id}` on SGW.")
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    remote_doc.revid,
                    body={**remote_doc.body, "updated_by": "nonconflict_case_7"},
                )
            ],
            wait_for_caching_feed=True,
        )

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        # Second pull: the update must arrive.
        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_8(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Pull of several documents that CBL does not have, most of them held by SGW with legacy
        revisions only, followed by a post-upgrade SGW mutation of one of them and a second pull
        with the checkpoint reset. SGW then sends all documents in one `changes` batch. The batch
        must be processed, only the updated document must be pulled, and the other documents must
        be unchanged (CBL-8954: one legacy-revID record used to fail the whole batch).
        +------------------+-------------------------------+-------------------------------+
        | nonconflict_2    |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     none      |      none     |  2-def,1-abc  |      none     |
        | After first pull |     2-def     |      none     |  2-def,1-abc  |      none     |
        | After SGW update |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
        | Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        All other documents keep the revid and HLV they had after the first pull.
        """
        doc_id = "nonconflict_2"
        doc_ids = [f"nonconflict_{i}" for i in range(1, 7)]
        db = await setup_upgrade_env(self, cblpytest, dataset_path, empty_local_db=True)
        sg = cblpytest.sync_gateways[0]

        # First pull: CBL has no docs, SGW has them (most with legacy revisions only).
        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=doc_ids,
            replicator_type=ReplicatorType.PULL,
        )

        remote_doc = await sg.get_document("upgrade", doc_id)
        assert remote_doc.cv is None, f"Expected remote doc to have no HLV, but got: {remote_doc.cv}"

        self.mark_test_step(f"Update `{doc_id}` on SGW.")
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    remote_doc.revid,
                    body={**remote_doc.body, "updated_by": "nonconflict_case_8"},
                )
            ],
            wait_for_caching_feed=True,
        )

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            if pre.doc_id != doc_id:
                # The other docs were not changed on SGW and must not have changed locally either:
                assert post.local.revid == pre.local.revid and post.local.cv == pre.local.cv, (
                    f"'{pre.doc_id}' changed: RevID {pre.local.revid} -> {post.local.revid}, "
                    f"HLV {pre.local.cv} -> {post.local.cv}"
                )
                return

            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        # Second pull with the checkpoint reset: SGW sends all docs again in one batch.
        replicator = await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=doc_ids,
            replicator_type=ReplicatorType.PULL,
            validator=validator,
            reset=True,
        )

        self.mark_test_step(f"Check that only `{doc_id}` was pulled.")
        pulled = [entry.document_id for entry in replicator.document_updates]
        assert pulled == [doc_id], f"Expected only '{doc_id}' to be pulled, but got: {pulled}"
        for entry in replicator.document_updates:
            assert not entry.is_push, f"Unexpected push event for '{entry.document_id}'"
            assert entry.error is None, f"Unexpected error for '{entry.document_id}': {entry.error}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_9(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Pull of a document that CBL already has at the same legacy revision as SGW, followed
        by a post-upgrade SGW mutation of that document. The first pull transfers nothing but
        records SGW's revision on the local document, which rewrites it into the 4.x record
        format while keeping its legacy revID. The second pull must accept the new revision
        (CBL-8954).

        Note: the rewrite in the first pull happens only because the `upgrade` dataset has no
        remote mark for the test's SGW URL. Cases 7 and 8 cover the same record format without
        that dependency.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     2-abc     |      none     |     2-abc     |      none     |
        | After first pull |     2-abc     |      none     |     2-abc     |      none     |
        | After SGW update |     2-abc     |      none     |  3-ghi 2-abc  |   [100@SGW1]  |
        | Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-abc  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        """
        doc_id = "nonconflict_3"
        db = await setup_upgrade_env(self, cblpytest, dataset_path)
        sg = cblpytest.sync_gateways[0]

        def first_pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Both sides already have the same legacy revision; nothing changes:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid == pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be equals to remote revid: {pre.remote.revid}"
            )

            assert post.local.revid == pre.local.revid and post.local.cv is None, (
                f"Expected local doc unchanged, but got RevID: {post.local.revid}, HLV: {post.local.cv}"
            )

        # First pull: nothing to transfer, but the local record is marked with SGW's revision.
        replicator = await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            validator=first_pull_validator,
        )
        self.mark_test_step("Check that no doc was pulled.")
        assert not replicator.document_updates, (
            f"Expected no document to be pulled, but got: {[e.document_id for e in replicator.document_updates]}"
        )

        remote_doc = await sg.get_document("upgrade", doc_id)
        self.mark_test_step(f"Update `{doc_id}` on SGW.")
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    remote_doc.revid,
                    body={**remote_doc.body, "updated_by": "nonconflict_case_9"},
                )
            ],
            wait_for_caching_feed=True,
        )

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        # Second pull: the update must arrive.
        replicator = await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            validator=validator,
        )

        self.mark_test_step(f"Check that `{doc_id}` was pulled.")
        pulled = [entry.document_id for entry in replicator.document_updates]
        assert pulled == [doc_id], f"Expected only '{doc_id}' to be pulled, but got: {pulled}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_1(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Push replication with a conflict between pre-upgrade CBL and SGW mutations —
        both sides have conflicting legacy revisions created before the 4.x upgrade.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     3-abc     |      none     |     3-def     |      none     |
        | Expected Result  |     3-abc     |      none     |     3-def     |      none     |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        doc_events = {
            WaitForDocumentEventEntry(
                "_default._default",
                "conflict_1",
                ReplicatorType.PUSH,
                flags=None,
                err_domain="CBL",
                err_code=10409,
            )
        }

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.remote.revid == pre.remote.revid, (
                f"Expected remote doc's revid to be unchanged. Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv is None, f"Expected remote doc's HLV to be unchanged (none), but got {post.remote.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_1"],
            replicator_type=ReplicatorType.PUSH,
            doc_events=doc_events,
            compare_docs=False,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_2(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between pre-upgrade CBL and SGW mutations,
        resolved by the default conflict resolver where SGW wins — both SGW and CBL
        have conflicting legacy revisions created before the 4.x upgrade,
        with SGW chosen as the winner under the legacy default conflict resolution.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     3-abc     |      none     |     3-def     |      none     |
        | Expected Result  |     3-def     |      none     |     3-def     |      none     |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid and post.local.revid != pre.local.revid, (
                f"Expected local doc revID to be updated, but got: {post.remote.revid}"
            )

            assert post.local.revid == post.remote.revid, (
                f"RevID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_2"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert pre.remote.revid == post.remote.revid, (
                f"Expected remote doc revID to be unchanged after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv is None, (
                f"Expected remote doc to have no HLV after resolved doc was pushed, but got: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_2"],
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_3(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between a pre-upgrade CBL mutation and a post-upgrade
        SGW mutation, resolved by the default conflict resolver where SGW wins — SGW and CBL
        have conflicting revisions, with SGW’s post-upgrade revision selected as the winner
        under the default conflict resolution.
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     3-abc     |      none     |     3-def     |  [100@SGW1]   |
        | Expected Result  |      none     |  [100@SGW1]   |     3-def     |  [100@SGW1]   |
        +------------------+---------------+---------------+---------------+---------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revID , but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_3"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert pre.remote.revid == post.remote.revid, (
                f"Expected remote doc revID to be unchanged after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert pre.remote.cv == post.remote.cv, (
                f"Expected remote doc HLV to be unchanged after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_3"],
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_4(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between pre-upgrade CBL and SGW mutations,
        resolved by the default conflict resolver where CBL wins — SGW and CBL have
        conflicting legacy revisions, with CBL chosen as the winner under the legacy
        default conflict resolution. CBL will rewrite the local winning revision
        as a child of the remote revision and push it to SGW.
        +------------------+--------------------------------------+--------------------------------------+
        |                  |              CBL                     |                 SGW                  |
        |                  +---------------+----------------------+---------------+----------------------+
        |                  |   Rev Tree    |         HLV          |   Rev Tree    |         HLV          |
        +------------------+---------------+----------------------+---------------+----------------------+
        | Initial State    |     3-def     |      none            |     3-abc     |      none            |
        | Expected Result  |      none     | [100@CBL1, 3abc@RTE] |     4-def     | [100@CBL1, 3abc@RTE] |
        +------------------+---------------+----------------------+---------------+----------------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revID, but got: {post.local.revid}"

            assert pre.local.cv is None and post.local.cv, f"Expected local doc to have HLV, but got: {post.local.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_4"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert post.remote.revid != pre.remote.revid, (
                f"Expected remote doc revID to be updated after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv and post.remote.cv == post.local.cv, (
                f"Expected remote doc HLV to be the same as local doc HLV after resolved doc was pushed. "
                f"Remote: {post.remote.cv}, After: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_4"],
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_5(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between a pre-upgrade CBL mutation and
        a post-upgrade SGW mutation, resolved by the default conflict resolver
        where CBL wins — SGW and CBL have conflicting revisions, with CBL selected
        as the winner under the legacy default conflict resolution. CBL will rewrite
        the local winning revision as a child of the remote revision and push it to SGW.
        +------------------+------------------------------------+------------------------------------+
        |                  |                   CBL              |            SGW                     |
        |                  +-------------+----------------------+-------------+----------------------+
        |                  |  Rev Tree   |         HLV          |  Rev Tree   |          HLV         |
        +------------------+-------------+----------------------+-------------+----------------------+
        | Initial State    |    3-def    |         none         |    3-abc    | [100@SGW1]           |
        | Expected Result  |             | [3def@RTE, 100@SGW1] |    4-def    | [3def@RTE, 100@SGW1] |
        +------------------+-------------+----------------------+-------------+----------------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revID, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv != post.remote.cv, (
                f"Expected local doc's HLV to be different from remote doc's HLV after the merge, "
                f"but got local={post.local.cv}, remote={post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_5"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert pre.remote.revid != post.remote.revid, (
                f"Expected remote doc revID to be updated after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv and post.remote.cv != pre.remote.cv, (
                f"Expected remote doc HLV to be updated after resolved doc was pushed. "
                f"Remote: {post.remote.cv}, After: {post.local.cv}"
            )

            assert post.remote.cv and post.remote.cv == post.local.cv, (
                f"Expected remote doc HLV to be the same as local doc HLV after resolved doc was pushed. "
                f"Remote: {post.remote.cv}, After: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_5"],
            replicator_type=ReplicatorType.PUSH,
            compare_docs=True,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_6(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between a post-upgrade CBL mutation and
        a pre-upgrade SGW mutation, resolved with local wins — SGW and CBL have
        conflicting revisions, with CBL selected as the winner under the legacy
        default conflict resolution. CBL will rewrite the local winning revision
        as a child of the remote revision and push it to SGW.
        +------------------+-------------------------------------+-------------------------------------+
        |                  |                    CBL              |                   SGW               |
        |                  +--------------+----------------------+--------------+----------------------+
        |                  |  Rev Tree    |          HLV         |   Rev Tree   |         HLV          |
        +------------------+--------------+----------------------+--------------+----------------------+
        | Initial State    |    none      | [100@CBL1]           |   3-abc      |          none        |
        | Expected Result  |              | [100@CBL1, 3abc@RTE] |   4-abc      | [100@CBL1, 3abc@RTE] |
        +------------------+--------------+----------------------+--------------+----------------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID after the merge, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv == pre.local.cv, (
                f"Expected local doc's HLV to be unchanged after the merge, but got before={pre.local.cv}, after={post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_6"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert post.remote.revid != pre.remote.revid, (
                f"Expected remote doc revID to be updated after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv and post.remote.cv == post.local.cv, (
                f"Expected remote doc HLV to be the same as local doc HLV after resolved doc was pushed. "
                f"Remote: {post.remote.cv}, After: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_6"],
            replicator_type=ReplicatorType.PUSH,
            compare_docs=True,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_7(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Bidirectional replication conflict between a post-upgrade CBL mutation and
        a pre-upgrade SGW mutation, resolved with remote wins — SGW and CBL have
        conflicting revisions, with the remote revision selected as the winner
        under the legacy default conflict resolution. CBL will rewrite the local
        winning revision as a child of the remote revision and push it to SGW.

        +------------------+---------------------------+---------------------------+
        |                  |            CBL            |            SGW            |
        |                  +-------------+-------------+-------------+-------------+
        |                  |  Rev Tree   |     HLV     |  Rev Tree   |     HLV     |
        +------------------+-------------+-------------+-------------+-------------+
        | Initial State    |    none     |  [100@CBL1] |    3-abc    |     none    |
        | Expected Result  |             |   3abc@RTE  |    3-abc    |     none    |
        +------------------+-------------+-------------+-------------+-------------+
        """
        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID after the merge, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv != pre.local.cv, (
                f"Expected local doc's HLV to be differnt after the merge, but got before={pre.local.cv}, after={post.local.cv}"
            )

            assert post.local.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected local doc's HLV to be a rev-tree encoded, but got before={post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_7"],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            assert post.remote.revid == pre.remote.revid, (
                f"Expected remote doc revID to be unchanged after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv is None, f"Expected remote doc HLV to be unchanged (None), but got {post.remote.cv}"

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=["conflict_7"],
            replicator_type=ReplicatorType.PUSH,
            compare_docs=False,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_8(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Pull replication conflict between pre-upgrade CBL and SGW mutations resolved with
        remote wins, followed by a post-upgrade SGW mutation of the same document. After the
        resolution CBL holds SGW's legacy revision, pulled with a legacy-only history, in the
        4.x record format. The second pull must accept the new revision (CBL-8954).
        +------------------+-------------------------------+-------------------------------+
        |                  |             CBL               |              SGW              |
        |                  +---------------+---------------+---------------+---------------+
        |                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
        +------------------+---------------+---------------+---------------+---------------+
        | Initial State    |     3-abc     |      none     |     3-def     |      none     |
        | After first pull |     3-def     |      none     |     3-def     |      none     |
        | After SGW update |     3-def     |      none     |  4-ghi 3-def  |   [100@SGW1]  |
        | Expected Result  |     none      |   [100@SGW1]  |  4-ghi 3-def  |   [100@SGW1]  |
        +------------------+---------------+---------------+---------------+---------------+
        """
        doc_id = "conflict_2"
        db = await setup_upgrade_env(self, cblpytest, dataset_path)
        sg = cblpytest.sync_gateways[0]

        def pull_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid and post.local.revid != pre.local.revid, (
                f"Expected local doc revID to be updated, but got: {post.remote.revid}"
            )

            assert post.local.revid == post.remote.revid, (
                f"RevID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, f"Expected local doc to have no HLV, but got: {post.local.cv}"

        # First pull: the conflict is resolved with the remote (legacy) revision.
        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=pull_validator,
        )

        remote_doc = await sg.get_document("upgrade", doc_id)
        self.mark_test_step(f"Update `{doc_id}` on SGW.")
        await sg.update_documents(
            "upgrade",
            [
                DocumentUpdateEntry(
                    doc_id,
                    remote_doc.revid,
                    body={**remote_doc.body, "updated_by": "conflict_case_8"},
                )
            ],
            wait_for_caching_feed=True,
        )

        def validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ) -> None:
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, f"Expected local doc to have no revid, but got: {post.local.revid}"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        # Second pull: the update must arrive.
        replicator = await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_ids=[doc_id],
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=validator,
        )

        self.mark_test_step(f"Check that `{doc_id}` was pulled.")
        pulled = [entry.document_id for entry in replicator.document_updates]
        assert pulled == [doc_id], f"Expected only '{doc_id}' to be pulled, but got: {pulled}"
