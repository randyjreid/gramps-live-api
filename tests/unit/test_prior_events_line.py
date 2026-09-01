"""⛔ #154: the dialog shows what the record ALREADY holds, not only what is added.

The preview showed what would be written and never what was there, so a proposal
adding a second Census rendered exactly like a first — and catching it meant
knowing that person's events from memory, for four or five people at a time, at
the moment the tool is meant to help.

⭐ **Information, not judgement.** Nothing here says *duplicate*. A census saying
one year against a tree saying another is two sources disagreeing, which is the
owner's research and not a verdict a renderer can reach.

⚠️ **Its own file**, for the reason ``test_attachable_bound`` records: appending
node vocabulary to ``test_document_preview`` pushed that file's GEDCOM-X key
density past this repository's own P2 threshold.
"""

from __future__ import annotations

from typing import Any

from gramps_live_api.host import document


def node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node from keyword arguments, never a dict literal. See P2 above."""
    return dict(id=local_id, **fields)


REGISTER = node("s1", title="Invented Register")


def _adding_a_census() -> document.Graph:
    return document.parse(
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            events=[node("e1", type="Census", date="1900", people=["p1"])],
        )
    )


def _with_prior(prior: tuple[str, ...] | None) -> document.Resolution:
    return document.Resolution(
        nodes=(
            document.Resolved("p1", "I0001", "person", True, "Anon Invented", prior_events=prior),
        )
    )


def _line(rendered: str, needle: str) -> str:
    return next(line for line in rendered.splitlines() if needle in line)


# -- criterion 1: a line naming what they hold, or saying plainly they hold none


def test_the_events_the_person_already_holds_are_named() -> None:
    rendered = document.preview(_adding_a_census(), _with_prior(("Census, 1880", "Census, 1890")))

    line = _line(rendered, "already has")

    assert "Census, 1880" in line
    assert "Census, 1890" in line


def test_holding_none_of_them_is_SAID_rather_than_left_blank() -> None:
    """⛔ Criterion 1's second half. Saying nothing is not saying none."""
    rendered = document.preview(_adding_a_census(), _with_prior(()))

    assert "already has: none of these" in rendered, rendered


def test_the_line_sits_with_the_person_and_above_what_is_being_added() -> None:
    """⭐ The plan's shape: read the record, then read the addition."""
    lines = document.preview(_adding_a_census(), _with_prior(("Census, 1880",))).splitlines()

    person = next(i for i, line in enumerate(lines) if "I0001" in line)
    already = next(i for i, line in enumerate(lines) if "already has" in line)
    adding = next(i for i, line in enumerate(lines) if line.strip().startswith("+ Census"))

    assert person < already < adding


# -- criterion 4: it states nothing about duplication -------------------------


def test_the_dialog_never_calls_anything_a_duplicate() -> None:
    """⛔ No warning, no highlight, no verdict.

    ⚠️ Most event types legitimately repeat -- Residence, Occupation, Census --
    so a warning would fire constantly, and one that fires constantly is one
    nobody reads. That converts a real signal into noise.
    """
    rendered = document.preview(_adding_a_census(), _with_prior(("Census, 1900",))).casefold()

    for word in ("duplicate", "warning", "already exists", "same as", "conflict"):
        assert word not in rendered, f"{word!r} turns information into judgement"


def test_an_exact_year_match_reads_no_differently_from_any_other() -> None:
    """⚠️ Two sources disagreeing is research, not an error the tool resolves.

    ⭐ Asserted STRUCTURALLY: the two renderings must differ only where the year
    text differs. A first version ended in ``or True`` and asserted nothing.
    """
    same = document.preview(_adding_a_census(), _with_prior(("Census, 1900",)))
    other = document.preview(_adding_a_census(), _with_prior(("Census, 1880",)))

    assert same.replace("Census, 1900 ·", "X").replace(
        "already has: Census, 1900", "already has: X"
    ) == other.replace("Census, 1880 ·", "X").replace(
        "already has: Census, 1880", "already has: X"
    ), "an exact match is rendered differently from any other year"


# -- criterion 5: a failed read is stated, never omitted ----------------------


def test_a_read_that_FAILED_says_so() -> None:
    """⛔ An absent line reads as *holds nothing*.

    ⚠️ So silence would be a claim about the tree rather than an admission about
    the read -- and the dialog must still open either way.
    """
    rendered = document.preview(_adding_a_census(), _with_prior(None))

    assert "already has: (could not be read)" in rendered, rendered
    assert "THIS IS WHAT WOULD BE WRITTEN" in rendered, "the dialog must still open"


