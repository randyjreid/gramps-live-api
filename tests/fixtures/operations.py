"""One canonical valid operation per registered type, and the negatives from it.

⚠️ **This is a fixture table, not a test.** The structural tests quantify over
``schema.REGISTRY``; what they cannot do is invent a *valid* example, because a
valid one needs invented names and sensible identifiers. So a new operation
type adds one entry here, and ``test_every_registered_type_has_an_example``
fails with an instruction if it does not.

Three constraints on the values, all from the PII guard running over this
checkout:

* Invented surnames only, from the register the other fixtures use.
* Note text stays under ``_GRAMPS_PROSE_LENGTH`` (20) characters. A prose key
  holding twenty characters or more scores 4 -- the whole threshold -- and is
  gated only by no GEDCOM X structural key being present in the same file.
  Staying under the floor means the fixture cannot become a finding if such a
  key ever lands beside it. Cheap, and it costs the fixture nothing.
* ⚠️ **Every example is BUILT, never written out as a payload.** Two of the
  schema's own field names -- the family name and the given name -- are also
  GEDCOM X identity keys, and the guard's identity keys are **ungated**: two
  filled ones in one file score the whole threshold on their own, with no
  structural key needed to arm them. A keyword argument is not a filled key, so
  a constructed operation matches nothing; the same payload written as a
  literal mapping of quoted keys to quoted values is a genuine P2 finding in a
  tracked file.

  The same rule, one shape along: **never put a value key in the same object as
  a type key.** That pairing is the GEDCOM X name-part shape and scores per
  object, wherever it sits. ``to_dict`` builds both at runtime, which is why
  the round-trip tests can hold a payload without this file containing one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from types import MappingProxyType
from typing import get_args, get_type_hints

from gramps_live_api.core.schema import (
    AddCitation,
    AddNote,
    AddPerson,
    AddPlace,
    ObjectRef,
    Operation,
    required_paths,
    to_dict,
)

EXAMPLES: Mapping[str, Operation] = MappingProxyType(
    {
        "add_citation": AddCitation(
            target=ObjectRef(object_type="person", handle="c9a1f0e2b7d46a", gramps_id="I0031"),
            citation=ObjectRef(object_type="citation", handle="e41b8c07a25fd3", gramps_id="C0042"),
        ),
        "add_note": AddNote(
            target=ObjectRef(object_type="family", handle="7fd3a9c15e0842", gramps_id="F0007"),
            note_type="research",
            text="Ashenmoor deed",
        ),
        "add_person": AddPerson(
            given="Elowen",
            surname="Ashenmoor",
            citation=ObjectRef(object_type="citation", handle="d0a7e93c184b6f", gramps_id="C0051"),
        ),
        "add_place": AddPlace(place_name="Thornwick"),
    }
)


MALFORMED: Mapping[str, Operation] = MappingProxyType(
    {
        "an object type nobody registered": AddNote(
            target=ObjectRef(object_type="dwelling", handle="b2c3d4e5f60718", gramps_id="P0002"),
            note_type="research",
            text="Ashenmoor deed",
        ),
        "a note type nobody registered": AddNote(
            target=ObjectRef(object_type="person", handle="b2c3d4e5f60718", gramps_id="I0012"),
            note_type="musing",
            text="Ashenmoor deed",
        ),
        "a handle that is not one printable token": AddNote(
            target=ObjectRef(object_type="person", handle="two words", gramps_id="I0012"),
            note_type="research",
            text="Ashenmoor deed",
        ),
        "provenance pointing at something that is not a citation": AddCitation(
            target=ObjectRef(object_type="person", handle="c9a1f0e2b7d46a", gramps_id="I0031"),
            citation=ObjectRef(object_type="source", handle="e41b8c07a25fd3", gramps_id="S0009"),
        ),
    }
)
"""Operations that are well-shaped but wrong, one per rule that needs one.

