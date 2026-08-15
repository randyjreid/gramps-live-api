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

import sys
import unicodedata
from collections.abc import Iterator, Mapping
from types import MappingProxyType

import pytest

from gramps_live_api.core import schema
from gramps_live_api.core._unrenderable import UNRENDERABLE_RANGES
from tests.fixtures.operations import EXAMPLES, SENTINELS, carrying, resolve

DEFAULT_IGNORABLE = "Default_Ignorable_Code_Point"
"""The derived core property that holds the class's invisible half.

Spelled out here rather than imported, on the same reasoning as
``EXPLICIT_BIDI_FORMATTING`` below: the name is a published fact, and a test
that read it off the thing under test would agree with it however wrong it was.
"""

EXPLICIT_BIDI_FORMATTING: frozenset[str] = frozenset(
    {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}
)
"""The explicit formatting types of the Unicode Bidirectional Algorithm, UAX #9.

⚠️ **A second published definition, on purpose.** The guard's own class is the
General_Category group "Other" of UAX #44; this is the algorithm that says which
characters *reorder* text, named by its own bidirectional types and read back
out of the UCD through ``unicodedata.bidirectional``. Two sources that must
agree is a test -- one source read twice is not, and it would pass just as
happily if both were wrong. The same reason ``permits`` in the fixture module
derives what a field *should* accept rather than calling the module's helper.
"""

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

