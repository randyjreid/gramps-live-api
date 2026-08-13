"""Operations survive a round trip, and an unknown field is refused.

Ignoring an unknown field is the failure mode here: a client sending a
misspelled key would be told nothing and the operation would execute as
something other than what was agreed.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_an_operation_survives_a_round_trip(type_name: str) -> None:
    example = EXAMPLES[type_name]

    assert schema.from_dict(schema.to_dict(example)) == example, (
        f"{type_name} did not come back equal to what went in"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_the_payload_survives_a_round_trip_too(type_name: str) -> None:
    # The other direction. A round trip that is equal only on the object side
    # can still be quietly dropping or inventing keys on the wire.
    payload = schema.to_dict(EXAMPLES[type_name])

    assert schema.to_dict(schema.from_dict(payload)) == payload


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_the_payload_names_the_operation_type(type_name: str) -> None:
    assert schema.to_dict(EXAMPLES[type_name])["type"] == type_name


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_an_unknown_field_at_the_top_level_is_rejected(type_name: str) -> None:
    payload = dict(schema.to_dict(EXAMPLES[type_name]))
    payload["confidence"] = "high"

    with pytest.raises(schema.UnknownFieldError) as raised:
        schema.from_dict(payload)

    assert "confidence" in str(raised.value), (
        f"the refusal must name the field so it can be fixed; got {raised.value}"
    )


def _types_with_a_reference() -> list[str]:
    return [
        type_name
        for type_name in sorted(EXAMPLES)
        if schema.reference_fields(type(EXAMPLES[type_name]))
    ]


def test_at_least_one_registered_type_nests_a_reference() -> None:
    assert _types_with_a_reference(), (
        "no registered type nests anything, so the nested-rejection criterion below is vacuous"
    )


@pytest.mark.parametrize("type_name", _types_with_a_reference())
def test_an_unknown_field_nested_one_level_deep_is_rejected(type_name: str) -> None:
    # Criterion 6 asks for both depths on purpose: a top-level check written
    # as one pass over the outer keys reports clean on everything below it.
    example = EXAMPLES[type_name]
    reference = schema.reference_fields(type(example))[0]
    payload = dict(schema.to_dict(example))
    nested = dict(payload[reference])  # type: ignore[call-overload]
    nested["role"] = "principal"
    payload[reference] = nested

    with pytest.raises(schema.UnknownFieldError) as raised:
        schema.from_dict(payload)

    assert f"{reference}.role" in str(raised.value), (
        "the refusal must name the nested field by its full path, or it points "
        f"at the wrong level; got {raised.value}"
    )


def test_a_payload_naming_no_operation_type_is_rejected() -> None:
    with pytest.raises(schema.SchemaError):
        schema.from_dict({"target": None})


def test_a_payload_naming_an_unregistered_operation_type_is_rejected() -> None:
    # The closed registry, met from the wire: a type nobody registered is not
    # an operation, and guessing at one is how a vocabulary drifts open.
    with pytest.raises(schema.SchemaError):
        schema.from_dict({"type": "delete_everything"})


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_missing_field_deserialises_and_is_judged_by_validate(type_name: str) -> None:
    # The two error surfaces, and the line between them. A STRUCTURAL fault --
    # a key nobody declared -- raises. A VALUE fault -- a key that should be
    # there and is not -- must survive deserialisation, or validate can never
    # see it and criterion 2's negatives are unreachable from the wire.
    payload = dict(schema.to_dict(EXAMPLES[type_name]))
    dropped = next(iter(key for key in payload if key != "type"))
    del payload[dropped]

    result = schema.validate(schema.from_dict(payload))

    assert not result.well_formed, (
        f"{type_name} missing {dropped} deserialised and then validated clean, "
        "so nothing anywhere reports it"
    )
    assert dropped in {violation.field_path.split(".")[0] for violation in result.violations}
