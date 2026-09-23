from pathlib import Path
from typing import Any

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database, GetDocumentResult
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)
from cbltest.api.syncgateway import SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.logging import cbl_info
from cbltest.utils import async_retry_assert
from shared.local_sync_gateway import (
    CBG_5713_FIX_COMMIT,
    LocalSyncGateway,
    unavailable_reason,
)
from shared.revtree_helpers import (
    assert_strictly_increasing_generations,
    current_rev,
    document_body,
    find_repeating_generation,
    parse_rev_history,
    rev_generation,
    rev_tree_ids,
    sync_metadata,
    walk_rev_tree,
)
from shared.upgrade_test_helpers import setup_upgrade_env

# The `upgrade` dataset supplies the pre-upgrade state this test needs: a Couchbase Server bucket
# written by a pre-4.0 Sync Gateway, plus a matching local database in which the client already holds
# legacy revisions.  It cannot be produced live, because a 4.x client cannot replicate with a pre-4.0
# Sync Gateway at all - it only speaks BLIP_3+CBMobile_4.
SG_DB = "upgrade"
COLLECTION = "_default._default"
USER = "user1"
PASSWORD = "pass"

# One document per repair trigger - the first read or write of a document repairs it, so the triggers
# cannot share one.  Both are documents where the client's legacy revision is on the same branch as
# Sync Gateway's, so its pushes are accepted rather than rejected as conflicts:
#   nonconflict_3 - client and Sync Gateway hold the same legacy revision, neither has an HLV
#   nonconflict_1 - client is one revision ahead of Sync Gateway on that same branch
READ_DOC = "nonconflict_3"
WRITE_DOC = "nonconflict_1"
DOC_IDS = (READ_DOC, WRITE_DOC)

# Four post-upgrade client updates, matching Sync Gateway's own repro
# (TestLegacyHistoryPushCreatesDuplicateGenerationRevs).  Two is the minimum to produce a
# same-generation parent link.
UPDATE_ROUNDS = 4

# Repair is always on - there is no config flag to enable.
INVALID_REV_TREE_STAT = "invalid_rev_tree_count"

# Labels for the Sync Gateway binaries this test switches between.
UNDER_TEST = "under_test"
PRE_FIX = "prefix"


async def _one_shot_replication(
    cblpytest: CBLPyTest,
    db: Database,
    replicator_type: ReplicatorType,
    doc_ids: list[str],
    *,
    enable_document_listener: bool = False,
) -> Replicator:
    """
    Runs a single one-shot replication to completion and returns the replicator so document events
    can be inspected.  One-shot rather than continuous so each local update is pushed as its own
    revision, and so nothing is left running when Sync Gateway is restarted underneath it.
    """
    sg = cblpytest.sync_gateways[0]
    replicator = Replicator(
        db,
        sg.replication_url(SG_DB),
        collections=[ReplicatorCollectionEntry(names=[COLLECTION], document_ids=doc_ids)],
        replicator_type=replicator_type,
        authenticator=ReplicatorBasicAuthenticator(USER, PASSWORD),
        pinned_server_cert=sg.tls_cert(),
        enable_document_listener=enable_document_listener,
    )
    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is None, (
        f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
    )
    return replicator


async def _sync_metadata(sg: SyncGateway, doc_id: str) -> dict:
    """Reads a document's `_sync` metadata without going through a path that would repair it."""
    return sync_metadata(await sg.get_raw_document(SG_DB, doc_id))


async def _wait_for_rev_change(sg: SyncGateway, doc_id: str, previous_rev: str) -> str:
    """Waits until the winning rev tree ID of a document in the bucket differs from previous_rev."""

    async def _poll() -> str:
        rev = current_rev(await _sync_metadata(sg, doc_id))
        assert rev != previous_rev, f"Document '{doc_id}' is still at rev {rev}"
        return rev

    return await async_retry_assert(_poll, tenacity.wait_fixed(1), tenacity.stop_after_delay(60))


async def _wait_for_repair(sg: SyncGateway, doc_id: str, corrupt_rev: str) -> dict:
    """Waits until a document's rev tree no longer has a same-generation parent link."""

    async def _poll() -> dict:
        metadata = await _sync_metadata(sg, doc_id)
        branch = walk_rev_tree(metadata)
        repeating = find_repeating_generation(branch)
        assert repeating is None, (
            f"Document '{doc_id}' is still corrupt at {current_rev(metadata)}: "
            f"'{repeating[1]}' is not a higher generation than its parent '{repeating[0]}'"
        )
        assert current_rev(metadata) != corrupt_rev, f"Document '{doc_id}' still wins with {corrupt_rev}"
        return metadata

    return await async_retry_assert(_poll, tenacity.wait_fixed(1), tenacity.stop_after_delay(60))


