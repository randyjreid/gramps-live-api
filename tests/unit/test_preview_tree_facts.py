"""⛔ What the tree knows, carried to a renderer that cannot ask it.

``document.py`` imports neither ``gramps`` nor ``gi``, which is what lets the
whole renderer run under CI. The cost was that it could not see two things the
**writer** sees, and it rendered as though they did not exist:

* which children a family **already holds** -- the writer appends only the rest,
  so the preview promised additions the write skips;
* whether Gramps can **read a date** -- the writer folds an unreadable one into
  the description, so the preview showed a date field the record would not have.

⭐ **Both are now answered by the host and carried in ``Resolution``.** Nothing
here parses a date or reads a tree; these tests hand the renderer the answers and
check what it draws.

⚠️ **Its own file, deliberately** -- appending to ``test_document_preview``
pushed that file's GEDCOM-X key density past this repository's own P2 threshold
once already, and ``test_attachable_bound`` records the same lesson.
"""

from __future__ import annotations

from typing import Any

from gramps_live_api.host import document


def node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node, built from keyword arguments rather than a dict literal.

    ⚠️ Spelled here rather than imported from another test module, for the reason
    ``test_attachable_bound`` gives: one test file importing another couples them.
    """
    return dict(id=local_id, **fields)


REGISTER = node("s1", title="Invented Register")


def _family_graph(children: list[str]) -> document.Graph:
    return document.parse(
        dict(
            source=REGISTER,
            people=[node(local, gramps_id=f"I000{n}") for n, local in enumerate(children, start=1)],
            families=[node("f1", gramps_id="F0001", children=list(children))],
        )
    )


def _family_resolution(children: list[str], already: tuple[str, ...]) -> document.Resolution:
    nodes = [document.Resolved("f1", "F0001", "family", True, "Household", children=already)]
    nodes += [
        document.Resolved(local, f"I000{n}", "person", True, f"Person {n}")
        for n, local in enumerate(children, start=1)
    ]
    return document.Resolution(nodes=tuple(nodes))


# -- criterion 2: only children that will actually be added -------------------


def test_a_child_already_in_the_family_is_NOT_listed_as_being_added() -> None:
    """⛔ The writer appends only children the family does not already hold.

    ``known = {ref.ref for ref in family.get_child_ref_list()}`` and then
    ``if child in known: continue``. The preview listed every named child, so it
    stated an addition that does not happen.
    """
    rendered = document.preview(
        _family_graph(["a", "b"]), _family_resolution(["a", "b"], already=("I0002",))
    )

    adding = next(line for line in rendered.splitlines() if "adding as children" in line)

    assert "I0001" in adding
    assert "I0002" not in adding, rendered


def test_when_every_named_child_is_already_there_nothing_is_claimed() -> None:
    """⚠️ And the line must not still say *adding*, which was the whole defect."""
    rendered = document.preview(_family_graph(["a"]), _family_resolution(["a"], already=("I0001",)))

    assert "adding as children" not in rendered, rendered
    assert "no children would be added" in rendered, rendered


def test_a_family_naming_NO_children_says_what_it_always_said() -> None:
    """⛔ The pre-existing sentence, unchanged.

    ⚠️ A test already asserts this wording for its own recorded reason -- a
    citation-only family attachment must not be called a no-op. Three cases exist
    here precisely so that one keeps its answer.
    """
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("a", gramps_id="I0001")],
            families=[node("f1", gramps_id="F0001")],
            citations=[node("c1", source="s1", attach_to=["f1"])],
        )
    )
    resolution = document.Resolution(
        nodes=(document.Resolved("f1", "F0001", "family", True, "Household"),)
    )

    assert "no children named for this family" in document.preview(graph, resolution)


# -- criterion 3: already-there children are SHOWN, not omitted ---------------


def test_a_child_already_there_is_shown_separately_and_never_dropped() -> None:
    """⛔ Silent omission loses the fact the owner most needs.

    ⚠️ Dropping the name entirely makes *the agent did not propose this person*
    and *the agent proposed them and they were already here* look identical --
    **and that difference is what tells the owner whether the agent's lookups
    worked.**
    """
    rendered = document.preview(
        _family_graph(["a", "b"]), _family_resolution(["a", "b"], already=("I0002",))
    )

    assert "already in this family, so not added again" in rendered, rendered
    already = next(line for line in rendered.splitlines() if "already in this family" in line)
    assert "I0002" in already
    assert "I0001" not in already, rendered


def test_the_two_lines_are_separate_so_neither_reads_as_the_other() -> None:
    rendered = document.preview(
        _family_graph(["a", "b"]), _family_resolution(["a", "b"], already=("I0002",))
    )
    lines = [line for line in rendered.splitlines() if line.strip().startswith("+ ")]

    assert sum(1 for line in lines if "adding as children" in line) == 1
    assert sum(1 for line in lines if "already in this family" in line) == 1


def test_a_child_being_CREATED_can_never_count_as_already_there() -> None:
    """⭐ It has no Gramps ID, so its key is its local id and cannot match."""
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("newcomer", given="Anon", surname="Invented")],
            families=[node("f1", gramps_id="F0001", children=["newcomer"])],
        )
    )
    resolution = document.Resolution(
        nodes=(document.Resolved("f1", "F0001", "family", True, "Household", children=("I0001",)),)
    )

    rendered = document.preview(graph, resolution)

    assert "adding as children" in rendered, rendered
    assert "already in this family" not in rendered, rendered


# -- criteria 4 and 5: an unreadable date renders as it will be STORED --------


def _dated(text: str, description: str = "") -> document.Graph:
    fields: dict[str, Any] = dict(type="Census", date=text, people=["q1"])
    if description:
        fields["description"] = description
    return document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[node("e1", **fields)],
        )
    )


def test_an_unreadable_date_is_not_drawn_as_a_date() -> None:
    """⛔ The record will not have one, so the dialog must not show one."""
    rendered = document.preview(
        _dated("12 Brumaire An VII"), document.Resolution(unparseable_dates=("e1",))
    )

    line = next(line for line in rendered.splitlines() if "Census" in line)

    assert "Census," not in line, line


def test_an_unreadable_date_appears_as_the_writer_will_STORE_it() -> None:
    """⭐ The writer's own string: ``date as written: <text>``, joined by ``;``."""
    rendered = document.preview(
        _dated("12 Brumaire An VII", "occupation: weaver"),
        document.Resolution(unparseable_dates=("e1",)),
    )
    unwrapped = " ".join(rendered.split())

    assert "occupation: weaver; date as written: 12 Brumaire An VII" in unwrapped, rendered


