"""⛔ A note proposed through the document route may carry a ``type``.

The one real capability the older note flow has and this route does not is a
caller-chosen note type, so every note this route writes has been a
``TRANSCRIPT`` whatever the document said. This file is the whole of what
changes: the key is accepted, the vocabulary is the frozen table, an omitted type
still writes exactly what it writes today, the preview names the effective type
at **both** render sites, and everything else is refused by name.

⛔ **Refused, never passed through to Gramps**, which is the opposite of the
choice ``_event_type`` makes for events and is deliberate. The recorded cost of
the other choice is the owner's own: *"An unrecognised type silently creates a
new custom type in the tree and nothing tells me it's new."* An event type comes
off a document and its vocabulary is open in practice; a note's type is a filing
decision drawn from a list Gramps itself publishes.

⚠️ **Nothing here writes out the ten accepted names.** They come from the
committed table, so this file cannot become a second tally of it.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from gramps_live_api.core import _note_types
from gramps_live_api.host import document
from tests.fixtures.host_sources import REPOSITORY_ROOT

TEXT = "A line copied from an invented parish register."
"""⛔ Invented. No real Gramps ID, name, date or place appears in this file."""


def node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node. ⚠️ Spelled here rather than imported from another test
    module: one test file importing another couples them."""
    return dict(id=local_id, **fields)


def a_note(**fields: Any) -> dict[str, Any]:
    """One ``notes[]`` entry. ⛔ ``type`` is set only when a caller passes one,
    because the default is the ABSENCE of the key and never a falsy value."""
    return dict(text=TEXT, **fields)


def payload(*notes: dict[str, Any]) -> dict[str, Any]:
    """One person and some notes, as the object a caller would send.

    ⚠️ **Built here rather than written out at each call site, and the reason is
    this repository's own guard.** A file carrying enough clustered genealogy
    vocabulary is reported as genealogy data by ``pii_guard``'s density property,
    and a graph literal per test is exactly that cluster. ⛔ The fix is where the
    tests live, never the guard's threshold -- which is what
    ``test_attachable_bound`` already says of the same collision.
    """
    return {"people": [node("p1")], "notes": list(notes)}


def attached_graph(**note_fields: Any) -> document.Graph:
    """A note on a person, which the per-node walk reaches and renders."""
    return document.parse(payload(a_note(attach_to=["p1"], **note_fields)))


def undrawn_graph(**note_fields: Any) -> document.Graph:
    """A note attached to nothing, which only the leftovers loop renders.

    ⛔ **This is the second render site, and assuming there is one is how the
    criterion would be half-met.** A typed note whose edge is undrawn, attached
    to nothing or to a node the walk never reached, renders here and nowhere
    else.
    """
    return document.parse(payload(a_note(attach_to=[], **note_fields)))


def some_accepted_type() -> str:
    """One accepted type that is NOT the default, taken from the table.

    ⚠️ Naming one here would be a second tally; what the tests need is only *a
    type a caller could choose that the default would not produce*.
    """
    chosen = sorted(_note_types.ACCEPTED_NOTE_TYPES - {document.DEFAULT_NOTE_TYPE})
    assert chosen, "the accepted set holds nothing but the default, so nothing here tests anything"
    return chosen[0]


# ---------------------------------------------------------------------------
# The key, and the default
# ---------------------------------------------------------------------------


def test_a_note_may_carry_a_type_and_a_graph_that_omits_it_still_parses() -> None:
    """⛔ Both halves, because either alone is half the criterion.

    ⚠️ Every graph that exists today omits ``type``, so a key made mandatory
    would break all of them, and a key not accepted at all would make the route
    refuse the very thing this work adds.
    """
    assert "type" in document.NODE_KEYS["notes"]

    typed = attached_graph(type=some_accepted_type())
    assert typed.notes[0]["type"] == some_accepted_type()

    untyped = attached_graph()
    assert "type" not in untyped.notes[0], "parse invented a key the caller never sent"


def test_an_omitted_type_means_the_type_the_writer_has_ALWAYS_written() -> None:
    """⛔ The backward-compatible half: every graph that exists now is unchanged.

    ⚠️ This is the one most easily broken by a default landing in the wrong
    place. The writer has hardcoded ``TRANSCRIPT`` for every note it ever
    created, so the default is not a new decision -- it is the existing
    behaviour, named.
    """
    assert document.note_type_of(attached_graph().notes[0]) == document.DEFAULT_NOTE_TYPE
    assert document.DEFAULT_NOTE_TYPE == "transcript"


