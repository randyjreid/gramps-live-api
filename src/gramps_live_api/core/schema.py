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
from collections.abc import Callable, Iterator, Mapping, Sequence
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

_PREVIEW_TEXT_LIMIT = 60
"""How much of a free-text value a one-line preview carries before eliding."""


def _named(reference: ObjectRef | None) -> str:
    """A reference as a person reads it: what kind of thing, and which one.

    ⚠️ **The handle is deliberately absent and must stay absent.** It is
    machine identity; naming it here is the one thing criterion 7 rules out
    outright, because an operation identified by an opaque string cannot be
    checked against a record by the person approving it.
    """
    if reference is None:
        return "an object that was not named"
    kind = reference.object_type or "object"
    return f"{kind} {reference.gramps_id}" if reference.gramps_id else f"an unidentified {kind}"


def _identified(reference: ObjectRef | None) -> str:
    """A reference where the sentence has already said what kind of thing it is.

    ``cite citation C0042`` is what naming the kind twice reads like, and a
    sentence a reviewer trips over is one they stop reading. Same guarantee as
    ``_named``: the identifier, never the handle.
    """
    if reference is None:
        return "an object that was not named"
    return reference.gramps_id or f"an unidentified {reference.object_type or 'object'}"


def _shortened(text: str) -> str:
    """Free text, quoted, and cut to something a single line can hold."""
    collapsed = " ".join(text.split())
    if not collapsed:
        return "(no text)"
    if len(collapsed) > _PREVIEW_TEXT_LIMIT:
        collapsed = collapsed[: _PREVIEW_TEXT_LIMIT - 1].rstrip() + "…"
    return f"“{collapsed}”"


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

    def render(self) -> str:
        """One sentence describing what this operation would do.

        Called only through ``preview``, which applies the single-line rule.
        An override returns whatever reads best; it does not have to remember
        to strip newlines, and that is the point of the choke point.
        """
        raise NotImplementedError


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
    FIELD_NULL = "FIELD_NULL"
    FIELD_WRONG_TYPE = "FIELD_WRONG_TYPE"
    OBJECT_TYPE_UNKNOWN = "OBJECT_TYPE_UNKNOWN"
    NOTE_TYPE_UNKNOWN = "NOTE_TYPE_UNKNOWN"
    HANDLE_MALFORMED = "HANDLE_MALFORMED"

    # ⚠️ Not the same rule as FIELD_WRONG_TYPE and not a near-duplicate of it.
    # This one is about WHAT A REFERENCE POINTS AT -- a citation field aimed at
    # a source -- where both values are perfectly typed strings. FIELD_WRONG_TYPE
    # is about the Python type of a value the wire delivered.
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

    def render(self) -> str:
        return f"cite {_identified(self.citation)} as evidence for {_named(self.target)}"


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

    def render(self) -> str:
        return f"add a {self.note_type} note to {_named(self.target)}: {_shortened(self.text)}"


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


def _declared_at(cls: type, path: str) -> tuple[tuple[type, ...], bool]:
    """The types ``path`` may hold on ``cls``, and whether ``None`` is one of them.

    Read off the declaration, like everything else in this section, and that is
    what makes the ONE documented skip fall out by construction instead of
    being restated: a field whose declared type admits ``None`` is
    ``_reference_missing``'s business, and today those are exactly the
    reference roots. An enumeration of "the fields that may be absent" would be
    the same fact pointed backwards -- correct now, and wrong the day a type
    declares an optional scalar.
    """
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


def _present_references(operation: Operation) -> Iterator[tuple[str, ObjectRef]]:
    """Every reference field of ``operation`` that really holds an ``ObjectRef``.

    ⚠️ **The choke point behind all three reference rules, and it is the point
    rather than a convenience.** A value of the wrong type is one rule's
    business -- ``_field_wrong_type`` reports it once, at its own path -- and
    every other rule ignores what it cannot judge. Three rules each remembering
    to check the type is three chances to forget, and the one that forgot raised
    a ``TypeError`` out of the validator: not a verdict, not a field path, and
    not something a caller can do anything with.
    """
    for name in reference_fields(type(operation)):
        reference = getattr(operation, name)
        if isinstance(reference, ObjectRef):
            yield name, reference


