from typing import Any

from opentelemetry.trace import get_tracer

from cbltest.api.database import AllDocumentsEntry, Database
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import AllDocumentsResponseRow, SyncGateway
from cbltest.version import VERSION
import os
import signal
import subprocess
import paramiko

def _compare_revisions(cbl_rev: str, sg_rev: list[str | None]):
    """
    A CBL revision and a SG revision are the same iff the cbl_rev
    (an array of rev tree rev id and hlv cv) matches one of the sg_revs exactly
    As a temporary workaround, if the cbl_rev ends with the string '@*"
    the revisions are the same if the two strings preceding the @s match.
    """
    if not cbl_rev.endswith("@*"):
        return (cbl_rev == sg_rev[0]) or (cbl_rev == sg_rev[1])
    else:
        # hack to be removed once CBL-6443 is fixed:
        # if the cbl_rev ends in "@*" compare it to the substring
        #  of the sg_cv (sg_rev[1]) preceding the "@"
        sg_cv = sg_rev[1]
        if sg_cv is None:
            return False
        i = sg_cv.find("@")
        if i < 1:
            return False
        return cbl_rev[:-2] == sg_cv[0:i]


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

    def __init__(self, success: bool, message: str | None = None):
        self.__success = success
        self.__message = message


_test_function_tracer = get_tracer("test_functions", VERSION)


def compare_doc_results(
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
                return DocsCompareResult(
                    False, f"Doc '{id}' present in {source_name} but not {dest_name}"
                )

            if not _compare_revisions(local_dict[id], remote_dict[id]):
                return DocsCompareResult(
                    False,
                    f"Doc '{id}' mismatched revid ({source_name}: {source[id]}, {dest_name}: {dest[id]})",
                )

        return DocsCompareResult(True)


def compare_doc_results_p2p(
    local: list[AllDocumentsEntry], remote: list[AllDocumentsEntry]
) -> DocsCompareResult:
    local_dict: dict[str, str] = {entry.id: entry.rev for entry in local}
    remote_dict: dict[str, str] = {entry.id: entry.rev for entry in remote}

    for id in local_dict:
        if id not in remote_dict:
            return DocsCompareResult(
                False, f"Doc '{id}' present in {local_dict} but not {remote_dict}"
            )

        if not _compare_revisions(local_dict[id], [remote_dict[id], None]):
            return DocsCompareResult(
                False,
                f"Doc '{id}' mismatched revid (local: {local_dict[id]}, remote: {remote_dict[id]})",
            )

    return DocsCompareResult(True)


def compare_doc_ids(
    local: list[AllDocumentsEntry],
    remote: list[AllDocumentsResponseRow],
) -> DocsCompareResult:
    local_ids = {e.id for e in local}
    remote_ids = {e.id for e in remote}

    missing_on_remote = local_ids - remote_ids
    if missing_on_remote:
        missing_id = next(iter(missing_on_remote))
        return DocsCompareResult(
            False, f"Doc '{missing_id}' present locally but missing on remote"
        )

    missing_on_local = remote_ids - local_ids
    if missing_on_local:
        missing_id = next(iter(missing_on_local))
        return DocsCompareResult(
            False, f"Doc '{missing_id}' present on remote but missing locally"
        )

    return DocsCompareResult(True)


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
    :func:`compare_doc_results()<cbltest.api.test_functions.compare_doc_results>` function
    for each collection
    """
    with _test_function_tracer.start_as_current_span("compare_local_and_remote"):
        lite_all_docs = await local.get_all_documents(*collections)

        for collection in collections:
            split = collection.split(".")
            assert len(split) == 2, (
                f"Invalid collection name in compare_local_and_remote: {collection}"
            )
            sg_all_docs = await remote.get_all_documents(bucket, split[0], split[1])

            lite_docs = lite_all_docs[collection]
            sg_docs = sg_all_docs.rows

            if doc_ids is not None:
                lite_docs = [entry for entry in lite_docs if entry.id in doc_ids]
                sg_docs = [entry for entry in sg_docs if entry.id in doc_ids]

            compare_result = compare_doc_results(lite_docs, sg_docs, mode)
            assert compare_result.success, f"{compare_result.message} ({collection})"

