from datetime import timedelta
from typing import Any

import tenacity
from opentelemetry.trace import get_tracer

from cbltest.api.database import AllDocumentsEntry, Database
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import AllDocumentsResponseRow, SyncGateway
from cbltest.utils import async_retry_assert
from cbltest.version import VERSION


def _same_cv(cbl_cv: str, sg_cv: str | None) -> bool:
    """
    A CBL CV and a SG CV are the same if they match exactly.  CBL reports its own source as `*`,
    so a CBL CV ending in `@*` matches any SG CV with the same timestamp.
    """
    if sg_cv is None:
        return False
    if not cbl_cv.endswith("@*"):
        return cbl_cv == sg_cv
    return cbl_cv[:-2] == sg_cv.partition("@")[0]


def _compare_revisions(cbl_rev: str, sg_rev: list[str | None]) -> bool:
    """
    A CBL revision and a SG revision are the same iff the cbl_rev matches either the SG rev tree
    rev ID or the SG CV (see :func:`_same_cv`)
    """
    return cbl_rev == sg_rev[0] or _same_cv(cbl_rev, sg_rev[1])


class DocsCompareResult:
    """
    A simple class to hold whether or not a list of documents
    matches another, and if not then the first reason why it
    does not.
    """

    @property
    def message(self) -> str | None:
        """
        If success is false, then this message will contain the description
        of the first difference found in the two lists
        """
        return self.__message

    @property
    def success(self) -> bool:
        """Gets whether or not the two lists match"""
        return self.__success

    def __init__(self, success: bool, message: str | None = None) -> None:
        self.__success = success
        self.__message = message

    def __bool__(self) -> bool:
        return self.__success

    def __str__(self) -> str:
        return "documents match" if self.__success else (self.__message or "documents do not match")


_test_function_tracer = get_tracer("test_functions", VERSION)


def _compare_doc_results(
    local: list[AllDocumentsEntry],
    remote: list[AllDocumentsResponseRow],
    mode: ReplicatorType,
) -> DocsCompareResult:
    """
    Checks for consistency between a list of local documents and a list of remote documents, accounting
    for the mode of replication that was run.  For PUSH_AND_PULL, the document count must match exactly,
    along with the contents.  For PUSH, the local list is consulted and the remote list is checked,
    and vice-versa for PULL (to account for other pre-existing documents that have not been synced
    due to the non bi-directional mode)

    :param local: The list of documents from the local side (Couchbase Lite)
    :param remote: The list of documents from the remote side (Sync Gateway)
    :param mode: The mode of replication that was run.
    """
    with _test_function_tracer.start_as_current_span("compare_doc_results"):
        if mode == ReplicatorType.PUSH_AND_PULL and len(local) != len(remote):
            return DocsCompareResult(
                False,
                f"Local count {len(local)} did not match remote count {len(remote)}",
            )

        local_dict: dict[str, str] = {}
        remote_dict: dict[str, list[str | None]] = {}

        for local_entry in local:
            local_dict[local_entry.id] = local_entry.rev

        for remote_entry in remote:
            remote_dict[remote_entry.id] = [remote_entry.revid, remote_entry.cv]

        source: dict[str, Any]
        dest: dict[str, Any]
        if mode == ReplicatorType.PUSH:
            source = local_dict
            dest = remote_dict
            source_name = "local"
            dest_name = "remote"
        else:
            source = remote_dict
            dest = local_dict
            source_name = "remote"
            dest_name = "local"

        for id in source:
            if id not in dest:
                return DocsCompareResult(False, f"Doc '{id}' present in {source_name} but not {dest_name}")

            if not _compare_revisions(local_dict[id], remote_dict[id]):
                return DocsCompareResult(
                    False,
                    f"Doc '{id}' mismatched revid ({source_name}: {source[id]}, {dest_name}: {dest[id]})",
                )

        return DocsCompareResult(True)