def _text(value: object) -> str:
    """``value`` if it is text, and the empty string if it is not.

    Same principle as ``_present_references``, one level down: a rule about the
    *content* of a string has nothing to say about a value that is not one, and
    it must not put that value into its message either -- a wire payload echoed
    into a violation is content this repository then has to scan.
    """
    return value if isinstance(value, str) else ""


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
            # Absence is not emptiness, and neither is this rule's business:
            # _reference_missing reports an absent reference root and
            # _field_null reports every other None, each once and by name.
            continue
        if isinstance(value, str) and not value.strip():
            violations.append(RuleViolation(RuleId.FIELD_EMPTY, path, f"{path} is empty"))
    return tuple(violations)


def _field_null(operation: Operation) -> tuple[RuleViolation, ...]:
    # A null the payload CARRIES, which is a different fault from a key it
    # omits: deserialisation cannot refuse it without becoming a second
    # validator with no field path, so validate has to be the one that judges
    # it. Skipping it is how well_formed=True is returned for an operation
    # missing a required value.
    violations = []
    for path in required_paths(type(operation)):
        if _at(operation, path) is not None:
            continue
        if _declared_at(type(operation), path)[1]:
            # The one skip there is, and it is the declaration's word rather
            # than a list kept here: a field that MAY hold None is reported by
            # _reference_missing when it does.
            continue
        violations.append(RuleViolation(RuleId.FIELD_NULL, path, f"{path} is null"))
    return tuple(violations)


def _field_wrong_type(operation: Operation) -> tuple[RuleViolation, ...]:
    # What the wire delivered is not what the field declares. Deserialisation
    # cannot refuse it without becoming a second validator with no field path,
    # so validate judges it -- and judges it ONCE, here, which is what lets every
    # other rule ignore a value it has nothing to say about.
    violations = []
    for path in required_paths(type(operation)):
        value = _at(operation, path)
        if value is _ABSENT or value is None:
            continue
        permitted, _ = _declared_at(type(operation), path)
        if not permitted or isinstance(value, permitted):
            continue
        declared = " or ".join(candidate.__name__ for candidate in permitted)
        violations.append(
            RuleViolation(
                RuleId.FIELD_WRONG_TYPE,
                path,
                # ⚠️ TYPE NAMES ONLY. The value is NOT named, and that is a
                # privacy decision rather than a formatting one: a wire payload
                # echoed into a message becomes content the guard has to read,
                # in a public repository whose previous phase was about exactly
                # that. The type is what a caller needs to fix it anyway.
                f"{path} is {type(value).__name__} where {declared} is declared",
            )
        )
    return tuple(violations)


def _object_type_unknown(operation: Operation) -> tuple[RuleViolation, ...]:
    violations = []
    for name, reference in _present_references(operation):
        object_type = _text(reference.object_type)
        if not object_type or object_type in OBJECT_TYPES:
            continue
        violations.append(
            RuleViolation(
                RuleId.OBJECT_TYPE_UNKNOWN,
                f"{name}.object_type",
                f"{object_type!r} is not one of the object types there are",
            )
        )
    return tuple(violations)


def _note_type_unknown(operation: Operation) -> tuple[RuleViolation, ...]:
    note_type = _text(getattr(operation, "note_type", ""))
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
    for name, reference in _present_references(operation):
        handle = _text(reference.handle)
        if not handle:
            continue
        if _WHITESPACE_OR_CONTROL.search(handle):
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
    expected_types = expected_object_types(type(operation))
    violations = []
    for name, reference in _present_references(operation):
        expected = expected_types.get(name)
        object_type = _text(reference.object_type)
        if expected is None or not object_type or object_type == expected:
            continue
        violations.append(
            RuleViolation(
                RuleId.REFERENCE_WRONG_TYPE,
                f"{name}.object_type",
                f"{name} must reference a {expected}, not a {object_type}",
            )
        )
    return tuple(violations)


