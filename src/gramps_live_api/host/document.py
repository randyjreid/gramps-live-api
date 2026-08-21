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


ATTACHABLE = ("people", "places", "source")
"""⭐ The three node kinds that may carry a ``gramps_id`` and mean *this one*.

**Events are deliberately absent**: their handles are invisible in the Gramps UI,
so nobody could supply one and a field nobody can fill is a field that only ever
holds a mistake. Citations, families and notes are always created -- a document
asserting a relationship is asserting a NEW claim about it, even between people
who already exist.

⭐ **Sources belong here as much as people do.** The same parish register gets
cited across many documents, and twelve copies of it is the same defect as twelve
copies of a person."""

IGNORED_WHEN_ATTACHING = ("given", "surname", "gender", "title", "author", "pubinfo")
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


@dataclass(frozen=True)
class Resolution:
    """Every requested node, looked up."""

    nodes: tuple[Resolved, ...] = ()

    @property
    def missing(self) -> tuple[Resolved, ...]:
        return tuple(node for node in self.nodes if not node.found)

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
    if source is not None and source.get("id"):
        source_id = source["id"]
        if source_id in known:
            raise GraphInvalid(f"the local id {source_id!r} is used more than once")
        known.add(source_id)

    def check(where: str, referenced: Any) -> None:
        if referenced is None:
            return
        if not isinstance(referenced, str) or referenced not in known:
            raise GraphInvalid(f"{where} refers to {referenced!r}, which is not in this graph")

    for event in events:
        check(f"event {event.get('id')!r}'s place", event.get("place"))
        for person in event.get("people") or []:
            check(f"event {event.get('id')!r}", person)
    for citation in citations:
        check(f"citation {citation.get('id')!r}'s source", citation.get("source"))
        for target in citation.get("attach_to") or []:
            check(f"citation {citation.get('id')!r}", target)
    for family in families:
        for parent in family.get("parents") or []:
            check(f"family {family.get('id')!r}'s parent", parent)
        for child in family.get("children") or []:
            check(f"family {family.get('id')!r}'s child", child)
    for note in notes:
        for target in note.get("attach_to") or []:
            check("a note", target)

    # ⛔ A ``gramps_id`` on a kind that is always created would be silently
    # ignored, and a field that is silently ignored is a field somebody relies
    # on. Refuse it instead, naming the kind.
    for group, one, items in (
        ("events", "event", events),
        ("citations", "citation", citations),
        ("families", "family", families),
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


def preview(graph: Graph, resolution: Resolution | None = None) -> str:
    """Everything that would be written, in plain readable text.

    ⭐ **Two sections, and the split is the point.** *Attaching to existing* names
    what Gramps already holds, **with the name read from the TREE**; *creating
    new* names what does not exist yet. A reader who sees the wrong person under
    the first heading cancels, and that is the whole safety mechanism.

    ⭐ **Rendered from the STORED record** -- never from anything an agent passes
    at approval time. That constraint is what carries the approval binding across
    from a console the server held no handle on to a dialog inside Gramps.
    """
    resolved = (resolution or Resolution()).by_local_id()
    people_by_id = {p.get("id"): p for p in graph.people}
    places_by_id = {p.get("id"): p for p in graph.places}

    def shown(local_id: Any) -> str:
        """A node's name -- from the tree if it exists there, else from the graph."""
        node = resolved.get(local_id)
        if node is not None and node.found:
            return f"{node.gramps_id}  {node.display}"
        entry = people_by_id.get(local_id) or places_by_id.get(local_id) or {}
        if entry.get("title"):
            return str(entry["title"])
        return _named(entry) if entry else str(local_id)

    def events_of(local_id: Any) -> list[str]:
        lines = []
        for event in graph.events:
            if local_id not in (event.get("people") or []):
                continue
            bits = [str(event.get("type") or "Event")]
            if event.get("date"):
                bits.append(str(event["date"]))
            place = event.get("place")
            if place:
                lines.append("    + " + ", ".join(bits) + ", " + shown(place))
            else:
                lines.append("    + " + ", ".join(bits))
        for citation in graph.citations:
            if local_id in (citation.get("attach_to") or []):
                target = citation.get("source")
                page = citation.get("page")
                lines.append("    + Citation -> " + shown(target) + (f" p.{page}" if page else ""))
        for note in graph.notes:
            if local_id in (note.get("attach_to") or []):
                lines.append("    + Note")
        return lines

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
                or (
                    graph.source if graph.source and graph.source.get("id") == node.local_id else {}
                )
                or {}
            )
            dropped = dropped_fields(entry)
            if dropped:
                out.append(
                    "      (the document also gave "
                    + ", ".join(dropped)
                    + " -- NOT applied; nothing already in your tree is changed)"
                )
            for line in events_of(node.local_id):
                out.append("  " + line)
        out.append("")

    creating_people = [p for p in graph.people if p.get("id") not in resolved]
    creating_places = [p for p in graph.places if p.get("id") not in resolved]
    creating_source = (
        graph.source if graph.source and graph.source.get("id") not in resolved else None
    )

    if creating_people or creating_places or creating_source or graph.families:
        out.append("CREATING NEW")
        out.append("")
        if creating_source:
            out.append("  Source  " + str(creating_source.get("title") or "Untitled document"))
            if creating_source.get("author"):
                out.append("            author: " + str(creating_source["author"]))
            if creating_source.get("pubinfo"):
                out.append("            detail: " + str(creating_source["pubinfo"]))
        for person in creating_people:
            gender = str(person.get("gender") or "unknown")
            out.append(f"  Person  {_named(person)}   [{gender}]")
            for line in events_of(person.get("id")):
                out.append("  " + line)
        for place in creating_places:
            out.append("  Place   " + str(place.get("title") or "?"))
        for family in graph.families:
            parents = " + ".join(shown(x) for x in (family.get("parents") or []))
            children = ", ".join(shown(c) for c in (family.get("children") or []))
            out.append("  Family  " + (parents or "(no parents named)"))
            if children:
                out.append("            children: " + children)
        out.append("")

    out.append("-" * 62)
    out.append("")
    if creating_people:
        out.append("⚠ The people under CREATING NEW are made fresh. Nothing is matched")
        out.append("  by name -- if one of them is already in your tree, you get a second copy.")
        out.append("")
    out.append("Nothing already in your tree is modified. Existing objects are only")
    out.append("added to.")
    out.append("")
    out.append("Write it writes all of the above, in ONE transaction.")
    out.append("Cancel writes nothing at all.")
    return "\n".join(out)


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
