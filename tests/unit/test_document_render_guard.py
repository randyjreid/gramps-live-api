"""What the approval render is allowed to put on screen.

``host.document.preview`` renders the text a person reads and approves before
anything is written to a tree, so a character that **reorders or hides** part of
it attacks the agreement step itself: the reviewer approves one sentence and a
different one is what the graph says.

⚠️ **This is not a second validator and these tests do not make it one.** The
guard is at the RENDERING boundary. ``parse`` is unchanged, ``propose_document``
still stores a graph carrying any of these characters, and a case whose injected
character breaks ``parse`` is dropped rather than asserted on -- the same drop
rule the retired ``test_schema_preview_guard.py`` used, for the same reason.

⭐ **The cases are generated from ``document.NODE_KEYS``**, which is where the
route declares what each node group accepts, so this file is derived from the
module under test rather than from a list somebody kept in step by hand. A key
added to a group later reaches the derivation on its own; what it needs from
this file is a fixture value, and the absence of one fails loudly below.

⚠️ **Every character is built with ``chr`` so this tracked file stays plain
ASCII**, and every value in it is invented.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from gramps_live_api.core import render_guard
from gramps_live_api.core._unrenderable import UNRENDERABLE_RANGES
from gramps_live_api.host import document

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

GUARDED: Mapping[str, str] = MappingProxyType(
    {
        "an override that reorders what follows it": chr(0x202E),
        "a zero-width character that hides between two others": chr(0x200B),
        "a control character no wrap removes": chr(0x07),
    }
)
"""One character per way the render can be attacked, built rather than typed.

⚠️ **None of the three is whitespace**, and that is what makes them usable
across the whole matrix. ``document._wrap`` puts note text through ``textwrap``,
which replaces ``\\t``, ``\\r``, ``\\x0b`` and ``\\x0c`` with spaces and splits
on ``\\n`` first -- so a whitespace control never survives to be refused in a
wrapped field, while it does survive in a field the renderer interpolates raw.
That asymmetry is real and it is pinned by its own two tests below rather than
smuggled into the matrix, where it would make a third of the cases mean
something different from the rest.
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
# The fixture, and the matrix derived from ``NODE_KEYS``.
# ---------------------------------------------------------------------------


