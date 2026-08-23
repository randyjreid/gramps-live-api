"""A document's findings as a graph, and the text a human reads before it lands.

⭐ **One operation carrying a whole document, with references by LOCAL ID.** Not
nine operation types and not a composite per document kind. A document asserts
things about several people at once -- that this child has these parents, that
this event happened at this place, that this citation supports all of it -- and
those assertions are edges. A shape without edges cannot carry them, so the
caller would have to invent an ordering and a second round trip to supply the
handles, which is the thing local ids exist to avoid.

**Local ids (``p1``, ``e1``) resolve to real Gramps handles inside the
transaction**, which is why they can be invented by something that has never
seen the tree.

⚠️ **Nothing here imports ``gramps`` or ``gi``, and nothing here writes.** This
module validates a graph and renders it as prose. The writing lives in the
plugin, where the Gramps classes are; the split is the same one the rest of the
host uses, and it is what lets every line below run under CI.

⛔ **Everything in a graph is created NEW. Nothing is matched against people the
tree already holds.** That is a real limitation rather than an oversight, and
``preview`` says so at the top in the words the owner will read.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

MAX_GRAPH_BYTES = 512 * 1024
"""A document's findings, not a tree import. Large enough for a dense census
page with forty people on it; small enough that a runaway caller cannot hand the
GTK main thread an hour of work in one callback -- R8's accepted risk 4."""

PERSON_ROLES = ("Primary", "Family", "Witness", "Clergy", "Informant", "Unknown")


SENTINEL = ".gramps-live-api-copy"
"""⛔ The file the owner creates by hand, INSIDE the tree directory. Same name and
same reason as ``core/apply``: placed beside a tree it would sit in the shared
parent and bless every tree there, including the live one."""

NAME_FILE = "name.txt"
"""What makes a directory a Gramps family tree at all, per ``gramps.cli.clidbman``."""


@dataclass(frozen=True)
class Blessing:
    """Whether a tree may be written to, and the message if it may not.

    ⚠️ **The message names the tree**, which is tree-derived text on the wire --
    and that is deliberate. A refusal a caller cannot act on is a refusal that
    gets routed around, and this one travels only to loopback, to the owner's own
    client, about the owner's own machine.
    """

    blessed: bool
    message: str


def blessing_of(tree_dir: str | None) -> Blessing:
    """The two-file check, spelled once."""
    if not tree_dir:
        return Blessing(blessed=False, message="the open database reports no save path")
    if not os.path.exists(os.path.join(tree_dir, NAME_FILE)):
        return Blessing(
            blessed=False,
            message=f"{tree_dir} is not a Gramps family tree directory",
        )
    if not os.path.exists(os.path.join(tree_dir, SENTINEL)):
        return Blessing(
            blessed=False,
            message=(
                f"{tree_dir} has not been blessed for writing. Create a file named "
                f"{SENTINEL} inside that directory if this is a copy you are willing "
                "to have written to. Nothing was touched."
            ),
        )
    return Blessing(blessed=True, message=tree_dir)


ATTACHABLE = ("people", "places", "source", "families")
"""⭐ The three node kinds that may carry a ``gramps_id`` and mean *this one*.

**Events are deliberately absent**: their handles are invisible in the Gramps UI,
so nobody could supply one and a field nobody can fill is a field that only ever
holds a mistake. Citations and notes are always created -- a document asserting a
fact is asserting a NEW claim about it, even about people who already exist.

⭐ **Families joined this list, and that is OQ-3 closed.** A family is not a claim
the way a citation is -- it is a record of a couple, and a tree holds one per
couple. Creating a second for a couple who already have one is the duplicate
problem in its most confusing form, because Gramps then shows the children split
across two households. A family Gramps ID is visible in the UI, so it can be
supplied.

⭐ **Sources belong here as much as people do.** The same parish register gets
cited across many documents, and twelve copies of it is the same defect as twelve
copies of a person."""

IGNORED_WHEN_ATTACHING = ("given", "surname", "gender", "title", "author", "pubinfo", "parents")
"""Fields that describe an object, and are therefore NOT applied to one that
already exists.

⛔ **Nothing already in the tree is ever modified.** An existing object is only
ever attached to. If a graph carries both a ``gramps_id`` and a name, the name is
**dropped and reported in the dialog** rather than written over what Gramps
holds -- overwriting a recorded birth year with a model's reading of a smudged
page is exactly the failure this rule exists to prevent.

**A diff is a different problem and needs its own ruling.** This is addition."""