async def _invalid_rev_tree_count(sg: SyncGateway) -> int:
    """Reads the count of rev trees Sync Gateway has found invalid, 0 if the stat is absent."""
    stats = await sg.get_db_expvars(SG_DB, "database")
    return int(stats.get(INVALID_REV_TREE_STAT, 0))


async def _wait_for_changes_entry(sg: SyncGateway, doc_id: str, expected_rev: str) -> None:
    """
    Waits until the changes feed reports a document at expected_rev.

    An entry's revision comes from the change cache, which is populated from the mutation feed, so
    this only passes once the write that produced expected_rev has reached that feed.  That is what
    the repair allocates a sequence for - without one, a client already told about the pre-repair
    revision would never hear about the repair.
    """

    async def _poll() -> None:
        changes = await sg.get_changes(SG_DB)
        entries = [entry for entry in changes.results if entry.id == doc_id]
        assert entries, f"Document '{doc_id}' is missing from the changes feed"
        latest = entries[-1]
        assert expected_rev in latest.changes, (
            f"Changes feed reports '{doc_id}' at {latest.changes} (sequence {latest.seq}), expected {expected_rev}"
        )

    await async_retry_assert(_poll, tenacity.wait_fixed(1), tenacity.stop_after_delay(60))


def _replication_errors(replicator: Replicator, doc_id: str) -> list[str]:
    """Collects the errors a replicator reported for one document."""
    return [
        f"({entry.error.domain} / {entry.error.code}) {entry.error.message}"
        for entry in replicator.document_updates
        if entry.document_id == doc_id and entry.error is not None
    ]


async def _client_document(db: Database, doc_id: str) -> GetDocumentResult:
    """Reads a document from the client's local database, failing if it is not there."""
    local_doc = await db.get_document(DocumentEntry(COLLECTION, doc_id))
    assert local_doc is not None, f"Document '{doc_id}' is missing on the client"
    cbl_info(f"Client history for '{doc_id}': {local_doc.revs}")
    return local_doc


def _assert_client_history_well_formed(local_doc: GetDocumentResult, doc_id: str) -> None:
    """The client must not be left holding a branch that repeats a generation either."""
    # A post-upgrade client reports version vector entries too, and those carry no generation.
    branch = list(reversed(rev_tree_ids(parse_rev_history(local_doc.revs))))
    assert branch, f"Client holds no rev tree history for '{doc_id}'"
    assert_strictly_increasing_generations(branch)


