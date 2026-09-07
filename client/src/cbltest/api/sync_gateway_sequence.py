"""Parsing of the sequences that Sync Gateway reports in its changes feed."""

import re


def parse_sequence_id(seq: int | str) -> int:
    """
    Parses a sequence, in whatever form Sync Gateway reported it, into the integer sequence that
    was assigned to the revision.

    A simple sequence arrives as a number, but one that is backfilled or triggered by a channel
    grant arrives as a colon delimited string: "TriggeredBy:Seq", or "LowSeq:TriggeredBy:Seq"
    where TriggeredBy may be empty (e.g. "5::10").  The revision's own sequence is the final
    component of every form; the components before it describe how far along the changes feed is
    in its backfill and say nothing about the revision.

    This follows parseIntegerSequenceID in Sync Gateway's db/sequence_id.go, with one deliberate
    difference: Go reads an empty string as sequence 0 (the zero value of a SequenceID), whereas
    a changes feed entry carrying no usable sequence is a bug worth surfacing here, so it raises.

    :param seq: the sequence exactly as Sync Gateway reported it
    :raises ValueError: if the sequence is not in one of the forms above
    """
    if isinstance(seq, int):
        if seq < 0:
            raise ValueError(f"Invalid sequence {seq!r}: a sequence is a uint64, so it cannot be negative")

        return seq

    # What each component means, by how many of them a sequence has, so a rejection can name the
    # component that was bad
    component_names = {
        1: ("Seq",),
        2: ("TriggeredBy", "Seq"),
        3: ("LowSeq", "TriggeredBy", "Seq"),
    }

    components = seq.split(":")
    names = component_names.get(len(components))
    if names is None:
        raise ValueError(
            f"Invalid sequence {seq!r}: expected Seq, TriggeredBy:Seq, or LowSeq:TriggeredBy:Seq, "
            f"but got {len(components)} colon separated components"
        )

    # TriggeredBy, the middle component of the three component form, is the only one allowed to
    # be empty, and Sync Gateway reads it as 0 when it is
    if len(components) == 3 and components[1] == "":
        components[1] = "0"

    # Sync Gateway writes every component with strconv.FormatUint and reads it back with
    # strconv.ParseUint, so a component is digits and nothing else: no sign, no whitespace,
    # no decimal point
    component_pattern = re.compile(r"[0-9]+")
    for name, component in zip(names, components, strict=True):
        if not component_pattern.fullmatch(component):
            reason = "is empty" if component == "" else f"{component!r} is not an unsigned decimal number"
            raise ValueError(f"Invalid sequence {seq!r}: the {name} component {reason}")

    return int(components[-1])