def test_the_default_is_the_ABSENCE_of_the_key_and_never_a_FALSY_value() -> None:
    """⛔ ``if not value or value in TABLE`` is the natural spelling and it is wrong.

    ⚠️ That shape is what the retired ``schema._note_type_unknown`` used, and it
    was safe there only because that module's ``_text`` had already coerced.
    Copied here without that coercion it reads ``type: []`` and ``type: 0`` as **omitted** and
    silently writes a transcript, which is a chosen value becoming a default
    without anybody being told. ⛔ A present ``type`` that is not an accepted
    string is REFUSED; only an absent one defaults.
    """
    for falsy in ([], 0, "", None, {}, False):
        with pytest.raises(document.GraphInvalid) as refused:
            attached_graph(type=falsy)
        assert "type" in str(refused.value), f"{falsy!r}: {refused.value}"


def test_a_type_that_is_not_a_string_is_refused_BEFORE_anything_is_done_with_it() -> None:
    """⛔ The fourth leaf held to this rule, after ``local``, ``source_id`` and
    ``referenced``.

    ⚠️ The graph arrives as JSON and the parser checks only that a node is an
    object with known keys, so ``type: []`` and ``type: 42`` are both reachable.
    A membership test alone would refuse them, but the message would say *not one
    of the note types* about something that is not a word at all.
    """
    for wrong in ([], 42, {"a": 1}, ["research"], 3.5):
        with pytest.raises(document.GraphInvalid) as refused:
            attached_graph(type=wrong)
        assert "text" in str(refused.value) or "string" in str(refused.value), (
            f"{wrong!r} is refused without saying a type has to be text: {refused.value}"
        )


# ---------------------------------------------------------------------------
# The refusal, and what it names
# ---------------------------------------------------------------------------


def test_an_unknown_type_is_refused_by_name_and_the_message_lists_the_SET() -> None:
    """⛔ In the shape ``_only_known_keys`` already uses.

    ⚠️ The vocabulary cannot go in the tool description -- ten names written out
    is 98 characters against eight spare in a budget that is already nearly full
    -- so **this refusal is where a caller meets the set**, and it is the only
    place. A refusal naming no alternatives is one a caller cannot act on.
    """
    with pytest.raises(document.GraphInvalid) as refused:
        attached_graph(type="gossip")
    message = str(refused.value)

    assert "gossip" in message, "the refusal does not name what was refused"
    for accepted in _note_types.ACCEPTED_NOTE_TYPES:
        assert accepted in message, f"the refusal does not offer {accepted!r}: {message}"


def test_the_refusal_names_WHICH_note_carries_the_bad_type() -> None:
    """⚠️ The caller has to find one node in its own graph to fix it.

    A note has no ``id`` -- it is the one group without one -- so the index is
    the only thing that can name it, exactly as ``_only_known_keys`` does.
    """
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse(payload(a_note(attach_to=["p1"]), a_note(attach_to=["p1"], type="gossip")))

    assert "notes[1]" in str(refused.value), (
        f"the refusal does not say which note was wrong: {refused.value}"
    )


def test_every_row_the_table_carries_and_does_NOT_accept_is_refused() -> None:
    """⛔ The nineteen, and they are the ones a lookup written slightly wrong
    would let through.

    ⚠️ They are all present in the table and differ from the accepted ten only by
    which list they came from, so a membership test written against
    ``NOTE_TYPE_ROWS`` instead of ``ACCEPTED_NOTE_TYPES`` would accept every one
    of them and pass every other test in this file.

    ⭐ ``custom`` and ``unknown`` are two of them. They need no special handling
    under a membership check and adding some would suggest the set were not
    trusted; they are refused by the same check as ``gossip``. This test names
    them because they are the two rows the table carries and does not accept, and
    that is worth saying out loud.
    """
    refused_names = sorted(
        {attribute.lower() for attribute, _v, _k, _l in _note_types.NOTE_TYPE_ROWS}
        - _note_types.ACCEPTED_NOTE_TYPES
    )
    assert refused_names, "the table accepts every row it carries, so this test proves nothing"

    let_through = []
    for name in refused_names:
        try:
            attached_graph(type=name)
        except document.GraphInvalid:
            continue
        let_through.append(name)

    assert let_through == [], (
        f"these note types are in the table, are not accepted, and were written "
        f"anyway: {let_through}"
    )