def test_an_unreadable_date_with_no_description_still_says_what_is_stored() -> None:
    """⚠️ The writer joins a LIST; with nothing else in it the date stands alone."""
    rendered = document.preview(
        _dated("12 Brumaire An VII"), document.Resolution(unparseable_dates=("e1",))
    )
    unwrapped = " ".join(rendered.split())

    assert "date as written: 12 Brumaire An VII" in unwrapped, rendered
    assert "; date as written" not in unwrapped, "no empty description should be joined onto"


# -- criterion 6: a readable date is unchanged --------------------------------


def test_a_readable_date_renders_exactly_as_before() -> None:
    """⛔ No verdict means readable, and readable means no change at all."""
    graph = _dated("1900", "occupation: weaver")

    assert document.preview(graph) == document.preview(graph, document.Resolution())


def test_an_empty_verdict_list_changes_nothing() -> None:
    """⚠️ The degraded path: a verdict that could not be obtained is empty, and an
    empty one must render as the dialog always did rather than inventing one."""
    graph = _dated("12 Brumaire An VII", "occupation: weaver")

    assert document.preview(graph, document.Resolution(unparseable_dates=())) == document.preview(
        graph
    )


def test_only_the_named_event_is_affected() -> None:
    """⭐ Two events, one verdict. The other must be untouched."""
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[
                node("e1", type="Census", date="12 Brumaire An VII", people=["q1"]),
                node("e2", type="Birth", date="1870", people=["q1"]),
            ],
        )
    )

    rendered = document.preview(graph, document.Resolution(unparseable_dates=("e1",)))

    assert "Birth, 1870" in rendered, rendered
    assert "Census, 12 Brumaire" not in rendered, rendered