Emptying a field exercises only the two rules about absence. Every other
PHASE_1 rule needs a value that is *present and wrong*, and a rule no test can
make fire is a rule nobody has checked. ``test_every_phase_1_rule_can_fire``
asserts the coverage rather than trusting this table to be complete.
"""


def pointing_nowhere(operation: Operation) -> Operation:
    """``operation`` with every reference re-aimed at an object that is not there.

    Syntactically perfect, resolving to nothing. ``object_type`` is preserved
    deliberately: rewriting it too would trip the wrong-type rule and the test
    would then pass for the wrong reason, proving nothing about existence.
    """
    rewritten: dict[str, object] = {}
    for field in fields(operation):
        reference = getattr(operation, field.name)
        if isinstance(reference, ObjectRef):
            rewritten[field.name] = replace(reference, handle="0000000000dead", gramps_id="X9999")
    return replace(operation, **rewritten)


def resolve(operation: Operation, path: str) -> object:
    """The value at a dotted field path, or raise ``AttributeError``.

    The criterion-5 assertion tool: a reported field path must name a field
    that *exists* on the operation. A path that resolves nowhere is a message
    nobody can act on, which is the same as no message.
    """
    value: object = operation
    for step in path.split("."):
        names = {field.name for field in fields(value)}  # type: ignore[arg-type]
        if step not in names:
            raise AttributeError(f"{path}: {type(value).__name__} has no field {step}")
        value = getattr(value, step)
        if value is None:
            return None
    return value


def emptied(operation: Operation, path: str) -> Operation:
    """``operation`` with the leaf at ``path`` reset to its declared default.

    This is why every field defaults to empty: one negative case per required
    field is *generated* from the example rather than written out, so a tenth
    operation type gets its whole negative set for free.
    """
    head, _, rest = path.partition(".")
    if not rest:
        return carrying(operation, path, _default_of(operation, head))

    reference = getattr(operation, head)
    if reference is None:
        raise ValueError(f"{path}: cannot empty a leaf of a reference that is already absent")
    return carrying(operation, path, _default_of(reference, rest))


def nulled(operation: Operation, path: str) -> Operation:
    """``operation`` with the leaf at ``path`` set explicitly to ``None``.

    The *other* kind of absence, and not the one ``emptied`` makes. A payload
    that carries a null is not a payload with a field missing, and a required
    field explicitly given no value has to be reported rather than skipped --
    generated per required field, for the same reason ``emptied`` is.
    """
    return carrying(operation, path, None)


def carrying(operation: Operation, path: str, value: object) -> Operation:
    """``operation`` with the leaf at ``path`` replaced by ``value``.

    Deliberately does no checking of ``value``: this is the test side of the
    claim that an operation is a *transport* type, so a fixture must be able to
    put anything the wire can carry where a field goes and leave the judging to
    ``validate``.
    """
    head, _, rest = path.partition(".")
    if not rest:
        return replace(operation, **{head: value})

    reference = getattr(operation, head)
    if reference is None:
        raise ValueError(f"{path}: cannot set a leaf of a reference that is already absent")
    return replace(operation, **{head: replace(reference, **{rest: value})})


def payload_with(type_name: str, path: str, value: object) -> dict[str, object]:
    """The canonical payload for ``type_name``, carrying ``value`` at ``path``.

    The same generated negative, met from the wire instead of built as an
    object. Both routes matter: an operation the transport can carry but
    ``validate`` never sees is the defect the two error surfaces exist to
    prevent.
    """
    payload = to_dict(EXAMPLES[type_name])
    head, _, rest = path.partition(".")
    if not rest:
        payload[head] = value
        return payload

    nested = payload[head]
    if not isinstance(nested, dict):
        raise ValueError(f"{path}: {head} carries no nested value on the wire")
    payload[head] = {**nested, rest: value}
    return payload


WIRE_VALUES: tuple[object, ...] = (None, 123, True, [], {}, 1.5)
"""What a JSON payload can carry where a field goes.

