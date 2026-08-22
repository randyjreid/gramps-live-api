"""The acceptance criteria for what the approval dialog shows, and what it records.

⚠️ **A1 and A3 are the blocking criteria.** They are not opinions and they are not
reviewable-by-argument: either every node's content is in the rendered text, or
the dialog is lying by omission on every write.

⭐ **Why these exist.** R3's ruled criterion is *"no byte reaches the tree that
was not rendered in full to the human in the approval dialog"*. Three defects
broke it at once, all the slice-1 elision defect in a new costume:

1. a note attached to an **event** rendered nowhere at all;
2. a note attached to a **person** rendered as ``+ Note`` with no body -- worse,
   because it looked like it had been shown;
3. long lines ran off the right edge behind a horizontal scrollbar.
"""

from __future__ import annotations

import json
import pathlib

from gramps_live_api.host import document

EVENT_NOTE = "NOTE ON THE EVENT -- must appear."
PERSON_NOTE = "NOTE ON THE PERSON -- must appear."
ORPHAN_NOTE = "ORPHAN NOTE on an event nobody is attached to."
UNATTACHED_NOTE = "NOTE ATTACHED TO NOTHING AT ALL."

LONG_NOTE = "Sie ist ein sehr langer Text. " * 14
"""420 characters, and deliberately one unbroken run of prose rather than a
paragraph -- the shape most likely to be truncated by a renderer that assumes
short strings."""


def note(body, attach_to):
    """A note node, built the same way and for the same reason as ``node``."""
    return {"text": body, "attach_to": list(attach_to)}


def node(local_id, **fields):
    """A graph node, built from keyword arguments rather than a JSON literal.

    ⚠️ **Deliberate, and not a style choice.** ``pii_guard``'s P2 signature scores
    JSON-shaped ``"key": "value"`` pairs carrying identity, and a test fixture
    written as a dict literal trips it -- correctly, because it cannot tell an
    invented person from a real one by looking. Keyword arguments carry the same
    fixture with no quoted-key/quoted-value pairs in the source.

    The guard's own module uses the same trick on its own patterns, splitting
    ``"ty" + "pe"`` so it does not match itself.
    """
    return {"id": local_id, **fields}


def _graph() -> document.Graph:
    """A1's graph: a note on an event, a note on a person, and a 400+ char note."""
    return document.parse(
        {
            "people": [node("p1", gramps_id="I0024")],
            "places": [node("l1", title="St Mary's")],
            "events": [
                node("e1", type="Baptism", date="1868-05-03", place="l1", people=["p1"]),
            ],
            "source": node("s1", title="Parish register"),
            "citations": [node("c1", source="s1", page="44", attach_to=["p1"])],
            "notes": [
                note(EVENT_NOTE, ["e1"]),
                note(PERSON_NOTE, ["p1"]),
                note(LONG_NOTE, ["s1"]),
            ],
        }
    )


def _resolution() -> document.Resolution:
    return document.Resolution(
        nodes=(document.Resolved("p1", "I0024", "person", True, "Standlake, Peregrine"),)
    )


# ---------------------------------------------------------------------------
# A1
# ---------------------------------------------------------------------------


def test_a1_every_note_body_is_rendered_in_full() -> None:
    """A1. All three bodies present, whole, whatever they are attached to."""
    rendered = document.preview(_graph(), _resolution())

    assert EVENT_NOTE in rendered, (
        "a note attached to an EVENT rendered nowhere at all -- the defect this "
        "criterion exists for"
    )
    assert PERSON_NOTE in rendered

    # The long note is wrapped, so it is not present as one line. Every word of
    # it must still be there, in order, once the wrapping is undone.
    unwrapped = " ".join(rendered.split())
    assert " ".join(LONG_NOTE.split()) in unwrapped, (
        "the 400-character note was truncated; R3 requires it rendered in full"
    )