@pytest.mark.parametrize("reasonable", ("event", "person", "sourceref"))
def test_a_type_that_READS_like_a_note_type_is_still_refused(reasonable: str) -> None:
    """⭐ Named individually because they read like perfectly reasonable choices.

    ⚠️ ``Event Note`` is a real Gramps note type and a caller asking for
    ``event`` on a note about an event is being sensible. It is refused because
    it is offered only in an event's own Notes tab: a note the tool wrote with it
    while attached to a person opens in that person's tab, where the user can
    REMOVE the type but could never have CHOSEN it, and cannot put it back. ⛔ The
    ten are exactly the set closed under the user's own editing, wherever the
    note sits, which is what the ruling asks for.

    ⚠️ ``sourceref`` is the sharpest of the three: no editor anywhere passes it as
    an exception, so it is reachable by no chooser at all.
    """
    assert reasonable in {attribute.lower() for attribute, _v, _k, _l in _note_types.NOTE_TYPE_ROWS}

    with pytest.raises(document.GraphInvalid):
        attached_graph(type=reasonable)


# ---------------------------------------------------------------------------
# ⛔ The preview, at BOTH render sites, for typed AND untyped notes
# ---------------------------------------------------------------------------


def _rendered(graph: document.Graph) -> str:
    return document.preview(graph, document.Resolution())


def test_a_TYPED_note_names_its_type_in_the_preview_at_the_ATTACHED_site() -> None:
    """⛔ A type written and not rendered is a byte reaching the tree that the
    approval did not show, which is the one property this route exists to hold."""
    chosen = some_accepted_type()
    rendered = _rendered(attached_graph(type=chosen))

    assert chosen in rendered, f"the type is written and not shown:\n{rendered}"
    assert TEXT in rendered, "the note body stopped being rendered"


def test_a_TYPED_note_names_its_type_in_the_preview_at_the_UNDRAWN_site() -> None:
    """⛔ There is no single note-rendering site, and assuming one is how this
    criterion would be half-met.

    ⚠️ A note attached to nothing, or to a node the per-node walk never reached,
    renders only under ``ALSO WRITTEN``. A fix applied to the first site alone
    passes the test above and leaves the second silent.
    """
    chosen = some_accepted_type()
    rendered = _rendered(undrawn_graph(type=chosen))

    assert "ALSO WRITTEN" in rendered, "this graph no longer reaches the leftovers loop"
    assert chosen in rendered, f"the type is written and not shown:\n{rendered}"
    assert TEXT in rendered


@pytest.mark.parametrize("build", (attached_graph, undrawn_graph))
def test_an_UNTYPED_note_names_the_type_IT_WILL_GET_at_both_sites(build: Any) -> None:
    """⛔ The case a typed-only test cannot catch, and the gap is not hypothetical.

    ⚠️ An implementation that renders the type only when the ``type`` key is
    present passes every typed case above, while a note whose written type is
    ``TRANSCRIPT`` shows no type at all in the approval. **That is a value
    reaching the tree that the approval did not display**, and it would be
    reached by the most natural way to write the rendering.

    ⚠️ **So every existing untyped graph's approval text changes**: where it read
    ``+ Note:`` it now names the type. That is a visible change to a dialog the
    owner already knows, resolved in favour of showing what will be written,
    because the alternative is an approval that displays less than the write
    performs.
    """
    rendered = _rendered(build())

    assert document.DEFAULT_NOTE_TYPE in rendered, (
        f"an untyped note shows no type, while the writer will give it "
        f"{document.DEFAULT_NOTE_TYPE!r}:\n{rendered}"
    )


def test_the_preview_still_fits_the_wrap_with_a_type_on_every_note() -> None:
    """⚠️ Nothing may run off the right edge and hide behind a scrollbar.

    The longest accepted name is added to a line that was already indented, so
    this is asserted rather than eyeballed.
    """
    longest = max(_note_types.ACCEPTED_NOTE_TYPES, key=len)
    for build in (attached_graph, undrawn_graph):
        rendered = _rendered(build(type=longest))
        too_wide = [line for line in rendered.splitlines() if len(line) > document.WRAP_AT]
        assert too_wide == [], f"these lines would be cut off at the right edge: {too_wide}"


