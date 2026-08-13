"""Validation decides well-formedness, and says so in its own name.

The boundary this file defends is the one the spec calls the danger: a module
that feels authoritative and silently defers the real checks. Everything here
is shape. Existence is not attempted, and a test asserts it is not attempted.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, pointing_nowhere


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
