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

No violation this module reports repeats a value the payload carried; the rule
and its reason are stated on ``RuleViolation``, which is where a new rule's
author meets it.

The registry is **closed**: there is no public registration function and
``REGISTRY`` is a read-only mapping. A closed set is what makes the provenance
partition assertable at all -- an open one makes this module's most important
property unfalsifiable.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import TypeVar, get_args, get_type_hints

from gramps_live_api.core._unrenderable import UNRENDERABLE_RANGES

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


@dataclass(frozen=True, slots=True)
class Fragment:
    """One piece of a rendered sentence, and the field whose value it is.

    ⚠️ **A renderer returns pieces rather than a string so that WHICH FIELD
    PRODUCED WHICH TEXT survives into the guard.** The alternative -- render a
    flat string, then match an offending character back against the operation's
    values -- cannot answer the question it is being asked: two fields carrying
    the same character are indistinguishable to a search, so it reports whichever
    the walk reaches first. That is an attribution by declaration order dressed
    up as an attribution by evidence, and it named fields whose correction
    changed nothing.

    ``field_path`` is the dotted path of the field this text came from, or
    ``None`` for the wording this module wrote itself. Both cases are
    load-bearing: the second is how the guard knows a character came from *our*
    renderer rather than from a payload, and so must not name a field at all.
    """

    text: str
    field_path: str | None = None


def _own(text: str) -> Fragment:
    """Wording this module wrote. No field carries it, so none is named for it."""
    return Fragment(text)


def _carried(path: str, text: str) -> Fragment:
    """Text that came from the field at ``path``, which is what a refusal names.

    ⚠️ **``path`` must be spelled as ``required_paths`` spells it**, because
    that is the vocabulary every other message in this module reports in.
    Asserted per registered type, so a mistyped prefix fails a test rather than
    reaching a reader as a field they cannot find.
    """
    return Fragment(text, path)


def _named(reference: ObjectRef | None, path: str) -> tuple[Fragment, ...]:
    """A reference as a person reads it: what kind of thing, and which one.

    ⚠️ **The handle is deliberately absent and must stay absent.** It is
    machine identity; naming it here is the one thing criterion 7 rules out
    outright, because an operation identified by an opaque string cannot be
    checked against a record by the person approving it. It contributes no
    fragment, which is also why no refusal can name it: a field the sentence
    never carries is not one the rendering guard has anything to say about.
    """
    if reference is None:
        return (_own("an object that was not named"),)
    kind = (
        _carried(f"{path}.object_type", reference.object_type)
        if reference.object_type
        else _own("object")
    )
    if reference.gramps_id:
        return (kind, _own(" "), _carried(f"{path}.gramps_id", reference.gramps_id))
    return (_own("an unidentified "), kind)


def _identified(reference: ObjectRef | None, path: str) -> tuple[Fragment, ...]:
    """A reference where the sentence has already said what kind of thing it is.

    ``cite citation C0042`` is what naming the kind twice reads like, and a
    sentence a reviewer trips over is one they stop reading. Same guarantee as
    ``_named``: the identifier, never the handle.
    """
    if reference is None:
        return (_own("an object that was not named"),)
    if reference.gramps_id:
        return (_carried(f"{path}.gramps_id", reference.gramps_id),)
    if reference.object_type:
        return (_own("an unidentified "), _carried(f"{path}.object_type", reference.object_type))
    return (_own("an unidentified object"),)


