"""What the approval render is allowed to put on screen.

``host.document.preview`` renders the text a person reads and approves before
anything is written to a tree, so a character that **reorders or hides** part of
it attacks the agreement step itself: the reviewer approves one sentence and a
different one is what the graph says.

⚠️ **Every character is built with ``chr`` so this tracked file stays plain
ASCII**, and every value in it is invented.
"""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from gramps_live_api.core import render_guard
from gramps_live_api.core._unrenderable import UNRENDERABLE_RANGES

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

⚠️ **A second published definition, on purpose.** The guard's own class is a
committed table derived from UAX #44's General_Category and the derived core
property ``Default_Ignorable_Code_Point``, at one pinned Unicode release; this
is the algorithm that says which characters *reorder* text, named by its own
bidirectional types and read back out of **the running interpreter's** database
through ``unicodedata.bidirectional``. That the two sources are also two
different Unicode versions is not a flaw in the cross-check -- it is what makes
it one. Two sources that must agree is a test; one source read twice is not, and
it would pass just as happily if both were wrong.
"""

INVISIBLE_OUTSIDE_OTHER: Mapping[str, int] = MappingProxyType(
    {
        "a combining grapheme joiner": 0x034F,
        "a Hangul choseong filler": 0x115F,
        "a Hangul jungseong filler": 0x1160,
        "the first variation selector": 0xFE00,
    }
)
"""Invisible characters the General_Category group "Other" does not hold.