# -- §4's bound: the privacy property is not reachable from here --------------


def test_children_carries_ids_only_and_nothing_else_is_rendered_from_it() -> None:
    """⛔ A Gramps ID the graph never named must not appear in the dialog.

    ⚠️ ``Resolved.children`` is tree-derived data crossing into the renderer, and
    the renderer must only ever test membership against it. **A private child is
    dropped upstream by the gated fetch**, but this asserts the weaker property
    the renderer itself owns: an id in that tuple is never printed unless the
    graph named the person.
    """
    rendered = document.preview(
        _family_graph(["a"]),
        _family_resolution(["a"], already=("I0999", "I0001")),
    )

    assert "I0999" not in rendered, rendered


def test_missing_still_holds_a_private_node_after_the_extension() -> None:
    """⛔ ``missing`` must keep carrying private nodes.

    ⚠️ Excluding them once made a private node the ONE id that is neither found
    nor missing, and a caller comparing the two lists could read that difference
    back as *this record exists and you may not see it*. The new field must not
    have disturbed it.
    """
    private = document.Resolved("p1", "I0001", "person", found=False, private=True)
    resolution = document.Resolution(nodes=(private,), unparseable_dates=("e1",))

    assert private in resolution.missing
    assert private in resolution.refused
    assert "private" in (resolution.refusal() or "")


# -- criterion 1: the HOST resolves the family's current children -------------


class _Child:
    """⚠️ ``get_privacy()``, because that is what ``_public`` asks.

    A first version of this fake exposed a ``.private`` attribute instead. The
    gate never looks at one, so a "private" child came back public and the test
    failed -- **correctly**: the fixture was wrong, not the gate.
    """

    def __init__(self, gramps_id: str, private: bool = False) -> None:
        self._gramps_id = gramps_id
        self._private = private

    def get_privacy(self) -> bool:
        return self._private

    def get_gramps_id(self) -> str:
        return self._gramps_id


class _Ref:
    """⚠️ A ChildRef carries its OWN ``priv`` -- the person may be public while
    their membership of this family is not."""

    def __init__(self, ref: str, private: bool = False) -> None:
        self.ref = ref
        self._private = private

    def get_privacy(self) -> bool:
        return self._private


class _Family:
    def __init__(self, refs: list[str]) -> None:
        self._refs = [_Ref(r) for r in refs]
        self.gramps_id = "F0001"

    def get_privacy(self) -> bool:
        return False

    def get_child_ref_list(self) -> list[_Ref]:
        return list(self._refs)

    def get_gramps_id(self) -> str:
        return self.gramps_id


class _Database:
    def __init__(self, family: _Family, people: dict[str, _Child]) -> None:
        self.family = family
        self.people = people

    def get_family_from_gramps_id(self, gramps_id: str) -> Any:
        return self.family if gramps_id == "F0001" else None

    def get_person_from_handle(self, handle: str) -> Any:
        return self.people.get(handle)


def test_the_accessor_reads_a_familys_current_children_into_the_resolution() -> None:
    """⛔ Criterion 1. The tree's answer, fetched where tree reads are allowed.

    ⚠️ ``accessor.py`` is the only module permitted to reach the database, and it
    imports neither ``gramps`` nor ``gi`` -- it duck-types on the injected
    ``dbstate``. That is why this can be exercised with a plain fake.
    """
    from gramps_live_api.host import accessor

    database = _Database(_Family(["h1", "h2"]), {"h1": _Child("I0001"), "h2": _Child("I0002")})

    assert accessor._children_of(database, "family", database.family) == ("I0001", "I0002")


