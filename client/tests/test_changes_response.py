"""Unit tests for ChangesResponseEntry, which flattens a changes feed entry's `changes`
array into a list of version strings.

A change carries a rev ID or a CV depending on the `version_type` the feed was asked for,
never both, so this is the one place in the Sync Gateway API where either key can be the
absent one. Elsewhere a document body always has a rev and may additionally have a cv.

The sample bodies are verbatim responses from Sync Gateway 4.2 on rosmar, for
GET /names._default._default/_changes?version_type={rev,cv}&limit=2."""

import pytest
from cbltest.api.syncgateway import ChangesResponse, ChangesResponseEntry

REV_FEED = {
    "results": [
        {"seq": 3, "id": "name_101", "changes": [{"rev": "1-081ac1c1a7eae0b22e8d7006e1f09f24"}]},
        {"seq": 4, "id": "name_102", "changes": [{"rev": "1-ecf34dc1dc4dbb1cdb526fee1e640ead"}]},
    ],
    "last_seq": "4",
}

CV_FEED = {
    "results": [
        {"seq": 3, "id": "name_101", "changes": [{"cv": "18d233413ba60000@TeiwvDjMUdPDkNq/vXC5RQ"}]},
        {"seq": 4, "id": "name_102", "changes": [{"cv": "18d233413baa0000@TeiwvDjMUdPDkNq/vXC5RQ"}]},
    ],
    "last_seq": "4",
}


class TestChangesResponseEntry:
    """Tests for ChangesResponseEntry's rev/cv flattening"""

    def test_rev_feed(self) -> None:
        response = ChangesResponse(REV_FEED)
        assert [e.id for e in response.results] == ["name_101", "name_102"]
        assert [e.seq for e in response.results] == [3, 4]
        assert [e.changes for e in response.results] == [
            ["1-081ac1c1a7eae0b22e8d7006e1f09f24"],
            ["1-ecf34dc1dc4dbb1cdb526fee1e640ead"],
        ]

    def test_cv_feed(self) -> None:
        response = ChangesResponse(CV_FEED)
        assert [e.id for e in response.results] == ["name_101", "name_102"]
        assert [e.changes for e in response.results] == [
            ["18d233413ba60000@TeiwvDjMUdPDkNq/vXC5RQ"],
            ["18d233413baa0000@TeiwvDjMUdPDkNq/vXC5RQ"],
        ]

    def test_rev_wins_when_both_present(self) -> None:
        """Sync Gateway sends one or the other, but a rev is the authoritative choice if both arrive."""
        entry = ChangesResponseEntry({"seq": 1, "id": "doc", "changes": [{"rev": "1-abc", "cv": "1@src"}]})
        assert entry.changes == ["1-abc"]

    def test_conflict_lists_every_change(self) -> None:
        entry = ChangesResponseEntry(
            {"seq": 7, "id": "doc", "changes": [{"rev": "2-aaa"}, {"rev": "2-bbb"}]},
        )
        assert entry.changes == ["2-aaa", "2-bbb"]

    def test_deleted_and_compound_seq(self) -> None:
        entry = ChangesResponseEntry({"seq": "2:5", "id": "doc", "changes": [{"rev": "3-abc"}], "deleted": True})
        assert entry.seq == "2:5"
        assert entry.deleted is True

    def test_no_changes_array(self) -> None:
        entry = ChangesResponseEntry({"seq": 1, "id": "doc"})
        assert entry.changes == []
        assert entry.deleted is False

    def test_neither_rev_nor_cv_raises(self) -> None:
        """The silent failure this guards against: a None flowing into a list[str] and only
        surfacing later as a mismatched revision comparison."""
        with pytest.raises(AssertionError, match="neither a rev nor a cv"):
            ChangesResponseEntry({"seq": 1, "id": "name_101", "changes": [{}]})

    def test_non_string_rev_raises(self) -> None:
        with pytest.raises(AssertionError, match="neither a rev nor a cv"):
            ChangesResponseEntry({"seq": 1, "id": "name_101", "changes": [{"rev": None}]})