⚠️ U+034F and U+FE00 are ``Mn`` and U+115F and U+1160 are ``Lo``, so a class
written as *general category* ``C`` cannot reach any of them -- and every one of
them renders as nothing. An invisible character in text somebody is about to
approve is precisely what this guard exists for, whichever category the standard
files it under.
"""


# ---------------------------------------------------------------------------
# The refusal itself.
# ---------------------------------------------------------------------------


def test_a_clean_set_of_lines_is_not_refused() -> None:
    """The guard refuses or gets out of the way, and it never alters anything."""
    lines = ["THIS IS WHAT WOULD BE WRITTEN TO YOUR TREE", "=" * 62, "", "  Alphaward Bravoton"]

    render_guard.refuse_unrenderable(lines)


def test_a_guarded_character_anywhere_in_any_line_is_refused() -> None:
    """⛔ Every character of every line, with nothing skipped."""
    for position, line in (
        (0, chr(0x202E) + "Alphaward"),
        (1, "Alpha" + chr(0x200B) + "ward"),
        (2, "Alphaward" + chr(0x07)),
    ):
        lines = ["Bravoton"] * 3
        lines[position] = line

        with pytest.raises(render_guard.UnrenderableTextError):
            render_guard.refuse_unrenderable(lines)


def test_the_refusal_names_the_published_fact_and_repeats_no_value() -> None:
    """⚠️ **The message reaches a screen**, so it may echo nothing the payload carried.

    The plugin's catch-all puts the traceback in a dialog. A payload echoed into
    an error is content this repository then has to scan, and any caller that
    logs the failure would be what published it.
    """
    sentinel = "Ashenmoorward"

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        render_guard.refuse_unrenderable([sentinel + chr(0x202E) + " deed"])

    message = str(refusal.value)
    assert refusal.value.label == "Cf", (
        "U+202E is a Cf in the committed table and the refusal must name the fact "
        f"the reader can look up; got {refusal.value.label!r}"
    )
    assert "Cf" in message, "a refusal naming nothing is one nobody can act on"
    assert sentinel not in message, "the refusal repeated a value the payload carried"
    assert chr(0x202E) not in message, "the refusal repeated the character the payload carried"


def test_a_payload_newline_inside_one_line_is_refused_as_the_control_it_is() -> None:
    """⭐ Per LINE, which is what makes a payload newline a refusal.

    The caller joins these lines with ``"\\n"`` afterwards, so a U+000A inside one
    of them is a payload character and not structure: it would forge an extra
    line in the approval dialog, reading as a record the graph never named.
    """
    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        render_guard.refuse_unrenderable(["  Person  Alphaward" + chr(0x0A) + "  I9990  Betaby"])

    assert refusal.value.label == "Cc"


def test_the_refusal_is_not_a_ValueError() -> None:
    """⚠️ ``GraphInvalid`` is a ``ValueError`` and means *the caller sent something
    unusable*; this means *a valid graph produced text nobody may be asked to
    approve*. Sharing a base would let an ``except ValueError`` written for the
    first silently swallow the second, on the one surface where failing closed is
    the point."""
    assert not issubclass(render_guard.UnrenderableTextError, ValueError)


@pytest.mark.parametrize(("description", "code_point"), sorted(INVISIBLE_OUTSIDE_OTHER.items()))
def test_an_invisible_character_outside_the_other_category_is_in_the_class(
    description: str, code_point: int
) -> None:
    """The class used to be the General_Category group "Other", and none of these is in it.

    Two are ``Mn`` and two are ``Lo``, so all four reached the screen as nothing
    at all. A reviewer approves text they can read; a character they cannot see
    is the attack, and which category the standard files it under is not the
    question.
    """
    assert render_guard.class_of(chr(code_point)) == DEFAULT_IGNORABLE, (
        f"{description} (U+{code_point:04X}) is guarded by the derived core property "
        f"and the class must say so; got {render_guard.class_of(chr(code_point))!r}"
    )


# ---------------------------------------------------------------------------
# The published-source cross-checks.
# ---------------------------------------------------------------------------


def _every_code_point() -> list[str]:
    """The whole code space. A full sweep costs about a tenth of a second."""
    return [chr(code_point) for code_point in range(sys.maxunicode + 1)]


def test_every_character_the_bidi_algorithm_defines_as_explicit_formatting_is_guarded() -> None:
    """The reordering half of the property, checked against UAX #9.

    Against the algorithm rather than against the class the guard is written in
    terms of, so this is two sources agreeing rather than one read twice.
    """
    formatting = [
        character
        for character in _every_code_point()
        if unicodedata.bidirectional(character) in EXPLICIT_BIDI_FORMATTING
    ]
    missed = [character for character in formatting if render_guard.class_of(character) is None]

    assert formatting, "the sweep found no explicit formatting at all, so this proves nothing"
    assert missed == [], (
        "a character the Bidirectional Algorithm defines as explicit formatting "
        f"can reorder text for review and is not guarded: {[ord(c) for c in missed]}"
    )


def test_every_character_this_interpreter_calls_other_but_assigned_is_guarded() -> None:
    """⭐ The regression sweep: every character refused before the table existed still is.

    The old class was exactly the assigned half of the General_Category group
    "Other" as the RUNNING interpreter reports it, so asking that question again
    is asking whether anything was lost -- and it is a question the committed
    table cannot answer about itself.
    """
    was_guarded = [
        character
        for character in _every_code_point()
        if unicodedata.category(character).startswith("C")
        and unicodedata.category(character) != "Cn"
    ]
    emitted = [character for character in was_guarded if render_guard.class_of(character) is None]

    assert len(was_guarded) > 100_000, (
        f"the sweep found only {len(was_guarded)} assigned Other characters, so this "
        f"proves nothing (this interpreter's UCD is {unicodedata.unidata_version})"
    )
    assert emitted == [], (
        "a character this interpreter's own database says is a control, a format "
        "character, a surrogate or private use is not guarded by the committed table: "
        f"{[ord(c) for c in emitted]}"
    )


# ---------------------------------------------------------------------------
# The committed table, and the lookup that reads it.
# ---------------------------------------------------------------------------


def _by_scan(character: str) -> str | None:
    """What the committed table says about ``character``, found by walking it.

    A deliberately different algorithm from the bisect under test. Comparing the
    two is a test; reading the answer off the same lookup would be a tautology
    that passes however wrong the lookup is.
    """
    code_point = ord(character)
    for first, last, label in UNRENDERABLE_RANGES:
        if first <= code_point <= last:
            return label
    return None


def test_the_lookup_agrees_with_the_table_at_every_boundary() -> None:
    """Every row's first and last code point, and the one either side of them.

    That is where a bisect goes wrong, and where an inclusive range read as a
    half-open one loses exactly one character per row.
    """
    disagreed = []
    for first, last, _ in UNRENDERABLE_RANGES:
        for code_point in (first - 1, first, last, last + 1):
            if not 0 <= code_point <= sys.maxunicode:
                continue
            character = chr(code_point)
            if render_guard.class_of(character) != _by_scan(character):
                disagreed.append(f"U+{code_point:04X}")

    assert disagreed == [], f"the lookup and the committed table disagree at: {disagreed}"


def test_the_committed_table_is_sorted_and_holds_no_range_twice() -> None:
    """The shape the lookup depends on.

    A bisect over unsorted starts answers confidently and wrongly, and an overlap
    would make the label a matter of which row happened to come first.
    """
    out_of_order = [
        (previous, following)
        for previous, following in zip(UNRENDERABLE_RANGES, UNRENDERABLE_RANGES[1:], strict=False)
        if previous[1] >= following[0]
    ]

    assert out_of_order == [], f"the table is not sorted, or two ranges overlap: {out_of_order}"


def test_every_committed_range_is_a_range_inside_the_code_space() -> None:
    malformed = [row for row in UNRENDERABLE_RANGES if not 0 <= row[0] <= row[1] <= sys.maxunicode]

    assert malformed == [], f"a committed range is empty or outside the code space: {malformed}"


def test_every_committed_label_names_a_published_fact() -> None:
    """Closed, because the label is what a refusal names and the derivation selects five.

    A sixth means the script started emitting something nothing in the guard is
    written about.
    """
    published = frozenset({"Cc", "Cf", "Co", "Cs", DEFAULT_IGNORABLE})
    unknown = sorted({row[2] for row in UNRENDERABLE_RANGES} - published)

    assert unknown == [], f"the table carries a label the guard has no meaning for: {unknown}"


def test_no_two_adjacent_committed_ranges_share_a_label() -> None:
    """What says the coalesce ran."""
    uncoalesced = [
        (previous, following)
        for previous, following in zip(UNRENDERABLE_RANGES, UNRENDERABLE_RANGES[1:], strict=False)
        if previous[2] == following[2] and previous[1] + 1 == following[0]
    ]

    assert uncoalesced == [], f"two adjacent ranges share a label: {uncoalesced}"


# ---------------------------------------------------------------------------
# The false-positive half: what the guard must NOT refuse.
# ---------------------------------------------------------------------------


def test_no_character_a_person_could_read_is_guarded_unless_it_is_invisible() -> None:
    """The false-positive half, and the assertion this class actually costs.

    Letters, marks, numbers, punctuation, symbols and separators are what text a
    person checks against a record is made of, and refusing any of them for its
    CATEGORY would be a guard that blocks legitimate data. The one published
    reason a readable character may be refused is that it is default-ignorable,
    and the size of that exemption is pinned by the test below rather than left
    open.
    """
    readable = frozenset({"L", "M", "N", "P", "S", "Z"})
    refused = [
        character
        for character in _every_code_point()
        if unicodedata.category(character)[0] in readable
        and render_guard.class_of(character) is not None
    ]
    for_their_category = [
        character for character in refused if render_guard.class_of(character) != DEFAULT_IGNORABLE
    ]

    assert refused, "no readable character is refused at all, so the exemption below is untested"
    assert for_their_category == [], (
        "a readable character is refused for its general category rather than for being "
        f"default-ignorable: {[ord(c) for c in for_their_category]}"
    )


def test_the_exemption_that_lets_a_readable_character_be_refused_is_pinned() -> None:
    """⚠️ The load-bearing half of the narrowing.

    Without a pin the test above stops constraining anything -- a table that
    started refusing whole alphabets under the default-ignorable label would pass
    it.

    ⚠️ **Pinned over the COMMITTED TABLE, not over the exempted set as this
    interpreter sees it.** Counting the readable characters the class refuses asks
    the running interpreter for categories: it answers 266 on UCD 13.0.0 and 267
    on 14.0.0 and 15.0.0, because U+180F is unassigned in the first and ``Mn`` in
    the others. The table's own figures are the same guarantee and hold
    everywhere.
    """
    exempting = [row for row in UNRENDERABLE_RANGES if row[2] == DEFAULT_IGNORABLE]

    assert len(exempting) == 13, (
        f"the number of default-ignorable ranges in the committed table moved: {exempting}"
    )
    assert sum(last - first + 1 for first, last, _ in exempting) == 4036, (
        "the default-ignorable half of the class changed size; a widening onto letters "
        "lands here, and a re-derivation that means it must move this figure deliberately"
    )


def test_a_code_point_unassigned_here_and_absent_from_the_table_is_not_guarded() -> None:
    """What this pins is that the class does not reach unassigned code points.

    ⚠️ **Both conditions are load-bearing.** The table is pinned at a Unicode
    release newer than any interpreter here bundles, so code points this one calls
    unassigned ARE in the class -- deliberately, and recorded in the costs block.
    Asking only what this interpreter calls ``Cn`` would therefore fail on a
    correct table. The case worth asserting is the code point neither source knows
    anything about.
    """
    unassigned = [
        character
        for character in _every_code_point()
        if unicodedata.category(character) == "Cn" and render_guard.class_of(character) is None
    ]

    assert len(unassigned) > 1000, (
        "too few code points are unassigned here and absent from the table for this to be "
        f"a real sweep; found {len(unassigned)} (this interpreter's UCD is "
        f"{unicodedata.unidata_version})"
    )

    render_guard.refuse_unrenderable(["Ashenmoorward" + unassigned[0] + " deed"])