def _same_p2p_revision(rev: str, other: str) -> bool:
    if rev == other:
        return True

    # A peer reports the source of its own changes as "*", other peers report its full source ID
    if rev.endswith("@*") or other.endswith("@*"):
        return rev.split("@")[0] == other.split("@")[0]

    return False


def compare_doc_results(
    local: list[AllDocumentsEntry],
    remote: list[AllDocumentsResponseRow],
    mode: ReplicatorType,
) -> None:
    """
    Asserts that a list of local documents and a list of remote documents are consistent,
    as described in :func:`_compare_doc_results()<cbltest.api.test_functions._compare_doc_results>`

    :param local: The list of documents from the local side (Couchbase Lite)
    :param remote: The list of documents from the remote side (Sync Gateway)
    :param mode: The mode of replication that was run
    :raises AssertionError: If the documents are not consistent
    """
    result = _compare_doc_results(local, remote, mode)
    if not result:
        raise AssertionError(str(result))


def compare_doc_results_p2p(
    local: list[AllDocumentsEntry],
    remote: list[AllDocumentsEntry],
) -> None:
    """
    Asserts that two peers hold the same documents at the same revisions

    :param local: The list of documents from the local peer
    :param remote: The list of documents from the remote peer
    :raises AssertionError: If a document is missing from either peer or has a different revision
    """
    local_revs = {entry.id: entry.rev for entry in local}
    remote_revs = {entry.id: entry.rev for entry in remote}
    for id, rev in local_revs.items():
        if id in remote_revs and _same_p2p_revision(rev, remote_revs[id]):
            remote_revs[id] = rev

    # Compare only the differing entries, so the pytest diff stays small when it is not truncated on CI
    local_only = {id: rev for id, rev in local_revs.items() if remote_revs.get(id) != rev}
    remote_only = {id: rev for id, rev in remote_revs.items() if local_revs.get(id) != rev}
    assert local_only == remote_only


def compare_doc_ids(
    local: list[AllDocumentsEntry],
    remote: list[AllDocumentsResponseRow],
) -> None:
    """
    Asserts that the local and remote sides hold the same document IDs, ignoring revisions

    :param local: The list of documents from the local side (Couchbase Lite)
    :param remote: The list of documents from the remote side (Sync Gateway)
    :raises AssertionError: If a document ID is missing from either side
    """
    local_ids = {entry.id for entry in local}
    remote_ids = {entry.id for entry in remote}

    # Compare only the differing IDs, so the pytest diff stays small when it is not truncated on CI
    assert local_ids - remote_ids == remote_ids - local_ids


async def compare_local_and_remote(
    local: Database,
    remote: SyncGateway,
    mode: ReplicatorType,
    bucket: str,
    collections: list[str],
    doc_ids: list[str] | None = None,
) -> None:
    """
    Checks the specified collections for consistency between local and remote, using the
    :func:`_compare_doc_results()<cbltest.api.test_functions._compare_doc_results>` function
    for each collection

    :raises AssertionError: If the documents in any collection are not consistent
    """
    with _test_function_tracer.start_as_current_span("compare_local_and_remote"):
        lite_all_docs = await local.get_all_documents(*collections)

        for collection in collections:
            split = collection.split(".")
            assert len(split) == 2, f"Invalid collection name in compare_local_and_remote: {collection}"
            sg_all_docs = await remote.get_all_documents(bucket, split[0], split[1])

            lite_docs = lite_all_docs[collection]
            sg_docs = sg_all_docs.rows

            if doc_ids is not None:
                lite_docs = [entry for entry in lite_docs if entry.id in doc_ids]
                sg_docs = [entry for entry in sg_docs if entry.id in doc_ids]

            compare_result = _compare_doc_results(lite_docs, sg_docs, mode)
            if not compare_result:
                raise AssertionError(f"{compare_result} ({collection})")