# ---------------------------------------------------------------------------
# ⛔ The writer, which is reachable with a graph the package did not validate
# ---------------------------------------------------------------------------


def writer_module() -> Any:
    """The writer, loaded by path, without Gramps.

    Precedent: ``test_attachable_bound`` and ``test_write_summary`` already do
    this. The writer deliberately does not import the package, so its copy of
    the accepted names cannot be shared at runtime.
    """
    specification = importlib.util.spec_from_file_location(
        "a_writer_for_note_types", REPOSITORY_ROOT / "gramps_plugin" / "gramps_live_api_writer.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def note_type_class(*, without: tuple[str, ...] = ()) -> type:
    """A stand-in for ``gramps.gen.lib.NoteType``, built FROM THE TABLE.

    ⛔ Built from the committed rows rather than written out, so it cannot be a
    third listing of the vocabulary. ``without`` removes attributes, which is how
    a Gramps that has renamed or dropped a built-in type is simulated.
    """
    attributes: dict[str, Any] = {
        attribute: value
        for attribute, value, _key, _declared_in in _note_types.NOTE_TYPE_ROWS
        if attribute not in without
    }

    def __init__(self: Any, value: int) -> None:
        self.value = value

    attributes["__init__"] = __init__
    return type("NoteType", (), attributes)


def test_the_writers_inlined_names_are_the_committed_ACCEPTED_SET() -> None:
    """⛔ A copy a test binds to its source is not a duplicate that nothing checks.

    ⚠️ The writer deliberately does not import the package, so the list cannot be
    shared at runtime. **An unchecked copy is what "no duplicate that nothing
    checks" forbids**, and this is the check.
    """
    writer = writer_module()

    assert set(writer.ACCEPTED_NOTE_TYPES) == set(_note_types.ACCEPTED_NOTE_TYPES), (
        "the writer's inlined vocabulary and the committed table disagree: "
        f"{sorted(set(writer.ACCEPTED_NOTE_TYPES) ^ set(_note_types.ACCEPTED_NOTE_TYPES))}"
    )
    assert len(writer.ACCEPTED_NOTE_TYPES) == len(set(writer.ACCEPTED_NOTE_TYPES))
    assert writer.DEFAULT_NOTE_TYPE == document.DEFAULT_NOTE_TYPE


def test_the_writer_accepts_a_name_ONLY_by_MEMBERSHIP_of_that_set() -> None:
    """⛔ Membership in a ten-element set is bounded, and that is the whole point.

    ⚠️ This criterion said for three revisions that the writer needed no copy,
    because ``getattr`` plus a few refusals would do. **Three consecutive review
    rounds each found a genuine, different hole in that list of refusals** --
    ``isinstance(value, int)`` for ``_DATAMAP``, which is a list;
    ``isinstance(name, str)`` for ``type: []`` and ``type: 42``; ``hasattr`` for
    ``type: "gossip"``, which resolves to nothing at all. That is a universally
    quantified negative over an unbounded space, and the rule for that shape is
    to bound it rather than to review it harder.

    ⭐ **And the sharpest of the three is the argument against ever going back.**
    ``NoteType._DEFAULT`` **is an int** -- it equals ``GENERAL`` -- so under the
    exclusion list ``type: "_default"`` passed ``hasattr``, passed
    ``isinstance(value, int)``, was neither ``CUSTOM`` nor ``UNKNOWN``, and
    **silently wrote a General note**: not a crash, a working undocumented alias.
    Every one of these is refused by the same single check, because none of these
    names is in the set.
    """
    writer = writer_module()

    for reachable in ("_DATAMAP", "_DEFAULT", "_CUSTOM", "gossip", "custom", "unknown", "event"):
        with pytest.raises(ValueError) as refused:
            writer._note_type_name({"text": TEXT, "type": reachable})
        assert "note type" in str(refused.value), f"{reachable}: {refused.value}"

    for wrong_shape in ([], 42, None, {}, True):
        with pytest.raises(ValueError):
            writer._note_type_name({"text": TEXT, "type": wrong_shape})


def test_the_writer_resolves_a_type_through_getattr_on_the_ATTRIBUTE_NAME() -> None:
    """⛔ Never a pinned integer, which is the discipline already used elsewhere.

    Gramps' numbering is an implementation detail, and a renumbering would
    silently file every note under the wrong type. Asserted against a stand-in
    class built from the table, so what is checked is the resolution and not this
    test's own arithmetic.
    """
    writer = writer_module()
    stub = note_type_class()
    by_attribute = {attribute: value for attribute, value, _k, _l in _note_types.NOTE_TYPE_ROWS}

    for accepted in sorted(_note_types.ACCEPTED_NOTE_TYPES):
        resolved = writer._resolved_note_type({"text": TEXT, "type": accepted}, stub)
        assert resolved.value == by_attribute[accepted.upper()], (
            f"{accepted!r} resolved to {resolved.value}, not to what Gramps declares"
        )


def test_a_note_with_no_type_is_written_as_it_has_ALWAYS_been_written() -> None:
    """⛔ Criterion 5 at the place the write actually happens.

    Every graph that exists today omits the key, and this asserts the integer
    that reaches Gramps for such a note is the one the hardcoded line produced.
    """
    writer = writer_module()
    stub = note_type_class()

    resolved = writer._resolved_note_type({"text": TEXT}, stub)

    assert resolved.value == stub.TRANSCRIPT


def test_a_vocabulary_that_has_DRIFTED_refuses_the_WHOLE_document() -> None:
    """⛔ The build-time question the plan left open, answered here.

    ⚠️ **The plugin registers against whichever Gramps is running**, deliberately:
    a pinned version stops matching the day Gramps updates and the plugin
    silently stops being registered. So a later Gramps that renames or removes a
    built-in note type leaves a name in the frozen table that the package
    validates, that the writer's membership check passes, and that ``getattr``
    then finds nothing for -- **after the owner approved the document**, which is
    the one moment this route exists to make safe.

    ⭐ Answered with the live check, which is the only one of the three candidates
    that cannot fail after approval: the writer compares its inlined names
    against the running class before the transaction opens, and refuses the whole
    document naming the drift. What is NOT acceptable is the implied behaviour,
    an ``AttributeError`` partway through a write already approved.
    """
    writer = writer_module()
    graph = payload(a_note(attach_to=["p1"]))

    dropped = sorted(_note_types.ACCEPTED_NOTE_TYPES)[0].upper()
    with pytest.raises(ValueError) as refused:
        writer._note_types_or_refuse(graph, note_type_class(without=(dropped,)))

    message = str(refused.value)
    assert dropped in message or dropped.lower() in message, (
        f"the refusal does not name which type has gone: {message}"
    )
    assert "nothing has been written" in message.lower(), (
        f"the refusal does not say the document was refused whole: {message}"
    )

    # ⭐ And it says nothing at all when the vocabulary is intact, which is the
    # non-vacuity partner: a check that refused everything would pass the half
    # above and make the route unusable.
    writer._note_types_or_refuse(graph, note_type_class())


def test_the_drift_check_reads_every_note_BEFORE_the_first_one_is_written() -> None:
    """⛔ A bad type on the third note must not leave the first two written.

    ⚠️ The transaction would roll back, but *refuse the whole document before any
    object is created* is the stated property and it does not depend on Gramps'
    abort behaviour being what this project remembers.
    """
    writer = writer_module()
    graph = payload(a_note(attach_to=["p1"]), a_note(attach_to=["p1"]), a_note(type="gossip"))

    with pytest.raises(ValueError) as refused:
        writer._note_types_or_refuse(graph, note_type_class())

    assert "gossip" in str(refused.value)


def test_a_graph_with_no_notes_is_not_refused_by_the_note_vocabulary() -> None:
    """⚠️ A deliberate narrowing, stated rather than left to be discovered.

    A document carrying no notes needs no note type, so refusing it because a
    note type it will never use has gone would refuse a write that would have
    worked. The check runs when there is something to check.
    """
    writer = writer_module()
    dropped = sorted(_note_types.ACCEPTED_NOTE_TYPES)[0].upper()

    writer._note_types_or_refuse({"people": [node("p1")]}, note_type_class(without=(dropped,)))
    writer._note_types_or_refuse(payload(), note_type_class(without=(dropped,)))
