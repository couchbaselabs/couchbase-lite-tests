from json import dumps
from typing import Any, cast

from cbltest.api.error import CblRemoteBadResponseError

# Bulk operations can span thousands of documents, so only this many failures go in the message.
_MAX_REPORTED_BULK_ERRORS = 10


def analyze_bulk_docs_response(response: Any, error_type: type[CblRemoteBadResponseError]) -> list:
    """
    Returns the per-document results of a _bulk_docs response, raising if any document failed.

    Sync Gateway and Edge Server both answer 201 even when individual documents fail, so the
    response body is the only place those failures appear.

    :param response: The parsed body of the _bulk_docs response
    :param error_type: The exception type to raise, identifying the server that was called
    """
    assert isinstance(response, list), "Invalid bulk docs response (not a list)"
    results = cast(list, response)
    for r in results:
        assert isinstance(r, dict), "Invalid item inside bulk docs response list (not an object)"

    errors = [cast(dict, r) for r in results if "error" in cast(dict, r)]
    if errors:
        shown = ", ".join(f"'{e.get('id')}' ({e['error']})" for e in errors[:_MAX_REPORTED_BULK_ERRORS])
        if len(errors) > _MAX_REPORTED_BULK_ERRORS:
            shown += f", and {len(errors) - _MAX_REPORTED_BULK_ERRORS} more"
        raise error_type(
            errors[0].get("status", 500),
            f"Bulk docs operation failed for {len(errors)} of {len(results)} documents: {shown}",
            body=dumps(errors),
        )

    return results
