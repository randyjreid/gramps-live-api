"""``to_dict`` says it emits a JSON-shaped mapping. Nothing asserted it.

The docstring made the claim and the round-trip tests could not check it: they
compare an object to itself through both directions, so a value that survives
the trip unchanged passes whether or not any encoder could emit it. A non-JSON
value therefore passed straight through while the suite stayed green and the
claim quietly became false.

A new file rather than an edit, because ``test_schema_serialisation.py`` is
registry-derived structural work and its diff must stay empty.

⚠️ **And it asserted the claim at ONE DEPTH, which is how the claim stayed
false.** A marker inside an ``ObjectRef`` was copied straight out of the
reference, so ``to_dict`` returned a raw ``Unrecorded`` and ``json.dumps``
raised -- while this file was green. The matrix below is now quantified over
**paths derived from the declaration, at every depth**, crossed with the values
this module models that no encoder can emit. That is the property; the recursion
in ``_to_wire`` satisfies it, and this is what states it, so the next depth
arrives already covered.

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
from collections.abc import Iterator, Mapping
from dataclasses import fields, is_dataclass
from types import MappingProxyType
from typing import get_args, get_type_hints

import pytest

from gramps_live_api.core import schema
from gramps_live_api.core.schema import UNRECORDED, ObjectRef, Operation, Unrecorded
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


_A_REFERENCE = ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044")
"""A reference built from invented values, in the register ``EXAMPLES`` uses."""


_UNEMITTABLE: Mapping[str, object] = MappingProxyType(
    {
        "the not-recorded marker": UNRECORDED,
        "a reference": _A_REFERENCE,
    }
)
"""The values this module models that no JSON encoder can emit.

⚠️ **Exactly ``_to_wire``'s two branches, and that is what makes this the
module's vocabulary rather than a guess at what might turn up.** Everything else
reaching ``to_dict`` arrived through ``from_dict``, which passes JSON through
already decoded. So a value the wire cannot carry is one of these two or one
nobody converts -- and the second set is empty by the same reading.

