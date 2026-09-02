"""Unit tests for Replicator.wait_for_all_doc_events.

Both tests exist to keep the wait from ever being tied back to the replicator's IDLE state.  A
continuous replicator reports IDLE whenever it has nothing in flight, and that includes the window
where Sync Gateway has accepted a document but has not yet released it to the changes feed.  So a
replicator can sit idle, with documents still legitimately on their way, for several seconds.

get_status is stubbed rather than mocked at the HTTP layer, because what is under test is the
polling policy, not the request plumbing.
"""

from datetime import timedelta

import pytest
from cbltest.api.error import CblTimeoutError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorDocumentEntry,
    ReplicatorDocumentFlags,
    ReplicatorProgress,
    ReplicatorStatus,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from opentelemetry.trace import get_tracer

LIST_DOC = WaitForDocumentEventEntry("_default.lists", "db1-list1", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE)
TASK_DOC = WaitForDocumentEventEntry(
    "_default.tasks", "db1-list1-task1", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE
)


def _doc_entry(collection: str, doc_id: str) -> ReplicatorDocumentEntry:
    return ReplicatorDocumentEntry({"collection": collection, "documentID": doc_id, "isPush": False, "flags": []})


class _IdleReplicator(Replicator):
    """
    A Replicator that always reports IDLE but only hands over its document events once
    `deliver_after_polls` polls have happened.

    That combination is the situation being guarded against: idle on every single poll, while the
    documents are still on their way.  It stands in for Sync Gateway holding a document back from
    the changes feed while the replicator, having nothing to do, reports itself idle.
    """

    def __init__(self, deliver_after_polls: int, docs: list[ReplicatorDocumentEntry]) -> None:
        self.polls = 0
        self.__deliver_after_polls = deliver_after_polls
        self.__docs = docs
        self.__updates: list[ReplicatorDocumentEntry] = []
        # Deliberately skip Replicator.__init__, which would need a real Database and
        # RequestFactory that play no part in the polling policy under test.  Set only the
        # attributes the wait helper reads.  The tracer goes in under its name-mangled attribute
        # because it is declared private on Replicator.
        self.continuous = True
        self.enable_document_listener = True
        self._Replicator__tracer = get_tracer(__name__)

    @property
    def document_updates(self) -> list[ReplicatorDocumentEntry]:
        return self.__updates

    async def get_status(self) -> ReplicatorStatus:
        self.polls += 1
        if self.polls >= self.__deliver_after_polls:
            for doc in self.__docs:
                if doc not in self.__updates:
                    self.__updates.append(doc)
        return ReplicatorStatus(ReplicatorProgress({"completed": False}), ReplicatorActivityLevel.IDLE, None)


@pytest.mark.asyncio(loop_scope="function")
async def test_keeps_polling_while_replicator_reports_idle() -> None:
    """Idle on every poll, with the documents only arriving on the 8th: the wait has to last."""
    repl = _IdleReplicator(
        deliver_after_polls=8,
        docs=[_doc_entry("_default.lists", "db1-list1"), _doc_entry("_default.tasks", "db1-list1-task1")],
    )

    await repl.wait_for_all_doc_events(
        {LIST_DOC, TASK_DOC},
        timeout=timedelta(seconds=30),
        ping_interval=timedelta(seconds=0.01),
    )

    assert repl.polls >= 8, "gave up while the replicator was idle but documents were still coming"


@pytest.mark.asyncio(loop_scope="function")
async def test_timeout_names_the_documents_that_never_arrived() -> None:
    """A timeout has to identify the missing documents, or a CI log cannot be diagnosed."""
    repl = _IdleReplicator(deliver_after_polls=1, docs=[_doc_entry("_default.lists", "db1-list1")])

    with pytest.raises(CblTimeoutError) as excinfo:
        await repl.wait_for_all_doc_events(
            {LIST_DOC, TASK_DOC},
            timeout=timedelta(seconds=0.2),
            ping_interval=timedelta(seconds=0.01),
        )

    message = str(excinfo.value)
    assert "db1-list1-task1" in message, message
    assert "db1-list1," not in message, f"the document that did arrive should not be listed: {message}"
