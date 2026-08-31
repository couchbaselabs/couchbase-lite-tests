"""Unit tests for the sequences Sync Gateway reports: parse_sequence_id, which update_document
uses to turn a changes feed entry's sequence into the one it hands to RemoteDocument, and the
feed level ChangesResponse.last_seq.

The forms under test are the ones Sync Gateway's own parser accepts (parseIntegerSequenceID in
db/sequence_id.go): Seq, TriggeredBy:Seq, and LowSeq:TriggeredBy:Seq."""

import pytest
from cbltest.api.sync_gateway_sequence import parse_sequence_id
from cbltest.api.syncgateway import ChangesResponse


class TestParseSequenceId:
    """Tests for parse_sequence_id()"""

    @pytest.mark.parametrize(
        "seq, expected",
        [
            # Seq: a simple sequence, which MarshalJSON sends as a bare JSON number because
            # TriggeredBy and LowSeq are both zero
            (5, 5),
            (0, 0),
            (18446744073709551615, 18446744073709551615),  # MaxSequenceID, i.e. uint64 max
            # The same values as strings.  Sync Gateway sends the simple form as a number, but
            # its own UnmarshalJSON takes either, so this does too.
            ("5", 5),
            ("0", 0),
            ("18446744073709551615", 18446744073709551615),
            # TriggeredBy:Seq: a backfill with no low sequence to report.  Sync Gateway only
            # emits this while Seq < TriggeredBy, which is what makes the backfill active.
            ("10:3", 3),
            ("2:1", 1),
            # LowSeq:TriggeredBy:Seq: a backfill with a low sequence behind the trigger
            ("1:10:3", 3),
            # LowSeq::Seq: a low sequence with no backfill in flight, so TriggeredBy is empty
            ("5::10", 10),
            # The ordering between components is Sync Gateway's business, not the parser's:
            # these are shapes it would never emit, and they still parse
            ("2:5", 5),
            ("0::7", 7),
        ],
    )
    def test_valid(self, seq: int | str, expected: int) -> None:
        assert parse_sequence_id(seq) == expected

    @pytest.mark.parametrize(
        "seq, reason",
        [
            # Empty components: only TriggeredBy of the three component form may be empty, and
            # the rejection names whichever component came up empty
            ("", "the Seq component is empty"),
            (":", "the TriggeredBy component is empty"),
            (":5", "the TriggeredBy component is empty"),
            ("5:", "the Seq component is empty"),
            ("::5", "the LowSeq component is empty"),
            ("1::", "the Seq component is empty"),
            # More components than any sequence form has
            ("1:2:3:4", "got 4 colon separated components"),
            # Forms strconv.ParseUint rejects, so Sync Gateway would never send them
            ("-5", "the Seq component '-5' is not an unsigned decimal number"),
            ("+5", "the Seq component '+5' is not an unsigned decimal number"),
            (" 5", "the Seq component ' 5' is not an unsigned decimal number"),
            ("5.0", "the Seq component '5.0' is not an unsigned decimal number"),
            ("abc", "the Seq component 'abc' is not an unsigned decimal number"),
            ("2:abc", "the Seq component 'abc' is not an unsigned decimal number"),
            ("1.5:2:3", "the LowSeq component '1.5' is not an unsigned decimal number"),
            # A number, but not one a uint64 sequence could hold
            (-5, "cannot be negative"),
        ],
    )
    def test_invalid(self, seq: int | str, reason: str) -> None:
        """Every rejection says which component was bad and why, since the sequence alone does
        not tell whoever reads the failure what Sync Gateway was expected to send."""
        with pytest.raises(ValueError) as exc_info:
            parse_sequence_id(seq)

        assert reason in str(exc_info.value)
        assert repr(seq) in str(exc_info.value)


class TestChangesResponseLastSeq:
    """last_seq is the sequence to resume the feed from.  sendSimpleChanges writes the changes
    envelope by hand and always closes it with a quoted last_seq, so it is a string that is
    always there, even when the feed returned nothing."""

    def test_last_seq_is_the_reported_string(self) -> None:
        response = ChangesResponse({"results": [], "last_seq": "12"})

        assert response.last_seq == "12"

    def test_a_compound_last_seq_keeps_its_form(self) -> None:
        """A compound last_seq has to survive intact, since it goes back out as `since`."""
        assert ChangesResponse({"results": [], "last_seq": "5::10"}).last_seq == "5::10"

    def test_a_missing_last_seq_is_rejected(self) -> None:
        with pytest.raises(AssertionError):
            ChangesResponse({"results": []})

    def test_a_numeric_last_seq_is_rejected(self) -> None:
        with pytest.raises(AssertionError):
            ChangesResponse({"results": [], "last_seq": 12})
