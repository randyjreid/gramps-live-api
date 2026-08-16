"""Every operation renders as one line a person could check against a record.

⚠️ **What these tests do not claim.** "A sentence a person can check against a
record" is a human judgement and is not an acceptance criterion -- it is a
reviewer checklist item. Everything below is a mechanical proxy for it. The
proxy carrying real weight is *no bare handle*: a preview naming an opaque
handle is not reviewable at all.

Asserted over the registry, and the expectations are derived from each example
rather than written down, so a tenth operation type is covered by this file
without this file changing.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema
from tests.fixtures.operations import EXAMPLES


def _references(operation: schema.Operation) -> list[schema.ObjectRef]:
    return [
        getattr(operation, name)
        for name in schema.reference_fields(type(operation))
        if getattr(operation, name) is not None
    ]


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_preview_is_a_non_empty_single_line_string(type_name: str) -> None:
    rendered = schema.preview(EXAMPLES[type_name])

    assert isinstance(rendered, str)
    assert rendered.strip(), f"{type_name} previews as nothing at all"
    assert "\n" not in rendered and "\r" not in rendered, f"a preview is one line; got {rendered!r}"


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_preview_names_no_opaque_handle(type_name: str) -> None:
    # The proxy that carries real weight, and the reason the reference model
    # requires a Gramps ID. Derived from the example's own handles, so it
    # cannot be satisfied by a preview that happens to avoid one spelling.
    example = EXAMPLES[type_name]
    rendered = schema.preview(example)

    leaked = [
        reference.handle
        for reference in _references(example)
        if reference.handle and reference.handle in rendered
    ]

    assert leaked == [], (
        "a preview naming an opaque handle is not reviewable at all, which is "
        f"the whole point of rendering one; got {rendered!r}"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_preview_shows_the_identifier_a_person_can_look_up(type_name: str) -> None:
    # The other half of D2, and the positive counterpart to the test above.
    # Naming no handle is easy to satisfy by naming nothing.
    example = EXAMPLES[type_name]
    rendered = schema.preview(example)

    absent = [
        reference.gramps_id
        for reference in _references(example)
        if reference.gramps_id and reference.gramps_id not in rendered
    ]

    assert absent == [], (
        "every object the operation touches must be named by the identifier a "
        f"person can look up; got {rendered!r} missing {absent}"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_preview_contains_no_none(type_name: str) -> None:
    rendered = schema.preview(EXAMPLES[type_name])

    assert "None" not in rendered, (
        f"'None' in a sentence for review is a hole where a value belongs; got {rendered!r}"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_preview_is_not_a_default_repr(type_name: str) -> None:
    example = EXAMPLES[type_name]
    rendered = schema.preview(example)

    assert " object at 0x" not in rendered, f"got a default object repr; got {rendered!r}"
    for cls in (type(example), schema.ObjectRef):
        assert f"{cls.__name__}(" not in rendered, (
            f"a dataclass repr is not a sentence anybody can check; got {rendered!r}"
        )


def test_the_single_line_rule_survives_a_value_containing_newlines() -> None:
    # The normalisation is a choke point in preview(), not a habit each
    # renderer is trusted to keep. A note is the value a person can put a
    # newline in, so it is the one that proves the choke point runs.
    multiline = schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        note_type="todo",
        text="first line\nsecond line\r\nthird",
    )

    rendered = schema.preview(multiline)

    assert "\n" not in rendered and "\r" not in rendered, (
        f"a value carrying newlines broke the single-line rule; got {rendered!r}"
    )
    assert rendered.strip()


def test_previewing_something_that_is_not_a_registered_operation_is_refused() -> None:
    with pytest.raises(schema.SchemaError):
        schema.preview(schema.Operation())


# ---------------------------------------------------------------------------
# full_display -- what the operator is shown before the write
# ---------------------------------------------------------------------------


def _note(text: str) -> schema.AddNote:
    return schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        note_type="research",
        text=text,
    )


def test_full_display_carries_the_whole_text_where_preview_elides_it() -> None:
    """A person cannot approve what they were not shown.

    ``preview`` is the one-line summary; it elides free text, and the approval
    used to be compared as that elided string -- so everything past the limit
    reached the tree without ever reaching a screen.
    """
    tail = "and the part that used to be invisible"
    note = _note("x" * schema._PREVIEW_TEXT_LIMIT + " " + tail)

    summary = schema.preview(note)
    entire = schema.full_display(note)

    assert tail not in summary, "this test is meaningless unless preview really elides"
    assert tail in entire
    assert note.text in entire


def test_two_notes_sharing_a_prefix_differ_in_full_display_though_not_in_preview() -> None:
    shared = "Marriage recorded in the parish register, second volume, page "
    a = _note(shared + "141. Confirmed against the original.")
    b = _note(shared + "141. FABRICATED: inheritance passes to the other line.")

    assert schema.preview(a) == schema.preview(b)
    assert schema.full_display(a) != schema.full_display(b)


def test_full_display_is_one_line_like_preview() -> None:
    # Same normalisation, and for the same reason: a carriage return emitted
    # raw overwrites the line it is on, which hides the content this function
    # exists to reveal.
    note = _note("first line\r\nsecond line\tand a tab")

    entire = schema.full_display(note)

    assert "\n" not in entire and "\r" not in entire and "\t" not in entire


def test_the_guard_reaches_a_hidden_character_past_the_elision_point() -> None:
    """The residual that Fix B retired, pinned shut.

    The guard used to be justified partly by truncation: a character past the
    limit was never emitted, so a guard over what we DISPLAY had nothing to say
    about it. ``full_display`` emits it, so the guard has to reach it -- else
    extending the display would have moved the attack rather than closed it.
    """
    right_to_left_override = chr(0x202E)
    note = _note("y" * (schema._PREVIEW_TEXT_LIMIT + 20) + right_to_left_override + "hidden")

    # preview elides it away, and says nothing about it. That is still correct.
    assert schema.preview(note)

    with pytest.raises(schema.UnrenderableFieldError) as refused:
        schema.full_display(note)

    assert refused.value.field_path == "text"


def test_full_display_defaults_to_the_sentence_for_an_operation_that_elides_nothing() -> None:
    citation = schema.AddCitation(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        citation=schema.ObjectRef(object_type="citation", handle="c1t4t10n", gramps_id="C0042"),
    )

    assert schema.full_display(citation) == schema.preview(citation)


def test_full_display_refuses_something_that_is_not_a_registered_operation() -> None:
    with pytest.raises(schema.SchemaError):
        schema.full_display(schema.Operation())
