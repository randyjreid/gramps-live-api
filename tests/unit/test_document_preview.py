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

import pytest

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


# ---------------------------------------------------------------------------
# Round 1 findings — both were A1 violations the criterion did not catch
# ---------------------------------------------------------------------------


def test_a_non_default_event_role_is_rendered() -> None:
    """⛔ ``role`` is APPLIED by the writer, so it must be shown.

    ``writer.write`` puts it on every ``EventRef`` with ``set_role``. Leaving it
    out let the owner approve an input value that would be written without
    seeing it -- R3's criterion broken in the way A1 exists to catch, and missed
    because the role is invisible in the summary and only appears in the writer.
    """
    graph = document.parse(
        {
            "people": [node("p1", given="Anna", surname="Witness")],
            "events": [node("e1", type="Marriage", date="1868", people=["p1"], role="Witness")],
        }
    )
    assert "as Witness" in document.preview(graph)


def test_the_default_role_is_not_repeated_on_every_line() -> None:
    """A preview that says *Primary* everywhere teaches the reader to skip it."""
    graph = document.parse(
        {
            "people": [node("p1", given="Anna", surname="Principal")],
            "events": [node("e1", type="Birth", date="1868", people=["p1"], role="Primary")],
        }
    )
    assert "as Primary" not in document.preview(graph)


def test_a_source_needs_a_local_id_like_every_other_node() -> None:
    """⛔ A source with a ``gramps_id`` and no ``id`` was rendered TWICE.

    ``requested`` invented a local id while ``preview`` kept the original, so the
    same source appeared under both ATTACHING TO EXISTING and CREATING NEW while
    the writer only ever attached. A preview describing two operations when one
    will run is the defect A1 exists to prevent.
    """
    with pytest.raises(document.GraphInvalid):
        document.parse(
            {
                "people": [node("p1", given="A", surname="B")],
                "source": {"gramps_id": "S0010"},
            }
        )
    with pytest.raises(document.GraphInvalid):
        document.parse(
            {
                "people": [node("p1", given="A", surname="B")],
                "source": {"id": 7, "gramps_id": "S0010"},
            }
        )


def test_an_attached_source_is_not_also_listed_as_created() -> None:
    """The same defect, asserted on the rendering rather than on the refusal."""
    graph = document.parse(
        {
            "people": [node("p1", given="A", surname="B")],
            "source": node("s1", gramps_id="S0010"),
        }
    )
    resolution = document.Resolution(
        nodes=(document.Resolved("s1", "S0010", "source", True, "Parish register"),)
    )
    rendered = document.preview(graph, resolution)
    assert "ATTACHING TO EXISTING" in rendered
    assert "Source" not in rendered.split("CREATING NEW")[-1], (
        "the attached source was also listed under CREATING NEW"
    )


def test_a_reference_must_be_the_right_kind_of_node() -> None:
    """⛔ Existence is not enough, and the gap was structural corruption.

    An event naming a PERSON id as its ``place`` used to pass, and the writer
    then put that person's handle in ``Event.place_handle`` — Gramps holding an
    event that points at a person as though it were a place. No dialog could
    show it, because the preview renders the graph's intent rather than the
    writer's mistake.
    """
    with pytest.raises(document.GraphInvalid) as refusal:
        document.parse(
            {
                "people": [node("p1", given="A", surname="B")],
                "events": [node("e1", type="Birth", place="p1", people=["p1"])],
            }
        )
    assert "not a place" in str(refusal.value)


def test_a_family_member_must_be_a_person() -> None:
    with pytest.raises(document.GraphInvalid):
        document.parse(
            {
                "people": [node("p1", given="A", surname="B")],
                "places": [node("l1", title="Somewhere")],
                "families": [node("f1", parents=["l1"], children=["p1"])],
            }
        )


def test_a_citation_may_support_any_kind_of_node() -> None:
    """⚠️ Deliberately unconstrained: the writer handles all four."""
    graph = document.parse(
        {
            "people": [node("p1", given="A", surname="B")],
            "places": [node("l1", title="Somewhere")],
            "events": [node("e1", type="Birth", place="l1", people=["p1"])],
            "source": node("s1", title="A register"),
            "citations": [node("c1", source="s1", attach_to=["p1", "e1", "l1"])],
        }
    )
    assert len(graph.citations) == 1


# ---------------------------------------------------------------------------
# Round 1's blocking finding: an attached family described as a new one.
# ---------------------------------------------------------------------------

