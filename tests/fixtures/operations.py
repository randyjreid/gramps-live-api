"""One canonical valid operation per registered type, and the negatives from it.

⚠️ **This is a fixture table, not a test.** The structural tests quantify over
``schema.REGISTRY``; what they cannot do is invent a *valid* example, because a
valid one needs invented names and sensible identifiers. So a new operation
type adds one entry here, and ``test_every_registered_type_has_an_example``
fails with an instruction if it does not.

Two constraints on the values, both from the PII guard running over this
checkout:

* Invented surnames only, from the register the other fixtures use.
* Note text stays under ``_GRAMPS_PROSE_LENGTH`` (20) characters. A prose key
  holding twenty characters or more scores 4 -- the whole threshold -- and is
  gated only by no GEDCOM X structural key being present in the same file.
  Staying under the floor means the fixture cannot become a finding if such a
  key ever lands beside it. Cheap, and it costs the fixture nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, replace
from types import MappingProxyType

from gramps_live_api.core.schema import AddCitation, AddNote, ObjectRef, Operation

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
    }
)


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
        return replace(operation, **{head: _default_of(operation, head)})

    reference = getattr(operation, head)
    if reference is None:
        raise ValueError(f"{path}: cannot empty a leaf of a reference that is already absent")
    return replace(operation, **{head: replace(reference, **{rest: _default_of(reference, rest)})})


def _default_of(owner: object, name: str) -> object:
    for field in fields(owner):  # type: ignore[arg-type]
        if field.name == name:
            return field.default
    raise AttributeError(f"{type(owner).__name__} has no field {name}")
