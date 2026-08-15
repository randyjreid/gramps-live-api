"""The identity-side operations: person, place, name, and the family links.

Everything generic is inherited. ``test_schema_registry``, ``test_schema_validation``,
``test_schema_rule_table``, ``test_schema_preview``, ``test_schema_preview_guard``,
``test_schema_serialisation`` and ``test_schema_violation_privacy`` all quantify over
the registry, so widening it covers the new types in those files **without any of them
being edited**. That is the criterion, not a happy accident: a test that must be
modified to admit a new type was restated rather than derived.

So this file holds only what is about *these* operations -- the properties the
generated sweeps cannot state, each named for the criterion it carries.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, carrying, pointing_nowhere

_SIDES = ("FACT_ASSERTING", "NON_FACT")


def _table(side: str) -> object:
    return getattr(schema, side)


def _recorded_rationales() -> dict[str, str]:
    """Every classified type, and the rationale its own side records for it.

    A side that records no rationale at all contributes an empty one rather than
    raising, so the failure below names the types and says what is missing
    instead of dying on a ``TypeError`` from subscripting a set.
    """
    recorded: dict[str, str] = {}
    for side in _SIDES:
        table = _table(side)
        for type_name in table:  # type: ignore[attr-defined]
            recorded[type_name] = table[type_name] if isinstance(table, Mapping) else ""
    return recorded


def test_both_sides_of_the_partition_record_a_rationale_per_type() -> None:
    # The partition proves TOTALITY, not correctness -- a fact-asserting
    # operation can be filed on the exempt side and nothing structural will say
    # so. The recorded rationale is the only thing a reviewer can check a
    # misclassification against, and that argument does not stop at the exempt
    # side: "this asserts a fact" is exactly as losable as "this does not".
    wrong = [side for side in _SIDES if not isinstance(_table(side), Mapping)]

    assert wrong == [], (
        "each side of the provenance partition must map a type name to the "
        "one-line reason it is on that side, because the classification is "
        "recorded PER TYPE and a bare set of names records no reason at all; "
        f"got {wrong} carrying names only"
    )


def _registered(type_name: str) -> schema.OperationSpec:
    spec = schema.REGISTRY.get(type_name)

    assert spec is not None, (
        f"{type_name} is not in the registry, so every structural test #20 "
        "quantifies over the registry silently skips it"
    )
    return spec


def _example(type_name: str) -> schema.Operation:
    operation = EXAMPLES.get(type_name)

    assert operation is not None, (
        f"{type_name} has no canonical example. TO FIX: add one entry to "
        "EXAMPLES in tests/fixtures/operations.py"
    )
    return operation


def test_add_person_asserts_a_fact_and_so_carries_its_evidence() -> None:
    _registered("add_person")

    assert "add_person" in schema.FACT_ASSERTING, (
        "add_person is FACT_ASSERTING. That a person existed is the "
        "archetypal genealogical fact, and a person enters the tree only "
        "because a record attests them -- an individual added on nobody's "
        "authority is the failure mode this project exists to avoid"
    )


_PLACE_AUTHORITY_RULE = "PLACE_NAME_NOT_IN_AUTHORITY"


def _rule_id(name: str) -> schema.RuleId:
    member = schema.RuleId.__members__.get(name)

    assert member is not None, (
        f"{name} is not a rule this module declares, so the boundary says "
        "nothing about the check it names"
    )
    return member


def _rule(name: str) -> schema.Rule:
    identifier = _rule_id(name)
    rows = [rule for rule in schema.RULES if rule.id is identifier]

    assert len(rows) == 1, f"{name} must appear in the frozen table exactly once; got {len(rows)}"
    return rows[0]


def test_add_place_is_exempt_because_its_warrant_is_an_external_authority() -> None:
    _registered("add_place")

    assert "add_place" in schema.NON_FACT, (
        "add_place is NON_FACT. A place is the container a genealogical fact "
        "refers to, not a claim about a person -- and place naming has its OWN "
        "warrant mechanism, the external place authority, which criterion 5 "
        "puts on the PHASE_3 side because checking it needs a database. Giving "
        "it a citation field would warrant it with the wrong instrument, and "
        "would make criteria 4 and 5 tell two stories instead of one"
    )


def test_the_place_authority_rule_is_declared_on_the_phase_3_side() -> None:
    # Criterion 5: DOCUMENTED, not validated. Declaring the rule is what makes
    # the constraint reviewable at all -- an undeclared one is a promise in a
    # docstring, and the whole reason the boundary is a table is that prose has
    # no fixed point.
    rule = _rule(_PLACE_AUTHORITY_RULE)

    assert rule.phase is schema.Phase.PHASE_3, (
        "whether a place name matches an external authority cannot be decided "
        f"without that authority; got {rule.phase.name}"
    )
    assert rule.check is None, (
        "a PHASE_3 rule must not be implemented -- an implemented one is a "
        "database question answered by guessing"
    )


def _place_authority_probe() -> schema.Rule:
    """The external-authority rule, given a check that reports unconditionally.

    One builder, read by the property and by its control, so the two cannot
    drift into asking about different rules -- which would leave the control
    passing for a probe the property never ran.
    """
    identifier = _rule_id(_PLACE_AUTHORITY_RULE)
    return schema.Rule(
        id=identifier,
        phase=schema.Phase.PHASE_3,
        check=lambda operation: (schema.RuleViolation(identifier, "place_name", "probe fired"),),
    )


def test_the_place_authority_rule_cannot_fire_from_validate() -> None:
    # Asked structurally rather than by sampling. Sampling shows only that the
    # rule did not HAPPEN to fire; this gives it a check that reports
    # unconditionally and asks whether the phase filter stops it anyway.
    result = schema._run((*schema.RULES, _place_authority_probe()), _example("add_place"))

    assert result.well_formed, (
        "the external-authority rule reported from validate, so this module "
        f"answered a question that needs a database; got {result.violations}"
    )


def test_the_place_authority_probe_fires_when_its_phase_allows_it() -> None:
    # The control. A probe that is inert proves nothing about the filter above,
    # and an assertion that passes because nothing happened is the shape this
    # repository keeps catching itself in.
    allowed = dataclasses.replace(_place_authority_probe(), phase=schema.Phase.PHASE_1)

    result = schema._run((allowed,), _example("add_place"))

    assert not result.well_formed, "the probe does not fire even when permitted; it proves nothing"


def test_update_name_is_a_sourced_claim_about_a_person_not_a_string_edit() -> None:
    spec = _registered("update_name")

    assert "update_name" in schema.FACT_ASSERTING, (
        "update_name is FACT_ASSERTING. The tempting error is to file it as "
        "NON_FACT because it 'only changes a string' -- which confuses the "
        "MECHANISM, a string edit, with the CONTENT: 'this person was called "
        "X' is an assertion about a person that evidence can support, and a "
        "spelling correction taken from a transcription is warranted by the "
        "record it was read out of. A name variant is precisely where "
        "competing sources disagree, which is the case provenance exists for"
    )
    assert spec.citation_field is not None, (
        "a fact-asserting operation declares the field carrying its "
        "provenance, and for update_name that is where the corrected spelling "
        "was read: a correction on nobody's authority is the failure mode this "
        "project exists to avoid, not a tidy-up"
    )


def test_update_name_records_the_name_of_a_person() -> None:
    # Internal consistency, and it costs nothing to declare: the field metadata
    # says what the reference must point at, and _reference_wrong_type reads
    # that metadata rather than being written per type.
    expects = schema.expected_object_types(_registered("update_name").cls)

    assert expects.get("target") == "person", (
        "a name belongs to a person, so the target says so and REFERENCE_WRONG_TYPE "
        f"reports a reference aimed elsewhere; got {expects.get('target')!r}"
    )


# ---------------------------------------------------------------------------
# The links -- criterion 3, which is the Phase-1/Phase-3 boundary at its
# sharpest.
# ---------------------------------------------------------------------------

_LINK_TYPES = ("link_child_to_family", "link_spouse_to_family")


def _ends_of(type_name: str) -> tuple[str, ...]:
    """The two ends a link joins: its reference fields other than its provenance.

    Derived from the class rather than named here, so a link that grows or
    renames an end is covered by whatever it actually declares. An enumeration
    would keep passing about the ends it used to have.
    """
    spec = _registered(type_name)
    return tuple(name for name in schema.reference_fields(spec.cls) if name != spec.citation_field)


@pytest.mark.parametrize("type_name", _LINK_TYPES)
def test_a_link_joins_exactly_two_ends(type_name: str) -> None:
    # The control for every sweep below. Each loops over the ends, and a loop
    # over an empty or one-item tuple passes while proving nothing about "both
    # ends".
    ends = _ends_of(type_name)

    assert len(ends) == 2, (  # noqa: PLR2004
        f"{type_name} joins two objects, and the sweeps below check BOTH of them; got {ends}"
    )


@pytest.mark.parametrize("type_name", _LINK_TYPES)
def test_a_well_formed_link_between_two_objects_that_do_not_exist_passes(type_name: str) -> None:
    # ⭐ CRITERION 3, AND THE ONE MOST LIKELY TO BE "FIXED" INTO A BUG.
    #
    # A link whose two ends are syntactically perfect and resolve to nothing is
    # WELL-FORMED. Whether the child, the spouse or the family exists is a
    # question that needs a tree, and it is declared on the PHASE_3 side --
    # TARGET_DOES_NOT_EXIST -- precisely so that answering it here is visibly
    # out of bounds rather than a judgement call. A reader who thinks a link to
    # nothing ought to fail is asking Phase 1 to guess.
    #
    # Both ends are re-aimed, and the object types are preserved: rewriting
    # those too would trip the wrong-type rule and the test would then pass for
    # a reason that says nothing about existence.
    example = _example(type_name)
    nowhere = example
    for end in _ends_of(type_name):
        nowhere = carrying(nowhere, f"{end}.handle", "0000000000dead")
        nowhere = carrying(nowhere, f"{end}.gramps_id", "X9999")

    result = schema.validate(nowhere)

    assert result.well_formed, (
        "a well-formed link between two objects that do not exist is "
        "WELL-FORMED. Reporting it here is existence checking, which needs a "
        "database and is declared on the PHASE_3 side of the rule table; got "
        f"{[(v.rule.name, v.field_path) for v in result.violations]}"
    )

    everywhere_nowhere = schema.validate(pointing_nowhere(example))

    assert everywhere_nowhere.well_formed, (
        "the same link with its citation re-aimed as well is still "
        f"well-formed; got {everywhere_nowhere.violations}"
    )


@pytest.mark.parametrize("type_name", _LINK_TYPES)
def test_a_malformed_handle_at_either_end_of_a_link_is_reported_there(type_name: str) -> None:
    # Criterion 3's other half: syntax IS checked, at BOTH ends. A rule applied
    # to one end and not the other is this repository's recurring shape -- a
    # property agreed, then applied in some of the places it holds.
    for end in _ends_of(type_name):
        path = f"{end}.handle"
        result = schema.validate(carrying(_example(type_name), path, "two words"))
        reported = {(violation.rule, violation.field_path) for violation in result.violations}

        assert (schema.RuleId.HANDLE_MALFORMED, path) in reported, (
            f"a handle that is not one printable token must be reported AT "
            f"{path}; got {sorted(reported)}"
        )


@pytest.mark.parametrize("type_name", _LINK_TYPES)
def test_an_unknown_object_type_at_either_end_of_a_link_is_reported_there(type_name: str) -> None:
    for end in _ends_of(type_name):
        path = f"{end}.object_type"
        result = schema.validate(carrying(_example(type_name), path, "dwelling"))
        reported = {(violation.rule, violation.field_path) for violation in result.violations}

        assert (schema.RuleId.OBJECT_TYPE_UNKNOWN, path) in reported, (
            f"an object type outside the closed set must be reported AT "
            f"{path}; got {sorted(reported)}"
        )


@pytest.mark.parametrize("type_name", _LINK_TYPES)
def test_a_link_end_aimed_at_the_wrong_kind_of_object_is_reported_there(type_name: str) -> None:
    # The end-specific one: both values are perfectly typed strings and both
    # name real object types. What is wrong is WHICH kind this end may point at,
    # which is why a child end and a family end cannot be checked by one rule
    # that forgot to ask.
    expects = schema.expected_object_types(_registered(type_name).cls)

    for end in _ends_of(type_name):
        expected = expects.get(end)

        assert expected is not None, (
            f"{end} declares no expected object type, so nothing stops this "
            "end of the link pointing at anything at all"
        )

        wrong = next(kind for kind in sorted(schema.OBJECT_TYPES) if kind != expected)
        path = f"{end}.object_type"
        result = schema.validate(carrying(_example(type_name), path, wrong))
        reported = {(violation.rule, violation.field_path) for violation in result.violations}

        assert (schema.RuleId.REFERENCE_WRONG_TYPE, path) in reported, (
            f"{end} must reference a {expected}, and a reference aimed "
            f"elsewhere must be reported AT {path}; got {sorted(reported)}"
        )


def test_link_child_to_family_asserts_the_relationship_it_records() -> None:
    _registered("link_child_to_family")

    assert "link_child_to_family" in schema.FACT_ASSERTING, (
        "a parent-child relationship is the fact this project exists to get "
        "right -- the spec calls the relationships the actual product -- and "
        "one asserted on nobody's authority is exactly the failure mode it "
        "exists to avoid"
    )


def test_link_spouse_to_family_asserts_the_relationship_it_records() -> None:
    _registered("link_spouse_to_family")

    assert "link_spouse_to_family" in schema.FACT_ASSERTING, (
        "a spousal relationship is a claim about two people that a record "
        "attests, exactly as the parent-child link is -- the relationships are "
        "what the tree is for, and one entered on nobody's authority is the "
        "failure mode this project exists to avoid"
    )


def test_every_registered_type_records_why_it_is_classified_as_it_is() -> None:
    recorded = _recorded_rationales()
    missing = sorted(
        type_name for type_name in schema.REGISTRY if not recorded.get(type_name, "").strip()
    )

    assert missing == [], (
        "every registered type records a one-line rationale for its "
        "classification. TO FIX: give each of these an entry on the side it is "
        f"classified on, saying why it belongs there: {missing}"
    )
