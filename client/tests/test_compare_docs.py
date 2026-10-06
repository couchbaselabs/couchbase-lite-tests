import pytest
from cbltest.api.database import AllDocumentsEntry
from cbltest.api.replicator_types import ReplicatorType
from cbltest.api.syncgateway import AllDocumentsResponseRow
from cbltest.api.test_functions import (
    compare_doc_ids,
    compare_doc_results,
    compare_doc_results_p2p,
)
from cbltest.response_types import PostGetAllDocumentsEntry


def local(id: str, rev: str) -> AllDocumentsEntry:
    return AllDocumentsEntry(PostGetAllDocumentsEntry({"id": id, "rev": rev}))


def remote(id: str, rev: str) -> AllDocumentsResponseRow:
    return AllDocumentsResponseRow(id, id, rev, None)


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
