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


def preview(graph: Graph) -> str:
    """Everything that would be written, in plain readable text.

    ⭐ **This is what the dialog shows, and it is rendered from the STORED
    record** -- never from anything an agent passes at approval time. That single
    constraint is what carries the approval binding across from a console the
    server held no handle on to a dialog inside Gramps: the thing the human reads
    and the thing that gets written come from one object.
    """
    people_by_id = {p.get("id"): p for p in graph.people}
    places_by_id = {p.get("id"): p for p in graph.places}

    out: list[str] = []
    out.append("THIS IS WHAT WOULD BE WRITTEN TO YOUR TREE")
    out.append("=" * 62)
    out.append("")
    out.append("*** EVERYTHING BELOW IS CREATED AS NEW. ***")
    out.append("")
    out.append("Nothing is matched against people already in your tree. If any of")
    out.append("these people are already there, you will get a SECOND COPY.")
    out.append("Matching existing people is a later problem and this does not do it.")
    out.append("")
    out.append("-" * 62)
    out.append("")

    if graph.source:
        out.append("SOURCE:   " + str(graph.source.get("title") or "Untitled document"))
        if graph.source.get("author"):
            out.append("AUTHOR:   " + str(graph.source["author"]))
        if graph.source.get("pubinfo"):
            out.append("DETAIL:   " + str(graph.source["pubinfo"]))
        out.append("")

    out.append(f"{len(graph.people)} person(s):")
    out.append("")
    for person in graph.people:
        gender = str(person.get("gender") or "unknown")
        out.append(f"  {_named(person)}   [{gender}]")
        for event in graph.events:
            if person.get("id") not in (event.get("people") or []):
                continue
            bits = [str(event.get("type") or "Event")]
            if event.get("date"):
                bits.append(str(event["date"]))
            place = places_by_id.get(event.get("place"))
            if place:
                bits.append("at " + str(place.get("title") or ""))
            out.append("      - " + "   ".join(bits))
        out.append("")

    if graph.families:
        out.append(f"{len(graph.families)} family record(s):")
        for family in graph.families:
            parents = " + ".join(
                _named(people_by_id.get(p, {})) for p in (family.get("parents") or [])
            )
            children = ", ".join(
                _named(people_by_id.get(c, {})) for c in (family.get("children") or [])
            )
            out.append("  " + (parents or "(no parents named)"))
            if children:
                out.append("      children: " + children)
        out.append("")

    if graph.places:
        out.append(
            f"{len(graph.places)} place(s): "
            + ", ".join(str(p.get("title") or "?") for p in graph.places)
        )
        out.append("")

    if graph.citations:
        out.append(f"{len(graph.citations)} citation(s) attached to what they support.")
    if graph.notes:
        out.append(f"{len(graph.notes)} note(s), including any transcription.")
    if graph.citations or graph.notes:
        out.append("")

    out.append("-" * 62)
    out.append("")
    out.append("OK writes all of the above, in ONE transaction.")
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