def test_a_PRIVATE_child_never_reaches_the_renderer() -> None:
    """⛔ Through ``_public``, like every other fetch in that module.

    ⭐ A dropped child is classified as *being added*, which is the safe
    direction: the dialog then claims an addition that may not happen, rather
    than naming a person the owner is not permitted to see.
    """
    from gramps_live_api.host import accessor

    database = _Database(
        _Family(["h1", "h2"]),
        {"h1": _Child("I0001"), "h2": _Child("I0002", private=True)},
    )

    assert accessor._children_of(database, "family", database.family) == ("I0001",)


def test_nothing_but_a_family_carries_children() -> None:
    from gramps_live_api.host import accessor

    database = _Database(_Family([]), {})

    assert accessor._children_of(database, "person", object()) == ()
    assert accessor._children_of(database, "family", None) == ()


# -- criterion 4: the verdict is the WRITER'S, obtained from the writer --------


def _plugin() -> Any:
    """The host plugin, loaded BY PATH.

    ⚠️ ``gramps_plugin/`` is outside the package and CONTRIBUTING forbids the
    package importing it. Loading the file here is a test reaching for a file,
    which is a different thing from a dependency.
    """
    import importlib.util

    from tests.fixtures.host_sources import PLUGIN_DIRECTORY

    path = PLUGIN_DIRECTORY / "gramps_live_api_host.py"
    specification = importlib.util.spec_from_file_location("a_host_for_dates", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _Writer:
    """A stand-in for the writer, recording what it was asked."""

    def __init__(self, unreadable: set[str]) -> None:
        self.unreadable = unreadable
        self.asked: list[str] = []

    def _gramps_date(self, text: str) -> Any:
        self.asked.append(text)
        return None if text in self.unreadable else object()


def test_the_plugin_asks_the_WRITER_and_never_parses_a_date_itself() -> None:
    """⛔ One implementation of *does this parse*, and it is the writer's.

    ⭐ The parser is ``gramps.gen.datehandler`` and nothing under ``src/`` may
    import ``gramps`` -- so the verdict is taken here, in the one file already
    permitted to, by calling the function the write itself will use.
    """
    plugin = _plugin()
    parsed = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[
                node("e1", type="Census", date="12 Brumaire An VII", people=["q1"]),
                node("e2", type="Birth", date="1870", people=["q1"]),
            ],
        )
    )
    writer = _Writer(unreadable={"12 Brumaire An VII"})

    enriched = plugin._with_date_verdicts(document.Resolution(), parsed, writer, lambda *a: None)

    assert enriched.unparseable_dates == ("e1",)
    assert writer.asked == ["12 Brumaire An VII", "1870"]


def test_an_event_ALREADY_in_the_tree_is_not_asked_about() -> None:
    """⛔ Its date is not being written, so it is not being previewed as written.

    ``parse`` refuses participants on an attached event and the writer never
    touches its fields -- *attached to, never altered*.
    """
    plugin = _plugin()
    parsed = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            citations=[node("c1", source="s1", attach_to=["e_old"])],
            events=[node("e_old", gramps_id="E9999")],
        )
    )
    writer = _Writer(unreadable=set())

    enriched = plugin._with_date_verdicts(document.Resolution(), parsed, writer, lambda *a: None)

    assert enriched.unparseable_dates == ()
    assert writer.asked == []


def test_a_verdict_that_cannot_be_obtained_degrades_to_the_old_behaviour() -> None:
    """⚠️ Never past it. Inventing an unreadable date would move a real one into
    the description -- a new wrong preview in place of the old one."""
    plugin = _plugin()
    parsed = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[node("e1", type="Census", date="1900", people=["q1"])],
        )
    )

    class _Exploding:
        def _gramps_date(self, text: str) -> Any:
            raise RuntimeError("the parser is unavailable")

    said: list[str] = []
    enriched = plugin._with_date_verdicts(
        document.Resolution(), parsed, _Exploding(), lambda level, message: said.append(message)
    )

    assert enriched.unparseable_dates == ()
    assert said and "render as before" in said[0]


