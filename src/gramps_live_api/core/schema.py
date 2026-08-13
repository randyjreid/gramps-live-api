"""The operation model: the vocabulary an agreed genealogical fact is expressed in.

⚠️ **A validated operation is WELL-FORMED, NOT CORRECT.** Everything this module
can decide is shape: required fields, membership of a closed set, type
correctness, internal consistency, and the *syntax* of a reference. Whether the
thing a reference names exists, whether it is the right thing, whether it
duplicates something already in the tree -- none of that is decidable without a
database, and none of it is attempted here. Those rules are declared on the
``PHASE_3`` side of ``RULES`` so the boundary is a table rather than a promise,
and a test asserts that no rule on that side can fire from ``validate``.

The result type is named ``WellFormedResult`` and never ``Valid`` anything, so
the distinction is hard to misread at a call site.

The registry is **closed**: there is no public registration function and
``REGISTRY`` is a read-only mapping. A closed set is what makes the provenance
partition assertable at all -- an open one makes this module's most important
property unfalsifiable.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import TypeVar, get_args, get_type_hints

# ---------------------------------------------------------------------------
# References -- D2, answered
#
# Handles are machine identity; Gramps IDs are the human-readable rendering.
# Both are REQUIRED, and that is a strengthening of the recommendation rather
# than a restatement of it: if the ID were optional, a reference carrying only
# a handle would force preview() to print either the handle -- which the
# criterion forbids, and which is the proxy carrying real weight, because an
# operation naming an opaque handle is not reviewable at all -- or a
# placeholder, which the criterion also forbids. Requiring the ID is what moves
# that criterion from defended case by case to true by construction.
#
# ⚠️ There is deliberately NO rule that the Gramps ID prefix agrees with the
# object type. Gramps ID prefixes are user-configurable, so such a rule would
# be wrong rather than merely incomplete. Do not add it.
# ---------------------------------------------------------------------------

OBJECT_TYPE_CITATION = "citation"

OBJECT_TYPES: frozenset[str] = frozenset(
    {
        "person",
        "family",
        "event",
        "place",
        "source",
        OBJECT_TYPE_CITATION,
        "note",
        "media",
        "repository",
    }
)
"""What a reference may point at: the Gramps primary object types.

An enumeration, accepted on exactly the grounds ``FILESYSTEM_ROOTS`` is
accepted in ``pii_guard``: closed, externally specified, and it does not grow
on our schedule. Membership is a PHASE_1 rule, which is why this is a set of
strings rather than an ``Enum`` -- see ``ObjectRef.object_type``.
"""

_EXPECTS = "expects"
"""Field metadata key: which object type a reference field must point at."""


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """A reference to one object that already exists in the tree.

    Every field defaults to empty for the reason given on ``Operation``: a
    reference the transport could carry must become a value ``validate`` can
    judge and name a field path for.

    ``object_type`` is a ``str`` against ``OBJECT_TYPES`` and not an ``Enum``
    on purpose. An ``Enum``-typed field cannot hold a non-member, so the
    membership rule the spec puts in PHASE_1 would be unreachable -- the check
    would instead be a ``ValueError`` from a constructor, which is a second
    validator with a different vocabulary and no field path.
    """

    object_type: str = ""
    handle: str = ""
    gramps_id: str = ""


@dataclass(frozen=True, slots=True)
class Operation:
    """Base for every operation type. Carries no fields of its own.

    ⚠️ **Every field of every operation defaults to empty, and that is a
    design decision rather than laziness.** An operation is a *transport*
    type: any payload the wire can carry has to become an object ``validate``
    can judge and report a field path for. A constructor that refuses a
    missing field is a second validator speaking a different vocabulary --
    the "two matchers, two ideas" shape this repository has recorded more than
    once -- and it puts the refusal somewhere no field path can reach.
    """


_Registered = TypeVar("_Registered", bound=type[Operation])


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """What the registry knows about one operation type."""

    type_name: str
    cls: type[Operation]
    citation_field: str | None
    """The field carrying provenance, or ``None`` for an exempt operation.

    Declared here and cross-checked against the dataclass by test, so the
    classification table and the schema cannot drift apart.
    """


_REGISTRY: dict[str, OperationSpec] = {}

REGISTRY: Mapping[str, OperationSpec] = MappingProxyType(_REGISTRY)
"""Every operation type there is, keyed by its wire name.

