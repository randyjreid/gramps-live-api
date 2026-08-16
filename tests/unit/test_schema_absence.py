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

import pytest

from gramps_live_api.core import schema
from gramps_live_api.core.schema import UNRECORDED, UNRECORDED_KEY, ObjectRef, Operation, Unrecorded
from tests.fixtures.operations import EXAMPLES, carrying, payload_with, resolve


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


# ---------------------------------------------------------------------------
# The wire spelling, in both directions
#
# Testing module privates follows the established precedent here: the seam is
# named so it can be tested directly, because its composition inside from_dict
# needs a registered type declaring the marker and there is not one yet.
# ---------------------------------------------------------------------------


def test_the_canonical_spelling_comes_back_as_the_member() -> None:
    assert schema._unrecorded_from_wire({UNRECORDED_KEY: "not_in_the_record"}) is UNRECORDED


@pytest.mark.parametrize("member", list(Unrecorded), ids=lambda member: member.name)
def test_every_member_survives_both_conversions(member: Unrecorded) -> None:
    # Quantified over the enum rather than written for the one member there is,
    # so a second member is covered before it exists -- which is the whole claim
    # the single-member deferral rests on.
    assert schema._unrecorded_from_wire(schema._to_wire(member)) is member


_NOT_THE_SPELLING: dict[str, object] = {
    "an empty mapping": {},
    "a mapping under a key nobody spells": {"not_recorded": "not_in_the_record"},
    "the key with a member nobody declared": {UNRECORDED_KEY: "typo"},
    "the key carrying a value that is not text": {UNRECORDED_KEY: []},
    "the key alongside something else": {UNRECORDED_KEY: "not_in_the_record", "extra": 1},
    "a bare string": "not_in_the_record",
    "a number": 123,
    "a null": None,
}


@pytest.mark.parametrize("description", sorted(_NOT_THE_SPELLING))
def test_anything_that_is_not_the_spelling_is_not_a_marker(description: str) -> None:
    # None rather than a raise, and that is the module's line rather than a
    # softness: a value fault must survive deserialisation so validate can see
    # it and report a field path. A deserialiser refusing this would be the
    # second-validator shape with no vocabulary for saying where the fault is.
    assert schema._unrecorded_from_wire(_NOT_THE_SPELLING[description]) is None, (
        f"{description} is not the marker's spelling and must not be read as one"
    )


def test_an_unhashable_value_under_the_key_does_not_raise() -> None:
    # ⚠️ Not defensive padding, and the reason it is a test of its own is so
    # nobody deletes the isinstance check ahead of the lookup as redundant.
    # dict.get raises TypeError on an unhashable key, and the wire can carry a
    # list. Without the check that TypeError comes out of the transport -- no
    # verdict, no field path -- which is the failure the reference choke point
    # already records having been made once.
    try:
        marker = schema._unrecorded_from_wire({UNRECORDED_KEY: []})
    except TypeError as raised:  # pragma: no cover - the defect this test is about
        pytest.fail(f"an unhashable wire value escaped the transport as a TypeError: {raised}")

    assert marker is None


# ---------------------------------------------------------------------------
# A marker where nothing declares one
#
# The stop condition that did not fire, asserted rather than argued: no new
# PHASE_1 rule is needed, because machinery already on that side judges the
# marker at any field whose declaration does not admit it.
#
# ⚠️ **The REFERENCE-LEAF half of this matrix is a FENCE, not evidence** -- the
# same distinction this suite's sibling draws about its sweep over the canonical
# examples. Those nine paths are green both before and after the change that made
# _to_wire recurse, because validate always reported FIELD_WRONG_TYPE there and
# reads the object rather than the payload. What the transport could not do was
# CARRY the operation to it. So this asserts a verdict that already existed, at a
# depth nothing had asked it at; the evidence for the change is in
# test_schema_wire_shape.py, which was red.
# ---------------------------------------------------------------------------


def _undeclaring_paths() -> list[tuple[str, str]]:
    """Every (type, path) where a marker is judged rather than structurally refused.

    Reference **roots** are excluded deliberately: a mapping at one is refused by
    name at deserialisation, which is a structural fault on a different surface
    and already covered. Restricting to the paths where both routes reach
    ``validate`` is what makes the two halves comparable at all.

    ⚠️ **That reason is about the ROOT and does not reach the LEAVES**, which is
    why no clause excludes a dotted path. A mapping at ``target`` is how the wire
    spells an object; a mapping at ``target.handle`` is a value where a ``str``
    is declared, and both routes reach ``validate`` for it exactly as they do at
    the top level. The clause that used to drop every dotted path gave this
    matrix the same one-depth shape the wire-shape matrix had -- and the finding
    that deepened that one was stated as *"never reaches validate for its
    FIELD_WRONG_TYPE verdict"*, which is the claim right here.

    ⚠️ **Residual, recorded rather than pre-hardened:** ``absence_fields`` answers
    at the top level, so the exclusion below does not consult an ``ObjectRef``
    leaf's declaration. Nothing declares the marker at one today. The day one
    does, this test's expectation is wrong for that path -- and it FAILS, loudly,
    rather than passing quietly, because the marker would then be well-formed
    there and no ``FIELD_WRONG_TYPE`` would be reported.
    """
    return [
        (type_name, declared)
        for type_name in sorted(EXAMPLES)
        for declared in schema.required_paths(type(EXAMPLES[type_name]))
        if declared not in schema.reference_fields(type(EXAMPLES[type_name]))
        and declared not in schema.absence_fields(type(EXAMPLES[type_name]))
    ]


UNDECLARING_PATHS = _undeclaring_paths()


def test_the_generated_undeclaring_matrix_is_not_empty() -> None:
    assert UNDECLARING_PATHS, "no field was reached; the two cases below are vacuous"


