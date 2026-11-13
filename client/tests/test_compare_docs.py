from datetime import timedelta
from typing import cast

import pytest
from cbltest.api.database import AllDocumentsEntry, Database
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import AllDocumentsResponseRow, ChangesResponse, SyncGateway
from cbltest.api.test_functions import (
    _same_cv,
    compare_doc_ids,
    compare_doc_results,
    compare_doc_results_p2p,
    wait_for_converging_cvs,
    wait_for_matching_cvs,
)
from cbltest.response_types import PostGetAllDocumentsEntry


def local(id: str, rev: str) -> AllDocumentsEntry:
    return AllDocumentsEntry(PostGetAllDocumentsEntry({"id": id, "rev": rev}))


def remote(id: str, rev: str) -> AllDocumentsResponseRow:
    return AllDocumentsResponseRow(id, id, rev, None)


# A changes feed entry: (doc ID, CV, deleted)
Feed = list[tuple[str, str, bool]]

# A zero timeout makes the waits give up after their first attempt.
NO_RETRY = timedelta(0)


class FakeSyncGateway:
    """Serves the given changes feeds one per call, then repeats the last one."""

    def __init__(self, name: str, *feeds: Feed) -> None:
        self.__name = name
        self.__feeds = list(feeds)
        self.version_types: list[str] = []

    async def get_changes(
        self, db_name: str, scope: str, collection: str, version_type: str, log_response: bool
    ) -> ChangesResponse:
        self.version_types.append(version_type)
        feed = self.__feeds.pop(0) if len(self.__feeds) > 1 else self.__feeds[0]
        results = [
            {"seq": seq, "id": doc_id, "changes": [{"cv": cv}], "deleted": deleted}
            for seq, (doc_id, cv, deleted) in enumerate(feed, start=1)
        ]
        return ChangesResponse({"results": results, "last_seq": str(len(feed))})

    def __str__(self) -> str:
        return f"SyncGateway {self.__name}"


class FakeDatabase:
    """A local database that holds the given live documents."""

    def __init__(self, revs: dict[str, str]) -> None:
        self.__revs = revs

    async def get_all_documents(self, *collections: str) -> dict[str, list[AllDocumentsEntry]]:
        return {c: [local(doc_id, rev) for doc_id, rev in self.__revs.items()] for c in collections}


def sync_gateway(name: str, *feeds: Feed) -> SyncGateway:
    return cast(SyncGateway, FakeSyncGateway(name, *feeds))


def database(revs: dict[str, str]) -> Database:
    return cast(Database, FakeDatabase(revs))


