from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from cbltest import CBLPyTest, CouchbaseServer
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database, GetDocumentResult
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorConflictResolver,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import RemoteDocument
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.logging import cbl_info


class DocSnapshot:
    def __init__(self, local: GetDocumentResult, remote: RemoteDocument):
        self.local = local
        self.remote = remote


DocValidator: TypeAlias = Callable[[DocSnapshot, DocSnapshot], None]


def tools_path() -> Path:
    # tests/shared/upgrade_test_helpers.py -> parents[1] is tests/
    return Path(__file__).resolve().parents[1] / ".tools"


async def setup_upgrade_env(
    test_case: CBLTestClass,
    cblpytest: CBLPyTest,
    dataset_path: Path,
    *,
    reset_expired_ttl: bool = False,
) -> Database:
    await test_case.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.0.0")

    dataset_ver = cblpytest.test_servers[0].dataset_version
    test_case.skip_if_not(
        dataset_ver == "4.0", f"Requires dataset v4.0 (current: {dataset_ver})."
    )

    test_case.mark_test_step("Delete Sync Gateway 'upgrade' database if exists")
    # delete_database silently swallows 403 internally (config-managed DBs)
    # and retries 500s; no need to wrap further.
    await cblpytest.sync_gateways[0].delete_database("upgrade")

    test_case.mark_test_step("Restore Couchbase Server Bucket using `upgrade` dataset")
    cbs: CouchbaseServer = cblpytest.couchbase_servers[0]
    cbs.drop_bucket("upgrade")
    # reset_expired_ttl restores the delta-sync old-revision backup bodies
    # (`_sync:rev:*`) so SGW can delta against a legacy ancestor rev.
    cbs.restore_bucket(
        "upgrade",
        tools_path(),
        dataset_path,
        "upgrade",
        reset_expired_ttl=reset_expired_ttl,
    )

    test_case.mark_test_step("Wait for SG to bring the restored database online.")

    # As of Sync Gateway 4.1.0, this can take a long time to come online (20s+) due to import-feed rollbacks caused by mismatched vBucket UUIDs.
    #
    # A good practice when taking new snapshots is to remove _sync:* docs before running a cbbackup.
    # cbbackupmgr restore --filter-keys cannot do a negative regex to filter out the dbconfig, checkpoints, etc.
    #
    await SyncGatewayCluster(cblpytest.sync_gateways[:1]).wait_for_db_online(
        "upgrade", max_retries=120, retry_delay=1
    )

    test_case.mark_test_step("Reset local database, and load `upgrade` dataset.")
    dbs = await cblpytest.test_servers[0].create_and_reset_db(
        ["db1"], dataset="upgrade"
    )
    return dbs[0]


async def do_upgrade_replication_test(
    test_case: CBLTestClass,
    cblpytest: CBLPyTest,
    db: Database,
    doc_id: str,
    replicator_type: ReplicatorType,
    conflict_resolver: ReplicatorConflictResolver | None = None,
    doc_events: set[WaitForDocumentEventEntry] | None = None,
    compare_docs: bool | None = True,
    validator: DocValidator | None = None,
) -> None:
    sg = cblpytest.sync_gateways[0]

    pre_local_doc = await db.get_document(DocumentEntry("_default._default", doc_id))
    pre_remote_doc = await sg.get_document("upgrade", doc_id)

    assert pre_local_doc is not None
    assert pre_remote_doc is not None
    cbl_info(f"Revision Info before Replication ({replicator_type}):")
    cbl_info(f"Local : RevID = {pre_local_doc.revid}, HLV = {pre_local_doc.cv}")
    cbl_info(f"Remote : RevID = {pre_remote_doc.revid}, HLV = {pre_remote_doc.cv}")

    wait_for_doc_events = bool(doc_events)

    conflict_resolver_name = (
        f"{conflict_resolver.name}" if conflict_resolver else "None"
    )

    test_case.mark_test_step(f"""
        Start a replicator:
        * endpoint: '/upgrade'
        * collections : '_default._default'
        * type: {replicator_type}
        * document_ids: ['{doc_id}']
        * continuous: {wait_for_doc_events}
        * conflict_resolver: {conflict_resolver_name}
    """)
    replicator = Replicator(
        db,
        cblpytest.sync_gateways[0].replication_url("upgrade"),
        collections=[
            ReplicatorCollectionEntry(
                names=["_default._default"],
                document_ids=[doc_id],
                conflict_resolver=conflict_resolver,
            )
        ],
        replicator_type=replicator_type,
        continuous=wait_for_doc_events,
        authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
        pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        enable_document_listener=wait_for_doc_events,
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

    if compare_docs:
        test_case.mark_test_step("Check that the doc is replicated correctly.")
        await compare_local_and_remote(
            db, sg, replicator_type, "upgrade", ["_default._default"], [doc_id]
        )

    local_doc = await db.get_document(DocumentEntry("_default._default", doc_id))
    remote_doc = await sg.get_document("upgrade", doc_id)

    assert local_doc is not None
    assert remote_doc is not None
    cbl_info(f"Revision Info after Replication ({replicator_type}):")
    cbl_info(f"Local : RevID = {local_doc.revid}, HLV = {local_doc.cv}")
    cbl_info(f"Remote : RevID = {remote_doc.revid}, HLV = {remote_doc.cv}")

    if validator:
        test_case.mark_test_step("Validate revid and HLV of local and remote doc.")
        validator(
            DocSnapshot(pre_local_doc, pre_remote_doc),
            DocSnapshot(local_doc, remote_doc),
        )
