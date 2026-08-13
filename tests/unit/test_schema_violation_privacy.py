"""A violation names the field and the expectation, never what arrived.

``_field_wrong_type`` was written to report type names only, for a privacy
reason stated at its own call site. Its siblings copied the rejected wire value
into the message, so a caller that logged a validation failure would publish
payload content -- and an operation payload is precisely where genealogical data
lives once this vocabulary is in use, in a public repository whose previous
phase existed to keep exactly that out.

**The defect was never the three call sites; it is that nothing stopped a
fourth rule doing it.** So this file asserts the property structurally, over the
cases the module generates for itself: every registered type, every required
path, by both routes a value can arrive. A test naming the three rules that were
found would be satisfied by three special cases and would say nothing about the
fourth.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import (
    EXAMPLES,
    MALFORMED,
    carrying,
    payload_with,
    sentinel_cases,
)


def _rendered(violation: schema.RuleViolation) -> str:
    """Everything one violation can be turned into by a caller.

    ⚠️ **Deliberately the WHOLE violation and not ``message`` alone.** A rule
    that built a field path out of payload content, or a fifth field added to
    the dataclass later, would carry the value past a message-only check while
    every message stayed clean. The property is about the object, so the
    assertion is about the object.
    """
    return f"{violation!r} {violation.rule.name} {violation.field_path} {violation.message}"


def _from_the_wire(type_name: str, path: str, value: object) -> schema.WellFormedResult | None:
    """What ``validate`` says about a payload carrying ``value``, or nothing.

    ``None`` where deserialisation refuses the payload outright: that is the
    documented structural surface, and a refusal hands back no violation to
    inspect. The object route below is what covers those paths.
    """
    try:
        operation = schema.from_dict(payload_with(type_name, path, value))
    except schema.SchemaError:
        return None
    return schema.validate(operation)


@pytest.mark.parametrize(("type_name", "path", "description", "sentinel"), sentinel_cases())
def test_no_violation_from_the_wire_repeats_the_value_the_payload_carried(
    type_name: str, path: str, description: str, sentinel: str
) -> None:
    result = _from_the_wire(type_name, path, sentinel)
    if result is None:
        return

    for violation in result.violations:
        assert sentinel not in _rendered(violation), (
            f"{violation.rule.name} repeated a value the payload carried -- "
            f"{description}, at {path} of {type_name}: {violation.message!r}. A "
            "violation names the field path, and where it helps the allowed set "
            "or the declared type; never what arrived, because a caller that "
            "logs the failure is then the thing that published it"
        )


@pytest.mark.parametrize(("type_name", "path", "description", "sentinel"), sentinel_cases())
def test_no_violation_built_as_an_object_repeats_the_value_it_was_given(
    type_name: str, path: str, description: str, sentinel: str
) -> None:
    # The route the wire cannot take. A reference ROOT given a string is refused
    # by deserialisation before validate sees it, so the rule that judges it --
    # FIELD_WRONG_TYPE, the one rule that already obeyed the property -- is
    # never reached above. Asserting here keeps the property from holding only
    # where a payload happens to be able to reach.
    result = schema.validate(carrying(EXAMPLES[type_name], path, sentinel))

    for violation in result.violations:
        assert sentinel not in _rendered(violation), (
            f"{violation.rule.name} repeated a value it was handed -- "
            f"{description}, at {path} of {type_name}: {violation.message!r}"
        )


def _rules_the_sentinel_sweep_provokes() -> set[schema.RuleId]:
    fired: set[schema.RuleId] = set()
    for type_name, path, _, sentinel in sentinel_cases():
        from_the_wire = _from_the_wire(type_name, path, sentinel)
        if from_the_wire is not None:
            fired.update(violation.rule for violation in from_the_wire.violations)
        as_an_object = schema.validate(carrying(EXAMPLES[type_name], path, sentinel))
        fired.update(violation.rule for violation in as_an_object.violations)
    return fired


def test_the_sentinel_sweep_provokes_every_rule_a_present_and_wrong_value_can() -> None:
    """The two tests above are vacuous over cases that provoke nothing.

    A containment assertion passes for free when there is nothing to contain, so
    the sweep has to be shown to reach the rules it claims to. Measured against
    ``MALFORMED`` rather than against a list of rule names: that table IS the
    present-and-wrong corpus, which is exactly what a sentinel is, so a rule
    added tomorrow with a fixture beside it is covered here without this test
    being edited. A list of names would go stale on the same day.
    """
    from_the_fixture_table = {
        violation.rule
        for operation in MALFORMED.values()
        for violation in schema.validate(operation).violations
    }
    missed = sorted(
        rule.name for rule in from_the_fixture_table - _rules_the_sentinel_sweep_provokes()
    )

    assert from_the_fixture_table, "the present-and-wrong corpus is empty, so this proves nothing"
    assert missed == [], (
        "these rules report a present-and-wrong value that no sentinel case "
        "provokes, so nothing above has checked what their messages carry. TO "
        "FIX: add a sentinel to SENTINELS in tests/fixtures/operations.py that "
        f"makes them fire: {missed}"
    )
