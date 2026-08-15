"""What a *valid* operation is allowed to put on screen.

``preview`` renders the one sentence a person reads and approves before
anything is written to a tree, so a character that **reorders or hides** part
of that sentence attacks the agreement step itself: the reviewer approves one
sentence and a different one is what the operation says.

⚠️ **This is not a second validator and these tests do not make it one.**
``preview``'s precondition is unchanged -- the operation has passed
``validate`` -- and every case below is an operation that is *still
well-formed*. A case whose injected character breaks a closed vocabulary is
dropped rather than asserted on, because this guard makes no claim about input
``validate`` would have rejected. The two are different things and the
docstring on ``preview`` records the distinction deliberately.

The cases are generated from the registry and the declared fields, so a field
added to any operation later is covered **without this file changing** -- the
same derivation ``test_schema_preview.py`` and the wire sweeps already use.

⚠️ **The characters are built with ``chr`` so this tracked file stays plain
ASCII**, and every value is invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES, carrying, resolve

GUARDED: Mapping[str, str] = MappingProxyType(
    {
        "an override that reorders what follows it": chr(0x202E),
        "a zero-width character that hides between two others": chr(0x200B),
        "a control character the single-line rule does not remove": chr(0x07),
    }
)
"""One character per way the sentence can be attacked, built rather than typed.

The first two are the ones #33 was raised about. The third is here because the
single-line rule removes the control characters that are *whitespace* and
leaves the rest, so a test that used only those would pass on a guard that does
nothing.
"""


def _value(type_name: str, path: str) -> str:
    """The example's value at ``path``, or the empty string where it holds no text."""
    value = resolve(EXAMPLES[type_name], path)
    return value if isinstance(value, str) else ""


def _sentence(type_name: str) -> str:
    """What the renderer builds, read without going through the guard.

    Deliberately ``render()`` and not ``preview()``: a test that asked the
    guarded function what the unguarded sentence looks like would be deriving
    its expectation from the thing under test.
    """
    return " ".join(EXAMPLES[type_name].render().split())


def _carrying(type_name: str, path: str, character: str) -> schema.Operation:
    """The canonical example with ``character`` pushed into the middle of ``path``."""
    value = _value(type_name, path)
    return carrying(EXAMPLES[type_name], path, value[:1] + character + value[1:])


def _split() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Every (type, text path, character) case, divided by whether it is rendered.

    Both sides are load-bearing. A field the sentence carries must be refused;
    a field it does not carry must not be, because the guard is at the
    **rendering** boundary and a character that never reaches the screen is not
    its business. That second list is what shows no validation-time rule crept
    in -- the option the ruling on #33 rejected.
    """
    rendered: list[tuple[str, str, str]] = []
    unrendered: list[tuple[str, str, str]] = []
    for type_name in sorted(EXAMPLES):
        for path in schema.required_paths(type(EXAMPLES[type_name])):
            if not _value(type_name, path):
                continue
            for description in sorted(GUARDED):
                operation = _carrying(type_name, path, GUARDED[description])
                if not schema.validate(operation).well_formed:
                    # Not this guard's business: the injected character broke a
                    # closed vocabulary, so preview's precondition no longer
                    # holds and nothing here claims anything about it.
                    continue
                side = rendered if _value(type_name, path) in _sentence(type_name) else unrendered
                side.append((type_name, path, description))
    return rendered, unrendered


RENDERED, UNRENDERED = _split()


def test_the_generated_matrix_reaches_both_sides() -> None:
    # A parametrized list that generates to nothing passes every test built on
    # it while asserting nothing at all.
    assert RENDERED, "no rendered field was reached; every case below is vacuous"
    assert UNRENDERED, "no unrendered field was reached; the boundary control proves nothing"


@pytest.mark.parametrize(("type_name", "path", "description"), RENDERED)
def test_a_rendered_field_carrying_a_guarded_character_is_refused(
    type_name: str, path: str, description: str
) -> None:
    operation = _carrying(type_name, path, GUARDED[description])

    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    assert refusal.value.field_path == path, (
        "a refusal that does not name the field is one nobody can act on; "
        f"{description} at {path} was reported at {refusal.value.field_path!r}"
    )


@pytest.mark.parametrize(("type_name", "path", "description"), RENDERED)
def test_the_refusal_names_a_field_that_exists_on_the_operation(
    type_name: str, path: str, description: str
) -> None:
    # The same tool criterion 5 of #20 is asserted with: a reported path that
    # resolves nowhere is a message nobody can act on, which is the same as no
    # message. ``resolve`` raises if the path names no field.
    operation = _carrying(type_name, path, GUARDED[description])

    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    resolve(operation, refusal.value.field_path)


@pytest.mark.parametrize(("type_name", "path", "description"), RENDERED)
def test_an_operation_the_guard_refuses_is_still_well_formed(
    type_name: str, path: str, description: str
) -> None:
    # ⚠️ The control that keeps the two apart. This guard is about what a VALID
    # operation may put on screen; it is not a second judge and it did not
    # quietly become a validation rule. If a character rule ever lands on a
    # field at validation time -- the option the ruling on #33 rejected -- this
    # is what fails.
    operation = _carrying(type_name, path, GUARDED[description])

    assert schema.validate(operation).well_formed, (
        f"{description} at {path} changed validate's verdict; the guard is at "
        "the rendering boundary and validate was not to move"
    )


@pytest.mark.parametrize(("type_name", "path", "description"), UNRENDERED)
def test_a_field_that_is_not_rendered_is_not_refused(
    type_name: str, path: str, description: str
) -> None:
    # ⚠️ The control that shows the guard stayed at the RENDERING boundary.
    # A character the sentence never carries cannot mislead the person reading
    # it, so refusing it would be a rule about what a field may hold -- which is
    # the option the ruling rejected. Today this reaches the handles, which
    # criterion 7 keeps out of every preview.
    operation = _carrying(type_name, path, GUARDED[description])

    assert schema.preview(operation) == _sentence(type_name), (
        f"{description} at {path} changed a sentence that does not carry it"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_an_ordinary_preview_is_unchanged_by_the_guard(type_name: str) -> None:
    # The other direction of the criterion: the guard either refuses or gets out
    # of the way, and it never alters a sentence. A guard that quietly rewrote
    # ordinary previews would be the stripping option arriving by the back door.
    assert schema.preview(EXAMPLES[type_name]) == _sentence(type_name)


def test_the_punctuation_the_renderer_itself_inserts_is_not_refused() -> None:
    # The renderer quotes free text and elides it with an ellipsis, none of
    # which is ASCII. A class that caught its own module's punctuation would
    # refuse every long note, so this is the false-positive control -- and it
    # reaches the elision, which the canonical examples are too short to.
    elided = schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        note_type="research",
        text="Ashenmoor deed " * 6,
    )

    rendered = schema.preview(elided)

    assert rendered.strip()
    assert chr(0x2026) in rendered, f"the elision did not run, so it is untested; got {rendered!r}"