Read-only, and populated only by ``_register`` calls inside this module. That
is what "closed" means mechanically: not a comment claiming the set is fixed,
but no route by which anything outside this file can add to it.
"""


def _register(
    type_name: str, *, citation_field: str | None
) -> Callable[[_Registered], _Registered]:
    """Add one operation type to the registry. Module-private, deliberately.

    Generic in the class so the decorated name keeps its own type. Returning
    ``type[Operation]`` would erase every subclass to its base at every call
    site, which is a type checker being told to stop helping.

    ``citation_field`` is required here, and the provenance *classification*
    deliberately is not -- see the partition tables below.
    """

    def decorate(cls: _Registered) -> _Registered:
        if type_name in _REGISTRY:
            raise ValueError(f"{type_name} is registered twice")
        _REGISTRY[type_name] = OperationSpec(
            type_name=type_name, cls=cls, citation_field=citation_field
        )
        return cls

    return decorate


def expected_object_types(cls: type[Operation]) -> Mapping[str, str]:
    """For each reference field of ``cls``, the object type it must point at.

    Read off the dataclass field metadata, so it stays true of whatever the
    class actually declares rather than of a list kept beside it.
    """
    return MappingProxyType(
        {
            field.name: str(field.metadata[_EXPECTS])
            for field in fields(cls)
            if _EXPECTS in field.metadata
        }
    )


# ---------------------------------------------------------------------------
# The provenance partition
#
# ⚠️ **The classification is declared HERE, not passed to _register, and that
# is the point rather than an oversight.** A mandatory argument at registration
# would make the partition true by construction -- and a test that cannot fail
# is not the criterion. The criterion says a type in neither, or in both,
# FAILS THE TEST, which requires the classification to be losable. D3's
# "forced classification at registration" is a mechanism for the hypothetical
# open set, in a later phase; it is not this one's shape.
#
# Do not "simplify" this into the decorator.
# ---------------------------------------------------------------------------

FACT_ASSERTING: frozenset[str] = frozenset({"add_citation"})
"""Operations that assert a genealogical fact, and so must carry provenance."""

NON_FACT: Mapping[str, str] = MappingProxyType(
    {
        "add_note": (
            "a note records what a researcher observed or intends; it asserts nothing "
            "about a person that evidence could support, so it carries no citation field"
        ),
    }
)
"""Operations exempt from the provenance rule, each with why it is exempt.

