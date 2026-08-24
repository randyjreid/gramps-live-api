"""⛔ One declaration decides which kinds may name something that already exists.

``gramps_id`` is accepted on five kinds. **A fifth hand-written branch in a
dispatch that already had four is how the next kind gets forgotten** -- and the
failure is silent, because a kind nobody walks simply never resolves and its
``gramps_id`` is ignored rather than refused.

⚠️ **Its own file, deliberately.** These tests are mostly node vocabulary, and
appending them to ``test_document_preview`` pushed that file's GEDCOM-X key
density past this repository's own P2 threshold. ⛔ The fix is where the tests
live, never the guard's threshold.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from gramps_live_api.host import accessor, document
from tests.fixtures.host_sources import REPOSITORY_ROOT


def node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node. ⚠️ Spelled here rather than imported from another test
    module -- one test file importing another couples them, and this file exists
    precisely to keep its vocabulary out of that one."""
    return dict(id=local_id, **fields)


def test_every_ATTACHABLE_kind_is_resolved_and_every_other_kind_is_REFUSED() -> None:
    """⛔ One declaration drives advertisement, resolution and refusal.

    ``gramps_id`` is now accepted on five kinds. **A fifth hand-written branch in
    a dispatch that already had four is how the next kind gets forgotten** — and
    the failure is silent, because a kind nobody walks simply never resolves and
    its ``gramps_id`` is ignored rather than refused.

    ⭐ So a sixth kind becomes attachable by being declared in ``ATTACHABLE``, and
    this test fails if any of the three places stop agreeing with it.

    ⚠️ **The interface contradicting itself has already cost a round**:
    ``find_families`` told the model to pass a family ID while
    ``propose_document`` said families were always created new, so the model
    discarded the ID and created a second household.
    """

    # ⛔ Every attachable kind must actually RESOLVE — appear in `requested`.
    #
    # ⚠️ The graph is built from ``GROUPS`` rather than spelled out per kind: a
    # literal fixture per kind is a second list, and it is also enough clustered
    # genealogy vocabulary to trip this repository's own P2 density guard.
    def _minimal(extra_group: str, entry: dict[str, Any]) -> dict[str, Any]:
        """A graph carrying ``entry`` in ``extra_group``, and nothing else of note.

        ⚠️ ``people`` is always present because ``parse`` requires it, and
        ``source`` is a single node rather than a list -- the one structural
        exception in the graph.
        """
        base: dict[str, Any] = {"people": [node("p0")]}
        if extra_group == "source":
            base["source"] = dict(entry)
        else:
            base[extra_group] = [dict(entry)]
        return base

    for group, one in document.ATTACHABLE.items():
        body = _minimal(group, {"id": "x1", "gramps_id": "X0001"})
        requested = document.requested(document.parse(body))
        wanted = "x1"
        assert any(r.local_id == wanted and r.kind == one for r in requested), (
            f"{group!r} is declared attachable and does not reach `requested`, so its "
            f"gramps_id would be silently ignored rather than resolved"
        )

    # ⛔ And every kind that is NOT attachable must be REFUSED, naming itself.
    for group, one in document.GROUPS.items():
        if group in document.ATTACHABLE:
            continue
        entry: dict[str, Any] = {"id": "x1", "gramps_id": "X0001"}
        if group == "citations":
            entry = {"id": "c1", "source": "s1", "gramps_id": "X0001"}
        if group == "notes":
            entry = {"text": "x", "gramps_id": "X0001"}
        body = _minimal(group, entry)
        if group == "citations":
            body["source"] = node("s1")

        with pytest.raises(document.GraphInvalid) as invalid:
            document.parse(body)
        assert one in str(invalid.value) or group in str(invalid.value), (
            f"{group!r} is not attachable and its refusal does not name it: {invalid.value}"
        )


def test_an_event_gramps_id_that_does_not_resolve_refuses_the_WHOLE_batch() -> None:
    """⛔ Falling back to creating is the duplicate the id existed to prevent.

    ⚠️ And it would do it silently — the owner approved *attach a citation to
    E0060*, and a fallback would write a second E-something carrying that
    citation while the dialog said otherwise.
    """
    graph = dict(people=[node("p1")], events=[node("e1", gramps_id="E9999")])
    document.parse(graph)  # accepted: the id is well-formed and events attach

    # The resolver reports it missing; the preview must not render it as attached.
    resolution = document.Resolution(
        nodes=(
            document.Resolved(
                local_id="e1", gramps_id="E9999", kind="event", found=False, display=""
            ),
        )
    )
    assert resolution.refusal() is not None, (
        "an unresolved event id must refuse the batch rather than fall through to "
        "creating a second copy of the event"
    )
    assert "E9999" in str(resolution.refusal())