class TestCompareDocs:
    def test_compare_doc_results_match(self) -> None:
        compare_doc_results([local("doc_1", "1-abc")], [remote("doc_1", "1-abc")], ReplicatorType.PUSH_AND_PULL)

    def test_compare_doc_results_mismatch(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_results(
                [local("doc_1", "1-abc")],
                [remote("doc_1", "2-def")],
                ReplicatorType.PUSH_AND_PULL,
            )

        assert str(e.value).startswith("Doc 'doc_1' mismatched revid"), str(e.value)

    def test_compare_doc_results_p2p_match(self) -> None:
        compare_doc_results_p2p([local("doc_1", "1-abc")], [local("doc_1", "1-abc")])

    def test_compare_doc_results_p2p_local_source(self) -> None:
        compare_doc_results_p2p([local("doc_1", "18084339b4320000@*")], [local("doc_1", "18084339b4320000@AbCdEf")])

    def test_compare_doc_results_p2p_mismatched_revision(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_results_p2p([local("doc_1", "1-abc")], [local("doc_1", "2-def")])

        assert "{'doc_1': '1-abc'} != {'doc_1': '2-def'}" in str(e.value), str(e.value)

    def test_compare_doc_results_p2p_missing_remotely(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_results_p2p([local("doc_1", "1-abc"), local("doc_2", "1-abc")], [local("doc_2", "1-abc")])

        assert "Left contains 1 more item" in str(e.value), str(e.value)
        assert "doc_2" not in str(e.value), str(e.value)

    def test_compare_doc_results_p2p_missing_locally(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_results_p2p([], [local("doc_1", "1-abc")])

        assert "Right contains 1 more item" in str(e.value), str(e.value)

    def test_compare_doc_ids_match(self) -> None:
        compare_doc_ids([local("doc_1", "1-abc")], [remote("doc_1", "2-def")])

    def test_compare_doc_ids_missing_remotely(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_ids([local("doc_1", "1-abc")], [])

        assert "Extra items in the left set" in str(e.value), str(e.value)

    def test_compare_doc_ids_missing_locally(self) -> None:
        with pytest.raises(AssertionError) as e:
            compare_doc_ids([], [remote("doc_1", "1-abc")])

        assert "Extra items in the right set" in str(e.value), str(e.value)


class TestSameCv:
    def test_exact_match(self) -> None:
        assert _same_cv("18084339b4320000@AbCdEf", "18084339b4320000@AbCdEf")

    def test_different_source(self) -> None:
        assert not _same_cv("18084339b4320000@AbCdEf", "18084339b4320000@GhIjKl")

    def test_local_source_matches_timestamp(self) -> None:
        assert _same_cv("18084339b4320000@*", "18084339b4320000@AbCdEf")

    def test_local_source_different_timestamp(self) -> None:
        assert not _same_cv("18084339b4320000@*", "18084339b4330000@AbCdEf")

    def test_no_remote_cv(self) -> None:
        assert not _same_cv("18084339b4320000@AbCdEf", None)


class TestWaitForConvergingCvs:
    @pytest.mark.asyncio
    async def test_same_docs_and_tombstones(self) -> None:
        feed = [("a", "1@x", False), ("b", "2@x", True)]
        sg1, sg2 = sync_gateway("sg1", feed), sync_gateway("sg2", list(reversed(feed)))

        await wait_for_converging_cvs(sg1, sg2, "db", timeout=NO_RETRY)

        assert cast(FakeSyncGateway, sg1).version_types == ["cv"]

    @pytest.mark.asyncio
    async def test_waits_until_feeds_converge(self) -> None:
        sg1 = sync_gateway("sg1", [("a", "1@x", False)], [("a", "2@y", False)])
        sg2 = sync_gateway("sg2", [("a", "2@y", False)])

        await wait_for_converging_cvs(sg1, sg2, "db", timeout=timedelta(seconds=5))

        assert len(cast(FakeSyncGateway, sg1).version_types) == 2

    @pytest.mark.asyncio
    async def test_reports_differing_docs(self) -> None:
        sg1 = sync_gateway("sg1", [("a", "1@x", False), ("b", "2@x", True), ("c", "3@x", False)])
        sg2 = sync_gateway("sg2", [("a", "1@x", False), ("b", "2@x", False), ("d", "4@y", False)])

        with pytest.raises(TimeoutError) as e:
            await wait_for_converging_cvs(sg1, sg2, "db", timeout=NO_RETRY)

        message = str(e.value)
        assert "3 of 4 docs differ between SyncGateway sg1 and SyncGateway sg2 in db._default._default" in message
        assert "b (2@x (deleted) vs 2@x)" in message, message
        assert "c (3@x vs missing)" in message, message
        assert "d (missing vs 4@y)" in message, message
        assert "a (" not in message, message


class TestWaitForMatchingCvs:
    @pytest.mark.asyncio
    async def test_matches_live_docs(self) -> None:
        sg = sync_gateway("sg", [("a", "1@x", False), ("b", "2@y", False), ("c", "3@x", True)])
        db = database({"a": "1@x", "b": "2@*"})

        await wait_for_matching_cvs(db, sg, "db", timeout=NO_RETRY)

        assert cast(FakeSyncGateway, sg).version_types == ["cv"]

    @pytest.mark.asyncio
    async def test_waits_until_remote_matches(self) -> None:
        sg = sync_gateway("sg", [("a", "1@x", False)], [("a", "2@x", False)])
        db = database({"a": "2@x"})

        await wait_for_matching_cvs(db, sg, "db", timeout=timedelta(seconds=5))

    @pytest.mark.asyncio
    async def test_reports_differing_docs(self) -> None:
        sg = sync_gateway("sg", [("a", "1@x", False), ("b", "2@x", False), ("c", "3@x", True), ("d", "4@x", False)])
        db = database({"a": "1@x", "b": "2@y", "c": "3@x", "e": "5@*"})

        with pytest.raises(TimeoutError) as e:
            await wait_for_matching_cvs(db, sg, "db", timeout=NO_RETRY)

        message = str(e.value)
        assert "4 of 5 docs differ between local and SyncGateway sg in db._default._default" in message, message
        assert "b (local 2@y vs remote 2@x)" in message, message
        assert "c (local 3@x vs remote missing)" in message, message
        assert "d (local missing vs remote 4@x)" in message, message
        assert "e (local 5@* vs remote missing)" in message, message
