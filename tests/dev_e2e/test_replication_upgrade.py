import os
from pathlib import Path
from typing import Callable

import pytest
from cbltest import CBLPyTest, CouchbaseServer
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import GetDocumentResult
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorType, ReplicatorCollectionEntry, ReplicatorBasicAuthenticator, \
    ReplicatorActivityLevel, ReplicatorConflictResolver, WaitForDocumentEventEntry, ReplicatorDocumentFlags
from cbltest.api.syncgateway import RemoteDocument
from cbltest.api.test_functions import compare_local_and_remote


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicationUpgrade(CBLTestClass):
    @staticmethod
    def tools_path() -> Path:
        script_path = os.path.abspath(os.path.dirname(__file__))
        return Path(script_path, "..", ".tools")

        # A simple snapshot class to hold local and remote documents
    class DocSnapshot:
        def __init__(self,local: GetDocumentResult | None, remote: RemoteDocument | None):
            self.local = local
            self.remote = remote

    # (pre_doc, post_doc) -> None
    DocValidator = Callable[[DocSnapshot, DocSnapshot], None]

    async def do_nonconflict_test(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        doc_id: str,
        replicator_type: ReplicatorType,
        conflict_resolver: ReplicatorConflictResolver | None = None,
        doc_events: set[WaitForDocumentEventEntry] | None = None,
        compare_docs: bool | None = True,
        validator: DocValidator | None = None
    ) -> None:
        # Delete SG database first to avoid reset error after backup restore
        self.mark_test_step("Delete Sync Gateway 'upgrade' database if exists")
        sg = cblpytest.sync_gateways[0]

        try:
            await sg.delete_database("upgrade")
        except CblSyncGatewayBadResponseError as e:
            if e.code != 403:
                raise

        self.mark_test_step("Restore Couchbase Server Bucket using `upgrade` dataset")
        source: CouchbaseServer = cblpytest.couchbase_servers[0]
        source.restore_bucket("foo", self.tools_path(), dataset_path, "upgrade")

        self.mark_test_step("Reset SG and load `upgrade` dataset")
        cloud = CouchbaseCloud(sg, cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "upgrade")

        self.mark_test_step("Reset local database, and load `upgrade` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="upgrade"
        )
        db = dbs[0]

        pre_local_doc = await db.get_document(DocumentEntry("_default._default", doc_id))
        pre_remote_doc = await sg.get_document("upgrade", doc_id)

        print(f"Rev ID : local doc={pre_local_doc.revid}, remote doc={pre_remote_doc.revid}")
        print(f"CV: local doc={pre_local_doc.cv}, remote doc={pre_remote_doc.cv}")

        wait_for_doc_events = bool(doc_events)

        self.mark_test_step(f"""
            Start a replicator: 
            * endpoint: '/upgrade'
            * collections : '_default._default'
            * type: {replicator_type}
            * document_ids: ['{doc_id}']
            * continuous: {wait_for_doc_events}
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("upgrade"),
            collections=[ReplicatorCollectionEntry(
                names=["_default._default"],
                document_ids=[doc_id],
                conflict_resolver=conflict_resolver
            )],
            replicator_type=replicator_type,
            continuous=wait_for_doc_events,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=wait_for_doc_events
        )

        await replicator.start()

        if wait_for_doc_events:
            self.mark_test_step("Wait until receiving all document replication events")
            await replicator.wait_for_all_doc_events(
                events=doc_events,
                max_retries=100,
            )
        else:
            self.mark_test_step("Wait until the replicator is stopped.")
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, (
                f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
            )

        if compare_docs:
            self.mark_test_step("Check that the doc is replicated correctly.")
            await compare_local_and_remote(
                db,
                sg,
                replicator_type,
                "upgrade",
                ["_default._default"],
                [doc_id]
            )

        if validator:
            self.mark_test_step("Validate revid and CV of local and remote doc")
            local_doc = await db.get_document(DocumentEntry("_default._default", doc_id))
            remote_doc = await sg.get_document("upgrade", doc_id)
            validator(
                self.DocSnapshot(pre_local_doc, pre_remote_doc),
                self.DocSnapshot(local_doc, remote_doc)
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_1(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 1 : Bidirectional replication, CBL has pre-upgrade mutation
        that hasn’t been replicated.
        Description: CBL has a mutation made prior to 4.x upgrade that has not been pushed
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no CV, but got: {post.local.cv}"
            )

            assert post.remote.cv and post.remote.cv.endswith("@Revision+Tree+Encoding"), (
                f"Expected remote doc's CV to end with '@Revision+Tree+Encoding', but got: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_1",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_2(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 2 : Bidirectional replication, SGW has pre-upgrade mutation
        that hasn’t been replicated.
        Description: SGW has a mutation made prior to 4.x upgrade that has not
        been pulled.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no CV, but got: {post.local.cv}"
            )

            assert post.remote.cv is None, (
                f"Expected remove doc to have no CV, but got: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_2",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_3(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 3 : Bidirectional replication, CBL has of pre-upgrade mutation
        that SGW already knows.
        Description: CBL has a pre-upgrade mutation that it has not pushed,
        but has been pushed by another peer.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"Revision ID mismatch: Local:  {post.local.revid}, Remote: {post.remote.revid}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no CV, but got: {post.local.cv}"
            )

            assert post.remote.cv is None, (
                f"Expected remove doc to have no CV, but got: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_3",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_4(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 4 : Bidirectional replication, CBL has pre-upgrade mutation that
        is in SGW’s history, and SGW includes post-upgrade mutations.
        Description: CBL has a pre-upgrade mutation that it has not pushed,
        but has been pushed by another peer and exists in SGW’s revision tree history.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid, (
                f"Expected remote doc to have revid, but got none"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"CV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_4",
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_5(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 5 : CBL pull of post-upgrade mutation that has common ancestor to CBL version.
        Description: SGW has a new mutation with CBL revTreeID as ancestor. CBL should identify
        it as non-conflict and pull the new revision.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid, (
                f"Expected remote doc to have revid, but got none"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"CV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_5",
            replicator_type=ReplicatorType.PULL,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonconflict_case_6(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Non-conflict 6 : CBL push of post-upgrade mutation that has common ancestor to SGW version.
        Description: CBL has post-upgrade mutation with common revTreeID ancestor as SGW version.
        SGW should identify as non-conflict and accept the pushed revision.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revid, but got: {post.local.revid}"
            )

            assert post.remote.revid, (
                f"Expected remote doc to have revid, but got none"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"CV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="nonconflict_6",
            replicator_type=ReplicatorType.PUSH,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_1(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 1 : Push replication, conflict between pre-upgrade CBL mutation and pre-upgrade SGW mutation.
        Description: SGW and CBL have conflicting legacy revisions.
        """
        doc_events = {
            WaitForDocumentEventEntry(
                "_default._default",
                "conflict_1",
                ReplicatorType.PUSH,
                flags=None,
                err_domain="CBL",
                err_code=10409
            )
        }

        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid, (
                f"Expected local doc to have revid, but got none"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no CV, but got: {post.local.cv}"
            )

            assert post.remote.revid, (
                f"Expected local doc to have revid, but got: none"
            )

            assert post.remote.cv is None, (
                f"Expected remote doc to have no CV, but got: {post.remote.cv}"
            )

            assert post.local.revid != post.remote.revid, (
                f"Expected local and remote docs to have different revids, "
                f"but both are {post.local.revid}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_1",
            replicator_type=ReplicatorType.PUSH,
            doc_events=doc_events,
            compare_docs=False,
            validator=validator)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_2(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 2 : Bidirectional replication, conflict between pre-upgrade CBL mutation and pre-upgrade
        SGW mutation, default conflict resolver, SGW wins.
        Description: SGW and CBL have conflicting legacy revisions, where SGW is the winner under legacy
        default conflict resolution.
        """

        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid and post.local.revid == post.remote.revid, (
                f"RevID mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

            assert post.local.cv is None, (
                f"Expected local doc to have no CV, but got: {post.local.cv}"
            )

            assert post.remote.cv is None, (
                f"Expected remote doc to have no CV, but got: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_2",
            replicator_type=ReplicatorType.PULL,
            validator=validator)

        # TODO: Try to push the resolved doc back

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_3(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 3 : Bidirectional replication, conflict between pre-upgrade CBL mutation
        and post-upgrade SGW mutation, default conflict resolver, SGW wins.
        Description: SGW and CBL have conflicting revisions, SGW is post-upgrade.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"CV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_3",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("remote-wins"),
            validator=validator)

        # TODO: Try to push the resolved doc back

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_4(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 4 : Bidirectional replication, conflict between pre-upgrade CBL mutation and
        pre-upgrade SGW mutation, default conflict resolver, CBL wins.
        Description: SGW and CBL have conflicting legacy revisions, where CBL is winner under
        legacy default conflict resolution. CBL will rewrite the local winner
        as child of remote and push
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv == post.remote.cv, (
                f"CV mismatch: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_4",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            validator=validator)

        # TODO: Try to push the resolved doc back

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_5(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 5 : Bidirectional replication, conflict between pre-upgrade CBL mutation
        and post-upgrade SGW mutation, default conflict resolver, CBL wins.
        Description: SGW and CBL have conflicting legacy revisions, where CBL is winner
        under legacy default conflict resolution. CBL will rewrite the local winner
        as child of remote and push.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv != post.remote.cv, (
                f"CV match: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_5",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            validator=validator)

        # TODO: Try to push the resolved doc back

    @pytest.mark.asyncio(loop_scope="session")
    async def test_conflict_case_6(
            self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Conflict 5 : Bidirectional replication, conflict between pre-upgrade CBL mutation
        and post-upgrade SGW mutation, default conflict resolver, CBL wins.
        Description: SGW and CBL have conflicting legacy revisions, where CBL is winner
        under legacy default conflict resolution. CBL will rewrite the local winner
        as child of remote and push.
        """
        def validator(pre: TestReplicationUpgrade.DocSnapshot, post: TestReplicationUpgrade.DocSnapshot):
            assert post.local.revid is None, (
                f"Expected local doc to have no revID, but got: {post.local.revid}"
            )

            assert post.local.cv and post.local.cv != post.remote.cv, (
                f"CV match: Local:  {post.local.cv}, Remote: {post.remote.cv}"
            )

        await self.do_nonconflict_test(
            cblpytest,
            dataset_path,
            doc_id="conflict_6",
            replicator_type=ReplicatorType.PULL,
            conflict_resolver=ReplicatorConflictResolver("local-wins"),
            compare_docs=False,
            validator=validator)

        # TODO: Try to push the resolved doc back