The reference is built from invented values, in the register ``EXAMPLES``
already uses, for the reason recorded on ``SENTINELS``.
"""


def _declared_paths(
    cls: type, prefix: str = "", seen: frozenset[type] = frozenset()
) -> Iterator[str]:
    """Every dotted path the declaration of ``cls`` reaches, at every depth.

    ⚠️ **A walk rather than one level of ``fields``, and the difference is the
    defect this file was extended for.** ``to_dict`` applies ``_to_wire`` to
    top-level fields, so a matrix built from ``fields(cls)`` alone asserts the
    JSON-shaped claim at exactly the depth the emitter happens to visit -- which
    is how a raw ``Unrecorded`` inside a reference passed a green suite. **A test
    that asserts a claim at one depth does not assert it at all depths.**

    Derived here from ``get_type_hints``/``get_args`` and deliberately NOT by
    calling ``schema.absence_fields``, which answers at the top level only --
    following this suite's precedent that a test reads the same declaration by
    its own route. A field whose annotation admits the marker is skipped: its
    declaration says the marker belongs there, so it is not a case about a value
    arriving where nothing declares it.

    ``seen`` carries the owner classes on the way down, so a self-referential
    declaration terminates rather than walking forever.
    """
    owners = seen | {cls}
    hints = get_type_hints(cls)
    for declared in fields(cls):  # type: ignore[arg-type]
        annotation = hints[declared.name]
        candidates = get_args(annotation) or (annotation,)
        if Unrecorded in candidates:
            continue
        path = f"{prefix}{declared.name}"
        yield path
        for candidate in candidates:
            if isinstance(candidate, type) and is_dataclass(candidate) and candidate not in owners:
                yield from _declared_paths(candidate, f"{path}.", owners)


def _marker_cases() -> list[tuple[str, str, str]]:
    """Every (type, path, value) a value no encoder can emit can be put at.

    Derived rather than hand-picked, so a type registered later brings its own
    cases -- and, since the walk above is recursive, brings them at every depth
    its declaration reaches rather than at its top level only.

    An operation is a *transport* type, so a fixture can put any of these where
    any field goes and leave the judging to ``validate`` -- which is what makes
    this reachable at all while no registered type declares the marker.

    ⚠️ **``carrying`` handles two levels, so a depth-3 path would raise
    ``TypeError`` from ``dataclasses.replace`` rather than quietly skip.** Loud
    is correct: the day a declaration nests that deep, this says so.
    """
    return [
        (type_name, path, description)
        for type_name in sorted(EXAMPLES)
        for path in _declared_paths(type(EXAMPLES[type_name]))
        for description in sorted(_UNEMITTABLE)
    ]


MARKER_CASES = _marker_cases()


def test_the_generated_marker_matrix_is_not_empty() -> None:
    # A parametrized list that generates to nothing passes every test built on
    # it while asserting nothing at all.
    assert MARKER_CASES, "no field was reached; every marker case below is vacuous"


def test_the_marker_matrix_reaches_a_nested_path() -> None:
    # ⚠️ **The same idiom as the guard above and for the same reason, one level
    # deeper.** An empty matrix reads as coverage; so does a matrix that quietly
    # stops at depth 1 -- which is not hypothetical, it is exactly what this file
    # did while the claim it asserts was false inside a reference. The non-empty
    # guard cannot see it, because a shallow walk still generates plenty.
    #
    # A VACUITY GUARD, so it is green on arrival: it is not evidence of the
    # behaviour, it is what stops the evidence being read at the wrong depth.
    nested = sorted({path for _, path, _ in MARKER_CASES if "." in path})

    assert nested, (
        "no generated path is nested, so the matrix asserts to_dict's claim at "
        "the top level only -- which is how a raw value inside a reference "
        "passed this file green"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_canonical_example_serialises_to_something_json_can_emit(type_name: str) -> None:
    # ⚠️ The FENCE. Green before this file existed and green after -- it is not
    # evidence of new behaviour and must not be counted as such.
    payload = schema.to_dict(EXAMPLES[type_name])

    assert _not_json(payload, "") is None
    json.dumps(payload)


@pytest.mark.parametrize(("type_name", "path", "description"), MARKER_CASES)
def test_to_dict_emits_json_for_a_marker_at_a_field_that_does_not_declare_it(
    type_name: str, path: str, description: str
) -> None:
    # The case with teeth. to_dict is by VALUE, not by declaration, precisely so
    # that this holds: a marker at a field whose declaration does not admit it is
    # still emitted as JSON. Making to_dict declaration-driven instead would
    # leave a raw Enum in the payload in exactly the case this test exists for.
    #
    # The operation is not well-formed -- validate reports the marker at that
    # path -- and that is a separate question from whether the transport can
    # carry it. Judging it requires getting it to a judge first. An operation
    # that cannot be CARRIED is untransportable rather than reportably invalid,
    # which inverts this module's own boundary: shape faults are reported at a
    # field path, not raised out of the transport.
    #
    # ⚠️ **The name records criterion 5 and the matrix is wider than the name.**
    # It crosses every declared path with both values _to_wire converts, because
    # the claim is about the payload rather than about one of them.
    value = _UNEMITTABLE[description]
    payload = schema.to_dict(carrying(EXAMPLES[type_name], path, value))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {offending} carries "
        f"{type(value).__name__}, which no JSON encoder can emit"
    )
    json.dumps(payload)


# ---------------------------------------------------------------------------
# One container deeper -- the shapes round 2 reported, named
#
# ⚠️ **These are the REPORTED shapes and they are kept by name, not folded into
# the generated set below.** A sample that happens to contain today's finding is
# not the same artifact as a case that says which finding it is: the generator's
# breadth is a budget somebody will trim, and the shape a reviewer actually
# constructed must not be trimmable by arithmetic. Every one of them had the same
# signature -- ``validate`` already returned FIELD_WRONG_TYPE at the path, and
# ``json.dumps(to_dict(op))`` raised, so the verdict existed and the transport
# hid it.
# ---------------------------------------------------------------------------


def _first_reference_leaf(cls: type) -> str:
    """Where a value goes to be carried at depth: the first leaf of the first reference.

    Derived rather than spelled, so a type whose reference field is named
    something else brings its own placement.
    """
    reference = schema.reference_fields(cls)[0]  # type: ignore[arg-type]
    return f"{reference}.{fields(ObjectRef)[0].name}"


_CONTAINED: Mapping[str, object] = MappingProxyType(
    {
        "a list holding the not-recorded marker": [UNRECORDED],
        "a mapping holding the not-recorded marker": {"a key": UNRECORDED},
        "a list holding a list holding the not-recorded marker": [[UNRECORDED]],
        "a list holding a reference": [_A_REFERENCE],
        "a mapping holding a reference": {"a key": _A_REFERENCE},
        "a read-only mapping holding the not-recorded marker": MappingProxyType(
            {"a key": UNRECORDED}
        ),
    }
)
"""The shapes reported against the one-container-deep conversion, verbatim."""


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
@pytest.mark.parametrize("description", sorted(_CONTAINED))
def test_to_dict_emits_json_for_a_container_holding_a_value_the_module_models(
    description: str, type_name: str
) -> None:
    example = EXAMPLES[type_name]
    value = _CONTAINED[description]
    payload = schema.to_dict(carrying(example, _first_reference_leaf(type(example)), value))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {description} at "
        f"{offending} is not one an encoder can emit"
    )
    json.dumps(payload)


# ---------------------------------------------------------------------------
# The branch for the unknown
#
# ⚠️ **A value the module cannot model emits a MARKER rather than raising, and
# the reason is the line this module already draws and writes down.** A
# STRUCTURAL fault raises; a VALUE fault does not, because refusing one would be
# a second validator with no field path. An alien object at a declared field is a
# value fault, and ``validate`` already returns FIELD_WRONG_TYPE at its path.
# **A typed transport error is this finding with a better name.**
#
# Unmodellable and modellable-but-misplaced share the surface and differ only in
# the payload: a modellable value keeps its faithful spelling, and only an
# unmodellable one is replaced. Splitting them across two error surfaces would
# make a caller's handling depend on a distinction it cannot predict.
# ---------------------------------------------------------------------------

_A_VALUE_NO_MESSAGE_MAY_REPEAT = "Thessaly-Grendlemere-4417"
"""Invented, and distinctive so its absence from the payload means something.