def test_the_three_states_are_all_distinguishable() -> None:
    """⭐ Holds some, holds none, could not be read -- three answers, three texts."""
    some = document.preview(_adding_a_census(), _with_prior(("Census, 1880",)))
    none = document.preview(_adding_a_census(), _with_prior(()))
    failed = document.preview(_adding_a_census(), _with_prior(None))

    assert len({some, none, failed}) == 3


def test_a_person_the_proposal_only_CITES_gets_no_line() -> None:
    """⭐ The plan's recommendation: nothing to compare against, so no line.

    ⛔ **And it decides a correctness question.** ``prior_events`` is ``None`` for
    a cited-only person *and* for a failed read, so without this the dialog would
    report them as unreadable -- which is false. The renderer asks whether the
    proposal touches the person, using the same pure function the accessor used
    to decide what to read.
    """
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            citations=[node("c1", source="s1", attach_to=["p1"])],
        )
    )
    resolution = document.Resolution(
        nodes=(document.Resolved("p1", "I0001", "person", True, "Anon Invented"),)
    )

    rendered = document.preview(graph, resolution)

    assert "already has" not in rendered, rendered
    assert "could not be read" not in rendered, rendered


# -- criterion 6: determinism -------------------------------------------------


def test_the_same_graph_renders_the_same_text_twice() -> None:
    graph = _adding_a_census()
    resolution = _with_prior(("Census, 1880", "Census, 1890"))

    assert document.preview(graph, resolution) == document.preview(graph, resolution)


# -- criteria 2 and 3, and the accessor that answers them ---------------------


class _Event:
    def __init__(self, kind: str, shown: str, private: bool = False) -> None:
        self._kind = kind
        self._shown = shown
        self._private = private

    def get_type(self) -> str:
        return self._kind

    def get_privacy(self) -> bool:
        return self._private

    def get_place_handle(self) -> str:
        return ""

    def get_gramps_id(self) -> str:
        return self._shown

    def get_date_object(self) -> Any:
        return None

    def get_description(self) -> str:
        return self._shown


class _Ref:
    def __init__(self, ref: str, private: bool = False) -> None:
        self.ref = ref
        self._private = private

    def get_privacy(self) -> bool:
        return self._private


class _Person:
    def __init__(self, refs: list[_Ref]) -> None:
        self._refs = refs

    def get_privacy(self) -> bool:
        return False

    def get_event_ref_list(self) -> list[_Ref]:
        return list(self._refs)

    def get_gramps_id(self) -> str:
        return "I0001"


class _Database:
    def __init__(self, person: _Person, events: dict[str, _Event]) -> None:
        self.person = person
        self.events = events

    def get_person_from_gramps_id(self, gramps_id: str) -> Any:
        return self.person if gramps_id == "I0001" else None

    def get_event_from_handle(self, handle: str) -> Any:
        return self.events.get(handle)


def _resolve(database: _Database, graph: dict[str, Any]) -> document.Resolution:
    from gramps_live_api.host import accessor
    from tests.fixtures.host import FakeDbState

    accessor.bind(FakeDbState(db=database))
    try:
        return accessor.resolve_nodes(graph)
    finally:
        accessor.forget()


_ADDING_A_CENSUS = dict(
    source=REGISTER,
    people=[node("p1", gramps_id="I0001")],
    events=[node("e1", type="Census", date="1900", people=["p1"])],
)


def test_the_line_is_read_from_the_TREE_and_never_from_the_proposal() -> None:
    """⛔ Criterion 2. The graph's own words must not appear in it."""
    database = _Database(_Person([_Ref("h1")]), {"h1": _Event("Census", "FROM THE TREE")})

    resolution = _resolve(database, _ADDING_A_CENSUS)

    assert resolution.nodes[0].prior_events is not None
    assert any("FROM THE TREE" in shown for shown in resolution.nodes[0].prior_events)


def test_a_PRIVATE_event_contributes_nothing() -> None:
    """⛔ Criterion 3. The existing gate applies, unchanged."""
    database = _Database(
        _Person([_Ref("h1"), _Ref("h2")]),
        {
            "h1": _Event("Census", "PUBLIC ONE"),
            "h2": _Event("Census", "PRIVATE ONE", private=True),
        },
    )

    resolution = _resolve(database, _ADDING_A_CENSUS)
    shown = " ".join(resolution.nodes[0].prior_events or ())

    assert "PUBLIC ONE" in shown
    assert "PRIVATE ONE" not in shown


