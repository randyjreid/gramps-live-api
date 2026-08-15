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