async def _update_and_push(cblpytest: CBLPyTest, db: Database, doc_id: str, properties: dict[str, Any]) -> None:
    """Updates a document on the client, pushes it, and fails if the push reported any error."""
    async with db.batch_updater() as updater:
        updater.upsert_document(COLLECTION, doc_id, new_properties=[properties])

    replicator = await _one_shot_replication(
        cblpytest, db, ReplicatorType.PUSH, [doc_id], enable_document_listener=True
    )
    errors = _replication_errors(replicator, doc_id)
    assert not errors, f"Pushing '{doc_id}' reported errors: {errors}"


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestRevTreeRepair(CBLTestClass):
    # No cleanup() call at the end of this test, unlike most of dev_e2e: it resets the test server,
    # and the client's local database has to survive the Sync Gateway restart in the middle.
    # test_replication_upgrade.py leaves it out for the same reason.

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revtree_repaired_after_upgrade(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]

        reason = unavailable_reason(sg)
        self.skip_if_not(reason is None, f"{reason}. This test builds and restarts Sync Gateway itself.")

        local = LocalSyncGateway(f"couchbase://{cbs.hostname}")

        self.mark_test_step("Keep a copy of the Sync Gateway under test, then start one from before the CBG-5713 fix")
        local.stash(UNDER_TEST)
        if local.has_stashed(PRE_FIX):
            local.start_stashed(PRE_FIX)
        else:
            local.build_and_start(f"{CBG_5713_FIX_COMMIT}^", stash_as=PRE_FIX)
        await sg._wait_for_rest_api()
        assert await sg.supports_version_vectors(), (
            f"Building the corruption needs a 4.0 or newer Sync Gateway, got {(await sg.get_version()).raw}"
        )

        db = await setup_upgrade_env(self, cblpytest, dataset_path)

        self.mark_test_step("Check the client holds a legacy revision - a rev tree ID and no HLV - for each document")
        for doc_id in DOC_IDS:
            local_doc = await db.get_document(DocumentEntry(COLLECTION, doc_id))
            assert local_doc is not None, f"Document '{doc_id}' is missing on the client"
            assert local_doc.revid is not None and local_doc.cv is None, (
                f"Document '{doc_id}' is not legacy on the client, RevID: {local_doc.revid}, HLV: {local_doc.cv}"
            )

        self.mark_test_step(f"Update each document {UPDATE_ROUNDS} times, pushing each revision separately")
        for round_number in range(1, UPDATE_ROUNDS + 1):
            previous_revs = {doc_id: current_rev(await _sync_metadata(sg, doc_id)) for doc_id in DOC_IDS}

            async with db.batch_updater() as updater:
                for doc_id in DOC_IDS:
                    updater.upsert_document(COLLECTION, doc_id, new_properties=[{"round": round_number}])

            await _one_shot_replication(cblpytest, db, ReplicatorType.PUSH, list(DOC_IDS))

            for doc_id in DOC_IDS:
                rev = await _wait_for_rev_change(sg, doc_id, previous_revs[doc_id])
                cbl_info(f"Round {round_number}: '{doc_id}' is now at {rev} on Sync Gateway")

        self.mark_test_step("Check every document's rev tree now has a parent link that does not increase generation")
        for doc_id in DOC_IDS:
            branch = walk_rev_tree(await _sync_metadata(sg, doc_id))
            repeating = find_repeating_generation(branch)
            assert repeating is not None, (
                f"Document '{doc_id}' has a well formed rev tree, so CBG-5713 did not reproduce. Either the "
                f"pre-fix Sync Gateway build is wrong, or the client stopped sending its legacy revision "
                f"in the push history (branch root -> leaf: {branch})"
            )
            cbl_info(f"'{doc_id}' is corrupt: '{repeating[1]}' parented to '{repeating[0]}' (branch {branch})")

        self.mark_test_step("Check Sync Gateway cannot encode the corrupt history for a pre-4.0 client")
        for doc_id in DOC_IDS:
            revisions = await sg.get_document_revisions(SG_DB, doc_id)
            assert revisions == [], f"Expected no usable revision history for '{doc_id}', got {revisions}"

        self.mark_test_step("Restart the Sync Gateway under test over the same bucket")
        local.start_stashed(UNDER_TEST)
        await sg._wait_for_rest_api()
        await SyncGatewayCluster(cblpytest.sync_gateways).wait_for_db_online(SG_DB)

        # The write path has to come first: anything that reads every document - compare_local_and_remote
        # below, for one - repairs this one too, and then the write is checked against a tree that is
        # already sound.
        self.mark_test_step(
            f"Check '{WRITE_DOC}' is still corrupt, reading it through _raw so the read does not repair it"
        )
        write_raw = await sg.get_raw_document(SG_DB, WRITE_DOC)
        write_corrupt = sync_metadata(write_raw)
        write_corrupt_rev = current_rev(write_corrupt)
        assert find_repeating_generation(walk_rev_tree(write_corrupt)) is not None, (
            f"'{WRITE_DOC}' is already repaired, so the write path is untested. Something read it "
            f"through Sync Gateway first (branch root -> leaf: {walk_rev_tree(write_corrupt)})"
        )
        body = document_body(write_raw)

        self.mark_test_step(f"Update '{WRITE_DOC}' through the Sync Gateway admin API")
        updated: dict[str, Any] = {k: v for k, v in body.items() if not k.startswith("_")}
        updated["updated_by"] = "revtree_repair_on_write"
        try:
            await sg.update_document(SG_DB, WRITE_DOC, updated, write_corrupt_rev)
        except CblSyncGatewayBadResponseError as e:
            # Repairing renames the revision the caller quoted, so the write is told its revision is
            # stale. Retrying against the repaired revision has to succeed.
            assert e.code == 409, f"Unexpected error updating '{WRITE_DOC}': {e}"
            cbl_info(f"write against pre-repair rev {write_corrupt_rev} was rejected as stale, retrying")
            write_repaired = await _wait_for_repair(sg, WRITE_DOC, write_corrupt_rev)
            await sg.update_document(SG_DB, WRITE_DOC, updated, current_rev(write_repaired))

        self.mark_test_step("Wait for the written document's rev tree to be repaired")
        write_repaired = await _wait_for_repair(sg, WRITE_DOC, write_corrupt_rev)

        self.mark_test_step("Check generations strictly increase for the written document too")
        write_branch = walk_rev_tree(write_repaired)
        assert_strictly_increasing_generations(write_branch)
        assert rev_generation(write_branch[-1]) > rev_generation(write_corrupt_rev), (
            f"Expected the written revision above generation {rev_generation(write_corrupt_rev)}, "
            f"got {write_branch[-1]}"
        )
        assert await sg.get_document_revisions(SG_DB, WRITE_DOC), (
            f"Expected a usable revision history for '{WRITE_DOC}' after repair"
        )

        self.mark_test_step(f"Record the corrupt state of '{READ_DOC}' through _raw, which does not repair it")
        corrupt_raw = await sg.get_raw_document(SG_DB, READ_DOC)
        corrupt = sync_metadata(corrupt_raw)
        corrupt_rev = current_rev(corrupt)
        corrupt_branch = walk_rev_tree(corrupt)
        corrupt_sequence = int(corrupt["sequence"])
        corrupt_body = document_body(corrupt_raw)
        count_before = await _invalid_rev_tree_count(sg)
        assert find_repeating_generation(corrupt_branch) is not None, (
            f"'{READ_DOC}' is already repaired, so the read path is untested (branch root -> leaf: {corrupt_branch})"
        )

        self.mark_test_step(f"Read '{READ_DOC}' through the Sync Gateway admin API")
        assert await sg.get_document(SG_DB, READ_DOC) is not None, f"Document '{READ_DOC}' could not be read"

        self.mark_test_step("Wait for the rev tree to be repaired")
        repaired = await _wait_for_repair(sg, READ_DOC, corrupt_rev)
        repaired_rev = current_rev(repaired)

        self.mark_test_step("Check generations strictly increase from the root of the branch to its leaf")
        # This is the requirement: a branch Sync Gateway can encode again.  The corrupt branch repeats a
        # generation once per client push, so the leaf has to climb by however many bad links there
        # were - not by exactly one.
        repaired_branch = walk_rev_tree(repaired)
        assert_strictly_increasing_generations(repaired_branch)
        assert rev_generation(repaired_rev) > rev_generation(corrupt_rev), (
            f"Expected {corrupt_rev} to be renumbered to a higher generation, got {repaired_rev}"
        )

        self.mark_test_step("Check the repair renumbered the existing revisions rather than replacing them")
        # Renumber-in-place is what the reference Go test expects (10-def becomes 11-def) and the only
        # thing Sync Gateway can do, since a rev ID is md5(parentRevID, body) and it no longer holds the
        # bodies needed to recompute the digests above the first renumbered link.  If CBG-5718 instead
        # mints fresh rev IDs, this is the assertion that will say so.
        assert [rev.partition("-")[2] for rev in repaired_branch] == [
            rev.partition("-")[2] for rev in corrupt_branch
        ], (
            f"Expected the repair to renumber the branch in place, keeping each digest in order.\n"
            f"  before: {corrupt_branch}\n  after:  {repaired_branch}"
        )

        self.mark_test_step("Check the repair left the document body alone")
        # The repair is a metadata only write: it renumbers the rev tree and touches nothing else.
        assert document_body(await sg.get_raw_document(SG_DB, READ_DOC)) == corrupt_body, (
            f"Expected the repair to leave the body of '{READ_DOC}' untouched"
        )

        self.mark_test_step("Check the repair took a new sequence, so it reaches the changes feed")
        assert int(repaired["sequence"]) > corrupt_sequence, (
            f"Expected a sequence above {corrupt_sequence}, got {repaired['sequence']}"
        )

        self.mark_test_step("Check the repaired revision actually reaches the changes feed")
        # The sequence above only says one was allocated.  This says the mutation carrying it reached
        # the change cache, which is what a client waiting on the feed will be told about.
        await _wait_for_changes_entry(sg, READ_DOC, repaired_rev)

        self.mark_test_step("Check Sync Gateway counted the invalid rev tree")
        assert await _invalid_rev_tree_count(sg) > count_before, (
            f"Expected {INVALID_REV_TREE_STAT} to rise above {count_before}"
        )

        self.mark_test_step("Check Sync Gateway can now encode the history for a pre-4.0 client")
        revisions = await sg.get_document_revisions(SG_DB, READ_DOC)
        assert revisions, f"Expected a usable revision history for '{READ_DOC}' after repair"
        assert_strictly_increasing_generations(list(reversed(revisions)))

        # The client has not replicated since the repair, so it still holds the revision it pushed onto
        # the pre-repair tree.  A repair that rebuilds the tree must not turn that into a conflict when
        # the client next pushes.
        self.mark_test_step(
            f"Update '{READ_DOC}' on the client on top of the revision it held before the repair, and push it"
        )
        await _update_and_push(cblpytest, db, READ_DOC, {"pushed_after_repair": True})

        self.mark_test_step("Check the document converged, and that the rev tree is still well formed")
        await compare_local_and_remote(db, sg, ReplicatorType.PUSH, SG_DB, [COLLECTION], [READ_DOC])
        assert_strictly_increasing_generations(walk_rev_tree(await _sync_metadata(sg, READ_DOC)))
        _assert_client_history_well_formed(await _client_document(db, READ_DOC), READ_DOC)

        # The push above started from a revision the client held before the repair.  This one starts
        # from the repaired lineage, which is what every write a client makes from now on will do.
        self.mark_test_step(f"Update '{READ_DOC}' again, this time on top of the repaired revision, and push it")
        await _update_and_push(cblpytest, db, READ_DOC, {"second_update_after_repair": True})

        self.mark_test_step("Check the second update converged and kept the rev tree well formed")
        await compare_local_and_remote(db, sg, ReplicatorType.PUSH, SG_DB, [COLLECTION], [READ_DOC])
        read_after_updates = await _sync_metadata(sg, READ_DOC)
        assert_strictly_increasing_generations(walk_rev_tree(read_after_updates))
        assert rev_generation(current_rev(read_after_updates)) > rev_generation(repaired_rev), (
            f"Expected '{READ_DOC}' above generation {rev_generation(repaired_rev)} after two client "
            f"updates, got {current_rev(read_after_updates)}"
        )
        assert await sg.get_document_revisions(SG_DB, READ_DOC), (
            f"Expected a usable revision history for '{READ_DOC}' after updating it post-repair"
        )
        _assert_client_history_well_formed(await _client_document(db, READ_DOC), READ_DOC)

        # The client is a revision behind on this one, on a branch whose ancestors were renamed
        # underneath it, so it has to accept the renamed lineage rather than fork a second branch.
        self.mark_test_step(f"Pull '{WRITE_DOC}' and check the client accepts the repaired revision")
        write_repaired_rev = current_rev(await _sync_metadata(sg, WRITE_DOC))
        await _wait_for_changes_entry(sg, WRITE_DOC, write_repaired_rev)
        replicator = await _one_shot_replication(
            cblpytest, db, ReplicatorType.PULL, [WRITE_DOC], enable_document_listener=True
        )
        errors = _replication_errors(replicator, WRITE_DOC)
        assert not errors, f"Pulling '{WRITE_DOC}' after repair reported errors: {errors}"

        self.mark_test_step("Check the pulled document converged and its history is well formed on the client")
        await compare_local_and_remote(db, sg, ReplicatorType.PULL, SG_DB, [COLLECTION], [WRITE_DOC])
        pulled = await _client_document(db, WRITE_DOC)
        _assert_client_history_well_formed(pulled, WRITE_DOC)
        assert pulled.body.get("updated_by") == "revtree_repair_on_write", (
            f"Client did not receive the revision written through the admin API, body: {pulled.body}"
        )

        self.mark_test_step(f"Update '{WRITE_DOC}' on the client on top of the pulled revision and push it back")
        await _update_and_push(cblpytest, db, WRITE_DOC, {"pushed_after_pull": True})

        self.mark_test_step("Check the round trip converged and left the rev tree well formed")
        await compare_local_and_remote(db, sg, ReplicatorType.PUSH, SG_DB, [COLLECTION], [WRITE_DOC])
        write_after_push = await _sync_metadata(sg, WRITE_DOC)
        assert_strictly_increasing_generations(walk_rev_tree(write_after_push))
        assert rev_generation(current_rev(write_after_push)) > rev_generation(write_repaired_rev), (
            f"Expected '{WRITE_DOC}' above generation {rev_generation(write_repaired_rev)} after the "
            f"client push, got {current_rev(write_after_push)}"
        )
        assert await sg.get_document_revisions(SG_DB, WRITE_DOC), (
            f"Expected a usable revision history for '{WRITE_DOC}' after the client round trip"
        )
        _assert_client_history_well_formed(await _client_document(db, WRITE_DOC), WRITE_DOC)