def test_a_private_event_REFERENCE_contributes_nothing_either() -> None:
    """⚠️ The ref carries its own ``priv``, like a ChildRef does."""
    database = _Database(_Person([_Ref("h1", private=True)]), {"h1": _Event("Census", "HIDDEN")})

    resolution = _resolve(database, _ADDING_A_CENSUS)

    assert resolution.nodes[0].prior_events == ()


def test_only_the_types_the_proposal_TOUCHES_are_listed() -> None:
    """⭐ Adding a Census shows Census events, not a whole life.

    ⚠️ A dialog nobody finishes reading is the elision defect in a new form.
    """
    database = _Database(
        _Person([_Ref("h1"), _Ref("h2")]),
        {"h1": _Event("Census", "A CENSUS"), "h2": _Event("Burial", "A BURIAL")},
    )

    resolution = _resolve(database, _ADDING_A_CENSUS)
    shown = " ".join(resolution.nodes[0].prior_events or ())

    assert "A CENSUS" in shown
    assert "A BURIAL" not in shown


def test_the_type_match_is_case_folded() -> None:
    """⚠️ The graph carries a document's word; the tree carries Gramps' spelling."""
    database = _Database(_Person([_Ref("h1")]), {"h1": _Event("Census", "MATCHED")})
    lower = dict(_ADDING_A_CENSUS)
    lower["events"] = [node("e1", type="census", date="1900", people=["p1"])]

    resolution = _resolve(database, lower)

    assert "MATCHED" in " ".join(resolution.nodes[0].prior_events or ())


def test_a_person_only_CITED_is_never_asked_about() -> None:
    """⭐ The accessor half of the cited-only case: no read, so no cost."""
    database = _Database(_Person([_Ref("h1")]), {"h1": _Event("Census", "UNREAD")})

    resolution = _resolve(
        database,
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            citations=[node("c1", source="s1", attach_to=["p1"])],
        ),
    )

    assert resolution.nodes[0].prior_events is None


def test_an_event_ALREADY_in_the_tree_touches_nobody() -> None:
    """⛔ ``parse`` refuses participants on an attached event, so it adds nothing."""
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            events=[node("e_old", gramps_id="E9999")],
            citations=[node("c1", source="s1", attach_to=["e_old", "p1"])],
        )
    )

    assert document.types_the_proposal_touches(graph) == {}


def test_a_read_that_RAISES_answers_None_and_not_empty() -> None:
    """⛔ Criterion 5's accessor half, and a negative control found it missing.

    ⚠️ Reporting a failure as ``()`` would render *already has: none of these* --
    **a claim about the tree made from a read that never happened.** The renderer
    tests pass ``None`` in directly, so they prove the renderer handles it and say
    nothing about anyone producing it.
    """

    class _Exploding(_Person):
        def get_event_ref_list(self) -> list[_Ref]:
            raise RuntimeError("the tree is unavailable")

    database = _Database(_Exploding([]), {})

    resolution = _resolve(database, _ADDING_A_CENSUS)

    assert resolution.nodes[0].prior_events is None
    assert "could not be read" in document.preview(document.parse(_ADDING_A_CENSUS), resolution)


def test_an_event_with_NO_type_still_asks_about_its_people() -> None:
    """⛔ The writer stores it as ``Event``, so it adds one and must be compared.

    ⚠️ Skipping it excluded that person from ``touched``, so nothing read their
    prior events and the dialog omitted the line -- while the write went ahead.
    **The comparison was withheld precisely where the type is least informative.**
    """
    untyped = document.parse(
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            events=[node("e1", date="1900", people=["p1"])],
        )
    )

    assert document.types_the_proposal_touches(untyped) == {"p1": ("Event",)}


def test_an_untyped_event_gets_the_already_has_line() -> None:
    """⭐ End to end: the writer's fallback type is what the accessor looks up."""
    database = _Database(_Person([_Ref("h1")]), {"h1": _Event("Event", "AN UNTYPED ONE")})

    resolution = _resolve(
        database,
        dict(
            source=REGISTER,
            people=[node("p1", gramps_id="I0001")],
            events=[node("e1", date="1900", people=["p1"])],
        ),
    )

    assert "AN UNTYPED ONE" in " ".join(resolution.nodes[0].prior_events or ())