@dataclass(frozen=True)
class Requested:
    """One node that says it already exists. ``kind`` is person, place or source."""

    local_id: str
    gramps_id: str
    kind: str


@dataclass(frozen=True)
class Resolved:
    """What the TREE says about a requested node.

    ⭐ **``display`` comes from Gramps and never from the graph.** That is the
    whole safety mechanism: if the model picked the wrong ID, the owner reads the
    wrong person's name in the dialog and cancels. Echoing the model's own guess
    back at him would defeat it entirely.
    """

    local_id: str
    gramps_id: str
    kind: str
    found: bool
    display: str = ""
    private: bool = False
    """⛔ The record exists and the tree marks it private.

    ⚠️ **A third state, not a flavour of ``found``.** Reporting a private record
    as absent would leave the caller unable to tell *no such person* from *that
    person is private*, which is ruling 1's second enforcement point; reporting
    it as found would confirm its existence to the agent, which was the leak."""


@dataclass(frozen=True)
class Resolution:
    """Every requested node, looked up."""

    nodes: tuple[Resolved, ...] = ()

    @property
    def missing(self) -> tuple[Resolved, ...]:
        """Everything that did not resolve, ⛔ **private records included.**

        ⚠️ **Excluding them here re-opened the leak the ``private`` state closed.**
        A private node answers ``found: false``, so leaving it out of ``missing``
        made it the ONE id that is neither found nor missing -- and a caller
        comparing those two fields could read that difference back as *this
        record exists and you may not see it*. **The privacy fix has to hold on
        the wire, not only in the flag.**

        The write path is unaffected because it checks ``refused`` FIRST, so a
        private target is still refused by name there rather than reported
        absent -- ruling 1's two enforcement points, kept apart by ordering
        rather than by making this list lie."""
        return tuple(node for node in self.nodes if not node.found)

    @property
    def refused(self) -> tuple[Resolved, ...]:
        """Nodes naming a record the tree marks private. Refused BY NAME."""
        return tuple(node for node in self.nodes if node.private)

    def refusal(self) -> str | None:
        """The refusal this resolution requires, or ``None``. ⛔ **Order is inside.**

        ⭐ **This exists so no consumer has to remember the order.** ``missing``
        deliberately includes private nodes -- otherwise a caller reads the
        difference between the two lists back as *this record exists* -- which
        means every write-side consumer has to check ``refused`` FIRST or it will
        report a private target as absent.

        ⚠️ **Ordering is a weaker guarantee than a type, and a second consumer
        promptly got it wrong**: the plugin's re-resolve checked only ``missing``,
        so a target that became private between the route's check and the dialog
        reported *absent* rather than being refused by name -- ruling 1's second
        enforcement point, lost to a call-site convention.

        **A method that answers both questions in the right order deletes the
        convention instead of documenting it.**
        """
        if self.refused:
            named = ", ".join(f"{node.gramps_id} ({node.kind})" for node in self.refused)
            return (
                f"these records are marked private in this tree: {named}. "
                "A private record cannot be written to, and it is refused by name "
                "rather than reported absent so you can tell the two apart."
            )
        if self.missing:
            named = ", ".join(f"{node.gramps_id} ({node.kind})" for node in self.missing)
            return (
                f"these Gramps IDs are not in the open tree: {named}. "
                "Nothing was written and no dialog was shown. Look them up with "
                "find_people / find_place / find_source, or leave gramps_id out "
                "to create a new record."
            )
        return None

    def by_local_id(self) -> dict[str, Resolved]:
        return {node.local_id: node for node in self.nodes}


def requested(graph: Graph) -> tuple[Requested, ...]:
    """Every node carrying a ``gramps_id``, as (local id, Gramps ID, kind).

    Pure, so the accessor can be handed a list of lookups rather than a graph to
    interpret.
    """
    out: list[Requested] = []
    for entry in graph.people:
        if entry.get("gramps_id"):
            out.append(Requested(str(entry["id"]), str(entry["gramps_id"]), "person"))
    for entry in graph.places:
        if entry.get("gramps_id"):
            out.append(Requested(str(entry["id"]), str(entry["gramps_id"]), "place"))
    for entry in graph.families:
        if entry.get("gramps_id"):
            out.append(Requested(str(entry["id"]), str(entry["gramps_id"]), "family"))
    if graph.source and graph.source.get("gramps_id"):
        out.append(
            Requested(
                str(graph.source.get("id") or "source"),
                str(graph.source["gramps_id"]),
                "source",
            )
        )
    return tuple(out)