def test_the_resolution_is_otherwise_untouched() -> None:
    """⭐ ``dataclasses.replace``: the nodes, and the privacy property, survive."""
    plugin = _plugin()
    private = document.Resolved("p1", "I0001", "person", found=False, private=True)
    parsed = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[node("e1", type="Census", date="12 Brumaire An VII", people=["q1"])],
        )
    )

    enriched = plugin._with_date_verdicts(
        document.Resolution(nodes=(private,)),
        parsed,
        _Writer(unreadable={"12 Brumaire An VII"}),
        lambda *a: None,
    )

    assert enriched.nodes == (private,)
    assert private in enriched.missing
    assert enriched.unparseable_dates == ("e1",)


def test_resolve_nodes_actually_PUTS_the_children_in_the_resolution() -> None:
    """⛔ Criterion 1's wiring, which the helper's own tests do not reach.

    ⚠️ **A negative control found this gap.** Deleting the ``children=`` argument
    from ``resolve_nodes`` left every other test in this file green: they call
    ``_children_of`` directly, so they prove the helper works and say nothing
    about anyone calling it. **A test of a helper is not a test of the path.**
    """
    from gramps_live_api.host import accessor
    from tests.fixtures.host import FakeDbState

    database = _Database(_Family(["h1", "h2"]), {"h1": _Child("I0001"), "h2": _Child("I0002")})
    accessor.bind(FakeDbState(db=database))
    try:
        resolution = accessor.resolve_nodes(dict(families=[dict(id="f1", gramps_id="F0001")]))
    finally:
        accessor.forget()

    assert resolution.nodes[0].children == ("I0001", "I0002")


def test_a_private_child_REFERENCE_is_dropped_even_when_the_person_is_public() -> None:
    """⛔ #103's ratchet caught this by reading the source, not by review.

    ⚠️ A ``ChildRef`` carries its own ``priv``. Reading only the person would
    answer *already a child* from a membership the tree marks private -- a
    disclosure through a field nobody was looking at.

    ⭐ The dropped reference makes the child read as *being added*, which
    over-reports rather than discloses.
    """
    from gramps_live_api.host import accessor

    family = _Family([])
    family._refs = [_Ref("h1"), _Ref("h2", private=True)]
    database = _Database(family, {"h1": _Child("I0001"), "h2": _Child("I0002")})

    assert accessor._children_of(database, "family", family) == ("I0001",)


def test_a_whitespace_only_description_joins_exactly_as_the_writer_joins_it() -> None:
    """⛔ The writer decides list membership on the RAW value, then strips.

    ``described = [str(spec["description"]).strip()] if spec.get("description")
    else []`` -- so ``"   "`` is truthy, contributes an empty element, and the
    stored string begins ``"; "``. Deciding it on the stripped value here dropped
    that separator and the dialog showed a description one character different
    from the one written.

    ⭐ Mirrored rather than tidied: the preview shows what will be stored.
    """
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[
                node("e1", type="Census", date="12 Brumaire", description="   ", people=["q1"])
            ],
        )
    )

    unwrapped = " ".join(
        document.preview(graph, document.Resolution(unparseable_dates=("e1",))).split()
    )

    assert "-- ; date as written: 12 Brumaire" in unwrapped, unwrapped


def test_a_real_description_is_unaffected_by_that() -> None:
    """⚠️ The control: the ordinary case must not gain a stray separator."""
    graph = document.parse(
        dict(
            source=REGISTER,
            people=[node("q1", given="Anon", surname="Invented")],
            events=[
                node("e1", type="Census", date="12 Brumaire", description="weaver", people=["q1"])
            ],
        )
    )

    unwrapped = " ".join(
        document.preview(graph, document.Resolution(unparseable_dates=("e1",))).split()
    )

    assert "-- weaver; date as written: 12 Brumaire" in unwrapped, unwrapped