Not a guess at what a client might send wrongly -- these are the JSON types,
which is the whole space the transport has. ``[]`` and ``{}`` are here for a
specific reason: they are FALSY, and a guard written as ``if not value`` lets a
falsy wrong-typed value through while catching the truthy ones.
"""


def permits(cls: type, path: str, value: object) -> bool:
    """Whether ``cls``'s own declaration allows ``value`` at ``path``.

    ⚠️ **Derived here from ``dataclasses.fields`` and ``get_type_hints``, and
    deliberately NOT by calling the module's helper.** The module decides what
    it will accept; this decides what it *should*, from the same declaration by
    a different route. Two sources that must agree is a test -- one source read
    twice is not, and it would pass just as happily if both were wrong.
    """
    permitted, optional = _declared(cls, path)
    if value is None:
        return optional
    return isinstance(value, permitted)


def _declared(cls: type, path: str) -> tuple[tuple[type, ...], bool]:
    owner: type = cls
    permitted: tuple[type, ...] = ()
    optional = False
    for step in path.split("."):
        annotation = get_type_hints(owner)[step]
        candidates = get_args(annotation) or (annotation,)
        permitted = tuple(
            candidate
            for candidate in candidates
            if isinstance(candidate, type) and candidate is not type(None)
        )
        optional = type(None) in candidates
        owner = permitted[0] if permitted else object
    return permitted, optional


def wrong_value_for(cls: type, path: str) -> object:
    """A value of a type ``path`` does not declare, chosen from ``WIRE_VALUES``.

    Derived rather than tabulated, so a field of a type nobody here anticipated
    still gets a negative case -- and if no wire value is wrong for it, that
    raises rather than quietly generating a case that proves nothing.
    """
    for value in WIRE_VALUES:
        if value is not None and not permits(cls, path, value):
            return value
    raise ValueError(f"{path}: no value in WIRE_VALUES is of a type it forbids")


def mistyped(operation: Operation, path: str) -> Operation:
    """``operation`` with the leaf at ``path`` holding a wrong-typed value."""
    return carrying(operation, path, wrong_value_for(type(operation), path))


def wire_cases() -> list[tuple[str, str, object]]:
    """Every (type, required path, wire value) a payload can be built from.

    The whole cross product, generated from the registry: what the transport can
    carry at every required field of every registered type. A tenth operation
    type widens it without anything here changing.
    """
    return [
        (type_name, path, value)
        for type_name in sorted(EXAMPLES)
        for path in required_paths(type(EXAMPLES[type_name]))
        for value in WIRE_VALUES
    ]


def forbidden_wire_values() -> list[tuple[str, str, object]]:
    """The subset of ``wire_cases`` whose value the declaration forbids.

    Two exclusions, both deliberate:

    * ``None`` -- an explicit null is a different fault with a different rule,
      and reporting it is ``nulled``'s business.
    * a **mapping** where a nested object is declared -- that is how the wire
      *spells* the object, not a value of the wrong type. ``{}`` deserialises
      to a well-typed reference whose leaves are empty, and ``FIELD_EMPTY`` is
      what reports that.
    """
    cases = []
    for type_name, path, value in wire_cases():
        cls = type(EXAMPLES[type_name])
        if value is None or permits(cls, path, value):
            continue
        nests = any(is_dataclass(candidate) for candidate in _declared(cls, path)[0])
        if nests and isinstance(value, Mapping):
            continue
        cases.append((type_name, path, value))
    return cases


SENTINELS: Mapping[str, str] = MappingProxyType(
    {
        "an ordinary token": "Zephyrine-Quorvane-8231",
        "a token carrying whitespace": "Zephyrine Quorvane 8231",
        "shaped like the content this repository exists to keep out": (
            "Tamsin Ashenmoor b. 1832 Larkspur Row"
        ),
    }
)
"""Distinctive values a payload can carry where a string field goes.

Distinctive is the whole point: a match in a violation message has to be
unambiguous, which ``123`` or ``"person"`` would not be. All three are
**invented**, from the same register the other fixtures use.

Three, and each earns its place. The plain token is the ordinary case; the one
carrying whitespace also provokes ``HANDLE_MALFORMED``, so the sweep reaches
every rule a present-and-wrong value can; the third is shaped like the content
this repository exists to keep out, because a rule that echoes a payload echoes
*that* on the day this vocabulary is in use, and a property demonstrated only
on a tidy token is a property nobody believes.

⚠️ **No sentinel may contain a path separator, a ``~``, or anything else
path-shaped.** These are literals in a tracked file that the guard scans, and a
path-shaped literal here would be a self-inflicted finding -- a trap this
repository has sprung on itself before, while writing *about* the detectors.
"""


def sentinel_cases() -> list[tuple[str, str, str, str]]:
    """(type, required path, description, sentinel) over the whole registry.

    Generated exactly as ``wire_cases`` is, and for the same reason: the
    property is that NO violation repeats a payload value, so the cases have to
    be every place a payload can put one. A tenth operation type extends the
    coverage without the test that consumes this being edited.
    """
    return [
        (type_name, path, description, sentinel)
        for type_name in sorted(EXAMPLES)
        for path in required_paths(type(EXAMPLES[type_name]))
        for description, sentinel in sorted(SENTINELS.items())
    ]


def _default_of(owner: object, name: str) -> object:
    for field in fields(owner):  # type: ignore[arg-type]
        if field.name == name:
            return field.default
    raise AttributeError(f"{type(owner).__name__} has no field {name}")