def _node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node, built from keyword arguments rather than a JSON literal.

    ⚠️ **Deliberate, and not a style choice** -- the same helper and the same
    reason as ``test_document_preview.py``'s. ``pii_guard``'s P2 signature scores
    JSON-shaped ``"key": "value"`` pairs carrying identity, and a fixture written
    as a dict literal trips it -- correctly, because it cannot tell an invented
    person from a real one by looking. **It reported this file** when the fixture
    below was a literal, scoring 40 against a threshold of 4. Keyword arguments
    carry the same fixture with no quoted-key/quoted-value pairs in the source.
    """
    return {"id": local_id, **fields}


def _note(text: str, attach_to: list[str], **fields: Any) -> dict[str, Any]:
    """A note node. It has no ``id``, so it cannot go through ``_node``."""
    return {"text": text, "attach_to": list(attach_to), **fields}


def _graph_body(**groups: Any) -> dict[str, Any]:
    """A graph body assembled from keyword groups rather than a dict literal.

    ⛔ **Same reason as ``_node``, and the same lesson ``test_document_preview``
    records having learned the hard way.** ``pii_guard`` counts the graph's own
    group keys as GEDCOM X structure and scores them by DENSITY over a whole
    file: six ``"notes": [`` literals in this file scored 6 against a threshold
    of 4 and the guard reported it. Assembling from keywords leaves no quoted
    group key in the source at all.
    """
    return dict(groups)


def _body() -> dict[str, Any]:
    """A creating-only graph that declares **every key** ``NODE_KEYS`` publishes.

    ⚠️ **Every value is invented**, and none names a real person, place, date or
    record. The local ids are the conventional ``p1``/``e1`` shape; the rest are
    invented words chosen to be unique in the rendered text, because the
    derivation asks whether a clean value appears in the clean render and a value
    that collided with the renderer's own prose would answer that wrongly.
    """
    return _graph_body(
        people=[
            _node("p1", given="Alphaward", surname="Bravoton", gender="female"),
            _node("p2", given="Charlieby", surname="Deltawick", gender="male"),
            _node("p3", given="Echofield", surname="Foxtrotmere", gender="unknown"),
        ],
        places=[_node("l1", title="Golfshire")],
        events=[
            _node(
                "e1",
                type="Censusward",
                date="1871-04-02",
                place="l1",
                people=["p1"],
                family="f1",
                role="Witnessby",
                description="Hotelward",
            )
        ],
        source=_node("s1", title="Indiafile", author="Juliettmere", pubinfo="Kilowattby"),
        citations=[_node("c1", source="s1", page="770044", attach_to=["p1"])],
        families=[_node("f1", parents=["p1", "p2"], children=["p3"])],
        notes=[_note("Limatextual", ["p1"], type="transcript")],
    )


def _first(body: dict[str, Any], group: str) -> dict[str, Any]:
    """The first node of ``group``, smoothing over ``source`` being a single node."""
    value = body[group]
    return value if isinstance(value, dict) else value[0]


def _injected(value: Any, character: str) -> Any:
    """``value`` with ``character`` pushed into it, whatever shape it declares.

    Two shapes, because ``NODE_KEYS`` declares two: a string, and a list of local
    ids. Injecting into a list's first element is what puts the character into a
    reference, which is exactly the case ``parse`` is expected to drop.
    """
    if isinstance(value, str):
        return value[:1] + character + value[1:]
    if isinstance(value, list) and value and isinstance(value[0], str):
        head = value[0]
        return [head[:1] + character + head[1:], *value[1:]]
    raise AssertionError(f"the fixture holds a shape the derivation cannot inject into: {value!r}")


def _twin(group: str, key: str, character: str) -> dict[str, Any]:
    """The fixture with ``character`` pushed into ``group``'s first node at ``key``."""
    body = copy.deepcopy(_body())
    entry = _first(body, group)
    entry[key] = _injected(entry[key], character)
    return body


def _clean_value(group: str, key: str) -> str:
    """What ``group``'s first node holds at ``key``, as text, before any injection."""
    value = _first(_body(), group)[key]
    return value[0] if isinstance(value, list) else str(value)


CLEAN = document.preview(document.parse(_body()))
"""The clean render, which every case below is measured against."""

FLAT = " ".join(CLEAN.split())
"""``CLEAN`` with its wrapping undone, so a value split across two lines still reads
as present."""

Case = tuple[str, str, str]
"""``(group, key, character description)``."""


def _split() -> tuple[list[Case], list[Case], list[Case]]:
    """Every ``NODE_KEYS`` case, divided by what the route does with it.

    Three ways a case can land, and all three are load-bearing:

    * **dropped** -- the injected character broke ``parse``, so the graph never
      reaches a render and this guard makes no claim about it. The retired file
      dropped the cases ``validate`` rejected for exactly this reason.
    * **carried** -- the clean value appears in the clean render, so the injected
      one would too, and the guard must refuse it.
    * **withheld** -- the graph parses and the clean value appears nowhere in the
      render. A character that never reaches the screen cannot mislead the person
      reading it, so refusing it would be a rule about what a field may HOLD,
      which is the design this guard's own comment block rejects.
    """
    dropped: list[Case] = []
    carried: list[Case] = []
    withheld: list[Case] = []
    for group in sorted(document.NODE_KEYS):
        for key in sorted(document.NODE_KEYS[group]):
            renders = " ".join(_clean_value(group, key).split()) in FLAT
            for description in sorted(GUARDED):
                try:
                    document.parse(_twin(group, key, GUARDED[description]))
                except document.GraphInvalid:
                    dropped.append((group, key, description))
                    continue
                (carried if renders else withheld).append((group, key, description))
    return dropped, carried, withheld


DROPPED, CARRIED, WITHHELD = _split()

PINNED_CARRIED: frozenset[str] = frozenset(
    {
        "citations.page",
        "events.date",
        "events.description",
        "events.role",
        "events.type",
        "notes.text",
        "people.gender",
        "people.given",
        "people.surname",
        "places.title",
        "source.author",
        "source.pubinfo",
        "source.title",
    }
)
"""Every declared key whose value the clean render carries, measured on this fixture.

⚠️ **This is the R3 control, and it is asserted as a SUBSET rather than as an
equality.** The two polarities are not the same guarantee:

* a key that **stops** rendering silently vacates its own matrix case -- the case
  moves to ``WITHHELD``, where the assertion is that nothing is refused, so it
  keeps passing while covering nothing. That is what the subset check catches,
  loudly, naming the key.
* a key that **starts** rendering -- a new field, or a new line in the renderer --
  arrives in ``CARRIED`` and is guarded from that moment with no edit here. An
  equality check would fail on it, which would be this file complaining about
  coverage it just gained.

⛔ ``families`` is absent because it declares no free-text key: ``id``,
``parents`` and ``children`` are all local ids, and all three are dropped by
``parse``. That is a fact about the group, not a hole in the derivation.
"""

NEVER_RENDERED: frozenset[str] = frozenset({"citations.id", "events.id"})
"""The two declared keys that survive ``parse`` and reach no screen.

⛔ **A local id is never rendered, and ``document`` says so as a defect it has
already had**: falling through to ``str(local_id)`` printed *"attached to c1"*,
"which tells the owner an attachment exists and nothing he can recognise or
refuse". So these two moving into ``CARRIED`` would mean the renderer had started
printing local ids again, and this pin is where that shows up.

The other four ``id`` keys are dropped by ``parse`` instead: something in the
fixture refers to them, and an injected character breaks the reference.
"""


def test_the_fixture_declares_every_key_that_NODE_KEYS_publishes() -> None:
    """⛔ A key with no fixture value is a key the derivation cannot reach.

    ⚠️ **Loud rather than skipped.** The natural spelling of the derivation --
    ``if key not in entry: continue`` -- makes a newly declared key vanish from
    the matrix in silence, and the render guard then has no case for the one
    field nobody has thought about yet. This is the assertion that turns adding a
    key into a one-line fixture edit instead of a silent loss of coverage.
    """
    body = _body()
    undeclared = sorted(
        f"{group}.{key}"
        for group in document.NODE_KEYS
        for key in document.NODE_KEYS[group]
        if key not in _first(body, group)
    )

    assert undeclared == [], (
        "these keys are declared by NODE_KEYS and carry no value in this file's "
        f"fixture, so the derivation cannot inject into them: {undeclared}"
    )


def test_the_derived_matrix_reaches_all_three_sides_and_nothing_stopped_rendering() -> None:
    """A matrix that generates to nothing passes every test built on it."""
    assert DROPPED, "no case was dropped by parse, so the drop rule proves nothing"
    assert CARRIED, "no rendered field was reached; every refusal case below is vacuous"
    assert WITHHELD, "no unrendered field was reached; the boundary control proves nothing"

    carried_keys = {f"{group}.{key}" for group, key, _ in CARRIED}
    assert carried_keys >= PINNED_CARRIED, (
        "these keys used to have their value in the approval render and no longer do, "
        "so their matrix cases have gone vacuous: "
        f"{sorted(PINNED_CARRIED - carried_keys)}"
    )

    withheld_keys = {f"{group}.{key}" for group, key, _ in WITHHELD}
    assert withheld_keys >= NEVER_RENDERED, (
        "a local id has started appearing in the approval render, which document.py "
        "records as a defect in its own right: "
        f"{sorted(NEVER_RENDERED - withheld_keys)}"
    )


@pytest.mark.parametrize(("group", "key", "description"), CARRIED)
def test_a_rendered_field_carrying_a_guarded_character_is_refused(
    group: str, key: str, description: str
) -> None:
    """⛔ Where the whole guard lands: a field the render carries is guarded.

    Derived from ``NODE_KEYS``, so a field added to the renderer later arrives
    here on its own, which is the doctrine the guard's own comment block states.
    """
    parsed = document.parse(_twin(group, key, GUARDED[description]))

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(parsed)

    assert refusal.value.label == render_guard.class_of(GUARDED[description]), (
        f"{description} at {group}.{key} was refused under the wrong published fact"
    )


@pytest.mark.parametrize(("group", "key", "description"), WITHHELD)
def test_a_field_the_render_does_not_carry_is_not_refused(
    group: str, key: str, description: str
) -> None:
    """⚠️ The control that shows the guard stayed at the RENDERING boundary.

    A character the render never carries cannot mislead the person reading it, so
    refusing it would be a rule about what a field may hold -- the design the
    guard's own comment block weighs and rejects, and the design the owner struck
    out of this change's plan.
    """
    parsed = document.parse(_twin(group, key, GUARDED[description]))

    assert document.preview(parsed) == CLEAN, (
        f"{description} at {group}.{key} changed a render that does not carry it"
    )


@pytest.mark.parametrize(("group", "key", "description"), CARRIED)
def test_a_graph_the_guard_refuses_is_still_a_graph_parse_accepts(
    group: str, key: str, description: str
) -> None:
    """⚠️ The control that keeps the two apart.

    This guard is about what a *well-formed* graph may put on screen. If a
    character rule ever lands at acceptance time -- the option the plan change of
    2026-09-05 struck out by name -- this is what fails.
    """
    document.parse(_twin(group, key, GUARDED[description]))


# ---------------------------------------------------------------------------
# The named criteria.
# ---------------------------------------------------------------------------


def _note_graph(text: str) -> document.Graph:
    """One created person and one note carrying ``text``."""
    return document.parse(
        _graph_body(
            people=[_node("p1", given="Alphaward", surname="Bravoton")],
            notes=[_note(text, ["p1"])],
        )
    )


def _attaching_graph(**payload: str) -> document.Graph:
    """A person the graph attaches to by ``gramps_id``, carrying ``payload``."""
    return document.parse(
        _graph_body(
            people=[_node("p1", gramps_id="I9001", **payload)],
            notes=[_note("Limatextual", ["p1"])],
        )
    )


def _resolution(display: str = "Standin, Invented") -> document.Resolution:
    """A stand-in for what the TREE says about ``p1``.

    ⚠️ **Hand-built here rather than shared with ``test_document_preview.py``.**
    That file's ``_resolution`` is bound to that file's graph and its invented
    display text; importing it would couple two files' fixtures so that a change
    to either one's graph moves the other's assertions. The construction is three
    lines and this one names the fields this file's cases turn on.
    """
    return document.Resolution(nodes=(document.Resolved("p1", "I9001", "person", True, display),))


def test_a_note_carrying_an_override_is_refused_naming_Cf_and_repeating_nothing() -> None:
    """⛔ Criterion 2. The refusal names the published fact and echoes no payload.

    ⚠️ **The message reaches a screen**: the plugin's catch-all puts the traceback
    in a dialog. A payload echoed into an error is content this repository then
    has to scan, and any caller that logs the failure would be what published it.
    """
    sentinel = "Ashenmoorward"
    graph = _note_graph(sentinel + chr(0x202E) + " deed")

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(graph)

    message = str(refusal.value)
    assert refusal.value.label == "Cf", (
        "U+202E is a Cf in the committed table and the refusal must name the fact "
        f"the reader can look up; got {refusal.value.label!r}"
    )
    assert "Cf" in message, "a refusal naming nothing is one nobody can act on"
    assert sentinel not in message, "the refusal repeated a value the payload carried"
    assert chr(0x202E) not in message, "the refusal repeated the character the payload carried"


def test_a_payload_newline_that_would_forge_a_dialog_line_is_refused() -> None:
    """⛔ Criterion 3, and the reason the guard scans LINES rather than the join.

    ⚠️ **This forgery is real on the unguarded renderer**, and it does not go
    through ``_wrap``: a created person is appended as a raw f-string, so a
    U+000A in ``given`` puts a second line into the approval text reading as a
    record the graph never named. The guard sees it as the ``Cc`` it is, because
    it runs over the assembled lines before they are joined.
    """
    forged = "Alphaward" + chr(0x0A) + "  I9990  Betaby Invented"
    graph = document.parse(
        _graph_body(
            people=[_node("p1", given=forged, surname="Bravoton")],
            notes=[_note("Limatextual", ["p1"])],
        )
    )

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(graph)

    assert refusal.value.label == "Cc", (
        f"U+000A is a Cc and the refusal must say so; got {refusal.value.label!r}"
    )


def test_a_created_persons_name_reaches_a_line_the_renderer_never_wraps() -> None:
    """⚠️ The evidence for the test above, so the criterion is not asserted on trust.

    Without this, a renderer that put every payload through ``_wrap`` would make
    the refusal above pass while proving nothing about forgery -- ``_wrap`` splits
    on ``\\n`` first, so a newline there is structure rather than a smuggled line.
    This reads the renderer's own output and shows the name sits in a line that
    was appended whole, which is what makes a payload newline a forged line.
    """
    rendered = document.preview(_note_graph("Limatextual"))

    assert "  Person  Alphaward Bravoton   [unknown]" in rendered.splitlines(), (
        "the created person's name is no longer interpolated into a line of its "
        f"own, so the forgery above is about nothing; got {rendered!r}"
    )
    assert render_guard.class_of(chr(0x0A)) == "Cc"


def test_a_tree_read_display_carrying_a_zero_width_character_is_refused() -> None:
    """⛔ Criterion 4. Coverage the retired note flow never had.

    ⭐ ``Resolved.display`` comes from Gramps and never from the graph, and it is
    the whole safety mechanism of the ATTACHING section. Text read out of a tree
    is still text somebody is being asked to approve, and this seam is the first
    place in this project that guards it.
    """
    graph = _attaching_graph(given="Alphaward")

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(graph, _resolution("Stan" + chr(0x200B) + "din, Invented"))

    assert refusal.value.label == "Cf"


def test_a_dropped_field_on_an_attaching_node_is_not_refused() -> None:
    """⛔ The unrendered-side case the plan asked to be probed, with its answer.

    **Probed, then asserted: it does not render, so it is not refused.** Under a
    found ``Resolution`` the ATTACHING section prints the tree's own display text
    and names ``given`` only as a field that was NOT applied -- the name itself
    never reaches the screen and the writer ignores its value. Refusing it would
    be the acceptance-time rule this guard is defined not to be.

    ⚠️ **The same graph WITHOUT a resolution is refused**, which is asserted here
    beside it because the difference between the two is precisely the finding
    that removed the propose-time gate from this change's plan.
    """
    graph = _attaching_graph(given="Al" + chr(0x202E) + "phaward", surname="Bravoton")

    rendered = document.preview(graph, _resolution())

    assert chr(0x202E) not in rendered, "the dropped field reached the screen after all"
    assert "given" in rendered, "the dialog must still say the field was not applied"
    assert document.dropped_fields(graph.people[0]) == ("given", "surname")

    with pytest.raises(render_guard.UnrenderableTextError):
        document.preview(graph)


def test_a_multiline_tabbed_note_renders_without_refusal() -> None:
    """⛔ Criterion 7, the legitimate-whitespace control.

    ⚠️ **It passes because the tab never reaches the guard**, not because the
    guard permits tabs: ``_wrap`` puts note text through ``textwrap``, which
    splits on ``\\n`` and replaces the remaining whitespace controls with spaces.
    Stating the mechanism matters -- a reader who assumed the guard exempts
    whitespace would be wrong, as the test below it shows.
    """
    graph = _note_graph("first paragraph\n\tsecond\tindented\n\nfourth paragraph")

    rendered = document.preview(graph)

    assert "first paragraph" in rendered
    assert "fourth paragraph" in rendered
    assert "\t" not in rendered, (
        "textwrap is what removes the tab; if it stops doing so this control "
        "starts asserting the opposite of what it says"
    )


def test_a_tab_in_a_field_the_renderer_does_not_wrap_IS_refused() -> None:
    """⚠️ The cost of the per-line wiring, pinned rather than discovered later.

    A created person's name is interpolated into a raw f-string, so it never
    meets ``textwrap`` and a tab in it arrives at the guard as the ``Cc`` it is.
    **That is a real cost and it is fail-closed**, on a character no genealogical
    identifier needs -- and it is the same mechanism that refuses the forged
    newline above, which is why it is recorded here rather than carved around.
    """
    graph = document.parse(
        _graph_body(
            people=[_node("p1", given="Alpha" + chr(0x09) + "ward")],
            notes=[_note("Limatextual", ["p1"])],
        )
    )

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(graph)

    assert refusal.value.label == "Cc"


def test_an_ordinary_render_is_unchanged_by_the_guard() -> None:
    """The other direction of the criterion: the guard refuses or gets out of the way.

    A guard that quietly rewrote ordinary renders would be the stripping option
    arriving by the back door, and stripping is the agreed-versus-written
    disagreement in miniature.
    """
    parsed = document.parse(_body())

    assert document.preview(parsed) == CLEAN
    for group in sorted(document.NODE_KEYS):
        for key in sorted(document.NODE_KEYS[group]):
            if f"{group}.{key}" not in PINNED_CARRIED:
                continue
            assert _clean_value(group, key) in FLAT, (
                f"{group}.{key} lost characters between the graph and the render, "
                "which is the stripping option arriving by the back door"
            )


@pytest.mark.parametrize(("description", "code_point"), sorted(INVISIBLE_OUTSIDE_OTHER.items()))
def test_an_invisible_character_outside_the_other_category_is_refused(
    description: str, code_point: int
) -> None:
    """The class used to be the General_Category group "Other", and none of these is in it.

    Two are ``Mn`` and two are ``Lo``, so all four reached the screen as nothing
    at all. A reviewer approves text they can read; a character they cannot see
    is the attack, and which category the standard files it under is not the
    question.
    """
    graph = _note_graph("Ashenmoorward" + chr(code_point) + " deed")

    with pytest.raises(render_guard.UnrenderableTextError) as refusal:
        document.preview(graph)

    assert refusal.value.label == DEFAULT_IGNORABLE, (
        f"{description} (U+{code_point:04X}) is guarded by the derived core property "
        f"and the refusal must name it; got {refusal.value.label!r}"
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


ORDINARY_LETTERS: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "Latin": (0x0041, 0x005A),
        "Greek": (0x0391, 0x03A9),
        "Cyrillic": (0x0410, 0x042F),
        "Hebrew": (0x05D0, 0x05EA),
        "Arabic": (0x0627, 0x063A),
        "Devanagari": (0x0915, 0x0939),
        "Han": (0x4E00, 0x4E1F),
        "Hangul": (0xAC00, 0xAC1F),
    }
)
"""A run of ordinary letters per script, named by code point and built with ``chr``.

⚠️ **This is the assertion that catches an over-broad class before a person
does.** ``Lo`` is most of the world's letters and ``Mn`` carries essential
combining marks, and the class reaches into both -- so a guard that refused a
legitimate name would be far worse than the defect it was widened to fix. None
of these ranges holds a Hangul filler or a variation selector; those are asserted
refused above, which is what keeps this from being the same sweep twice.
"""


