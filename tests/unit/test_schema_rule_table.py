"""The validation boundary is a frozen table, and nothing outside it fires.

"Validate as far as is possible without a database" has no fixed point -- a
reviewer can always name one more check that is possible. The exit condition
here is *the table is total and nothing outside it fires*, which closes.
"""

from __future__ import annotations

import dataclasses

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, MALFORMED, emptied, mistyped, nulled


def test_every_rule_the_module_declares_appears_in_the_table_exactly_once() -> None:
    tabled = [rule.id for rule in schema.RULES]

    assert sorted(set(tabled), key=lambda rule: rule.name) == sorted(
        schema.RuleId, key=lambda rule: rule.name
    ), (
        "every rule id must be classified in the table: an id the table does "
        f"not carry is a rule on neither side of the boundary; got {tabled}"
    )
    assert len(tabled) == len(set(tabled)), (
        f"a rule id classified twice can be classified two ways; got {tabled}"
    )


def test_the_phase_3_side_of_the_table_is_not_empty() -> None:
    # Without this, "no PHASE_3 rule can fire" is vacuously true and the
    # criterion below proves nothing at all.
    declared = [rule.id for rule in schema.RULES if rule.phase is schema.Phase.PHASE_3]

    assert declared, (
        "the PHASE_3 side must declare the checks this module deliberately "
        "cannot make, or the boundary is asserted against an empty set"
    )


def test_the_phase_a_rule_is_on_decides_whether_it_is_implemented() -> None:
    wrong = [
        (rule.id.name, rule.phase.name, rule.check is not None)
        for rule in schema.RULES
        if (rule.check is not None) != (rule.phase is schema.Phase.PHASE_1)
    ]

    assert wrong == [], (
        "a PHASE_1 rule must have a check and a PHASE_3 rule must not: an "
        "implemented PHASE_3 rule is a database question answered by guessing, "
        f"and an unimplemented PHASE_1 rule is a boundary claim nothing keeps; got {wrong}"
    )


def _every_negative_case() -> list[tuple[str, str]]:
    return [
        (type_name, path)
        for type_name in sorted(EXAMPLES)
        for path in schema.required_paths(type(EXAMPLES[type_name]))
    ]


@pytest.mark.parametrize(("type_name", "path"), _every_negative_case())
def test_validate_emits_nothing_the_table_does_not_carry(type_name: str, path: str) -> None:
    tabled = {rule.id for rule in schema.RULES}
    result = schema.validate(emptied(EXAMPLES[type_name], path))

    outside = [v.rule for v in result.violations if v.rule not in tabled]

    assert outside == [], f"validate emitted a rule the table does not classify; got {outside}"


@pytest.mark.parametrize(("type_name", "path"), _every_negative_case())
def test_no_phase_3_rule_fires_from_validate(type_name: str, path: str) -> None:
    phase_3 = {rule.id for rule in schema.RULES if rule.phase is schema.Phase.PHASE_3}
    result = schema.validate(emptied(EXAMPLES[type_name], path))

    fired = [v.rule.name for v in result.violations if v.rule in phase_3]

    assert fired == [], (
        "a PHASE_3 rule fired from validate, so this module answered a "
        f"question that needs a tree; got {fired}"
    )


def _rules_observed_firing() -> set[schema.RuleId]:
    """Every rule any test case in the fixtures can actually provoke.

    The generated cases come first and carry the weight: each is one derived
    mutation of a canonical example, per required field of every registered
    type, so a tenth operation type extends this coverage without this file
    being edited. ``MALFORMED`` is the hand-written remainder, for the rules
    that need a value which is present, well-typed and wrong.
    """
    fired: set[schema.RuleId] = set()
    for derive in (emptied, nulled, mistyped):
        for type_name, path in _every_negative_case():
            result = schema.validate(derive(EXAMPLES[type_name], path))
            fired.update(violation.rule for violation in result.violations)
    for operation in MALFORMED.values():
        fired.update(violation.rule for violation in schema.validate(operation).violations)
    return fired


def test_every_phase_1_rule_can_fire() -> None:
    # The converse of "every rule the validator emits is in the table", and
    # the half that catches dead code: a rule declared PHASE_1 with a check
    # nothing provokes has never been run, so nothing says it works.
    declared = {rule.id for rule in schema.RULES if rule.phase is schema.Phase.PHASE_1}
    never = sorted(rule.name for rule in declared - _rules_observed_firing())

    assert never == [], (
        "these PHASE_1 rules are implemented and no test case makes them "
        "report, so their checks have never run. TO FIX: add one operation "
        "that is well-shaped and wrong to MALFORMED in "
        f"tests/fixtures/operations.py, one per rule listed here: {never}"
    )


@pytest.mark.parametrize("description", sorted(MALFORMED))
def test_each_malformed_case_is_reported(description: str) -> None:
    result = schema.validate(MALFORMED[description])

    assert not result.well_formed, (
        f"{description} validated clean, so the fixture no longer exercises "
        "the rule it was written for"
    )


def _probe() -> schema.Rule:
    """A PHASE_3 rule that always reports, for asking whether the filter works.

    Sampling real cases can only ever show that no PHASE_3 rule *happened* to
    fire. This asks the structural question instead: given a PHASE_3 rule that
    fires unconditionally, does the filter stop it? A tenth operation type
    inherits the answer without this test changing.
    """
    return schema.Rule(
        id=schema.RuleId.TARGET_DOES_NOT_EXIST,
        phase=schema.Phase.PHASE_3,
        check=lambda operation: (
            schema.RuleViolation(schema.RuleId.TARGET_DOES_NOT_EXIST, "target", "probe fired"),
        ),
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_the_probe_can_fire_when_its_phase_allows_it(type_name: str) -> None:
    # The probe test below is worthless if the probe is inert. This is the
    # control for it: the same rule, moved to PHASE_1, must report.
    allowed = dataclasses.replace(_probe(), phase=schema.Phase.PHASE_1)

    result = schema._run((allowed,), EXAMPLES[type_name])

    assert not result.well_formed, "the probe does not fire even when permitted; it proves nothing"


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_phase_3_rule_that_always_fires_still_cannot(type_name: str) -> None:
    result = schema._run((*schema.RULES, _probe()), EXAMPLES[type_name])

    assert result.well_formed, (
        "a PHASE_3 rule that reports unconditionally must still report "
        "nothing through the validator, because the phase filter is a choke "
        f"point and not a convention; got {result.violations}"
    )