def _shortened(text: str, path: str) -> tuple[Fragment, ...]:
    """Free text, quoted, and cut to something a single line can hold.

    ⚠️ **Only what survives the elision is attributed**, because only that
    reaches the sentence. The recorded residual -- a character past the limit is
    never emitted, and a guard over what we DISPLAY has nothing to say about it
    -- is true here by construction rather than by the guard happening to scan
    a string the elision had already shortened.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return (_own("(no text)"),)
    if len(collapsed) > _PREVIEW_TEXT_LIMIT:
        kept = collapsed[: _PREVIEW_TEXT_LIMIT - 1].rstrip()
        return (_own("“"), _carried(path, kept), _own("…”"))
    return (_own("“"), _carried(path, collapsed), _own("”"))


def _quoted(text: str, path: str) -> tuple[Fragment, ...]:
    """Free text in full: the UN-ELIDED twin of ``_shortened``.

    ⚠️ **This exists because the elision reached further than display.** The
    approval compared rendered sentences, so two notes sharing a 59-character
    prefix produced one sentence, and everything past it was written without
    ever having been approved or shown. The binding is now over the operation
    (see ``core.apply``), and this is the other half: what the person is shown
    before the prompt has to be everything the tree will receive.

    Same whitespace normalisation as ``_shortened`` and for the same reason --
    the rendering guard reads what is EMITTED, and matching that normalisation
    is what makes reading provenance off the fragments equivalent to scanning
    the finished string.

    ⚠️ **Recorded residual: whitespace is the one thing display and storage
    still differ on.** A note carrying newlines or runs of spaces is shown
    collapsed and stored as written. That is a deliberate trade rather than an
    oversight: emitting the raw text would put a carriage return on a terminal,
    which overwrites the line it is on and can hide the content this function
    exists to reveal. Content is complete; layout is not preserved.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return (_own("(no text)"),)
    return (_own("“"), _carried(path, collapsed), _own("”"))


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

    def render(self) -> tuple[Fragment, ...]:
        """One sentence describing what this operation would do, in pieces.

        Called only through ``preview``, which joins the pieces and applies the
        single-line rule. An override returns whatever reads best; it does not
        have to remember to strip newlines, and that is the point of the choke
        point.

        ⚠️ **Every piece built from a field's value names that field.** The
        rendering guard reports the field a refused character came from, and it
        reads that off these fragments rather than searching the operation for
        the character afterwards -- a search cannot tell two rendered fields
        carrying the same character apart, and answers by declaration order. A
        renderer that inlines a value without naming its path leaves the guard
        with nothing to name, which fails the generated matrix in
        ``test_schema_preview_guard.py`` rather than degrading quietly.
        """
        raise NotImplementedError

    def full(self) -> tuple[Fragment, ...]:
        """Everything this operation would write, with nothing elided.

        Called only through ``full_display``, which a caller shows before asking
        for approval. The default IS ``render`` -- an operation carrying no
        elided field shows the same thing twice, and saying so here means a new
        operation type is covered without its author having to think about it.

        ⚠️ **Override this wherever ``render`` elides.** An operation whose
        renderer shortens a value and does not override here would be approved
        against a summary again, which is the defect this pair exists to close.
        """
        return self.render()


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

    ⚠️ **NOTHING ON A VIOLATION REPEATS A VALUE THE PAYLOAD CARRIED.** Not the
    message, not the field path. A violation names the field, and where it
    helps the **allowed set** or the **declared type** -- never what arrived.

    This is a privacy decision and not a formatting one. A wire payload echoed
    into a violation becomes content this repository then has to scan, in a
    public repository whose previous phase existed to keep exactly that out;
    and any caller that logs or serialises a validation failure would be the
    thing that published it. An operation payload is precisely where
    genealogical data will live once this vocabulary is in use.

    **The module's own vocabulary may be named** -- ``OBJECT_TYPES``,
    ``NOTE_TYPES``, the type a field declares. That is ours rather than the
    caller's, and naming what *is* permitted is what makes a violation
    actionable while leaking nothing. Do not instead truncate, redact or
    fingerprint the rejected value: a truncated payload is still payload, and a
    redaction mechanism here would be a second, weaker copy of one ``pii_guard``
    already owns.

    Asserted structurally over generated wire cases -- every registered type,
    every required path -- in ``tests/unit/test_schema_violation_privacy.py``,
    because three rules obeying this is not the same property as the module
    obeying it.
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

    def render(self) -> tuple[Fragment, ...]:
        return (
            _own("cite "),
            *_identified(self.citation, "citation"),
            _own(" as evidence for "),
            *_named(self.target, "target"),
        )


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

    def render(self) -> tuple[Fragment, ...]:
        return (
            _own("add a "),
            _carried("note_type", self.note_type),
            _own(" note to "),
            *_named(self.target, "target"),
            _own(": "),
            *_shortened(self.text, "text"),
        )

    def full(self) -> tuple[Fragment, ...]:
        """The same sentence with the note's text entire, because ``render`` elides it."""
        return (
            _own("add a "),
            _carried("note_type", self.note_type),
            _own(" note to "),
            *_named(self.target, "target"),
            _own(": "),
            *_quoted(self.text, "text"),
        )


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