RULES: tuple[Rule, ...] = (
    Rule(RuleId.REFERENCE_MISSING, Phase.PHASE_1, _reference_missing),
    Rule(RuleId.FIELD_EMPTY, Phase.PHASE_1, _field_empty),
    Rule(RuleId.FIELD_NULL, Phase.PHASE_1, _field_null),
    Rule(RuleId.FIELD_WRONG_TYPE, Phase.PHASE_1, _field_wrong_type),
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
    """The value at a dotted path, or ``_ABSENT`` if a step along it cannot resolve.

    A reference that is absent stops the walk, and so does one of the wrong
    type: either way the fault belongs to the path that CARRIES it, reported
    once there rather than again at every leaf underneath. ``required_paths``
    comes from ``fields``, so a well-typed operation always resolves every step
    and this can only be reached by a fault reported elsewhere.
    """
    value: object = operation
    for step in path.split("."):
        if value is None or not hasattr(value, step):
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


# ---------------------------------------------------------------------------
# Serialisation
#
# ⚠️ **Two error surfaces, and the line between them is load-bearing.**
#
# A STRUCTURAL fault -- a key nobody declared, a payload naming no operation
# type or an unregistered one -- RAISES. There is no operation to hand back
# and no field path to hang a violation on.
#
# A VALUE fault -- a declared key that is absent, empty or wrong -- does NOT
# raise. It deserialises to the field's empty default and ``validate`` reports
# it with a field path. If deserialisation refused these instead, validate
# could never see them and every negative case would be unreachable from the
# wire, which is the same defect as having two validators.
# ---------------------------------------------------------------------------

TYPE_KEY = "type"
"""The key naming which operation a payload is."""


class SchemaError(Exception):
    """A payload that is not an operation at all."""


class UnknownFieldError(SchemaError):
    """A payload carrying a field no operation declares.

    Rejected rather than ignored: a misspelled key silently dropped means the
    operation that executes is not the one that was agreed, and nothing
    anywhere says so.
    """

    def __init__(self, field_path: str) -> None:
        super().__init__(f"{field_path} is not a field of this operation")
        self.field_path = field_path


def type_name_of(operation: Operation) -> str:
    """The wire name of ``operation``'s type."""
    for name, spec in REGISTRY.items():
        if spec.cls is type(operation):
            return name
    raise SchemaError(f"{type(operation).__name__} is not a registered operation")


def to_dict(operation: Operation) -> dict[str, object]:
    """``operation`` as a JSON-shaped mapping, every declared field present."""
    payload: dict[str, object] = {TYPE_KEY: type_name_of(operation)}
    for declared in fields(operation):
        value = getattr(operation, declared.name)
        payload[declared.name] = (
            {leaf.name: getattr(value, leaf.name) for leaf in fields(ObjectRef)}
            if isinstance(value, ObjectRef)
            else value
        )
    return payload


def from_dict(payload: Mapping[str, object]) -> Operation:
    """Build the operation ``payload`` describes, refusing what it cannot be."""
    type_name = payload.get(TYPE_KEY)
    if not isinstance(type_name, str):
        raise SchemaError(f"a payload must name its operation under {TYPE_KEY!r}")
    if type_name not in REGISTRY:
        raise SchemaError(f"{type_name!r} is not a registered operation type")

    cls = REGISTRY[type_name].cls
    declared = {field.name for field in fields(cls)}
    references = set(reference_fields(cls))

    for key in payload:
        if key != TYPE_KEY and key not in declared:
            raise UnknownFieldError(key)

    arguments: dict[str, object] = {}
    for name in declared:
        if name not in payload:
            continue
        value = payload[name]
        arguments[name] = _reference_from(name, value) if name in references else value
    return cls(**arguments)


def _reference_from(name: str, value: object) -> ObjectRef | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError(f"{name} must be a reference or absent")

    leaves = {leaf.name for leaf in fields(ObjectRef)}
    for key in value:
        if key not in leaves:
            # Named by full path: a refusal reporting only the leaf points at
            # the wrong level, and criterion 6 asks for both depths.
            raise UnknownFieldError(f"{name}.{key}")
    return ObjectRef(**value)


def preview(operation: Operation) -> str:
    """One line describing what ``operation`` would do, for a person to approve.

    ⚠️ **The single-line rule is applied HERE and nowhere else.** Nine
    renderers each remembering to strip newlines is nine chances to forget;
    one choke point is a property. Dispatch goes through the registry, so
    something that is not a registered operation is refused rather than
    rendered as whatever its class happens to say.

    ⚠️ **Precondition: ``operation`` has passed ``validate``.** This renders a
    sentence for a person to approve; it is not a second judge and does not
    check its input. A renderer given a value ``validate`` would have rejected
    may raise, and that is by design -- making it total would mean rendering
    arbitrary wire values for the benefit of a caller who skipped the judge,
    which is the second-vocabulary shape this module refuses everywhere else.
    The precondition is stated because an unstated one becomes somebody's defect
    later.
    """
    type_name_of(operation)  # refuses anything unregistered
    return " ".join(operation.render().split())


def validate(operation: Operation) -> WellFormedResult:
    """Decide whether ``operation`` is **well-formed**. Not whether it is correct.

    Shape only. Nothing here asks whether a referenced object exists, whether
    it is the right one, or whether this duplicates something already in the
    tree -- those are declared on the PHASE_3 side of ``RULES`` and cannot
    fire from here.
    """
    return _run(RULES, operation)