def test_an_ATTACHED_event_may_not_also_name_participants() -> None:
    """⛔ The preview promised a relationship the writer never wrote.

    An event carrying a ``gramps_id`` and also ``people`` or ``family`` parsed
    cleanly, the approval dialog rendered a ``+`` for it under each named target,
    and the writer's attach path skipped **both** the person ``EventRef`` loop and
    the deferred family attachment. **So the owner approved a relationship that was
    never written** — the preview/writer class, with six recorded instances, in the
    code added to let a citation reach an existing event.

    ⭐ **Refused rather than dropped-and-reported.** Dropping leaves the caller
    believing it can express participation on an existing event, and leaves the
    rendering to be suppressed separately; refusing makes the disagreement
    impossible rather than announced.
    """
    for extra in ({"people": ["p1"]}, {"family": "f1"}):
        body: dict[str, Any] = {
            "people": [node("p1", gramps_id="I0001"), node("p2")],
            "families": [node("f1", parents=["p1", "p2"])],
            "events": [dict(node("e1", gramps_id="E0060"), **extra)],
        }
        with pytest.raises(document.GraphInvalid) as invalid:
            document.parse(body)
        message = str(invalid.value)
        assert "keeps the participants it has" in message, message
        assert "e1" in message, "the refusal must name the node"

    # ⭐ The case this feature exists for is untouched: an attached event with a
    # citation and nothing else.
    fine = {
        "people": [node("p1", gramps_id="I0001")],
        "events": [node("e1", gramps_id="E0060")],
        "source": node("s1"),
        "citations": [node("c1", source="s1", attach_to=["e1"])],
    }
    assert document.parse(fine) is not None

    # ⚠️ And a CREATED event still carries participants, which is most events.
    created = {
        "people": [node("p1")],
        "events": [node("e1", people=["p1"])],
    }
    assert document.parse(created) is not None


def test_the_caller_preview_agrees_with_the_dialog_about_attached_events() -> None:
    """⛔ The agent's immediate answer contradicted the approval dialog.

    ``caller_preview`` reported **every** event as *always created new*. For a
    proposal that correctly named an existing event, the caller was told it was
    about to create one — so it could abandon or "fix" a correct proposal, and
    **produce the duplicate by fixing it.**
    """
    graph = document.parse(
        {
            "people": [node("p1", gramps_id="I0001")],
            "events": [node("e1", gramps_id="E0060")],
            "source": node("s1"),
            "citations": [node("c1", source="s1", attach_to=["e1"])],
        }
    )
    text = document.caller_preview(graph)

    assert "event   E0060" in text, "an attached event is not listed as attaching"
    assert "1 events (always created new)" not in text, (
        "the caller is told an existing event will be created new"
    )
    assert "attaching to an event already in the tree" in text


def test_a_created_event_carries_a_DESCRIPTION_and_the_preview_shows_it() -> None:
    """⛔ A census line's occupation had nowhere structured to go.

    ``events[]`` carried type, date, place, people and role — so an occupation,
    a relationship to head, or a marital status ended up in note prose, which
    nothing can query. The tree's own events already carry such strings.

    ⚠️ **And the preview must render it.** A description written and not shown is
    the preview/writer class, which this project has six recorded instances of —
    so this asserts the rendering, not merely that the field parses.
    """
    graph = document.parse(
        {
            "people": [node("p1")],
            "events": [node("e1", type="Census", date="1930-04-01", description="a clause")],
        }
    )
    assert graph.events[0]["description"] == "a clause"

    shown = document.preview(graph, document.Resolution())
    assert "a clause" in shown, "the description is written and not shown"


def test_an_ATTACHED_event_DROPS_its_description_and_says_so() -> None:
    """⛔ Same rule as every other field on an attached node.

    An event already in the tree keeps its own description; applying the
    payload's would be editing a record the owner asked to attach to.
    """
    graph = document.parse(
        {
            "people": [node("p1", gramps_id="I0001")],
            "events": [node("e1", gramps_id="E0060", description="not applied")],
        }
    )
    assert "description" in document.dropped_fields(graph.events[0]), (
        "an attached event's description is not reported as dropped"
    )

    resolution = document.Resolution(
        nodes=(
            document.Resolved(
                local_id="e1", gramps_id="E0060", kind="event", found=True, display="Service 1932"
            ),
        )
    )
    shown = document.preview(graph, resolution)
    assert "NOT applied" in shown and "description" in shown, (
        "the owner is not told the description was dropped"
    )