def _one_of(vocabulary: frozenset[str]) -> str:
    """A closed set of this module's own, written out for a caller to read.

    The half of ``RuleViolation``'s rule that says what a message MAY carry: a
    violation that names only the field tells a caller where the fault is and
    not what would fix it, and the permitted set is ours rather than the
    payload's.

    ``sorted`` is load-bearing. A ``frozenset`` iterates in an order that
    depends on ``PYTHONHASHSEED``, so joining it unsorted gives a message that
    changes between runs -- undiffable in a log, and untestable by equality.
    """
    return ", ".join(sorted(vocabulary))


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
                # Type names only, per the rule on RuleViolation: the field and
                # what was expected, never what arrived. The type is what a
                # caller needs to fix it anyway.
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
        path = f"{name}.object_type"
        violations.append(
            RuleViolation(
                RuleId.OBJECT_TYPE_UNKNOWN,
                path,
                f"{path} is not one of the object types there are: {_one_of(OBJECT_TYPES)}",
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
            f"note_type is not one of the note types there are: {_one_of(NOTE_TYPES)}",
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
                f"{name} must reference a {expected}",
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


# ---------------------------------------------------------------------------
# What a preview may put on screen
#
# ``preview`` renders the one sentence a person reads and approves BEFORE
# anything is written to a tree, which is this project's whole review model:
# what was agreed and what is written are provably the same thing. A character
# that REORDERS or HIDES part of that sentence -- a bidirectional override, a
# zero-width character -- attacks the agreement step itself, because the
# reviewer approves one sentence and a different one is what the operation says.
#
# ⚠️ **The guard is over what ``preview`` EMITS, not over what any field may
# hold.** It reads the rendered sentence, so every rendered field is covered at
# once and a field added to an operation later is covered without this being
# edited. The alternative -- a character rule per field at validation time --
# was weighed and rejected: nothing here can establish what characters Gramps
# emits in an opaque identifier, and a rendering guard does not need to. It
# constrains what we DISPLAY, not what we accept.
#
# ---------------------------------------------------------------------------
# What this costs, and what it does not reach. Recorded rather than carved
# around, because each of these is a residual somebody should meet here instead
# of discovering it.
#
# ⚠️ **The class refuses characters some scripts need.** The zero-width
# non-joiner and joiner (U+200C, U+200D) are required by Persian and Indic
# text, and they are the same general category as the ones that hide a sentence
# from its reader. **So a legitimate note in those scripts becomes
# unpreviewable, and therefore unapprovable.** That is a real cost and it is
# taken as a stated trade: no published definition separates
# invisible-and-dangerous from invisible-and-legitimate, because the same
# characters are both. Carving the joiners out by hand would be the enumeration
# pointed backwards -- a known-safe list, failing by admitting whatever nobody
# carved. If this ever needs narrowing it needs a ruling with evidence, not an
# exemption added here.
#
# ⭐ **That cost is WIDER since the class became the union with
# Default_Ignorable_Code_Point, and the extra characters are ordinary script
# data, not formatting.** Refused now, and every one of them is used
# legitimately:
#
#   - the **Mongolian free variation selectors** (U+180B-U+180D, U+180F), which
#     select the positional form of a Mongolian letter;
#   - the **variation selectors** (U+FE00-U+FE0F, U+E0100-U+E01EF), which are
#     how an ideographic variation sequence names one of several published
#     glyphs for a Han character -- exactly the kind of thing a genealogical
#     source spells a surname with;
#   - the **Hangul fillers** (U+115F, U+1160, U+3164, U+FFA0), which stand in
#     for an absent jamo in an incomplete syllable;
#   - the **combining grapheme joiner** (U+034F) and the Khmer vowel inherent
#     signs (U+17B4-U+17B5).
#
# **This is a real cost to legitimate script data and it is not negligible.**
# The trade is taken deliberately and on one ground: in a *rendered identifier*
# an invisible character is precisely the risk this guard exists for. A
# reviewer approves a sentence they can read, and a character that occupies no
# space is one the sentence does not show them -- whatever role it plays in a
# font. A reader who needs this reversed should find the reasoning here rather
# than a shrug: it needs a ruling with evidence, and the evidence would be
# about which of these can appear in a Gramps identifier or a note that a
# person still has to check against a record.
#
# ⚠️ **Truncation USED to mean a hidden character went unrefused, and that
# residual is now retired rather than merely qualified.** It read: ``_shortened``
# elides free text, so a character past the limit is never emitted, and a guard
# over what we DISPLAY has nothing to say about a character that reaches no
# screen. The premise was true of ``preview`` alone.
#
# ``full_display`` emits the text entire, because a person cannot approve what
# they were not shown, so a character past the elision point now DOES reach a
# screen -- and the guard runs over those fragments too. The reasoning was sound
# and its premise stopped holding the moment a second display site existed; it is
# rewritten here rather than left for a reader to inherit as still-true.
#
# ⚠️ **Implicit reordering is not covered, and must not be.** A strong
# right-to-left letter -- an ordinary name, category Lo -- reorders the neutral
# characters around it under UAX #9 with no formatting character present at
# all, and it is nowhere near this class. Covering it would mean refusing
# legitimate names, in a genealogy tool. That mitigation belongs to whatever
# eventually displays the sentence, which can isolate each field; it is not
# available to a function that returns a string.
#
# ⚠️ **The class no longer depends on the interpreter, and what it costs
# instead is a PIN.** The verdict used to move between the Unicode databases
# CPython bundles -- 139,742 / 139,744 / 139,751 code points on 3.10 / 3.11 /
# 3.12, nine of them flipping, with the older interpreter the permissive side.
# It is now a committed derived table (``_unrenderable.py``, generated by
# ``scripts/derive_unrenderable.py``, provenance in
# ``docs/schema-render-guard-derivation.md``): 143,787 code points, identical
# on all three, measured rather than argued. The two prices of that:
#
#   - **The table is pinned NEWER than any interpreter here bundles**, at
#     Unicode 17.0.0 against UCD 13.0.0 / 14.0.0 / 15.0.0. So the guard refuses
#     code points the running interpreter calls unassigned -- **3,779 / 3,776 /
#     3,769** of them respectively. That is deliberate and it is fail-closed:
#     the standard has assigned them, and a display stack newer than the
#     service will act on them. It is the direction the old residual could not
#     choose, because the old class had no version of its own.
#   - **The class is a fact about ONE release and does not track a later one
#     until somebody re-derives it.** That is the mirror image of the residual
#     this replaces: determinism bought with staleness. A character assigned
#     after 17.0.0 is emitted until the table is regenerated -- a fail-OPEN,
#     bounded by the standard's release cadence and visible in a diff, which
#     the old dependence was neither. Re-derivation is one command over two
#     artifacts and it is written down.
#
# **Both deterministic alternatives were still weighed and rejected, and this
# stays so the next reader does not reach for them.** Pinning an explicit set
# of format characters *here* is the enumeration this module refuses
# everywhere else -- it fails open on whatever the standard assigns next, with
# nothing to re-derive. Inverting to a safe-to-display set is that enumeration
# pointed backwards, failing closed on legitimate text nobody listed. **A
# derived table is neither**: what it enumerates is a published property at a
# named version, so it fails open only until it is regenerated, and the
# regeneration is mechanical.
# ---------------------------------------------------------------------------

_RANGE_STARTS: tuple[int, ...] = tuple(first for first, _, _ in UNRENDERABLE_RANGES)
"""Where each committed range begins, for the lookup below.

Derived from the table rather than written beside it, so the two cannot drift.
A frozenset of the ~139,700 code points was rejected on memory grounds; a
bisect over 41 rows answers in ``O(log n)``.
"""


def _class_of(character: str) -> str | None:
    """Which published fact puts ``character`` in the class, or ``None``.

    **The class is a committed derived table, not a question put to the running
    interpreter.** ``_unrenderable.py`` is generated by
    ``scripts/derive_unrenderable.py`` from two artifacts of one published
    Unicode release, whose digests the module carries and whose provenance is
    in ``docs/schema-render-guard-derivation.md``. The verdict is therefore a
    fact about the standard, and the same operation previews the same way on
    every interpreter this project supports -- measured, not assumed.

    **The class is the UNION of two published facts**, because neither contains
    the other:

    - the General_Category values ``Cc``, ``Cf``, ``Co`` and ``Cs`` of UAX #44,
      where the explicit directional formatting characters of the Bidirectional
      Algorithm (UAX #9) live, along with the zero-width characters, the
      controls, the surrogates and the private-use areas;
    - the derived core property ``Default_Ignorable_Code_Point``, which reaches
      **outside** that group -- U+034F is ``Mn``, U+115F and U+1160 are ``Lo``,
      and all three render as nothing at all.

    A class written as the group alone emitted every one of those; a class
    written as the property alone would emit the controls and the surrogates.

    ⚠️ **``Cn`` is absent because nothing selects it, not because a clause
    excludes it.** Unassigned code points ARE stated explicitly in the
    general-category artifact; the derivation names the four categories it
    wants, so unassigned and every readable category are left out by the same
    structure. There is no ``!= "Cn"`` anywhere to get wrong, and round 3's
    arithmetic about which direction that exclusion failed in no longer has
    anything to weigh -- the class does not move between interpreters at all.

    ⚠️ **Do not add a case here, and do not hand-edit the table.** A character
    this guard should refuse and does not is a re-derivation against a newer
    release, or a defect in the derivation script -- both of which are visible
    in a diff. A case added by hand is the enumeration this module refuses
    everywhere else, and it would make the committed table stop being the class.

    Returns the label the table carries, which is what the refusal names, so a
    caller never has to ask a second source what it just refused.
    """
    code_point = ord(character)
    position = bisect.bisect_right(_RANGE_STARTS, code_point) - 1
    if position < 0:
        return None
    _, last, label = UNRENDERABLE_RANGES[position]
    return label if code_point <= last else None


def _is_unrenderable(character: str) -> bool:
    """Whether ``character`` can reorder or hide text in a sentence for review.

    See ``_class_of``, which is the same question with the answer kept.
    """
    return _class_of(character) is not None


class UnrenderableFieldError(SchemaError):
    """A field whose value cannot be put in front of a reviewer as it stands.

    Carries a field path for the reason ``UnknownFieldError`` does: a refusal
    that does not say where the fault is, is one nobody can act on.

    ⚠️ **The message names the field and the published fact that refused the
    character, never the character itself** -- the rule on ``RuleViolation``,
    which this obeys for the same reason. Naming the *class* is the same move
    ``_field_wrong_type`` already makes when it names the arrived value's type:
    what a caller needs to fix it, without echoing what arrived.

    ⚠️ **``category`` is read off the committed table and is not a call to the
    running interpreter.** It used to be ``unicodedata.category``, and under a
    pinned table that would report ``Cn`` for a code point the table guards as
    ``Cf`` -- a refusal naming the one category the class does not hold, which
    is worse than naming nothing. So the value is a General_Category value or
    ``Default_Ignorable_Code_Point``: the attribute keeps its meaning and gains
    one value that is not a category, because one half of the class is not one.
    """

    def __init__(self, field_path: str, category: str) -> None:
        super().__init__(
            f"{field_path} carries a {category} character, "
            "which can reorder or hide text in a sentence for review"
        )
        self.field_path = field_path
        self.category = category


def _emitted(fragment: Fragment) -> str:
    """What ``fragment`` actually puts on screen, after the single-line rule.

    ⚠️ **The same normalisation ``preview`` applies to the whole sentence, and
    it must stay the same one.** Collapsing only deletes or normalises
    whitespace, so the non-whitespace characters a fragment contributes are
    identical either way -- which is what makes reading provenance off the
    fragments equivalent to scanning the finished string, rather than a wider
    check wearing its clothes. Scanning the raw text instead would newly refuse
    the control characters that ARE whitespace, which the single-line rule
    removes before anything reaches a screen.
    """
    return " ".join(fragment.text.split())


def _refuse_unrenderable(fragments: Sequence[Fragment]) -> None:
    """Refuse the sentence if a fragment carries a character that reorders or hides it.

    Attribution is read off the fragment that produced the character, so a
    refusal names the field whose correction changes the outcome. Deterministic
    in both directions: the first fragment in the order a person READS the
    sentence, and the first offending character within it. Sentence order rather
    than declaration order is the tie-break on purpose -- when two rendered
    fields both carry the character, the one the reader meets first is the one
    the refusal is about.
    """
    for fragment in fragments:
        for character in _emitted(fragment):
            label = _class_of(character)
            if label is None:
                continue
            if fragment.field_path is None:
                # No field carries it, so this module's own renderer emitted it:
                # a defect here rather than in the payload, and no field to name.
                # Refused all the same -- a sentence nobody can trust is not
                # shown because of where the character came from.
                raise SchemaError(
                    "the rendering itself carries a character that can reorder "
                    "or hide text in a sentence for review"
                )
            raise UnrenderableFieldError(fragment.field_path, label)


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

    ⚠️ **The rendering guard below is NOT a second judge and does not weaken
    that precondition.** It is about what a *valid* operation may put on screen:
    an operation refused here is still well-formed, ``validate`` is unchanged,
    and a test asserts exactly that.

    **Refusing is the choice, rather than escaping or stripping the character.**
    Stripping changes what the reviewer sees from what the operation holds,
    which is the agreed-versus-written disagreement in miniature. Escaping is
    lossless and still loses: it vacates the field-named, actionable signal
    silently, and a sentence carrying an override escape is not a sentence a
    person can check against a record -- which is the whole purpose of rendering
    one. Refusing is how this function already treats an operation it cannot
    render. The cost is real and is recorded rather than hidden: a *displayable*
    operation becomes unpreviewable, and the class covers characters some
    scripts need legitimately.
    """
    type_name_of(operation)  # refuses anything unregistered
    fragments = operation.render()
    rendered = " ".join("".join(fragment.text for fragment in fragments).split())
    _refuse_unrenderable(fragments)
    return rendered


def full_display(operation: Operation) -> str:
    """Everything ``operation`` would write, with nothing elided, for approval.

    ``preview`` is the one-line summary a person reads; this is what they must
    actually be shown before the write, because the summary elides free text at
    ``_PREVIEW_TEXT_LIMIT`` and a person cannot approve what they were not shown.

    ⚠️ **The rendering guard runs over THIS too, and that is the point rather
    than symmetry.** Extending what is displayed extends what has to be guarded:
    a bidirectional override or a zero-width character sitting past the elision
    point reached no screen before and reaches one now. Guarding only ``preview``
    would have moved the attack rather than closed it.

    Same precondition as ``preview``: ``operation`` has passed ``validate``.
    """
    type_name_of(operation)  # refuses anything unregistered
    fragments = operation.full()
    rendered = " ".join("".join(fragment.text for fragment in fragments).split())
    _refuse_unrenderable(fragments)
    return rendered


def validate(operation: Operation) -> WellFormedResult:
    """Decide whether ``operation`` is **well-formed**. Not whether it is correct.

    Shape only. Nothing here asks whether a referenced object exists, whether
    it is the right one, or whether this duplicates something already in the
    tree -- those are declared on the PHASE_3 side of ``RULES`` and cannot
    fire from here.

    ⚠️ **An operation the registry does not name is refused, exactly as
    ``preview`` and ``to_dict`` refuse it.** The rule table derives what it
    checks from the declared fields of a registered type, so a class carrying
    none produces no required path, provokes no rule, and would otherwise come
    back well-formed -- a clean verdict on something every other entry point
    rejects, handed to a caller with no way to tell.

    ⚠️ **This is NOT an exception to "validate never raises on any operation
    ``from_dict`` can produce", and the difference is the point.** That
    property is quantified over what the wire can PRODUCE, and ``from_dict``
    refuses a type name the registry does not carry before it constructs
    anything -- so no payload yields an unregistered class. Refusing one is
    outside that quantifier rather than a hole in it, and the property stays
    exactly as strong. A reader who meets this ``SchemaError`` and repairs the
    never-raises property has repaired the wrong one; the distinction is
    pinned by a test so it cannot be reached by accident.
    """
    type_name_of(operation)  # refuses anything unregistered
    return _run(RULES, operation)
