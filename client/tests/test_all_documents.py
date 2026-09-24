"""An _all_docs row carries the document exactly as Sync Gateway stored it, metadata included,
so feeding one straight back as an update body is the mistake this covers.
"""

import pytest
from cbltest.api.syncgateway import AllDocumentsResponse, DocumentUpdateEntry


def response(doc: dict | None) -> AllDocumentsResponse:
    row: dict = {"key": "doc1", "id": "doc1", "value": {"rev": "1-abc", "cv": "1@src"}}
    if doc is not None:
        row["doc"] = doc
    return AllDocumentsResponse({"total_rows": 1, "rows": [row]})


STORED = {"_id": "doc1", "_rev": "1-abc", "_cv": "1@src", "type": "note", "index": 0}


def test_doc_keeps_the_body_sync_gateway_returned() -> None:
    assert response(STORED).rows[0].doc == STORED


def test_body_drops_the_fields_an_update_sets_for_itself() -> None:
    assert response(STORED).rows[0].body == {"type": "note", "index": 0}


def test_body_is_none_without_include_docs() -> None:
    """A row fetched without include_docs has no body to offer, rather than an empty one."""
    assert response(None).rows[0].body is None


def test_body_can_be_updated_but_doc_cannot() -> None:
    row = response(STORED).rows[0]

    assert row.body is not None
    DocumentUpdateEntry(row.id, row.revid, body={**row.body, "message": "updated"})

    assert row.doc is not None
    with pytest.raises(AssertionError):
        DocumentUpdateEntry(row.id, row.revid, body={**row.doc, "message": "updated"})