The partition proves **totality, not correctness**: nothing here stops a
fact-asserting operation being filed on this side. The recorded rationale is
what a reviewer checks that against, which is why an empty one fails.
"""


# ⚠️ ``_register`` goes OUTSIDE ``@dataclass``. With ``slots=True`` the
# dataclass decorator returns a NEW class object, so registering underneath it
# files the half-built one and every consumer walks a class nobody uses.
# Asserted by test.


NOTE_TYPES: frozenset[str] = frozenset({"research", "todo"})
"""What a note is for. Closed, and a member of it is a PHASE_1 rule."""


class Phase(Enum):
    """Which phase is able to decide a rule."""

    PHASE_1 = "PHASE_1"
    PHASE_3 = "PHASE_3"


class RuleId(Enum):
    """Every rule this module knows about, on either side of the boundary."""

    REFERENCE_MISSING = "REFERENCE_MISSING"
    FIELD_EMPTY = "FIELD_EMPTY"
    OBJECT_TYPE_UNKNOWN = "OBJECT_TYPE_UNKNOWN"
    NOTE_TYPE_UNKNOWN = "NOTE_TYPE_UNKNOWN"
    HANDLE_MALFORMED = "HANDLE_MALFORMED"
    REFERENCE_WRONG_TYPE = "REFERENCE_WRONG_TYPE"

    # ⚠️ Declared, deliberately unimplemented, and NOT decorative. Without a
    # populated PHASE_3 side the criterion "no PHASE_3 rule can fire" is
    # vacuously true and proves nothing.
    TARGET_DOES_NOT_EXIST = "TARGET_DOES_NOT_EXIST"
    CITATION_DOES_NOT_EXIST = "CITATION_DOES_NOT_EXIST"
    REFERENCE_TYPE_MISMATCHES_TREE = "REFERENCE_TYPE_MISMATCHES_TREE"
    DUPLICATE_OF_EXISTING = "DUPLICATE_OF_EXISTING"


@dataclass(frozen=True, slots=True)
class RuleViolation:
    """One reason an operation is not well-formed.

    ``field_path`` is dotted and always names a field that exists on the
    operation, because a message pointing nowhere is a message nobody can act
    on. Asserted over every negative case.
    """

    rule: RuleId
    field_path: str
    message: str


@dataclass(frozen=True, slots=True)
class WellFormedResult:
    """What ``validate`` decided. Well-formed is **not** correct."""

    well_formed: bool
    violations: tuple[RuleViolation, ...]


@dataclass(frozen=True, slots=True)
class Rule:
    """One validation rule, declared with the phase that can decide it."""

    id: RuleId
    phase: Phase
    check: Callable[[Operation], tuple[RuleViolation, ...]] | None
    """``None`` for a PHASE_3 rule: declared here, decidable only with a tree."""


@_register("add_citation", citation_field="citation")
@dataclass(frozen=True, slots=True)
class AddCitation(Operation):
    """Attach evidence that already exists to an object that already exists."""

    target: ObjectRef | None = None
    citation: ObjectRef | None = field(default=None, metadata={_EXPECTS: OBJECT_TYPE_CITATION})


@_register("add_note", citation_field=None)
@dataclass(frozen=True, slots=True)
class AddNote(Operation):
    """A research note or a to-do, attached to any object.

    Carries no citation field, because it is on the exempt side of the
    partition -- a different kind of operation, not a weaker one.
    """

    target: ObjectRef | None = None
    note_type: str = ""
    text: str = ""


# ---------------------------------------------------------------------------
# Field paths, derived from the dataclasses rather than listed beside them
# ---------------------------------------------------------------------------


def reference_fields(cls: type[Operation]) -> tuple[str, ...]:
    """The fields of ``cls`` that hold a reference to another object."""
    hints = get_type_hints(cls)
    return tuple(field.name for field in fields(cls) if ObjectRef in get_args(hints[field.name]))


def required_paths(cls: type[Operation]) -> tuple[str, ...]:
    """Every dotted path of ``cls`` that must carry a value to be well-formed.

    Derived by walking the dataclass, so criterion 2's "one positive and one
    negative per required field" is *generated* for every type there will ever
    be. A list kept beside the class would be an enumeration, and it would go
    stale on the first field anyone adds.

    A reference contributes its own path *and* its leaves: an absent reference
    and an empty handle inside a present one are different failures, and a
    reviewer needs to be told which one happened.
    """
    references = reference_fields(cls)
    paths: list[str] = []
    for declared in fields(cls):
        paths.append(declared.name)
        if declared.name in references:
            paths.extend(f"{declared.name}.{leaf.name}" for leaf in fields(ObjectRef))
    return tuple(paths)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

_WHITESPACE_OR_CONTROL = re.compile(r"[\s\x00-\x1f\x7f]")
"""What a handle may not contain.

