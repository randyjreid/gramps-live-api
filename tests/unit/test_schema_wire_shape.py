"""``to_dict`` says it emits a JSON-shaped mapping. Nothing asserted it.

The docstring made the claim and the round-trip tests could not check it: they
compare an object to itself through both directions, so a value that survives
the trip unchanged passes whether or not any encoder could emit it. A non-JSON
value therefore passed straight through while the suite stayed green and the
claim quietly became false.

A new file rather than an edit, because ``test_schema_serialisation.py`` is
registry-derived structural work and its diff must stay empty.

⚠️ **The sweep over the canonical examples is a REGRESSION FENCE, not
evidence.** It is green before the change that added this file and green after,
because every registered type already carries only JSON-shaped values. It is
here so that the day one does not, something says so. The case with teeth is
the one below it, which was red.

Two sources are asked to agree, which is the point of checking it twice: the
structural walk, which can name the path of the offending value, and
``json.dumps``, which is the encoder the claim is actually about but whose
``TypeError`` names no field.
"""

from __future__ import annotations

import json
from dataclasses import fields

import pytest

from gramps_live_api.core import schema
from gramps_live_api.core.schema import UNRECORDED
from tests.fixtures.operations import EXAMPLES, carrying

_JSON_SCALARS = (bool, int, float, str)


def _not_json(value: object, path: str) -> str | None:
    """The path of the first value no JSON encoder can emit, or ``None``.

    A path rather than a boolean: a refusal that does not say where the fault is
    is one nobody can act on, which is the rule the violations in this module
    already obey.
    """
    if value is None or isinstance(value, _JSON_SCALARS):
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            offending = _not_json(item, f"{path}[{index}]")
            if offending is not None:
                return offending
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return path
            offending = _not_json(item, f"{path}.{key}" if path else key)
            if offending is not None:
                return offending
        return None
    return path


def _marker_cases() -> list[tuple[str, str]]:
    """Every (type, field) a marker can be put at that does not declare one.

    Derived rather than hand-picked, so a type registered later brings its own
    cases. An operation is a *transport* type, so a fixture can put the marker
    where any field goes and leave the judging to ``validate`` -- which is what
    makes this reachable at all while no registered type declares the marker.
    """
    return [
        (type_name, declared.name)
        for type_name in sorted(EXAMPLES)
        for declared in fields(type(EXAMPLES[type_name]))
        if declared.name not in schema.absence_fields(type(EXAMPLES[type_name]))
    ]


MARKER_CASES = _marker_cases()


def test_the_generated_marker_matrix_is_not_empty() -> None:
    # A parametrized list that generates to nothing passes every test built on
    # it while asserting nothing at all.
    assert MARKER_CASES, "no field was reached; every marker case below is vacuous"


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_canonical_example_serialises_to_something_json_can_emit(type_name: str) -> None:
    # ⚠️ The FENCE. Green before this file existed and green after -- it is not
    # evidence of new behaviour and must not be counted as such.
    payload = schema.to_dict(EXAMPLES[type_name])

    assert _not_json(payload, "") is None
    json.dumps(payload)


@pytest.mark.parametrize(("type_name", "path"), MARKER_CASES)
def test_to_dict_emits_json_for_a_marker_at_a_field_that_does_not_declare_it(
    type_name: str, path: str
) -> None:
    # The case with teeth. to_dict is by VALUE, not by declaration, precisely so
    # that this holds: a marker at a field whose declaration does not admit it is
    # still emitted as JSON. Making to_dict declaration-driven instead would
    # leave a raw Enum in the payload in exactly the case this test exists for.
    #
    # The operation is not well-formed -- validate reports the marker at that
    # path -- and that is a separate question from whether the transport can
    # carry it. Judging it requires getting it to a judge first.
    payload = schema.to_dict(carrying(EXAMPLES[type_name], path, UNRECORDED))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {offending} carries "
        f"{type(UNRECORDED).__name__}, which no JSON encoder can emit"
    )
    json.dumps(payload)