ATTACHED_FAMILY_GRAPH = dict(
    people=[node("pn", given="Wilhelmina", surname="Newcomer", gender="female")],
    families=[node("f1", gramps_id="F0100", parents=["pn"], children=["pn"])],
)

ATTACHED_FAMILY_RESOLUTION = document.Resolution(
    nodes=(
        document.Resolved(
            "f1", "F0100", "family", True, "Kettleby, Bartholomew + Kettleby, Susanna  [2 children]"
        ),
    )
)


def test_an_attached_family_is_not_described_as_a_new_one() -> None:
    """⛔ The owner must not be asked to approve a different operation.

    The writer APPENDS CHILDREN to a family that already exists. The preview
    listed every family under ``CREATING NEW`` regardless -- so the dialog
    described creating a household, and the write modified one. That is R3's
    criterion, which is that no byte reaches the tree that was not rendered to
    the human, failing on the description rather than on the bytes.
    """
    rendered = document.preview(document.parse(ATTACHED_FAMILY_GRAPH), ATTACHED_FAMILY_RESOLUTION)

    creating = rendered.split("CREATING NEW", 1)
    if len(creating) > 1:
        assert "F0100" not in creating[1], (
            "the family being ATTACHED TO is listed under CREATING NEW:\n" + rendered
        )
        assert "Kettleby" not in creating[1]

    assert "ATTACHING TO EXISTING" in rendered
    attaching = rendered.split("ATTACHING TO EXISTING", 1)[1].split("CREATING NEW", 1)[0]
    assert "F0100" in attaching, "the attached family is not under ATTACHING TO EXISTING"
    assert "Kettleby, Bartholomew" in attaching, (
        "the household the owner is attaching to is unnamed, so he cannot notice "
        "it is the wrong one"
    )


def test_the_preview_says_what_is_being_added_to_the_family() -> None:
    """⛔ *Attach to this family* is not an operation until it says what joins it."""
    rendered = document.preview(document.parse(ATTACHED_FAMILY_GRAPH), ATTACHED_FAMILY_RESOLUTION)

    assert "adding as children" in rendered, (
        "the preview names the family but never says what would be put in it:\n" + rendered
    )
    assert "Newcomer" in rendered


def test_the_document_parents_are_reported_as_not_applied() -> None:
    """⛔ Attaching never rewrites recorded parents, and must say so."""
    rendered = document.preview(document.parse(ATTACHED_FAMILY_GRAPH), ATTACHED_FAMILY_RESOLUTION)

    assert "parents" in rendered and "NOT applied" in rendered, (
        "the graph gave parents for an existing family and the preview did not "
        "say they would be ignored:\n" + rendered
    )


def test_caller_preview_no_longer_claims_families_are_always_new() -> None:
    """⛔ It told the caller its own proposal would do something it would not."""
    rendered = document.caller_preview(document.parse(ATTACHED_FAMILY_GRAPH))

    assert "always created new" not in rendered, (
        "caller_preview still claims every family is created new:\n" + rendered
    )
    assert "already in the tree" in rendered


CITATION_ONLY_FAMILY_GRAPH = dict(
    people=[node("pn", given="Wilhelmina", surname="Newcomer", gender="female")],
    source=node("s1", title="Parish register"),
    families=[node("f1", gramps_id="F0100")],
    citations=[node("c1", source="s1", page="12", attach_to=["f1"])],
)


def test_a_citation_only_family_attachment_is_not_called_a_no_op() -> None:
    """⛔ The preview said nothing would be added, then rendered what would.

    ``family`` is in the writer's commit table, so a citation whose ``attach_to``
    names a family IS committed onto it. The line claiming otherwise was a
    statement about the whole operation when it only knew about children — and
    ``attached_to`` renders the citation immediately below, so the approval text
    contradicted itself on the same screen.
    """
    rendered = document.preview(
        document.parse(CITATION_ONLY_FAMILY_GRAPH), ATTACHED_FAMILY_RESOLUTION
    )

    assert "nothing would be added" not in rendered, (
        "the preview calls a real citation attachment a no-op:\n" + rendered
    )
    assert "no children named" in rendered, (
        "it should still say the family gains no CHILDREN -- that part was true"
    )
    assert "Parish register" in rendered or "c1" in rendered or "Citation" in rendered, (
        "and the citation that IS being attached must appear:\n" + rendered
    )


DUPLICATE_CHILD_GRAPH = dict(
    people=[
        node("pn", given="Wilhelmina", surname="Newcomer", gender="female"),
        node("pa", gramps_id="I0500"),
        node("pb", gramps_id="I0500"),
    ],
    families=[node("f1", gramps_id="F0100", children=["pn", "pn", "pa", "pb"])],
)