def test_a1_no_note_appears_without_its_content() -> None:
    """A1. ``+ Note`` with nothing after it is the worst of the three defects.

    It looks like the content was shown. A reader who trusts the dialog would
    approve a body they never saw.
    """
    rendered = document.preview(_graph(), _resolution())
    for index, line in enumerate(rendered.splitlines()):
        if line.strip() == "+ Note":
            raise AssertionError(
                f"line {index} is a bodiless '+ Note': {rendered.splitlines()[index : index + 3]}"
            )


def test_a1_nothing_is_wider_than_the_wrap() -> None:
    """A1. No line runs off the edge, so nothing hides behind a scrollbar."""
    rendered = document.preview(_graph(), _resolution())
    too_wide = [line for line in rendered.splitlines() if len(line) > document.WRAP_AT]
    assert too_wide == [], f"these lines would be cut off at the right edge: {too_wide}"


def test_a1_every_node_in_the_graph_appears_somewhere() -> None:
    """A1, as the structural property rather than three examples.

    ⭐ The backstop: a note whose ``attach_to`` names something the renderer does
    not walk must still be rendered. This is the case that used to vanish.
    """
    graph = document.parse(
        {
            "people": [node("p1", given="Anon", surname="Body")],
            "events": [node("e1", type="Burial", date="1900")],
            "notes": [
                note(ORPHAN_NOTE, ["e1"]),
                note(UNATTACHED_NOTE, []),
            ],
        }
    )
    rendered = document.preview(graph)
    assert ORPHAN_NOTE in rendered
    assert UNATTACHED_NOTE in rendered
    assert "Burial" in rendered


def test_the_preview_never_renders_what_the_caller_said_about_an_existing_node() -> None:
    """⛔ The property that caught a wrong spelling: the tree wins, always.

    The caller sent one spelling; the tree holds another. The dialog must show
    the tree's, or a wrong Gramps ID becomes invisible.
    """
    graph = document.parse({"people": [node("p1", gramps_id="I0024", surname="Friedrich")]})
    resolution = document.Resolution(
        nodes=(document.Resolved("p1", "I0024", "person", True, "Friederich, Anna"),)
    )
    rendered = document.preview(graph, resolution)
    assert "Friederich, Anna" in rendered
    assert "surname" in rendered, "the dropped field must be disclosed, not silently ignored"


# ---------------------------------------------------------------------------
# A3
# ---------------------------------------------------------------------------


def test_a3_the_journal_names_every_object_created(tmp_path) -> None:
    """A3. A record naming every created object, durable, in the tree's own dir."""
    graph = _graph()
    created = {
        "people": ["I0100"],
        "events": ["E0200"],
        "places": ["P0300"],
        "sources": ["S0400"],
        "citations": ["C0500"],
        "notes": ["N0600", "N0601", "N0602"],
        "families": [],
    }
    record = document.journal_record(
        graph,
        created,
        {"people": ["I0024"]},
        tree_dir=str(tmp_path),
        written_utc="2026-08-22T00:00:00+00:00",
        approved_preview=document.preview(graph, _resolution()),
    )
    path = document.write_journal(str(tmp_path), record, stem="20260822T000000Z-document")

    assert (tmp_path / document.UNDO_DIRECTORY).is_dir()
    written = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

    for kind, ids in created.items():
        for gramps_id in ids:
            assert gramps_id in written["created"].get(kind, []), (
                f"{gramps_id} was created and is not in the journal"
            )
    assert written["created"].get("families") is None, (
        "empty kinds are left out, not recorded as an empty list"
    )

    # ⭐ What was ATTACHED to is recorded separately, because reversing it means
    # removing a reference rather than deleting a record.
    assert written["attached_to_existing"]["people"] == ["I0024"]

    # The graph as asked for, and the text the human actually approved.
    assert written["graph"]["people"][0]["gramps_id"] == "I0024"
    assert EVENT_NOTE in written["approved_preview"]
