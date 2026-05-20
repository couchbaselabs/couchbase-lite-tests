from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator_types import (
    ReplicatorConflictResolver,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.upgrade_test_helpers import (
    DocSnapshot,
    do_upgrade_replication_test,
    setup_upgrade_env,
)


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationUpgrade(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_1(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no HLV, but got: {post.local.cv}"
            )

            assert post.remote.cv and post.remote.cv.endswith(
                "@Revision+Tree+Encoding"
            ), (
                f"Expected remote doc's HLV to end with '@Revision+Tree+Encoding', but got: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_1",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_2(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no HLV, but got: {post.local.cv}"
            )

            assert post.remote.cv is None, (
                f"Expected remove doc to have no HLV, but got: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_2",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_3(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid == pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be equals to remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no HLV, but got: {post.local.cv}"
            )

            assert post.remote.cv is None, (
                f"Expected remove doc to have no HLV, but got: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_3",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_4(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid, "Expected remote doc to have revid, but got none"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_4",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_5(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid, "Expected remote doc to have revid, but got none"

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_5",
            replicator_type=ReplicatorType.PULL,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_6(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.remote.revid}, HLV: {pre.remote.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid is not None, (
                "Expected remote doc to have revid, but got none"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="nonconflict_6",
            replicator_type=ReplicatorType.PUSH,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_1(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.remote.revid == pre.remote.revid, (
                f"Expected remote doc's revid to be unchanged. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv is None, (
                f"Expected remote doc's HLV to be unchanged (none), "
                f"but got {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_1",
            replicator_type=ReplicatorType.PUSH,
            doc_events=doc_events,
            compare_docs=False,
            validator=validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_2(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
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

            assert post.local.cv is None, (
                f"Expected local doc to have no HLV, but got: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_2",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
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
            doc_id="conflict_2",
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_3(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.local.revid < pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be < remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID , but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"HLV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_3",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
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
            doc_id="conflict_3",
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_4(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert pre.local.cv is None and post.local.cv, (
                f"Expected local doc to have HLV, bot got: {post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_4",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
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
            doc_id="conflict_4",
            replicator_type=ReplicatorType.PUSH,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_5(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is not None and pre.local.cv is None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is not None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.local.revid > pre.remote.revid, (
                f"Precondition is invalid, local revid: {pre.local.revid} should be > remote revid: {pre.remote.revid}"
            )

            # Validate Post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv != post.remote.cv, (
                f"Expected local doc's HLV to be different from remote doc's HLV after the merge, "
                f"but got local={post.local.cv}, remote={post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_5",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
            assert post.remote.revid and pre.remote.revid != post.remote.revid, (
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
            doc_id="conflict_5",
            replicator_type=ReplicatorType.PUSH,
            compare_docs=True,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_6(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID after the merge, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv == pre.local.cv, (
                f"Expected local doc's HLV to be unchanged after the merge, "
                f"but got before={pre.local.cv}, after={post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_6",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
            assert post.remote.revid and post.remote.revid != pre.remote.revid, (
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
            doc_id="conflict_6",
            replicator_type=ReplicatorType.PUSH,
            compare_docs=True,
            validator=push_validator,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_7(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
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
        ):
            # Validate pre-condition:
            assert pre.local.revid is None and pre.local.cv is not None, (
                f"Local precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            assert pre.remote.revid is not None and pre.remote.cv is None, (
                f"Remote precondition is invalid, RevID: {pre.local.revid}, HLV: {pre.local.cv}"
            )

            # Validate post-condition:
            assert post.local.revid is None, (
                f"Expected local doc to have no revID after the merge, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv != pre.local.cv, (
                f"Expected local doc's HLV to be differnt after the merge, "
                f"but got before={pre.local.cv}, after={post.local.cv}"
            )

            assert post.local.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected local doc's HLV to be a rev-tree encoded, "
                f"but got before={post.local.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_7",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            compare_docs=False,
            validator=pull_validator,
        )

        def push_validator(
            pre: DocSnapshot,
            post: DocSnapshot,
        ):
            assert post.remote.revid == pre.remote.revid, (
                f"Expected remote doc revID to be unchanged after resolved doc was pushed. "
                f"Before: {pre.remote.revid}, After: {post.remote.revid}"
            )

            assert post.remote.cv is None, (
                f"Expected remote doc HLV to be unchanged (None), "
                f"but got {post.remote.cv}"
            )

        await do_upgrade_replication_test(
            self,
            cblpytest,
            db,
            doc_id="conflict_7",
            replicator_type=ReplicatorType.PUSH,
            compare_docs=False,
            validator=push_validator,
        )