def test_a_PRIMARY_role_on_an_attached_event_is_refused_like_any_other() -> None:
    """⛔ A conclusion generalised from one case, and it was wrong.

    An earlier note in ``document.py`` claimed ``role`` could never survive on an
    attached event — reasoned from a **non-Primary** role, which is refused for
    having no carriers. ⚠️ ``role: "Primary"`` takes a different path: that check
    only rejects non-Primary roles, so it was accepted, silently discarded by the
    writer, and **not reported as dropped** — contradicting the tool's own promise
    that supplied roles are shown as dropped.

    ⭐ Both are now refused by name, so there is no state needing a report.
    """
    for role in ("Primary", "primary", "Witness", "Informant"):
        with pytest.raises(document.GraphInvalid) as invalid:
            document.parse(
                {
                    "people": [node("p1", gramps_id="I0001")],
                    "events": [node("e1", gramps_id="E0060", role=role)],
                }
            )
        assert "role" in str(invalid.value), f"{role}: {invalid.value}"

    # ⭐ A CREATED event still takes a role, which is most of their use.
    assert (
        document.parse(
            {
                "people": [node("p1")],
                "events": [node("e1", type="Baptism", people=["p1"], role="Witness")],
            }
        )
        is not None
    )


def test_the_MCP_INSTRUCTION_and_the_PARSER_agree_about_attached_events() -> None:
    """⛔ The instruction is a claim about the code, and it was false.

    ⚠️ After ``role`` became refused rather than dropped, ``server.py`` still told
    callers their role would be *"dropped and shown to the owner as dropped"*. A
    caller following the documented instruction had its **entire proposal
    rejected** -- so the text that exists to stop a duplicate was itself the thing
    producing the failure.

    ⭐ This asserts the agreement rather than the sentence, so the next person to
    move a field between REFUSED and DROPPED cannot leave the instruction behind.
    """
    instruction = (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    refused = ("people", "family", "role")
    dropped = ("type", "date", "place", "description")

    # The instruction names all three as refused, in one sentence, and none of
    # them as merely dropped.
    sentence = instruction[instruction.index("An attached event also keeps") :][:400]
    for field in refused:
        assert f'"{field}"' in sentence, f"the instruction does not name {field} as refused"

    values = {
        "people": ["p1"],
        "family": "f1",
        "role": "Primary",
        "type": "Baptism",
        "date": "1881-04-02",
        "place": "pl1",
        "description": "a description the tree already has",
    }

    for field in refused:
        with pytest.raises(document.GraphInvalid):
            document.parse(
                {
                    "people": [node("p1", gramps_id="I0001")],
                    "families": [node("f1", gramps_id="F0001")],
                    "places": [node("pl1", title="Amherst County, Invented")],
                    "events": [node("e1", gramps_id="E0060", **{field: values[field]})],
                }
            )

    for field in dropped:
        entry = node("e1", gramps_id="E0060", **{field: values[field]})
        parsed = document.parse(
            {
                "people": [node("p1", gramps_id="I0001")],
                "places": [node("pl1", title="Amherst County, Invented")],
                "events": [entry],
            }
        )
        reported = document.dropped_fields(parsed.events[0])
        assert field in reported, (
            f"the instruction promises {field} is shown to the owner as dropped, "
            f"but it is not reported: {reported}"
        )
        # ⛔ And it must reach the owner's DIALOG, not just a tuple -- rendered
        # the way the host renders it, with a resolution (``host.py:588``). A
        # field recorded as dropped and never shown is the preview/writer class
        # in its quietest form.
        shown = document.preview(
            parsed,
            document.Resolution(
                nodes=(
                    document.Resolved(
                        local_id="p1",
                        kind="person",
                        gramps_id="I0001",
                        found=True,
                        display="Tabitha Quillfeather",
                    ),
                    document.Resolved(
                        local_id="e1",
                        kind="event",
                        gramps_id="E0060",
                        found=True,
                        display="Census 1880 at Amherst County, Invented",
                    ),
                )
            ),
        )
        assert field in shown, f"{field} is recorded as dropped but never rendered:\n{shown}"
        # ⛔ The SUPPLIED value must not appear as if it would be written.
        assert str(values[field]) not in shown, (
            f"the dialog shows the value supplied for {field}, which is dropped -- "
            f"the owner would approve a value the writer never applies:\n{shown}"
        )


def test_the_INSTRUCTION_names_the_right_lookup_for_FAMILY_owned_events() -> None:
    """⛔ Pointing a caller at the wrong lookup looks exactly like *no such event*.

    ⚠️ The instruction said only *"look it up with list_events"*. A marriage is
    owned by the FAMILY, not by either spouse -- ``EventBase.get_event_ref_list``
    returns each object's OWN list, and ``Person.family_list`` holds family
    handles, not the family's event refs, so nothing bridges them. A caller asking
    ``list_events`` about a marriage gets an empty answer **whether or not the
    marriage is there**, and creates the second marriage record for a couple who
    already have one.

    ⭐ Confirmed live before the fix: family F0001 carries its Marriage, and it is
    reachable only through ``list_family_events``.

    ⚠️ This is the finding the birth/death one was mistaken for. That one claimed
    a store the person'"'"'s list did not cover, and was wrong because ``birth_ref``
    is an INDEX into that very list. This one is right because a family is a
    different object with its own list and no index back. **The difference is
    whether an index bridges the two stores, and it is worth checking rather than
    reasoning about.**
    """
    instruction = (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    guidance = instruction[instruction.index("IF AN EVENT ALREADY EXISTS") :][:1200]

    assert "list_family_events" in guidance, (
        "the lookup guidance never names list_family_events, so a caller looking "
        "for a marriage is sent to a tool that cannot return one"
    )
    # ⛔ The sentence that names the family route must itself name what is
    # family-owned. ⚠️ A first version accepted "marriage" anywhere in the
    # guidance and so passed against text that had stopped saying which events
    # those are -- the word survives in a later sentence. The control was
    # SILENT, which is the only reason this is written the narrow way.
    route = guidance[
        guidance.index("list_family_events") - 260 : guidance.index("list_family_events")
    ]
    assert "MARRIAGE" in route, (
        "the sentence pointing at list_family_events does not say which events "
        f"are family-owned, so naming the tool does not say when to use it: {route!r}"
    )
    # ⛔ Both routes named, and the person route still named -- a fix that sent
    # everything to list_family_events would break the common case.
    assert "list_events" in guidance


class _AnyRecord:
    """A record every getter returns. ⛔ Public, so ``_public`` lets it through."""

    def get_privacy(self) -> bool:
        return False

    def get_handle(self) -> str:
        return "a_handle"


class _AnswersEveryGetter:
    """A database whose every ``get_*_from_gramps_id`` finds something.

    ⛔ **The point is that a MISS here can only mean the dispatch did not handle
    the kind**, never that the record was absent -- so the assertion is about the
    enumeration and nothing else.
    """

    def __getattr__(self, name: str) -> Any:
        if name.startswith("get_") and name.endswith("_from_gramps_id"):
            return lambda gramps_id: _AnyRecord()
        raise AttributeError(name)


def test_every_ATTACHABLE_kind_reaches_BOTH_dispatches_that_must_know_it() -> None:
    """⛔ The bound this file is named for, which it did not previously have.

    ⚠️ The test above proves only that an attachable kind reaches
    ``document.requested()``. It says nothing about the two **separate,
    hand-maintained enumerations** that must also know the kind:

    * ``accessor._by_gramps_id`` -- an ``if kind == ...`` chain that falls
      through to ``return False, None``. A kind missing there makes ``/resolve``
      report a **valid Gramps ID as missing**.
    * ``gramps_live_api_writer._BY_GRAMPS_ID`` -- a dict. A kind missing there
      makes ``_existing()`` unable to fetch the record it was told to attach to.

    ⭐ So adding a kind to ``ATTACHABLE`` could break the resolver or the writer
    **while the "every attachable kind is resolved" test stayed green** -- a check
    succeeding for a reason unrelated to the property it names, in the file
    written to bound that property. Raised by a review round; it was right.
    """
    specification = importlib.util.spec_from_file_location(
        "a_writer_under_test", REPOSITORY_ROOT / "gramps_plugin" / "gramps_live_api_writer.py"
    )
    assert specification is not None and specification.loader is not None
    writer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(writer)

    database = _AnswersEveryGetter()

    for group, kind in document.ATTACHABLE.items():
        existed, found = accessor._by_gramps_id(database, kind, "X0001")
        assert existed and found is not None, (
            f"{group!r} ({kind!r}) is declared attachable but accessor._by_gramps_id "
            "does not handle it, so /resolve would report a VALID Gramps ID as "
            "missing and the caller would create a duplicate"
        )

        assert kind in writer._BY_GRAMPS_ID, (
            f"{group!r} ({kind!r}) is declared attachable but the writer has no "
            f"getter for it, so _existing() cannot fetch what it was told to "
            f"attach to: {sorted(writer._BY_GRAMPS_ID)}"
        )