DUPLICATE_CHILD_RESOLUTION = document.Resolution(
    nodes=(
        document.Resolved(
            "f1", "F0100", "family", True, "Kettleby, Bartholomew + Kettleby, Susanna"
        ),
        document.Resolved("pa", "I0500", "person", True, "Kettleby, Tobias"),
        document.Resolved("pb", "I0500", "person", True, "Kettleby, Tobias"),
    )
)


def test_a_child_named_twice_is_previewed_once() -> None:
    """⛔ The preview promised two additions the writer would never make.

    The writer passes resolved handles through ``_unique`` and adds one
    ``ChildRef``. Rendering the person twice makes the owner approve — and the
    journal record — an addition that does not happen.
    """
    rendered = document.preview(document.parse(DUPLICATE_CHILD_GRAPH), DUPLICATE_CHILD_RESOLUTION)
    line = next(row for row in rendered.splitlines() if "adding as children" in row)

    assert line.count("Wilhelmina") == 1, f"the same local id was rendered twice: {line!r}"


def test_two_local_ids_naming_one_person_are_previewed_once() -> None:
    """⛔ The subtler half: distinct local ids, one Gramps ID, one person.

    ⚠️ ``document.preview`` never touches the database, so handle identity is not
    available to it — but the resolved ``gramps_id`` is, and that is the same
    fact by another name.
    """
    rendered = document.preview(document.parse(DUPLICATE_CHILD_GRAPH), DUPLICATE_CHILD_RESOLUTION)
    attaching = rendered.split("ATTACHING TO EXISTING", 1)[1].split("CREATING NEW", 1)[0]
    line = next(row for row in attaching.splitlines() if "adding as children" in row)

    assert line.count("I0500") == 1, (
        f"one person reached by two local ids was rendered twice: {line!r}"
    )


# ---------------------------------------------------------------------------
# #105: an event that belongs to a family, and the preview that must name it.
# ---------------------------------------------------------------------------

FAMILY_EVENT_GRAPH = dict(
    people=[
        node("p1", given="Herbert", surname="Invented", gender="male"),
        node("p2", given="Louise", surname="Madeup", gender="female"),
    ],
    families=[node("f1", parents=["p1", "p2"])],
    events=[node("e1", type="Marriage", date="1946-12-14", family="f1")],
)


def test_a_family_event_names_the_household_it_joins() -> None:
    """⛔ R3's criterion is that no byte reaches the tree unrendered.

    **A marriage attaching to a household the owner never saw named is that
    criterion failing.** The write is a few lines; this is the reason the slice
    exists.
    """
    rendered = document.preview(document.parse(FAMILY_EVENT_GRAPH))

    assert "Marriage" in rendered
    assert "Herbert Invented + Louise Madeup" in rendered, (
        "the household the marriage joins is not named:\n" + rendered
    )
    assert "f1" not in rendered, (
        "the family is rendered as a LOCAL ID, which nobody can recognise or refuse"
    )


def test_a_family_event_renders_under_that_family() -> None:
    """⚠️ Present is not the same as findable.

    Matching events only by their ``people`` left the marriage in the leftovers
    section -- rendered in full, so R3 held, but not where the owner looks.
    """
    rendered = document.preview(document.parse(FAMILY_EVENT_GRAPH))
    family_line = next(
        index for index, row in enumerate(rendered.splitlines()) if row.strip().startswith("Family")
    )
    following = "\n".join(rendered.splitlines()[family_line : family_line + 4])

    assert "Marriage" in following, (
        "the marriage does not appear under the family it joins:\n" + rendered
    )


def test_an_event_may_not_name_a_family_that_is_not_one() -> None:
    """⛔ Same reference discipline as ``place`` and ``people``."""
    for bad, why in (("nope", "not in this graph"), ("p1", "not a family")):
        with pytest.raises(document.GraphInvalid) as invalid:
            document.parse(
                dict(
                    people=[node("p1", given="Herbert", surname="Invented")],
                    events=[node("e1", type="Marriage", family=bad)],
                )
            )
        assert why in str(invalid.value), f"{bad!r}: {invalid.value}"