async def wait_for_converging_cvs(
    sg1: SyncGateway,
    sg2: SyncGateway,
    db_name: str,
    scope: str = "_default",
    collection: str = "_default",
    timeout: timedelta = timedelta(seconds=60),
) -> None:
    """
    Waits until the changes feeds of two Sync Gateways, for example on clusters linked by XDCR,
    hold the same documents and tombstones with the same current version (CV).  The changes feed
    is what a replicator reads, so a replication started after this sees the converged versions.

    :param sg1: One Sync Gateway to compare
    :param sg2: The other Sync Gateway to compare
    :param db_name: The name of the database on both Sync Gateways
    :param scope: The scope to compare
    :param collection: The collection to compare
    :param timeout: How long to wait before raising TimeoutError
    """

    async def _versions(sg: SyncGateway) -> dict[str, tuple[str, bool]]:
        changes = await sg.get_changes(db_name, scope, collection, version_type="cv", log_response=False)
        return {entry.id: (entry.changes[0], entry.deleted) for entry in changes.results}

    def _describe(version: tuple[str, bool] | None) -> str:
        if version is None:
            return "missing"
        cv, deleted = version
        return f"{cv} (deleted)" if deleted else cv

    async def _compare_cvs() -> None:
        versions1, versions2 = await _versions(sg1), await _versions(sg2)
        differing = sorted(d for d in versions1.keys() | versions2.keys() if versions1.get(d) != versions2.get(d))
        examples = ", ".join(
            f"{d} ({_describe(versions1.get(d))} vs {_describe(versions2.get(d))})" for d in differing[:5]
        )
        assert not differing, (
            f"{len(differing)} of {len(versions1.keys() | versions2.keys())} docs differ between {sg1} and {sg2} "
            f"in {db_name}.{scope}.{collection}, for example: {examples}"
        )

    with _test_function_tracer.start_as_current_span("wait_for_converging_cvs"):
        await async_retry_assert(
            _compare_cvs, tenacity.wait_fixed(1), tenacity.stop_after_delay(timeout.total_seconds())
        )


async def wait_for_matching_cvs(
    local: Database,
    remote: SyncGateway,
    db_name: str,
    scope: str = "_default",
    collection: str = "_default",
    timeout: timedelta = timedelta(seconds=30),
) -> None:
    """
    Waits until the local database holds exactly the live documents on a Sync Gateway's changes
    feed, each at the same current version (CV)

    :param local: The local database
    :param remote: The Sync Gateway to compare against
    :param db_name: The name of the Sync Gateway database
    :param scope: The scope to compare
    :param collection: The collection to compare
    :param timeout: How long to wait before raising TimeoutError
    """
    local_collection = f"{scope}.{collection}"

    async def _compare() -> None:
        changes = await remote.get_changes(db_name, scope, collection, version_type="cv", log_response=False)
        remote_cvs = {entry.id: entry.changes[0] for entry in changes.results if not entry.deleted}
        local_docs = await local.get_all_documents(local_collection)
        local_cvs = {entry.id: entry.rev for entry in local_docs.get(local_collection) or []}
        differing = sorted(
            d
            for d in local_cvs.keys() | remote_cvs.keys()
            if d not in local_cvs or not _same_cv(local_cvs[d], remote_cvs.get(d))
        )
        examples = ", ".join(
            f"{d} (local {local_cvs.get(d, 'missing')} vs remote {remote_cvs.get(d, 'missing')})" for d in differing[:5]
        )
        assert not differing, (
            f"{len(differing)} of {len(local_cvs.keys() | remote_cvs.keys())} docs differ between local and {remote} "
            f"in {db_name}.{local_collection}, for example: {examples}"
        )

    with _test_function_tracer.start_as_current_span("wait_for_matching_cvs"):
        await async_retry_assert(_compare, tenacity.wait_fixed(1), tenacity.stop_after_delay(timeout.total_seconds()))
