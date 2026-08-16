"""The not-recorded marker: what it is, how it is derived, how it spells itself.

Everything about ``Unrecorded`` in one place, so the evidence for #40's criteria
is countable.

⚠️ **The count belongs to the criterion, not to this file.** The criterion in
``docs/phase1-core-schema.spec.md`` names the tests that carry it by name, and
this file's total will move later for reasons #40 has nothing to do with. A
count of a file read as a count of a criterion is a number that goes stale with
nothing announcing it.
"""

from __future__ import annotations

from gramps_live_api.core import schema


def test_the_marker_has_exactly_one_member() -> None:
    # One member, because "the record does not say" and "the person bore none"
    # are deliberately not distinguished -- see the reason recorded where the
    # enum is defined. A second member arriving is a ruling, not an edit.
    members = [member.name for member in schema.Unrecorded]

    assert members == ["NOT_IN_THE_RECORD"], (
        f"the marker is one member and a second one is a ruling; got {members}"
    )


def test_the_member_spells_itself_for_the_wire() -> None:
    assert schema.Unrecorded.NOT_IN_THE_RECORD.value == "not_in_the_record"


def test_the_module_offers_the_member_and_its_wire_key() -> None:
    # Both are part of the vocabulary a caller reads: the member is the value an
    # operation carries, the key is how a payload spells it.
    assert schema.UNRECORDED is schema.Unrecorded.NOT_IN_THE_RECORD
    assert schema.UNRECORDED_KEY == "unrecorded"
