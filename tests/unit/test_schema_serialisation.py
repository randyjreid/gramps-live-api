"""Operations survive a round trip, and an unknown field is refused.

Ignoring an unknown field is the failure mode here: a client sending a
misspelled key would be told nothing and the operation would execute as
something other than what was agreed.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, payload_with, resolve


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


# ---------------------------------------------------------------------------
# The reserved key
#
# ⭐ **The precedent, and it outlives this fix: an in-band signal must be
# INJECTIVE -- by reservation or by escaping.** ``UNCONVERTIBLE_KEY`` is what
# ``to_dict`` emits for a value this module cannot model, and a payload allowed
# to spell it made the signal ambiguous: a genuine conversion failure and a
# decoder-producible value that merely looked like one came out of ``to_dict``
# byte-identical. So the bounded closer's assertion that the marker never
# appears was FALSE, and unexercised only because no sampled value spelled the
# key. ``from_dict`` reserves it at the door instead, and the marker becomes
# injective by construction rather than by hope.
# ---------------------------------------------------------------------------


def _paths_the_walk_owns(type_name: str) -> list[str]:
    """Every declared path of ``type_name`` where the reserved-key walk refuses.

    Derived from the declaration, like every other matrix here. A reference
    ROOT is not one of them: a mapping there is how the wire spells an object,
    so ``_reference_from`` meets the key first and reports it as an undeclared
    leaf -- pinned by ``test_the_reserved_key_at_a_reference_root_is_still_unknown``.
    """
    cls = type(EXAMPLES[type_name])
    references = set(schema.reference_fields(cls))
    return [path for path in schema.required_paths(cls) if path not in references]


_WALK_CASES = [
    (type_name, path) for type_name in sorted(EXAMPLES) for path in _paths_the_walk_owns(type_name)
]

_ROOT_CASES = [
    (type_name, reference)
    for type_name in sorted(EXAMPLES)
    for reference in schema.reference_fields(type(EXAMPLES[type_name]))
]


def test_the_two_reserved_key_matrices_partition_every_declared_path() -> None:
    # ⚠️ **Two independent comprehensions can drop a path from BOTH**, which is a
    # coverage cut nothing else would announce; and an empty root half would make
    # the pin below read as coverage while asserting nothing at all. Green on
    # arrival and not evidence, like the tripwires in the wire-shape file.
    declared = {
        (type_name, path)
        for type_name in sorted(EXAMPLES)
        for path in schema.required_paths(type(EXAMPLES[type_name]))
    }

    assert set(_WALK_CASES) | set(_ROOT_CASES) == declared, (
        "a declared path is in neither matrix, so nothing says what the reserved key does there"
    )
    assert not set(_WALK_CASES) & set(_ROOT_CASES), (
        "a path is in both matrices, which are asserted to raise different types"
    )
    assert _WALK_CASES and _ROOT_CASES, (
        "one half is empty, so its assertion is vacuous while still reading as coverage"
    )


_RESERVED_SHAPES: tuple[tuple[str, object, str], ...] = (
    ("at the field itself", {schema.UNCONVERTIBLE_KEY: "set"}, ""),
    ("one list deep", [{schema.UNCONVERTIBLE_KEY: "set"}], "[0]"),
    ("one mapping deep", {"a key": {schema.UNCONVERTIBLE_KEY: "set"}}, ".a key"),
)
"""The key at a declared field and below one, each with the path it must compose.

The two containers are the two a decoder produces, which is the whole space the
bounded claim is quantified over.
"""


@pytest.mark.parametrize(("type_name", "path"), _WALK_CASES)
@pytest.mark.parametrize(
    ("description", "value", "suffix"),
    _RESERVED_SHAPES,
    ids=[description for description, _, _ in _RESERVED_SHAPES],
)
def test_the_reserved_key_is_refused_with_the_path_it_sits_at(
    description: str, value: object, suffix: str, type_name: str, path: str
) -> None:
    # ⚠️ **Refused on KEY PRESENCE, not on the exact one-key shape**, and that is
    # what makes the reservation injective rather than merely narrow: the
    # detector the bounded closer runs calls a payload a marker when any mapping
    # CONTAINS the key, so anything narrower here would leave payloads the
    # detector still reads as one. Matching the detector exactly is the argument
    # that the closer becomes TRUE rather than untriggered.
    with pytest.raises(schema.ReservedKeyError) as raised:
        schema.from_dict(payload_with(type_name, path, value))

    assert raised.value.field_path == f"{path}{suffix}.{schema.UNCONVERTIBLE_KEY}", (
        f"the refusal must name where the reserved key sits ({description} at "
        f"{path}), or it points at the wrong level and a caller cannot find it; "
        f"got {raised.value.field_path}"
    )


@pytest.mark.parametrize(("type_name", "reference"), _ROOT_CASES)
def test_the_reserved_key_at_a_reference_root_is_still_unknown(
    type_name: str, reference: str
) -> None:
    # Unchanged by the reservation, and pinned so it stays that way.
    # ``_reference_from`` runs first and a reference declares its leaves, so the
    # key is simply not one of them -- the pre-existing structural surface the
    # spec already records at criterion 5's consequences. Both refusals are a
    # ``SchemaError`` carrying a field path, so nothing a caller handles them by
    # moves; only which of the two truthful messages it gets.
    payload = payload_with(type_name, reference, {schema.UNCONVERTIBLE_KEY: "set"})

    with pytest.raises(schema.UnknownFieldError) as raised:
        schema.from_dict(payload)

    assert raised.value.field_path == f"{reference}.{schema.UNCONVERTIBLE_KEY}"


def _a_cyclic_mapping() -> dict[str, object]:
    """A payload value that refers to itself, which no decoder can produce.

    JSON is a tree, so this is the best-effort side by construction. It is
    tested because the reserved-key refusal is the first thing ``from_dict``
    does that WALKS its argument, and a walk that does not terminate is the one
    failure mode where nothing propagates as itself -- because nothing
    propagates at all. Before the walk existed a cyclic value passed straight
    through and ``to_dict`` broke the cycle with the marker.
    """
    cycle: dict[str, object] = {}
    cycle["a key"] = cycle
    return cycle


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_cyclic_payload_value_carrying_no_reserved_key_still_arrives(type_name: str) -> None:
    # Terminates and passes the value through untouched. A hang here is the
    # failure -- there is no assertion that can catch one, which is why the walk
    # marks the containers it has already visited rather than trusting the input.
    path = _paths_the_walk_owns(type_name)[0]
    cycle = _a_cyclic_mapping()

    operation = schema.from_dict(payload_with(type_name, path, cycle))

    assert resolve(operation, path) is cycle, (
        f"{type_name} lost or rewrote a cyclic value at {path}; the walk only "
        "refuses, and everything it does not refuse arrives as it was sent"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_cyclic_payload_value_carrying_the_reserved_key_is_still_refused(type_name: str) -> None:
    # The other half, and one test cannot do both: marking a container as
    # visited must not become a way to walk PAST a reserved key. The key sits in
    # a sibling of the back-edge rather than in the cycle's own mapping, so
    # reaching it requires the walk to keep going after it has met the cycle.
    path = _paths_the_walk_owns(type_name)[0]
    cycle = _a_cyclic_mapping()
    cycle["another key"] = [{schema.UNCONVERTIBLE_KEY: "set"}]

    with pytest.raises(schema.ReservedKeyError) as raised:
        schema.from_dict(payload_with(type_name, path, cycle))

    assert raised.value.field_path == f"{path}.another key[0].{schema.UNCONVERTIBLE_KEY}"


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