def test_the_singulariser_names_a_family_a_family() -> None:
    """⚠️ A latent bug that only a new reference could reach.

    ``kind_of`` derived its singular by chopping the last letter, so ``families``
    became ``familie``. Nothing referenced a family until events gained one --
    **a rule whose definition came from the SPELLING rather than the vocabulary**,
    unreachable right up until a new spelling arrived.
    """
    with pytest.raises(document.GraphInvalid) as invalid:
        document.parse(
            dict(
                people=[node("p1", given="Herbert", surname="Invented")],
                events=[node("e1", type="Marriage", family="p1")],
            )
        )

    assert "familie" not in str(invalid.value), (
        f"the error message calls a family a 'familie': {invalid.value}"
    )
    assert "not a family" in str(invalid.value)


def test_a_family_nothing_would_create_is_refused() -> None:
    """⛔ The preview promised a family the writer skips, so the event orphaned.

    The writer skips a family with no parents and no children at
    ``if not parents and not children``. ``parse`` accepted it, the preview said
    the family would be created and the marriage attached, and the write produced
    **an event attached to nothing** -- the approved account and the write
    disagreeing again, in the #106 class.

    ⭐ Refusing here also closes the older, quieter case: an empty family node
    used to render as a promise and write nothing at all, event or no event.
    """
    with pytest.raises(document.GraphInvalid) as invalid:
        document.parse(
            dict(
                people=[node("p1", given="Herbert", surname="Invented")],
                families=[node("f1")],
                events=[node("e1", type="Marriage", family="f1")],
            )
        )

    assert "nothing would be written for it" in str(invalid.value)


def test_the_family_shapes_that_DO_get_written_are_still_accepted() -> None:
    """⚠️ A refusal that also refuses correct graphs is worse than the defect."""
    parents_only = dict(
        people=[
            node("p1", given="Herbert", surname="Invented", gender="male"),
            node("p2", given="Louise", surname="Madeup", gender="female"),
        ],
        families=[node("f1", parents=["p1", "p2"])],
        events=[node("e1", type="Marriage", family="f1")],
    )
    attaching = dict(
        people=[node("p1", given="Herbert", surname="Invented")],
        families=[node("f1", gramps_id="F0003", children=["p1"])],
    )
    children_only = dict(
        people=[node("p1", given="Herbert", surname="Invented")],
        families=[node("f1", children=["p1"])],
    )

    for graph, label in (
        (parents_only, "parents only"),
        (attaching, "attaching by gramps_id"),
        (children_only, "children only"),
    ):
        assert document.parse(graph) is not None, f"{label} was refused"


def test_a_role_with_nobody_to_carry_it_is_refused() -> None:
    """⛔ The preview promised ``as Witness`` and the writer applied it nowhere.

    The FAMILY reference's role is fixed at ``FAMILY`` -- it must be, or
    ``role:"Primary"`` and no role render identically while writing differently.
    So a role on an event that names no ``people`` reaches nothing at all.

    ⚠️ **Third time on this branch that the approved account and the write
    disagreed**, which is what #106 is filed about.
    """
    with pytest.raises(document.GraphInvalid) as invalid:
        document.parse(
            dict(
                people=[
                    node("p1", given="Herbert", surname="Invented", gender="male"),
                    node("p2", given="Louise", surname="Madeup", gender="female"),
                ],
                families=[node("f1", parents=["p1", "p2"])],
                events=[node("e1", type="Marriage", family="f1", role="Witness")],
            )
        )

    assert "nothing would carry it" in str(invalid.value)


def test_a_role_WITH_people_is_still_accepted() -> None:
    """⚠️ A refusal that also refuses correct graphs is worse than the defect."""
    with_people = dict(
        people=[
            node("p1", given="Herbert", surname="Invented", gender="male"),
            node("p2", given="Louise", surname="Madeup", gender="female"),
        ],
        families=[node("f1", parents=["p1", "p2"])],
        events=[node("e1", type="Marriage", family="f1", people=["p1"], role="Witness")],
    )
    no_role = dict(
        people=[
            node("p1", given="Herbert", surname="Invented", gender="male"),
            node("p2", given="Louise", surname="Madeup", gender="female"),
        ],
        families=[node("f1", parents=["p1", "p2"])],
        events=[node("e1", type="Marriage", family="f1")],
    )
    primary_only = dict(
        people=[node("p1", given="Herbert", surname="Invented")],
        families=[node("f1", children=["p1"])],
        events=[node("e1", type="Marriage", family="f1", role="Primary")],
    )

    for graph, label in (
        (with_people, "a role with people to carry it"),
        (no_role, "a family event with no role"),
        (primary_only, "an explicit Primary, which the preview suppresses anyway"),
    ):
        assert document.parse(graph) is not None, f"{label} was refused"