@pytest.mark.parametrize(("type_name", "path"), UNDECLARING_PATHS)
def test_a_marker_where_nothing_declares_one_is_judged_at_that_path(
    type_name: str, path: str
) -> None:
    built = schema.validate(carrying(EXAMPLES[type_name], path, UNRECORDED))
    from_wire = schema.validate(
        schema.from_dict(payload_with(type_name, path, {UNRECORDED_KEY: "not_in_the_record"}))
    )

    expected = (schema.RuleId.FIELD_WRONG_TYPE, path)
    for route, result in (("built as an object", built), ("met from the wire", from_wire)):
        reported = {(violation.rule, violation.field_path) for violation in result.violations}
        assert expected in reported, (
            f"a marker at {path}, which does not declare one, was not reported as "
            f"{expected[0].name} there when {route}; got {sorted(reported)}"
        )


@pytest.mark.parametrize(("type_name", "path"), UNDECLARING_PATHS)
def test_the_two_routes_disagree_only_about_what_arrived(type_name: str, path: str) -> None:
    # ⚠️ **The consequence, asserted rather than smoothed over.** A marker at a
    # field that does not declare it serialises to the mapping and comes back a
    # plain dict, because from_dict reads the DECLARATION and this field's does
    # not admit the marker. So that invalid operation is not round-trip
    # identical -- and what matters is that it is judged, at its own path, by
    # both routes. The messages differ because each names the type that actually
    # arrived, which is the one thing a violation may say about a value.
    built = schema.validate(carrying(EXAMPLES[type_name], path, UNRECORDED))
    from_wire = schema.validate(
        schema.from_dict(payload_with(type_name, path, {UNRECORDED_KEY: "not_in_the_record"}))
    )

    assert {(violation.rule, violation.field_path) for violation in built.violations} == {
        (violation.rule, violation.field_path) for violation in from_wire.violations
    }

    def _said_at(result: schema.WellFormedResult) -> str:
        return next(
            violation.message for violation in result.violations if violation.field_path == path
        )

    assert Unrecorded.__name__ in _said_at(built), (
        f"the object route met the marker itself at {path}; got {_said_at(built)}"
    )
    assert dict.__name__ in _said_at(from_wire), (
        f"the wire route met the mapping the marker spells at {path}, because this "
        f"field's declaration does not admit the marker; got {_said_at(from_wire)}"
    )


# ---------------------------------------------------------------------------
# The second silent-weakening hazard, and the tripwire that stops it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_no_canonical_example_carries_the_marker(type_name: str) -> None:
    for path in schema.required_paths(type(EXAMPLES[type_name])):
        assert not isinstance(resolve(EXAMPLES[type_name], path), Unrecorded), (
            f"{type_name} carries the marker at {path}. The preview guard builds its "
            "matrix in _split, in test_schema_preview_guard.py, which skips any path "
            "whose example value is not a string -- so a marker here would drop that "
            "field out of the guard matrix with nothing reporting it. Keep the "
            "canonical examples fully recorded; the not-recorded cases belong in the "
            "per-type file."
        )


# ---------------------------------------------------------------------------
# The composition, armed and currently empty
#
# from_dict dispatches on the registry, so the POSITIVE path -- a payload whose
# field declares the marker -- cannot be reached without a registered type that
# declares one. The two halves are covered directly above; only their wiring
# inside from_dict is uncovered, and this is what closes it the day a
# declaration appears.
#
# Two ways to close it now were weighed and rejected. Registering a probe type
# from a fixture works and pytest here is sequential, but the closed-registry
# tests read REGISTRY at run time, so the structural properties would become
# order-dependent -- and a closed registry with order-dependent tests is a worse
# defect than an uncovered wiring seam. Adding a registered operation is the
# application half, which is out of scope and would need a canonical example,
# which is the hazard directly above.
# ---------------------------------------------------------------------------


def _marker_paths() -> list[tuple[str, str]]:
    """Every (type, field) at which a registered type declares the marker."""
    return [
        (type_name, path)
        for type_name in sorted(EXAMPLES)
        for path in schema.absence_fields(type(EXAMPLES[type_name]))
    ]


MARKER_PATHS = _marker_paths()


def test_no_registered_type_declares_the_marker_yet() -> None:
    # ⚠️ **This test fails ON PURPOSE, and its failure is the instruction.**
    #
    # Every other suite here refuses silent vacuity by asserting its matrix is
    # non-empty. This one cannot, because the matrix is empty by design until
    # the reshape lands. So it asserts the emptiness instead and says what that
    # costs -- the honest inverse, and the reason the gap cannot be forgotten.
    assert MARKER_PATHS == [], (
        "the reshape has landed an operation declaring the marker, so the "
        "round-trip below is no longer vacuous. TO FIX: delete this test. It "
        "exists only to stop the empty matrix reading as coverage."
    )


@pytest.mark.parametrize(("type_name", "path"), MARKER_PATHS)
def test_a_declared_marker_round_trips_in_both_directions(type_name: str, path: str) -> None:
    # Derive-do-not-enumerate applied to a set that is currently empty: the day
    # a declaration appears, these cases arrive with nothing here edited. Until
    # then this generates no cases and the test above says so out loud.
    operation = carrying(EXAMPLES[type_name], path, UNRECORDED)
    payload = schema.to_dict(operation)

    assert schema.validate(operation).well_formed, (
        f"{type_name} carrying the marker at {path}, which declares it, is not well-formed"
    )
    assert payload[path] == {UNRECORDED_KEY: UNRECORDED.value}
    assert schema.from_dict(payload) == operation, (
        f"{type_name} did not come back equal carrying the marker at {path}"
    )
    assert schema.to_dict(schema.from_dict(payload)) == payload