Same register and the same rule as ``SENTINELS``: no path separator, no ``~``,
nothing path-shaped, because this is a literal in a file the guard scans.
"""


class _Unmodellable:
    """A value nothing here models, carrying something no payload may repeat.

    A module-level class rather than a lambda or a bare ``object()``: the fault
    marker names ``type(value).__name__``, so the name has to be one a reader
    meets in the failure message.
    """

    def __init__(self, carried: str) -> None:
        self.carried = carried

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.carried}>"


def _carrying_at_the_first_leaf(type_name: str, value: object) -> Operation:
    example = EXAMPLES[type_name]
    return carrying(example, _first_reference_leaf(type(example)), value)


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_to_dict_emits_json_for_a_value_the_module_cannot_model(type_name: str) -> None:
    # The transport must carry it to the judge. validate already reports
    # FIELD_WRONG_TYPE at that path, so what raising would cost is not a verdict
    # -- it is the verdict's field path, reported out of a surface that has none.
    payload = schema.to_dict(_carrying_at_the_first_leaf(type_name, _Unmodellable("a value")))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {offending} carries a value the "
        "module cannot model, which no JSON encoder can emit"
    )
    json.dumps(payload)


def test_the_fault_marker_names_the_type_and_never_the_value() -> None:
    # The rule on RuleViolation, obeyed by the transport for the same reason: a
    # payload echoed into the record becomes content this repository then has to
    # scan. The TYPE is what a caller needs to fix it, and it is ours to name.
    value = _Unmodellable(_A_VALUE_NO_MESSAGE_MAY_REPEAT)

    wire = schema._to_wire(value)

    assert wire == {schema.UNCONVERTIBLE_KEY: type(value).__name__}
    assert _A_VALUE_NO_MESSAGE_MAY_REPEAT not in json.dumps(wire), (
        "the fault marker repeated the value it refused, which is the one thing "
        "no message in this module may do"
    )


def test_a_mapping_keyed_by_something_that_is_not_text_is_unconvertible() -> None:
    # A whole-mapping verdict rather than a per-key one, deliberately: a JSON
    # object is string-keyed, and stringifying the key would invent data the
    # payload never carried.
    value = {0: "a value"}

    assert schema._to_wire(value) == {schema.UNCONVERTIBLE_KEY: type(value).__name__}


def test_a_read_only_mapping_converts_rather_than_raising() -> None:
    # GREEN ON ARRIVAL from the container recursion, and kept because it is the
    # totality gain nobody asked for: this module hands MappingProxyType around
    # as REGISTRY and EXAMPLES, and json.dumps raises on one.
    wire = schema._to_wire(MappingProxyType({"a key": "a value"}))

    assert wire == {"a key": "a value"}
    assert type(wire) is dict


def test_a_self_referential_list_is_emitted_as_json() -> None:
    # ⚠️ **Termination is the OTHER HALF of "total", and without it the word is
    # simply false.** A list holding itself is constructible in two lines, and a
    # structural recursion over it does not stop. It is a termination condition
    # rather than a case added to an enumeration, which is the distinction that
    # keeps this from being the next shape nobody wrote down.
    cycle: list[object] = []
    cycle.append(cycle)

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", cycle))

    assert _not_json(payload, "") is None
    json.dumps(payload)


def test_a_self_referential_mapping_is_emitted_as_json() -> None:
    # The same, through the other container, because a fix applied to one branch
    # of a structural recursion is a fix applied to one branch.
    cycle: dict[str, object] = {}
    cycle["a key"] = cycle

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", cycle))

    assert _not_json(payload, "") is None
    json.dumps(payload)


def test_a_value_appearing_twice_is_not_read_as_a_cycle() -> None:
    # ⚠️ **The guard on the SHAPE of the termination fix, and the reason it is
    # here before the fix is.** "Seen" carried as a set that accumulates across
    # the whole walk marks the second sibling as a cycle and emits the fault
    # marker for a value that is perfectly emittable -- a fail-closed defect that
    # every other test in this file would pass over. Carried along the current
    # PATH instead, a shared value is converted twice and neither is a cycle.
    shared = ["a value"]

    assert schema._to_wire([shared, shared]) == [["a value"], ["a value"]]


def test_a_tuple_becomes_a_json_array() -> None:
    # GREEN ON ARRIVAL, and recorded because it is a CONSEQUENCE rather than a
    # gain: that operation is no longer round-trip identical, since a tuple comes
    # back a list. Correct -- JSON has no tuple -- and reachable only on an
    # operation that is invalid either way. No fixture carries one.
    assert schema._to_wire(("a value",)) == ["a value"]