INVISIBLE_OUTSIDE_OTHER: Mapping[str, int] = MappingProxyType(
    {
        "a combining grapheme joiner": 0x034F,
        "a Hangul choseong filler": 0x115F,
        "a Hangul jungseong filler": 0x1160,
        "the first variation selector": 0xFE00,
    }
)
"""Round 4's named inputs: invisible characters the "Other" group does not hold.

⚠️ **This is the finding, stated as a fixture.** U+034F and U+FE00 are ``Mn``
and U+115F and U+1160 are ``Lo``, so a class written as *general category*
``C`` cannot reach any of them -- and every one of them renders as nothing.
An invisible character in a sentence somebody is about to approve is precisely
what this guard exists for, whichever category the standard files it under.

Named by code point and built with ``chr``, like everything else here, so this
tracked file stays plain ASCII.
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
    fragments = EXAMPLES[type_name].render()
    return " ".join("".join(fragment.text for fragment in fragments).split())


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
    # ⚠️ **This is where criterion 1 lands, and it is what the whole guard rests
    # on.** The cases are generated from the registry and the declared fields,
    # so a field added to any operation later and rendered into the sentence
    # arrives here on its own. Its renderer must carry the path its text came
    # from: a renderer that inlines the value and names no field leaves the
    # character in text this module claims it wrote itself, and the refusal
    # comes back as a bare SchemaError naming nothing -- which FAILS ABOVE,
    # loudly, rather than falling back to a search over the operation's values.
    # There is no such fallback any more, deliberately: a search cannot tell two
    # rendered fields carrying the same character apart.


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


def test_a_character_in_an_unrendered_and_a_rendered_field_names_the_rendered_one() -> None:
    # ⚠️ The refusal has to name the field whose CORRECTION CHANGES THE OUTCOME.
    # A handle is never rendered -- criterion 7 keeps it out of every preview --
    # so a refusal naming one sends the reader to a field they can fix without
    # the refusal going away. That does not fail criterion 4 loudly; it vacates
    # it silently, which is this module's recorded defect shape.
    character = GUARDED["an override that reorders what follows it"]
    operation = carrying(
        carrying(EXAMPLES["add_note"], "target.handle", "7fd3a9" + character + "c15e0842"),
        "text",
        "Ashenmoor" + character + " deed",
    )

    assert schema.validate(operation).well_formed, (
        "this case is only the rendering guard's business while the operation "
        "is still well-formed; preview's precondition is unchanged"
    )
    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    assert refusal.value.field_path == "text", (
        "the sentence carries the character from text and never carries the "
        "handle at all, so naming target.handle is a refusal whose correction "
        f"leaves the refusal standing; got {refusal.value.field_path!r}"
    )


def test_a_character_in_two_rendered_fields_names_the_one_that_contributed_it() -> None:
    # ⚠️ The case that separates PROVENANCE from a narrowed search, and the one
    # the finding did not name. Excluding unrendered fields from a search would
    # pass the test above and fail this one: both fields here are rendered, so
    # only carrying which field produced which text can tell them apart.
    #
    # AddCitation is the discriminating type because its declaration order and
    # its sentence order DISAGREE -- target is declared first, the citation is
    # rendered first -- so a search over required_paths answers target.gramps_id
    # and the sentence answers citation.gramps_id.
    character = GUARDED["an override that reorders what follows it"]
    operation = carrying(
        carrying(EXAMPLES["add_citation"], "citation.gramps_id", "C00" + character + "42"),
        "target.gramps_id",
        "I00" + character + "31",
    )

    assert schema.validate(operation).well_formed, (
        "this case is only the rendering guard's business while the operation "
        "is still well-formed; preview's precondition is unchanged"
    )
    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    assert refusal.value.field_path == "citation.gramps_id", (
        "the offending character reaches the sentence from citation.gramps_id "
        "first; target.gramps_id is what DECLARATION ORDER answers, which is "
        f"the attribution this guard must not be making; got {refusal.value.field_path!r}"
    )


@pytest.mark.parametrize(("description", "code_point"), sorted(INVISIBLE_OUTSIDE_OTHER.items()))
def test_an_invisible_character_outside_the_other_category_is_refused(
    description: str, code_point: int
) -> None:
    # ⚠️ Round 4's finding. The class used to be the General_Category group
    # "Other", and none of these four is in it -- two are Mn and two are Lo --
    # so all four reached the screen as nothing at all. A reviewer approves a
    # sentence they can read; a character they cannot see is the attack, and
    # which category the standard files it under is not the question.
    operation = carrying(EXAMPLES["add_note"], "text", "Ashenmoor" + chr(code_point) + " deed")

    assert schema.validate(operation).well_formed, (
        "this case is only the rendering guard's business while the operation "
        "is still well-formed; preview's precondition is unchanged"
    )
    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    assert refusal.value.field_path == "text", (
        f"{description} (U+{code_point:04X}) reaches the sentence from text; "
        f"got {refusal.value.field_path!r}"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_every_field_a_renderer_names_is_a_field_that_exists(type_name: str) -> None:
    # The control on the new mechanism. Provenance is carried by the renderer
    # naming the path its text came from, so a mistyped prefix there would
    # report a field nobody can act on -- the same fault criterion 5 rules out
    # for a violation. ``resolve`` raises if the path names no field.
    named = [
        fragment.field_path
        for fragment in EXAMPLES[type_name].render()
        if fragment.field_path is not None
    ]

    assert named, f"{type_name} renders no field at all, so its provenance proves nothing"
    for path in named:
        resolve(EXAMPLES[type_name], path)


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


def _every_code_point() -> Iterator[str]:
    """The whole code space. A full sweep costs about a tenth of a second."""
    return (chr(code_point) for code_point in range(sys.maxunicode + 1))


def test_every_character_the_bidi_algorithm_defines_as_explicit_formatting_is_guarded() -> None:
    # The reordering half of the property, checked against UAX #9 rather than
    # against the class the guard is written in terms of.
    formatting = [
        character
        for character in _every_code_point()
        if unicodedata.bidirectional(character) in EXPLICIT_BIDI_FORMATTING
    ]
    missed = [character for character in formatting if not schema._is_unrenderable(character)]

    assert formatting, "the sweep found no explicit formatting at all, so this proves nothing"
    assert missed == [], (
        "a character the Bidirectional Algorithm defines as explicit formatting "
        f"can reorder a sentence for review and is not guarded: {[ord(c) for c in missed]}"
    )


def test_no_character_a_person_could_read_is_guarded_unless_it_is_invisible() -> None:
    # The false-positive half, and the assertion this change actually costs.
    # Letters, marks, numbers, punctuation, symbols and separators are what a
    # sentence a person checks against a record is made of, and refusing any of
    # them for its CATEGORY would be a guard that blocks legitimate data.
    #
    # ⚠️ It used to say no readable character is refused at all, and that is no
    # longer true: U+115F and U+1160 are Lo, U+034F and U+FE00 are Mn, and all
    # four are invisible -- round 4's finding. So the narrowing is to the one
    # published reason a readable character may be refused, and the size of that
    # exemption is pinned by the test below rather than left open.
    readable = frozenset({"L", "M", "N", "P", "S", "Z"})
    refused = [
        character
        for character in _every_code_point()
        if unicodedata.category(character)[0] in readable and schema._is_unrenderable(character)
    ]
    for_their_category = [
        character for character in refused if schema._class_of(character) != DEFAULT_IGNORABLE
    ]

    assert refused, "no readable character is refused at all, so the exemption below is untested"
    assert for_their_category == [], (
        "a readable character is refused for its general category rather than for being "
        f"default-ignorable: {[ord(c) for c in for_their_category]}"
    )


def test_the_exemption_that_lets_a_readable_character_be_refused_is_pinned() -> None:
    # ⚠️ The load-bearing half of the narrowing. Without a pin the test above
    # stops constraining anything -- a table that started refusing whole
    # alphabets under the default-ignorable label would pass it.
    #
    # ⚠️ Pinned over the COMMITTED TABLE, not over the exempted set as this
    # interpreter sees it, and that is deliberate. Counting the readable
    # characters the class refuses asks the running interpreter for categories:
    # it answers 266 on UCD 13.0.0 and 267 on 14.0.0 and 15.0.0, because U+180F
    # is unassigned in the first and Mn in the others. Pinning that number would
    # put the interpreter back into an assertion this whole change exists to get
    # it out of. The table's own figures are the same guarantee and hold
    # everywhere: a re-derivation that widens the invisible half fails here, in
    # the code points nobody can see as well as in the ones this interpreter has
    # a category for.
    exempting = [row for row in UNRENDERABLE_RANGES if row[2] == DEFAULT_IGNORABLE]

    assert len(exempting) == 13, (
        f"the number of default-ignorable ranges in the committed table moved: {exempting}"
    )
    assert sum(last - first + 1 for first, last, _ in exempting) == 4036, (
        "the default-ignorable half of the class changed size; a widening onto letters "
        "lands here, and a re-derivation that means it must move this figure deliberately"
    )


def test_a_code_point_this_interpreter_calls_unassigned_and_the_table_omits_is_previewed() -> None:
    # ⚠️ What this pins is that the class does not reach unassigned code points,
    # and it no longer pins anything about version dependence -- there is none
    # left to pin. `Cn` is stated explicitly in the artifact the table is
    # derived from; what keeps it out is that the derivation's wanted set does
    # not name it, so there is no exclusion clause to "complete".
    #
    # ⚠️ Both conditions are load-bearing. The table is pinned at a Unicode
    # release newer than any interpreter here bundles, so code points this one
    # calls unassigned ARE in the class -- deliberately, and recorded in the
    # costs block. Asking only what this interpreter calls Cn would therefore
    # fail on a correct table. The case worth asserting is the code point
    # neither source knows anything about.
    unassigned = [
        character
        for character in _every_code_point()
        if unicodedata.category(character) == "Cn" and not schema._is_unrenderable(character)
    ]

    assert len(unassigned) > 1000, (
        "too few code points are unassigned here and absent from the table for this to be "
        f"a real sweep; found {len(unassigned)} (this interpreter's UCD is "
        f"{unicodedata.unidata_version})"
    )
    operation = carrying(EXAMPLES["add_note"], "text", "Ashenmoor" + unassigned[0] + " deed")

    assert schema.validate(operation).well_formed, (
        "this case is only the rendering guard's business while the operation "
        "is still well-formed; preview's precondition is unchanged"
    )
    assert unassigned[0] in schema.preview(operation), (
        f"U+{ord(unassigned[0]):04X} is unassigned in UCD {unicodedata.unidata_version} and "
        "absent from the committed table, and the guard refused it anyway"
    )


@pytest.mark.parametrize(("description", "sentinel"), sorted(SENTINELS.items()))
def test_the_refusal_repeats_no_value_the_payload_carried(description: str, sentinel: str) -> None:
    # The rule on RuleViolation, which this refusal obeys for the same reason: a
    # payload echoed into an error becomes content this repository then has to
    # scan, and any caller that logs the failure would be what published it.
    character = GUARDED["an override that reorders what follows it"]
    operation = carrying(EXAMPLES["add_citation"], "citation.gramps_id", sentinel + character)

    with pytest.raises(schema.UnrenderableFieldError) as refusal:
        schema.preview(operation)

    message = str(refusal.value)
    assert sentinel not in message, f"the refusal repeated {description}"
    assert character not in message, "the refusal repeated the character the payload carried"
    assert "citation.gramps_id" in message, "a refusal naming nothing is one nobody can act on"


def test_a_character_no_field_carries_is_refused_without_naming_one() -> None:
    # ⚠️ Reaches a module-private function deliberately, because there is no
    # route to this branch through the public one: it fires when a renderer in
    # this module emits a guarded character itself, and the registry is closed,
    # so registering a type that did would break the partition and the example
    # table that quantify over it. The branch still has to be right -- a
    # sentence nobody can trust is not shown because of where the character came
    # from -- and it must not claim a field carried something no field carries.
    with pytest.raises(schema.SchemaError) as refusal:
        schema._refuse_unrenderable((schema.Fragment("cite citation " + chr(0x202E)),))

    assert not isinstance(refusal.value, schema.UnrenderableFieldError), (
        "a refusal naming a field no value came from points the reader at the wrong place"
    )
