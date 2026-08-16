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

from dataclasses import dataclass

from gramps_live_api.core import schema
from gramps_live_api.core.schema import ObjectRef, Operation, Unrecorded


@dataclass(frozen=True, slots=True)
class _Declaring(Operation):
    """An operation class the registry does not name, declaring one of each.

    Written here rather than imported, following the precedent in
    ``test_schema_validation.py``: the registry is closed, so a class carrying
    a declaration nothing registered carries yet can only come from a test.

    ⚠️ **Module level rather than inside a test, and that is required rather
    than tidy.** ``get_type_hints`` resolves a string annotation against the
    defining module's globals, so a class defined inside a function cannot
    resolve the names it was written with.
    """

    given: str | Unrecorded = ""
    surname: str = ""
    target: ObjectRef | None = None


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


def test_absence_is_read_off_the_declaration() -> None:
    # The derivation extended, not restated: the same question reference_fields
    # asks of the same declaration, with the other type in it.
    assert schema.absence_fields(_Declaring) == ("given",)


def test_a_field_that_cannot_hold_the_marker_is_not_an_absence_field() -> None:
    # Both controls in one place, because each fails differently. A plain str
    # field would be found by a derivation reading the field NAMES; a reference
    # root would be found by one reading "this field may be missing" -- which is
    # the confusion the marker exists to end, since Optional here already means
    # a reference root rather than a part the record does not give.
    found = schema.absence_fields(_Declaring)

    assert "surname" not in found, "a plain str field admits no marker"
    assert "target" not in found, (
        "an optional reference is a reference root, not a part the record omits"
    )


def test_absence_and_reference_are_disjoint_on_the_same_class() -> None:
    # Two derivations over one declaration, asked to disagree about every field.
    # A field in both would mean the two wire directions each claim it.
    absences = set(schema.absence_fields(_Declaring))
    references = set(schema.reference_fields(_Declaring))

    assert not absences & references, (
        f"a field cannot be both a reference and an absence; both claim {absences & references}"
    )


def test_a_class_declaring_no_marker_has_no_absence_field() -> None:
    # The registry as it stands, which is what keeps the round-trip property
    # unchanged for every type that exists today.
    for spec in schema.REGISTRY.values():
        assert schema.absence_fields(spec.cls) == (), (
            f"{spec.type_name} declares the marker, which no registered type does yet"
        )