⚠️ Deliberately the whole of the rule. A Gramps handle is **opaque**, so a
length or a character class beyond "it is one printable token" would be
asserting a structure Gramps does not guarantee -- inventing a fact about
somebody else's format and then enforcing it. Reference *syntax* is all
Phase 1 has any standing to check.
"""


def _reference_missing(operation: Operation) -> tuple[RuleViolation, ...]:
    return tuple(
        RuleViolation(RuleId.REFERENCE_MISSING, name, f"{name} names no object")
        for name in reference_fields(type(operation))
        if getattr(operation, name) is None
    )


def _field_empty(operation: Operation) -> tuple[RuleViolation, ...]:
    violations = []
    for path in required_paths(type(operation)):
        value = _at(operation, path)
        if value is _ABSENT or value is None:
            # An absent reference is reported once, by _reference_missing.
            continue
        if isinstance(value, str) and not value.strip():
            violations.append(RuleViolation(RuleId.FIELD_EMPTY, path, f"{path} is empty"))
    return tuple(violations)


def _object_type_unknown(operation: Operation) -> tuple[RuleViolation, ...]:
    violations = []
    for name in reference_fields(type(operation)):
        reference = getattr(operation, name)
        if reference is None or not reference.object_type:
            continue
        if reference.object_type not in OBJECT_TYPES:
            violations.append(
                RuleViolation(
                    RuleId.OBJECT_TYPE_UNKNOWN,
                    f"{name}.object_type",
                    f"{reference.object_type!r} is not one of the object types there are",
                )
            )
    return tuple(violations)


def _note_type_unknown(operation: Operation) -> tuple[RuleViolation, ...]:
    note_type = getattr(operation, "note_type", "")
    if not note_type or note_type in NOTE_TYPES:
        return ()
    return (
        RuleViolation(
            RuleId.NOTE_TYPE_UNKNOWN,
            "note_type",
            f"{note_type!r} is not one of the note types there are",
        ),
    )


def _handle_malformed(operation: Operation) -> tuple[RuleViolation, ...]:
    violations = []
    for name in reference_fields(type(operation)):
        reference = getattr(operation, name)
        if reference is None or not reference.handle:
            continue
        if _WHITESPACE_OR_CONTROL.search(reference.handle):
            violations.append(
                RuleViolation(
                    RuleId.HANDLE_MALFORMED,
                    f"{name}.handle",
                    "a handle is one printable token and this one is not",
                )
            )
    return tuple(violations)


def _reference_wrong_type(operation: Operation) -> tuple[RuleViolation, ...]:
    # Internal consistency, and derived from the field metadata rather than
    # written per type -- so #22 and #23 inherit it without touching this.
    violations = []
    for name, expected in expected_object_types(type(operation)).items():
        reference = getattr(operation, name)
        if reference is None or not reference.object_type:
            continue
        if reference.object_type != expected:
            violations.append(
                RuleViolation(
                    RuleId.REFERENCE_WRONG_TYPE,
                    f"{name}.object_type",
                    f"{name} must reference a {expected}, not a {reference.object_type}",
                )
            )
    return tuple(violations)


RULES: tuple[Rule, ...] = (
    Rule(RuleId.REFERENCE_MISSING, Phase.PHASE_1, _reference_missing),
    Rule(RuleId.FIELD_EMPTY, Phase.PHASE_1, _field_empty),
    Rule(RuleId.OBJECT_TYPE_UNKNOWN, Phase.PHASE_1, _object_type_unknown),
    Rule(RuleId.NOTE_TYPE_UNKNOWN, Phase.PHASE_1, _note_type_unknown),
    Rule(RuleId.HANDLE_MALFORMED, Phase.PHASE_1, _handle_malformed),
    Rule(RuleId.REFERENCE_WRONG_TYPE, Phase.PHASE_1, _reference_wrong_type),
    # The other side of the boundary. Declared so it is visible and reviewable,
    # unimplemented because none of it is decidable without a tree.
    Rule(RuleId.TARGET_DOES_NOT_EXIST, Phase.PHASE_3, None),
    Rule(RuleId.CITATION_DOES_NOT_EXIST, Phase.PHASE_3, None),
    Rule(RuleId.REFERENCE_TYPE_MISMATCHES_TREE, Phase.PHASE_3, None),
    Rule(RuleId.DUPLICATE_OF_EXISTING, Phase.PHASE_3, None),
)
"""The frozen rule table. This IS the validator's program, not a description.

⚠️ The phase filter lives in ``_run`` and nowhere else. That single choke
point is what makes "no PHASE_3 rule can fire" a structural property rather
than something sampled over whatever cases a test happened to try.
"""


_ABSENT = object()


def _at(operation: Operation, path: str) -> object:
    """The value at a dotted path, or ``_ABSENT`` if a reference along it is."""
    value: object = operation
    for step in path.split("."):
        if value is None:
            return _ABSENT
        value = getattr(value, step)
    return value


def _run(rules: Sequence[Rule], operation: Operation) -> WellFormedResult:
    """Apply every PHASE_1 rule in ``rules`` and accumulate what they say.

    Every rule runs: there is no early return, because an operation with three
    faults must report three faults. Fixing them one round trip at a time is
    the behaviour this accumulation exists to prevent.
    """
    violations = [
        violation
        for rule in rules
        if rule.phase is Phase.PHASE_1 and rule.check is not None
        for violation in rule.check(operation)
    ]
    return WellFormedResult(well_formed=not violations, violations=tuple(violations))


def validate(operation: Operation) -> WellFormedResult:
    """Decide whether ``operation`` is **well-formed**. Not whether it is correct.

    Shape only. Nothing here asks whether a referenced object exists, whether
    it is the right one, or whether this duplicates something already in the
    tree -- those are declared on the PHASE_3 side of ``RULES`` and cannot
    fire from here.
    """
    return _run(RULES, operation)
