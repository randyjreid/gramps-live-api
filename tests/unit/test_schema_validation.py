"""Validation decides well-formedness, and says so in its own name.

The boundary this file defends is the one the spec calls the danger: a module
that feels authoritative and silently defers the real checks. Everything here
is shape. Existence is not attempted, and a test asserts it is not attempted.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, emptied, pointing_nowhere, resolve


def test_the_result_type_is_named_for_well_formedness_not_validity() -> None:
    name = type(schema.validate(EXAMPLES["add_note"])).__name__

    assert "WellFormed" in name, f"the result type must say what it decided; got {name!r}"
    assert "Valid" not in name, (
        "'Valid' is the word that makes a caller believe the operation is "
        f"correct, which this module cannot decide; got {name!r}"
    )


def test_the_module_docstring_states_that_well_formed_is_not_correct() -> None:
    doc = (schema.__doc__ or "").lower()

    assert "well-formed" in doc and "not correct" in doc, (
        "the module docstring must state that a validated operation is "
        "well-formed and not correct, because the distinction is the whole "
        "boundary and a docstring is where a caller meets it"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_the_canonical_example_of_every_registered_type_is_well_formed(type_name: str) -> None:
    result = schema.validate(EXAMPLES[type_name])

    assert result.well_formed, (
        f"the canonical example of {type_name} must validate clean, or every "
        f"negative case below is measured against a broken baseline; got "
        f"{result.violations}"
    )
    assert result.violations == ()


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_well_formed_reference_to_a_nonexistent_object_passes(type_name: str) -> None:
    # Criterion 3, and the reason the result type is named as it is. These
    # handles and identifiers are syntactically perfect and resolve to nothing
    # anywhere. Phase 1 must pass them: existence is Phase 3's question, and a
    # module that answered it here would be guessing.
    result = schema.validate(pointing_nowhere(EXAMPLES[type_name]))

    assert result.well_formed, (
        "a syntactically well-formed reference to an object that does not "
        "exist is WELL-FORMED. Reporting it here would be existence checking, "
        f"which needs a database and belongs to Phase 3; got {result.violations}"
    )


def _every_required_field() -> list[tuple[str, str]]:
    """(type, path) for every required field of every registered type.

    Computed from the registry at collection time, so a tenth operation type
    brings its whole positive-and-negative set with it and this file does not
    change.
    """
    return [
        (type_name, path)
        for type_name in sorted(EXAMPLES)
        for path in schema.required_paths(type(EXAMPLES[type_name]))
    ]


@pytest.mark.parametrize(("type_name", "path"), _every_required_field())
def test_the_example_is_well_formed_with_this_field_present(type_name: str, path: str) -> None:
    # Criterion 2's positive half, one per required field. Parametrised rather
    # than asserted once so a failure names the field it is about.
    result = schema.validate(EXAMPLES[type_name])

    assert result.well_formed, f"{type_name} with {path} present must pass; got {result.violations}"


@pytest.mark.parametrize(("type_name", "path"), _every_required_field())
def test_emptying_one_required_field_is_reported_at_that_field(type_name: str, path: str) -> None:
    result = schema.validate(emptied(EXAMPLES[type_name], path))

    assert not result.well_formed, (
        f"{type_name} with {path} emptied must not be well-formed -- a required "
        "field nothing reports is a required field in name only"
    )
    assert path in [violation.field_path for violation in result.violations], (
        f"the failure must be reported AT {path}, not merely somewhere; got "
        f"{[(v.rule.name, v.field_path) for v in result.violations]}"
    )


@pytest.mark.parametrize(("type_name", "path"), _every_required_field())
def test_every_reported_field_path_names_a_field_that_exists(type_name: str, path: str) -> None:
    # Criterion 5, asserted over every negative case rather than over a chosen
    # one. A path that resolves nowhere is a message nobody can act on.
    result = schema.validate(emptied(EXAMPLES[type_name], path))

    for violation in result.violations:
        assert violation.field_path, (
            f"{violation.rule.name} reported an empty field path, which tells "
            "a caller nothing about where to look"
        )
        resolve(EXAMPLES[type_name], violation.field_path)


def _types_with_at_least_three_required_leaves() -> list[str]:
    return [
        type_name
        for type_name in sorted(EXAMPLES)
        if len(_leaf_paths(type_name)) >= 3  # noqa: PLR2004
    ]


def _leaf_paths(type_name: str) -> list[str]:
    # Leaves only: emptying a reference root collapses its own leaves, so
    # three faults would be reported as one and the test would measure the
    # wrong thing.
    cls = type(EXAMPLES[type_name])
    roots = set(schema.reference_fields(cls))
    return [path for path in schema.required_paths(cls) if path not in roots]


def test_at_least_one_registered_type_can_carry_three_faults_at_once() -> None:
    assert _types_with_at_least_three_required_leaves(), (
        "no registered type has three required leaves, so the "
        "three-simultaneous-errors criterion below is vacuous"
    )


@pytest.mark.parametrize("type_name", _types_with_at_least_three_required_leaves())
def test_three_simultaneous_faults_are_all_reported(type_name: str) -> None:
    faulty = EXAMPLES[type_name]
    broken = _leaf_paths(type_name)[:3]
    for path in broken:
        faulty = emptied(faulty, path)

    result = schema.validate(faulty)
    reported = {(violation.rule, violation.field_path) for violation in result.violations}

    assert len(reported) >= 3, (  # noqa: PLR2004
        "three distinct faults must be reported as three, not as the first "
        f"one found -- fixing them one round trip at a time is what "
        f"accumulation exists to prevent; broke {broken}, got {sorted(reported)}"
    )
    for path in broken:
        assert path in {field_path for _, field_path in reported}, (
            f"{path} was emptied and nothing reported it; got {sorted(reported)}"
        )