def dropped_fields(entry: dict[str, Any]) -> tuple[str, ...]:
    """Descriptive fields present on a node that already exists, so not applied."""
    if not entry.get("gramps_id"):
        return ()
    return tuple(field for field in IGNORED_WHEN_ATTACHING if entry.get(field))


class GraphInvalid(ValueError):
    """The graph could not be used as given. The message names the reason."""


@dataclass(frozen=True)
class Graph:
    """A document's findings. Every collection is optional except ``people``."""

    people: tuple[dict[str, Any], ...] = ()
    places: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()
    source: dict[str, Any] | None = None
    citations: tuple[dict[str, Any], ...] = ()
    families: tuple[dict[str, Any], ...] = ()
    notes: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """The graph as it arrived, for storing and for handing to the writer."""
        return dict(self.raw)


def _sequence(body: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = body.get(key) or []
    if not isinstance(value, list):
        raise GraphInvalid(f"{key!r} must be a list, not {type(value).__name__}")
    for item in value:
        if not isinstance(item, dict):
            raise GraphInvalid(f"every entry in {key!r} must be an object")
    return tuple(value)


def parse(body: Any) -> Graph:
    """Validate a graph, or refuse it saying which part is wrong.

    ⚠️ **Every reference is checked here, before the transaction opens.** A local
    id that resolves to nothing is a caller error, and finding it half way
    through a write means an aborted transaction and a message from Gramps rather
    than a message from us.
    """
    if isinstance(body, (bytes, bytearray)):
        if len(body) > MAX_GRAPH_BYTES:
            raise GraphInvalid(f"the graph is larger than {MAX_GRAPH_BYTES} bytes")
        try:
            body = json.loads(body.decode("utf-8"))
        except Exception as failure:
            raise GraphInvalid(f"the body is not JSON: {failure}") from failure

    if not isinstance(body, dict):
        raise GraphInvalid("the graph must be a JSON object")

    people = _sequence(body, "people")
    if not people:
        raise GraphInvalid("a graph with no people has nothing to write")

    places = _sequence(body, "places")
    events = _sequence(body, "events")
    citations = _sequence(body, "citations")
    families = _sequence(body, "families")
    notes = _sequence(body, "notes")

    source = body.get("source")
    if source is not None and not isinstance(source, dict):
        raise GraphInvalid("'source' must be an object")

    known: set[str] = set()
    kind_of: dict[str, str] = {}
    """Which kind each local id names, so an edge can be checked for TYPE and not
    merely for existence."""
    for group, items in (
        ("people", people),
        ("places", places),
        ("events", events),
        ("citations", citations),
        ("families", families),
    ):
        for item in items:
            local = item.get("id")
            if not local:
                raise GraphInvalid(f"every entry in {group!r} needs an 'id'")
            if not isinstance(local, str):
                raise GraphInvalid(f"the id {local!r} in {group!r} must be a string")
            if local in known:
                raise GraphInvalid(f"the local id {local!r} is used more than once")
            known.add(local)
            # ⚠️ ``group[:-1]`` is a naive singulariser and it was wrong for
            # families -- it produced "familie". Nothing referenced a family
            # until events gained one, so the bug sat here unreachable: a rule
            # whose definition comes from the SPELLING rather than from the
            # vocabulary, right up until a new spelling arrives.
            kind_of[local] = {"people": "person", "places": "place", "families": "family"}.get(
                group, group[:-1]
            )
    if source is not None:
        # ⛔ Held to the SAME rule as every other node group. A source carrying a
        # ``gramps_id`` but no ``id`` used to be accepted, and a non-string id
        # too: ``requested`` then invented or stringified a local id while
        # ``preview`` kept the original, so the same source was rendered under
        # BOTH headings -- attaching to one that exists and creating a new one --
        # while the writer only ever attached. A preview that describes two
        # operations when one will run is the defect A1 exists to prevent.
        source_id = source.get("id")
        if not source_id:
            raise GraphInvalid("the source needs an 'id', like every other node")
        if not isinstance(source_id, str):
            raise GraphInvalid(f"the source id {source_id!r} must be a string")
        if source_id in known:
            raise GraphInvalid(f"the local id {source_id!r} is used more than once")
        known.add(source_id)
        kind_of[source_id] = "source"

    def check(where: str, referenced: Any, *, must_be: str | None = None) -> None:
        """A reference must exist, and where the writer needs one kind, BE it.

        ⛔ **Existence alone is not enough**, and the gap was not theoretical: an
        event naming a PERSON id as its ``place`` passed validation, and the
        writer then stored that person's handle in ``Event.place_handle``. Gramps
        would hold an event pointing at a person as though it were a place --
        silent structural corruption that no dialog could show, because the
        preview renders the graph's intent rather than the writer's mistake.
        """
        if referenced is None:
            return
        if not isinstance(referenced, str) or referenced not in known:
            raise GraphInvalid(f"{where} refers to {referenced!r}, which is not in this graph")
        if must_be is not None and kind_of.get(referenced) != must_be:
            raise GraphInvalid(
                f"{where} refers to {referenced!r}, which is a "
                f"{kind_of.get(referenced)} and not a {must_be}"
            )

    for event in events:
        check(f"event {event.get('id')!r}'s place", event.get("place"), must_be="place")
        for person in event.get("people") or []:
            check(f"event {event.get('id')!r}", person, must_be="person")
        # ⭐ A marriage belongs to a FAMILY, and until now nothing could say so.
        check(f"event {event.get('id')!r}'s family", event.get("family"), must_be="family")
    for citation in citations:
        check(
            f"citation {citation.get('id')!r}'s source",
            citation.get("source"),
            must_be="source",
        )
        for target in citation.get("attach_to") or []:
            # ⚠️ Unconstrained on purpose: a citation may support a person, an
            # event, a place or a family, and the writer handles each.
            check(f"citation {citation.get('id')!r}", target)
    for family in families:
        for parent in family.get("parents") or []:
            check(f"family {family.get('id')!r}'s parent", parent, must_be="person")
        for child in family.get("children") or []:
            check(f"family {family.get('id')!r}'s child", child, must_be="person")
    for note in notes:
        for target in note.get("attach_to") or []:
            check("a note", target)

    # ⛔ A ``gramps_id`` on a kind that is always created would be silently
    # ignored, and a field that is silently ignored is a field somebody relies
    # on. Refuse it instead, naming the kind.
    for group, one, items in (
        ("events", "event", events),
        ("citations", "citation", citations),
    ):
        for item in items:
            if item.get("gramps_id"):
                raise GraphInvalid(
                    f"{one} {item.get('id')!r} carries a 'gramps_id', but "
                    f"{group} are always created. Only {', '.join(ATTACHABLE)} may "
                    "name something that already exists."
                )
    for note in notes:
        if note.get("gramps_id"):
            raise GraphInvalid("a note carries a 'gramps_id', but notes are always created")

    return Graph(
        people=people,
        places=places,
        events=events,
        source=source,
        citations=citations,
        families=families,
        notes=notes,
        raw=body,
    )


def _named(entry: dict[str, Any]) -> str:
    name = " ".join(
        str(part) for part in (entry.get("given"), entry.get("surname")) if part
    ).strip()
    return name or "(no name given)"


WRAP_AT = 78
"""Where the rendered text wraps itself.

⛔ **Wrapped, never truncated, and never left to a horizontal scrollbar.** R3's
ruled criterion is *"no byte reaches the tree that was not rendered in full to
the human in the approval dialog"*, and a line running off the right edge behind
a scrollbar is content approved unseen -- the slice-1 elision defect in a new
costume, where approval compared sentences cut at 60 characters.

78 rather than the dialog's full width so that a long word cannot push a line
past the edge even at the deepest indent this renderer uses.
"""


def _wrap(text: str, indent: str) -> list[str]:
    """``text`` as lines that fit, at ``indent``. Never drops anything.

    ⚠️ **``textwrap`` alone would eat a blank line between paragraphs**, so
    paragraphs are wrapped one at a time and the blanks put back. A transcription
    is the thing most likely to have them and the thing most worth reading.
    """
    import textwrap

    out: list[str] = []
    for paragraph in str(text).split("\n"):
        if not paragraph.strip():
            out.append(indent.rstrip())
            continue
        out.extend(
            textwrap.wrap(
                paragraph,
                width=max(20, WRAP_AT - len(indent)),
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [indent.rstrip()]
        )
    return out


def _event_line(event: dict[str, Any], named: Any) -> str:
    """One event as the dialog shows it. ⛔ **Including its role.**

    ⚠️ **``role`` is an input the writer APPLIES** -- ``set_role`` puts it on
    every ``EventRef`` the event produces -- so leaving it out of the preview let
    the owner approve a value that would be written without seeing it. That is
    R3's ruled criterion broken in exactly the way A1 exists to catch, and it was
    missed because the role is invisible in the summary and only appears deep in
    the writer.

    The default is not shown, because a preview that repeats *Primary* on every
    line teaches the reader to skip the field that matters.
    """
    bits = [str(event.get("type") or "Event")]
    if event.get("date"):
        bits.append(str(event["date"]))
    if event.get("place"):
        bits.append("at " + named(event["place"]))
    role = str(event.get("role") or "").strip()
    if role and role.casefold() != "primary":
        bits.append(f"as {role}")
    # ⛔ The household the event JOINS, named. R3's criterion is that no byte
    # reaches the tree unrendered, and a marriage attaching to a family the owner
    # never saw named is that criterion failing -- the write is small, this line
    # is the reason the slice exists.
    if event.get("family"):
        bits.append("on the family " + named(event["family"]))
    return ", ".join(bits)


def preview(graph: Graph, resolution: Resolution | None = None) -> str:
    """Everything that would be written, in plain readable text.

    ⭐ **Two sections, and the split is the point.** *Attaching to existing* names
    what Gramps already holds, **with the name read from the TREE**; *creating
    new* names what does not exist yet. A reader who sees the wrong person under
    the first heading cancels, and that is the whole safety mechanism.

    ⭐ **Rendered from the STORED record and from the tree** -- never from
    anything an agent passes at approval time.

    ⛔ **Every node in the graph appears, with its content.** That is enforced
    structurally rather than hoped for: nodes are rendered under whatever they
    attach to, the ones that got rendered are recorded, and anything left over
    gets its own section at the end. A note whose ``attach_to`` names something
    this renderer did not walk used to render **nowhere at all**; now it cannot.
    """
    resolved = (resolution or Resolution()).by_local_id()
    people_by_id = {p.get("id"): p for p in graph.people}
    places_by_id = {p.get("id"): p for p in graph.places}
    families_by_id = {f.get("id"): f for f in graph.families}
    source_id = graph.source.get("id") if graph.source else None

    shown_events: set[int] = set()
    shown_citations: set[int] = set()
    shown_notes: set[int] = set()

    def named_node(local_id: Any) -> str:
        """A node's name -- from the tree if it exists there, else from the graph."""
        node = resolved.get(local_id)
        if node is not None and node.found:
            return f"{node.gramps_id}  {node.display}"
        # ⭐ A family the graph is CREATING has no name of its own and no
        # gramps_id to look up, so it is named by the couple it joins -- "the
        # household on the line above", which is how the owner will read it.
        # ⚠️ Without this a marriage rendered as "on the family f1", and a local
        # id is not something anybody can recognise or refuse.
        family = families_by_id.get(local_id)
        if family is not None:
            parents = [named_node(x) for x in (family.get("parents") or [])]
            return " + ".join(parents) if parents else "the family being created"

        entry = people_by_id.get(local_id) or places_by_id.get(local_id) or {}
        if entry.get("title"):
            return str(entry["title"])
        if entry:
            return _named(entry)
        if local_id == source_id and graph.source:
            return str(graph.source.get("title") or "the source")
        return str(local_id)

    def attached_to(local_id: Any, indent: str) -> list[str]:
        """Every event, citation and note that names ``local_id``, in full."""
        out: list[str] = []
        for index, event in enumerate(graph.events):
            # ⭐ An event reaches a node through its PEOPLE or through its FAMILY.
            # Matching only people left a marriage rendered in the leftovers
            # section rather than under the household it joins -- present, which
            # is what R3 requires, but not where the owner is looking for it.
            if local_id not in (event.get("people") or []) and event.get("family") != local_id:
                continue
            shown_events.add(index)
            out.extend(_wrap("+ " + _event_line(event, named_node), indent))
        for index, citation in enumerate(graph.citations):
            if local_id not in (citation.get("attach_to") or []):
                continue
            shown_citations.add(index)
            page = citation.get("page")
            out.extend(
                _wrap(
                    "+ Citation -> "
                    + named_node(citation.get("source"))
                    + (f"  p.{page}" if page else ""),
                    indent,
                )
            )
        for index, note in enumerate(graph.notes):
            if local_id not in (note.get("attach_to") or []):
                continue
            shown_notes.add(index)
            out.extend(_wrap("+ Note:", indent))
            out.extend(_wrap(note.get("text") or "(empty)", indent + "    "))
        return out

    out: list[str] = []
    out.append("THIS IS WHAT WOULD BE WRITTEN TO YOUR TREE")
    out.append("=" * 62)
    out.append("")

    attaching = [n for n in (resolution or Resolution()).nodes if n.found]
    if attaching:
        out.append("ATTACHING TO EXISTING")
        out.append("")
        for node in attaching:
            out.append(f"  {node.gramps_id}  {node.display}")
            entry = (
                people_by_id.get(node.local_id)
                or places_by_id.get(node.local_id)
                or families_by_id.get(node.local_id)
                or (graph.source if graph.source and source_id == node.local_id else {})
                or {}
            )
            # ⭐ An existing family is ADDED TO, and this is the line that says
            # what the addition is. Without it the owner approved "attach to this
            # household" with no statement of what would be put in it.
            if node.local_id in families_by_id:
                # ⛔ De-duplicated, because the WRITER de-duplicates. A graph may
                # name the same child twice, and two local ids may name the same
                # gramps_id -- the writer passes the resolved handles through
                # ``_unique`` and adds one ChildRef, so rendering the person
                # twice makes the owner approve, and the journal record, an
                # addition that never happens.
                #
                # ⚠️ Keyed on the resolved gramps_id where there is one, which is
                # as close to the writer's handle-level identity as a renderer
                # that never touches the database can get. Two distinct NEW
                # people become two distinct records anyway, so the local id is
                # the right key for them.
                seen_children: set[Any] = set()
                joining = []
                for child in entry.get("children") or []:
                    resolved_child = resolved.get(child)
                    key = (
                        resolved_child.gramps_id
                        if resolved_child is not None and resolved_child.found
                        else child
                    )
                    if key in seen_children:
                        continue
                    seen_children.add(key)
                    joining.append(named_node(child))
                # ⛔ This line speaks about CHILDREN and nothing else. Saying
                # "nothing would be added to this family" was a claim about the
                # whole operation, and it was false: a citation or a note whose
                # attach_to names the family IS committed onto it -- ``family``
                # is in the writer's commit table -- and ``attached_to`` renders
                # exactly that, three lines below, contradicting it.
                out.extend(
                    _wrap(
                        "adding as children: " + ", ".join(joining)
                        if joining
                        else "no children named for this family",
                        "      + ",
                    )
                )
            dropped = dropped_fields(entry)
            if dropped:
                out.extend(
                    _wrap(
                        "(the document also gave "
                        + ", ".join(dropped)
                        + " -- NOT applied; nothing already in your tree is changed)",
                        "      ",
                    )
                )
            out.extend(attached_to(node.local_id, "      "))
            out.append("")

    creating_people = [p for p in graph.people if p.get("id") not in resolved]
    creating_places = [p for p in graph.places if p.get("id") not in resolved]
    creating_source = graph.source if graph.source and source_id not in resolved else None
    # ⛔ Families split like everything else. Rendering ALL of them here said
    # "creating a new household" for a family the writer was going to APPEND
    # CHILDREN TO -- and the same family was listed under ATTACHING TO EXISTING
    # at the same time, so the dialog described two different operations at once
    # and neither was the one that would run.
    creating_families = [f for f in graph.families if f.get("id") not in resolved]

    if creating_people or creating_places or creating_source or creating_families:
        out.append("CREATING NEW")
        out.append("")
        if creating_source:
            out.append("  Source  " + str(creating_source.get("title") or "Untitled document"))
            if creating_source.get("author"):
                out.extend(_wrap("author: " + str(creating_source["author"]), "            "))
            if creating_source.get("pubinfo"):
                out.extend(_wrap("detail: " + str(creating_source["pubinfo"]), "            "))
            out.extend(attached_to(source_id, "      "))
            out.append("")
        for person in creating_people:
            gender = str(person.get("gender") or "unknown")
            out.append(f"  Person  {_named(person)}   [{gender}]")
            out.extend(attached_to(person.get("id"), "      "))
            out.append("")
        for place in creating_places:
            out.append("  Place   " + str(place.get("title") or "?"))
            out.extend(attached_to(place.get("id"), "      "))
        for family in creating_families:
            parents = " + ".join(named_node(x) for x in (family.get("parents") or []))
            children = ", ".join(named_node(c) for c in (family.get("children") or []))
            out.append("  Family  " + (parents or "(no parents named)"))
            if children:
                out.extend(_wrap("children: " + children, "            "))
            out.extend(attached_to(family.get("id"), "      "))
        out.append("")

    # ⛔ The completeness backstop. Anything the walk above did not reach is
    # rendered here rather than silently omitted -- an event with no people, a
    # note attached to an event, a citation attached to nothing.
    leftovers: list[str] = []
    for index, event in enumerate(graph.events):
        if index in shown_events:
            continue
        leftovers.extend(_wrap("Event     " + _event_line(event, named_node), "  "))
        leftovers.extend(attached_to(event.get("id"), "      "))
    for index, citation in enumerate(graph.citations):
        if index in shown_citations:
            continue
        page = citation.get("page")
        leftovers.extend(
            _wrap(
                "Citation  -> "
                + named_node(citation.get("source"))
                + (f"  p.{page}" if page else ""),
                "  ",
            )
        )
    for index, note in enumerate(graph.notes):
        if index in shown_notes:
            continue
        target = ", ".join(str(x) for x in (note.get("attach_to") or [])) or "nothing"
        leftovers.extend(_wrap(f"Note      (attached to {target}):", "  "))
        leftovers.extend(_wrap(note.get("text") or "(empty)", "      "))
    if leftovers:
        out.append("ALSO WRITTEN")
        out.append("")
        out.extend(leftovers)
        out.append("")

    out.append("-" * 62)
    out.append("")
    if creating_people:
        out.extend(
            _wrap(
                "The people under CREATING NEW are made fresh. Nothing is matched by "
                "name -- if one of them is already in your tree, you get a second copy.",
                "  ",
            )
        )
        out.append("")
    out.append("Nothing already in your tree is modified. Existing objects are only")
    out.append("added to.")
    out.append("")
    out.append("Write it writes all of the above, in ONE transaction.")
    out.append("Cancel writes nothing at all.")
    return "\n".join(out)


UNDO_DIRECTORY = ".gramps-live-api-undo"
"""⚠️ **The same directory ``core/apply`` journals into**, deliberately.

Slice 1 journals every write it makes; ``/document`` did not, so a six-object
write was unrecoverable the moment Gramps closed and discarded its in-memory undo
stack. **That has already cost something** -- a document was written that turned
out to be already entered, and removing the duplicates became a manual job.

One directory rather than two: somebody undoing a mistake should not have to know
which path wrote it."""

JOURNAL_FORMAT = "gramps-live-api/document/1"


def journal_record(
    graph: Graph,
    created: dict[str, list[str]],
    attached: dict[str, list[str]],
    *,
    tree_dir: str,
    written_utc: str,
    approved_preview: str,
) -> dict[str, Any]:
    """What was written, in enough detail to reverse it by hand.

    ⭐ **Every object created is named by its Gramps ID**, which is what somebody
    types into Gramps to find it again. The graph goes in beside it so the record
    also says what was *asked for*, not only what resulted.

    ``attached`` records the existing objects that gained something -- reversing
    those means removing a reference rather than deleting a record, and the two
    are different jobs.
    """
    return {
        "record": JOURNAL_FORMAT,
        "written_utc": written_utc,
        "tree": tree_dir,
        "created": {kind: list(ids) for kind, ids in created.items() if ids},
        "attached_to_existing": {kind: list(ids) for kind, ids in attached.items() if ids},
        "graph": graph.as_dict(),
        "approved_preview": approved_preview,
    }


def write_journal(tree_dir: str, record: dict[str, Any], *, stem: str) -> str:
    """Put the record in the tree's own undo directory and return where it landed.

    ⚠️ **``fsync`` before returning**, for the reason ``core/apply`` gives: "the
    record was written" must not mean "the record is in a buffer" while the
    database change reaches the disk.
    """
    directory = os.path.join(tree_dir, UNDO_DIRECTORY)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, stem + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def caller_preview(graph: Graph) -> str:
    """What the AGENT is shown after proposing. ⛔ Not the approval surface.

    ⭐ **This renders no name it looked up.** It names the Gramps IDs the graph
    carries and says the dialog will show who they are. The hazard is precisely
    the caller echoing back names it resolved itself: a preview that says
    *"attaching to Standlake, Peregrine"* reads as confirmation, when the only
    thing that can confirm it is the tree, in the dialog, in front of the owner.

    ⚠️ **So the split here is ids versus descriptions**, not names versus names.
    """
    attaching_people = [p for p in graph.people if p.get("gramps_id")]
    attaching_places = [p for p in graph.places if p.get("gramps_id")]
    attaching_source = graph.source if graph.source and graph.source.get("gramps_id") else None
    creating_people = [p for p in graph.people if not p.get("gramps_id")]
    creating_places = [p for p in graph.places if not p.get("gramps_id")]
    creating_source = graph.source if graph.source and not graph.source.get("gramps_id") else None

    out: list[str] = []
    if attaching_people or attaching_places or attaching_source:
        out.append("ATTACHING TO EXISTING RECORDS")
        for entry in attaching_people:
            out.append(f"  person  {entry['gramps_id']}")
        for entry in attaching_places:
            out.append(f"  place   {entry['gramps_id']}")
        if attaching_source:
            out.append(f"  source  {attaching_source['gramps_id']}")
        out.append("  (the dialog will show who these are, read from the tree)")
        out.append("")

    if creating_people or creating_places or creating_source:
        out.append("CREATING NEW RECORDS")
        for entry in creating_people:
            out.append(f"  person  {_named(entry)}")
        for entry in creating_places:
            out.append(f"  place   {entry.get('title') or '?'}")
        if creating_source:
            out.append(f"  source  {creating_source.get('title') or 'Untitled'}")
        out.append("")
        # ⚠️ Scoped to a NON-EMPTY creating section. Warning about duplicates
        # when nothing is being created is noise that teaches the reader to skip
        # the warning that matters.
        if creating_people:
            out.append(
                "  WARNING: the people above are created fresh. Nothing is matched by "
                "name. If any of them is already in the tree, use find_people to get "
                "their Gramps ID and pass it as gramps_id instead."
            )
            out.append("")

    for label, items in (
        ("events", graph.events),
        ("citations", graph.citations),
        ("notes", graph.notes),
    ):
        if items:
            out.append(f"  {len(items)} {label} (always created new)")
    # ⛔ Families are NOT always created new any more, and saying so here was a
    # false statement to the caller about what its own proposal would do. One
    # carrying a gramps_id is added to instead.
    joining = [f for f in graph.families if f.get("gramps_id")]
    new_families = [f for f in graph.families if not f.get("gramps_id")]
    if new_families:
        out.append(f"  {len(new_families)} families (created new)")
    if joining:
        out.append(
            f"  {len(joining)} families (adding children to a family already in the tree; "
            "its recorded parents are not changed)"
        )
    return "\n".join(out).rstrip()


CREATABLE = ("people", "events", "places", "families", "citations", "notes", "sources")
"""Every kind ``writer.write`` can create. ⛔ **One list, and the summary derives
from it**, because two tallies drift and one cannot."""


def summarise_created(created: dict[str, list[str]]) -> str:
    """What a write actually made, from the record of what it made.

    ⛔ **Derived, never hand-maintained.** The writer used to keep a second
    ``counts`` dict beside the record of created objects -- and that dict had six
    keys where the record had seven. **A source was written and the log line said
    zero sources**, which is worse than cosmetic: that line had already been used
    as evidence for what a write did.

    ⚠️ **A diagnostic that under-reports reads as evidence of absence.** So the
    second tally is deleted rather than corrected: a kind that is created is a
    kind that is counted, by construction.
    """
    parts = [f"{len(created.get(kind) or ())} {kind}" for kind in CREATABLE if created.get(kind)]
    return ", ".join(parts) or "nothing"


def summary(graph: Graph) -> str:
    """One line, for the agent. ⛔ No names -- the agent supplied them already."""
    parts = [f"{len(graph.people)} people"]
    for label, items in (
        ("events", graph.events),
        ("places", graph.places),
        ("families", graph.families),
        ("citations", graph.citations),
        ("notes", graph.notes),
    ):
        if items:
            parts.append(f"{len(items)} {label}")
    if graph.source:
        parts.append("1 source")
    return ", ".join(parts)