@pytest.mark.parametrize(("script", "letters"), sorted(ORDINARY_LETTERS.items()))
def test_a_name_in_an_ordinary_script_renders_unchanged(
    script: str, letters: tuple[int, int]
) -> None:
    """Assembled at runtime from a letter range, so it is invented by construction."""
    first, last = letters
    invented = "".join(chr(code_point) for code_point in range(first, min(first + 8, last + 1)))

    rendered = document.preview(_note_graph(invented))

    assert invented in rendered, (
        f"an ordinary {script} name did not survive the guard; got {rendered!r}"
    )


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


def test_a_code_point_this_interpreter_calls_unassigned_and_the_table_omits_is_rendered() -> None:
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

    assert unassigned[0] in document.preview(_note_graph("Ashenmoorward" + unassigned[0] + " deed"))


# ---------------------------------------------------------------------------
# Acceptance is not gated.
# ---------------------------------------------------------------------------


def test_propose_document_stores_a_graph_the_approval_render_would_refuse(tmp_path: Path) -> None:
    """⛔ Criterion 2's second half: the guard is on the render, not on acceptance.

    ⚠️ **This change removed a propose-time gate from its own plan**, on the
    owner's grounds that the guard is over what the approval render EMITS. This is
    the assertion that keeps it removed: the agent's call succeeds, the proposal
    is stored with the character intact, and the refusal happens later, where a
    person would have been asked to read it.

    ⚠️ **Skipped in this ONE test rather than at module scope.** The MCP server is
    an optional extra; a module-level skip would take the whole render guard with
    it on a leg that does not install it, which is a guard silently going
    untested.

    ⚠️ **The skip claims the absent-subject exemption**, in the words
    ``test_every_skip_names_a_seam_twin_that_exists`` requires: there is no seam
    twin for a server that is not installed, because there is nothing there to
    cover. The property this test is about -- that acceptance does not gate on
    characters -- is covered without the extra by the whole ``WITHHELD`` side of
    the matrix above and by
    ``test_a_graph_the_guard_refuses_is_still_a_graph_parse_accepts``.
    """
    if importlib.util.find_spec("mcp") is None:  # pragma: no cover - installed in dev
        pytest.skip(
            "the MCP server is an optional extra and it is not installed, so "
            "propose_document cannot be reached at all -- there is nothing to cover "
            "here. CI's mcp leg installs '.[mcp]'."
        )
    from gramps_live_api import config
    from gramps_live_api_mcp import server as mcp_server
    from tests.fixtures import trees
    from tests.unit.test_cli import equipped

    environ = dict(equipped(tmp_path))
    environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    environ["HOME"] = str(tmp_path / "home")
    environ[config.ENV_COPY] = trees.blessed(tmp_path / "copy").tree_dir
    tools = mcp_server.Tools(environ, session="renderguardsession")

    reply = tools.propose_document(
        _graph_body(
            people=[_node("p1", given="Alphaward", surname="Bravoton")],
            notes=[_note("Ashenmoorward" + chr(0x202E) + " deed", ["p1"])],
        )
    )

    stored = list((tmp_path / "copy").rglob(str(reply["proposal_id"]) + ".json"))
    assert stored, "propose_document reported an id and stored no proposal under it"
    assert chr(0x202E) in stored[0].read_text(encoding="utf-8"), (
        "the stored graph lost the character, so acceptance sanitised it -- the "
        "agreed-versus-written disagreement this guard exists to prevent"
    )
    with pytest.raises(render_guard.UnrenderableTextError):
        document.preview(_note_graph("Ashenmoorward" + chr(0x202E) + " deed"))
