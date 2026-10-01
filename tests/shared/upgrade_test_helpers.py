import os
from collections.abc import Callable, Iterable
from pathlib import Path

from cbltest import CBLPyTest, CouchbaseServer
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database, GetDocumentResult
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblTestServerBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorConflictResolver,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import RemoteDocument, SyncGateway
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.logging import cbl_info
from cbltest.plugins.cluster_cleanup import perform_cleanup


class DocSnapshot:
    """The local and remote (SGW) state of one document at one point in time."""

    def __init__(self, doc_id: str, local: GetDocumentResult | None, remote: RemoteDocument) -> None:
        self.doc_id = doc_id
        self.__local = local
        self.remote = remote

    @property
    def local_exists(self) -> bool:
        """False if the document did not exist in the local database when the snapshot was taken."""
        return self.__local is not None

    @property
    def local(self) -> GetDocumentResult:
        """The local document. Check `local_exists` first if the document may be missing."""
        assert self.__local is not None, "The document does not exist in the local database"
        return self.__local


type DocValidator = Callable[[DocSnapshot, DocSnapshot], None]


def tools_path() -> Path:
    # tests/shared/upgrade_test_helpers.py -> parents[1] is tests/
    return Path(__file__).resolve().parents[1] / ".tools"


def is_initial_upgrade_phase() -> bool:
    """
    True when this is the first phase of an SGW upgrade run, which is the only phase
    with no state to inherit from the phase before it.

    `SGW_UPGRADE_PHASE` is set per pytest invocation by the upgrade pipelines
    (`jenkins/pipelines/QE/upg-sgw/test{,_rolling}.sh`); unset means no pipeline is
    driving the test, which is treated the same as the first phase.
    """
    return os.environ.get("SGW_UPGRADE_PHASE", "") in ("", "initial")


async def cleanup_unless_mid_upgrade(cblpytest: CBLPyTest) -> None:
    """
    Body for a `cluster_cleanup` fixture override on an SGW upgrade test class: clean
    only in the initial phase, since later phases assert that earlier docs survived.
    """
    if not is_initial_upgrade_phase():
        cbl_info(f"🧹 Skipping cleanup: phase '{os.environ['SGW_UPGRADE_PHASE']}' inherits the previous state")
        return

    await perform_cleanup(cblpytest)


