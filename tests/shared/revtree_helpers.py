import re
from typing import cast

SYNC_XATTR = "_sync"
XATTRS_KEY = "_xattrs"


def rev_generation(rev_id: str) -> int:
    """
    Returns the generation of a rev tree ID.  Sync Gateway only requires '<int>-<anything>'
    with the integer >= 1, so anything after the first hyphen is opaque.
    """
    generation, _, _ = rev_id.partition("-")
    return int(generation)


def parse_rev_history(revs: str) -> list[str]:
    """
    Splits the `_revs` string a test server returns for a document into revision IDs, newest
    first.  Platforms separate entries with either a comma or a semicolon.
    """
    return [part.strip() for part in revs.replace(";", ",").split(",") if part.strip()]


def rev_tree_ids(history: list[str]) -> list[str]:
    """
    Keeps only the rev tree IDs from a client's revision history.  A post-upgrade client reports
    version vector entries such as '17f4ed7b51a50000@MlAW1NbbT8KcTRO8oPnpgw' alongside, or instead
    of, 'N-digest' rev tree IDs, and those carry no generation.
    """
    return [rev for rev in history if re.match(r"^\d+-", rev)]


def sync_metadata(raw_document: dict) -> dict:
    """
    Extracts the `_sync` xattr from the payload of `GET /{db}/_raw/{doc}`.

    `_raw` is used rather than the SDK because Sync Gateway repairs an invalid rev tree whenever
    it loads a document, so reading one through any other endpoint would repair the very thing
    under observation.  `_raw` reads the bucket directly and leaves the document alone.
    """
    xattrs = raw_document.get(XATTRS_KEY)
    assert isinstance(xattrs, dict), f"Raw document has no '{XATTRS_KEY}': {sorted(raw_document)}"
    metadata = xattrs.get(SYNC_XATTR)
    assert isinstance(metadata, dict), f"Raw document has no '{SYNC_XATTR}' xattr, only {sorted(xattrs)}"
    return cast(dict, metadata)


def document_body(raw_document: dict) -> dict:
    """Returns just the body from the payload of `GET /{db}/_raw/{doc}`, without the xattrs."""
    return {key: value for key, value in raw_document.items() if key != XATTRS_KEY}


def current_rev(sync_metadata: dict) -> str:
    """
    Returns the winning rev tree ID from a `_sync` xattr.  A pre-upgrade document stores `rev`
    as a bare string; once it has an HLV the field becomes an object and the rev tree ID moves
    to its nested `rev` key.
    """
    rev = sync_metadata["rev"]
    if isinstance(rev, str):
        return rev
    return cast(str, cast(dict, rev)["rev"])


def walk_rev_tree(sync_metadata: dict) -> list[str]:
    """
    Walks a `_sync` xattr's rev tree from the winning revision back to its root, returning the
    branch root first.  `history.parents[i]` is an index into `history.revs`, and -1 is a root.
    """
    history = cast(dict, sync_metadata["history"])
    revs = cast(list[str], history["revs"])
    parents = cast(list[int], history["parents"])
    assert len(revs) == len(parents), f"Malformed rev tree: {len(revs)} revs but {len(parents)} parents"

    winner = current_rev(sync_metadata)
    assert winner in revs, f"Winning revision '{winner}' is missing from the rev tree: {revs}"

    index = revs.index(winner)
    branch: list[str] = []
    while index >= 0:
        assert revs[index] not in branch, f"Cycle in rev tree at {revs[index]}: {revs}"
        branch.append(revs[index])
        index = parents[index]

    branch.reverse()
    return branch


def assert_strictly_increasing_generations(branch: list[str]) -> None:
    """
    Asserts every revision in a root-to-leaf branch is at least one generation higher than its
    parent.  This is the TDK analogue of Sync Gateway's
    `RequireStrictlyIncreasingRevTreeGenerations`, and the property CBG-5713 broke.
    """
    generations = [rev_generation(rev) for rev in branch]
    for i in range(1, len(branch)):
        assert generations[i] > generations[i - 1], (
            f"Revision '{branch[i]}' is not a higher generation than its parent '{branch[i - 1]}' "
            f"(branch root -> leaf: {branch})"
        )


def find_repeating_generation(branch: list[str]) -> tuple[str, str] | None:
    """
    Returns the first (parent, child) pair in a root-to-leaf branch whose generations do not
    increase, or None if the branch is well formed.
    """
    for i in range(1, len(branch)):
        if rev_generation(branch[i]) <= rev_generation(branch[i - 1]):
            return branch[i - 1], branch[i]
    return None