async def setup_upgrade_env(
    test_case: CBLTestClass,
    cblpytest: CBLPyTest,
    dataset_path: Path,
    *,
    reset_expired_ttl: bool = False,
    empty_local_db: bool = False,
) -> Database:
    await test_case.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.0.0")

    dataset_ver = cblpytest.test_servers[0].dataset_version
    test_case.skip_if_not(dataset_ver == "4.0", f"Requires dataset v4.0 (current: {dataset_ver}).")

    test_case.mark_test_step("Restore Couchbase Server Bucket using `upgrade` dataset")
    cbs: CouchbaseServer = cblpytest.couchbase_servers[0]
    cbs.restore_bucket(
        "upgrade",
        tools_path(),
        dataset_path,
        "upgrade",
        reset_expired_ttl=reset_expired_ttl,
    )

    test_case.mark_test_step("Wait for SG to bring the restored database online.")

    await cblpytest.sync_gateway_cluster.wait_for_db_online("upgrade", max_retries=120, retry_delay=1)

    if empty_local_db:
        test_case.mark_test_step("Reset local database, and load `empty` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
    else:
        test_case.mark_test_step("Reset local database, and load `upgrade` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="upgrade")
    return dbs[0]


async def _snapshot(db: Database, sg: SyncGateway, doc_id: str, *, local_may_be_missing: bool) -> DocSnapshot:
    """Fetches the local and remote copies of a document; a missing local copy is allowed only if requested."""
    remote = await sg.get_document("upgrade", doc_id)
    try:
        local = await db.get_document(DocumentEntry("_default._default", doc_id))
    except CblTestServerBadResponseError as e:
        if not (local_may_be_missing and e.code == 404):
            raise
        local = None
    return DocSnapshot(doc_id, local, remote)


def _log_snapshots(title: str, snapshots: Iterable[DocSnapshot]) -> None:
    """Logs the revid and HLV of each snapshot, local and remote."""
    cbl_info(title)
    for snap in snapshots:
        local = f"RevID = {snap.local.revid}, HLV = {snap.local.cv}" if snap.local_exists else "(no document)"
        cbl_info(f"  {snap.doc_id}: Local : {local}")
        cbl_info(f"  {snap.doc_id}: Remote : RevID = {snap.remote.revid}, HLV = {snap.remote.cv}")


async def do_upgrade_replication_test(
    test_case: CBLTestClass,
    cblpytest: CBLPyTest,
    db: Database,
    doc_ids: list[str],
    replicator_type: ReplicatorType,
    conflict_resolver: ReplicatorConflictResolver | None = None,
    doc_events: set[WaitForDocumentEventEntry] | None = None,
    compare_docs: bool | None = True,
    validator: DocValidator | None = None,
    reset: bool = False,
) -> Replicator:
    """
    Replicates `doc_ids` once with the SGW `upgrade` database and verifies the result. The revid and HLV of every
    document (local and remote) are logged before and after, as are the document replication events, which a
    listener always collects into the returned Replicator's `document_updates`.

    :param doc_ids: The documents to replicate (document ID filter) and to compare afterwards.
    :param replicator_type: push, pull or pushAndPull.
    :param conflict_resolver: Conflict resolver for the `_default._default` collection.
    :param doc_events: If given, run continuously until these document replication events are received.
    :param compare_docs: Compare each document's local and remote copies after replication.
    :param validator: Called once per document with its pre and post snapshots (`pre.doc_id` tells which;
                      `pre.local_exists` is False if the document was not local before).
    :param reset: Reset the replicator's checkpoint before starting.
    :return: The stopped Replicator.
    """
    sg = cblpytest.sync_gateways[0]
    assert doc_ids, "doc_ids must not be empty"

    pre = {doc_id: await _snapshot(db, sg, doc_id, local_may_be_missing=True) for doc_id in doc_ids}
    _log_snapshots(f"Revision Info before Replication ({replicator_type}):", pre.values())

    wait_for_doc_events = bool(doc_events)

    conflict_resolver_name = f"{conflict_resolver.name}" if conflict_resolver else "None"

    test_case.mark_test_step(f"""
        Start a replicator:
        * endpoint: '/upgrade'
        * collections : '_default._default'
        * type: {replicator_type}
        * document_ids: {doc_ids}
        * continuous: {wait_for_doc_events}
        * conflict_resolver: {conflict_resolver_name}
        * reset: {reset}
        * enable_document_listener: True
    """)
    replicator = Replicator(
        db,
        cblpytest.sync_gateways[0].replication_url("upgrade"),
        collections=[
            ReplicatorCollectionEntry(
                names=["_default._default"],
                document_ids=doc_ids,
                conflict_resolver=conflict_resolver,
            )
        ],
        replicator_type=replicator_type,
        continuous=wait_for_doc_events,
        reset=reset,
        authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        enable_document_listener=True,
    )

    await replicator.start()

    if doc_events:
        test_case.mark_test_step("Wait until receiving all document replication events")
        await replicator.wait_for_all_doc_events(
            events=doc_events,
            max_retries=100,
        )
    else:
        test_case.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

    cbl_info(f"Document replication events ({len(replicator.document_updates)}):")
    for entry in replicator.document_updates:
        cbl_info(f"  {entry.document_id}: {entry.direction}, flags = {entry.flags}, error = {entry.error}")

    docs = "the doc is" if len(doc_ids) == 1 else "all docs are"
    if compare_docs:
        test_case.mark_test_step(f"Check that {docs} replicated correctly.")
        await compare_local_and_remote(db, sg, replicator_type, "upgrade", ["_default._default"], doc_ids)

    post = {doc_id: await _snapshot(db, sg, doc_id, local_may_be_missing=False) for doc_id in doc_ids}
    _log_snapshots(f"Revision Info after Replication ({replicator_type}):", post.values())

    if validator:
        test_case.mark_test_step(
            f"Validate revid and HLV of local and remote {'doc' if len(doc_ids) == 1 else 'docs'}."
        )
        for doc_id in doc_ids:
            validator(pre[doc_id], post[doc_id])

    return replicator
