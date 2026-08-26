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
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from gramps_live_api.host import paths

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


GROUPS = {
    "people": "person",
    "places": "place",
    "events": "event",
    "source": "source",
    "citations": "citation",
    "families": "family",
    "notes": "note",
}
"""Every node group a document graph can carry, and its singular.

⛔ **``ATTACHABLE`` is a subset of this**, and the kinds that are always created
are the complement -- computed, never listed twice. A group that is neither
attachable nor refused cannot exist, because both sets come from here."""


ATTACHABLE = {
    "people": "person",
    "places": "place",
    "source": "source",
    "families": "family",
    "events": "event",
}
"""⭐ **The ONE declaration of which node kinds may carry a ``gramps_id``**, mapping
the graph's group name to the singular this project uses in messages.

⛔ **Everything else is driven off this.** ``requested`` walks it rather than
carrying one loop per kind, the refusal for the non-attachable kinds is its
complement, and the tool description is generated from it. **A sixth kind becomes
attachable by being declared here** -- there is no second place to remember, which
is what four hand-written branches had become.

⭐ **Events joined this list, and the exclusion that kept them out has expired.**
The reasoning was: *their handles are invisible in the Gramps UI, so nobody could
supply one.* ⚠️ **That was about HANDLES.** Gramps IDs are visible, and
``list_events`` returns them -- so the premise stopped being true when that route
shipped, and the exclusion has since been enforcing a constraint that no longer
exists.

⛔ **The live consequence, which is why this is a correction rather than a
widening:** a citation belonging on an event that already exists could not be
attached to it, so the only way to record the source was to create a **second copy
of the event** -- the exact duplication this whole feature set exists to prevent.

Citations and notes remain always-created -- a document asserting a fact is
asserting a NEW claim about it, even about people who already exist.

⭐ **Families joined this list, and that is OQ-3 closed.** A family is not a claim
the way a citation is -- it is a record of a couple, and a tree holds one per
couple. Creating a second for a couple who already have one is the duplicate
problem in its most confusing form, because Gramps then shows the children split
across two households. A family Gramps ID is visible in the UI, so it can be
supplied.

⭐ **Sources belong here as much as people do.** The same parish register gets
cited across many documents, and twelve copies of it is the same defect as twelve
copies of a person."""

IGNORED_WHEN_ATTACHING = (
    "given",
    "surname",
    "gender",
    "title",
    "author",
    "pubinfo",
    "parents",
    # ⛔ An attached EVENT is not modified either. Its type, date, place,
    # description and role describe an event that already exists and already has
    # them -- applying the payload's would be **editing a record the owner asked
    # to attach to**, which is the one thing attaching is defined not to do.
    "type",
    "date",
    "place",
    "description",
)
# ⚠️ ``role`` is deliberately NOT here, and the reasoning had to be corrected
# once. It is REFUSED on an attached event rather than dropped -- explicitly, in
# ``parse`` -- so there is no state in which it needs reporting as dropped.
#
# ⛔ **The first version of this note claimed role could never survive, having
# tested only a non-Primary role.** ``role: "Primary"`` took a different path: the
# with-no-carriers check only rejects non-Primary, so it was accepted, silently
# discarded by the writer, and not reported as dropped. **A conclusion generalised
# from one case**, which is why the refusal now names ``role`` outright.
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
                "Nothing was written and no dialog was shown. " + how_to_resolve_them()
            )
        return None

    def by_local_id(self) -> dict[str, Resolved]:
        return {node.local_id: node for node in self.nodes}


def requested(graph: Graph) -> tuple[Requested, ...]:
    """Every node carrying a ``gramps_id``, as (local id, Gramps ID, kind).

    Pure, so the accessor can be handed a list of lookups rather than a graph to
    interpret.
    """
    # ⛔ **Driven off ``ATTACHABLE``, not one branch per kind.**
    #
    # ⚠️ This was four hand-written loops, and a fifth kind would have been a fifth
    # branch -- in a function whose omission is silent, because a kind nobody walks
    # simply never resolves and its ``gramps_id`` is ignored rather than refused.
    # **A sixth kind now inherits this by being declared.**
    out: list[Requested] = []
    for group, one in ATTACHABLE.items():
        for entry in _entries(graph, group):
            if entry.get("gramps_id"):
                out.append(Requested(str(entry.get("id") or one), str(entry["gramps_id"]), one))
    return tuple(out)


def _entries(graph: Graph, group: str) -> tuple[dict[str, Any], ...]:
    """The nodes in one group, as a sequence whatever its shape.

    ⚠️ ``source`` is a single node rather than a list -- the one structural
    exception in the graph -- and it is smoothed over HERE so that everything
    walking ``ATTACHABLE`` does not each have to know it.
    """
    value = getattr(graph, group, None)
    if value is None:
        return ()
    if isinstance(value, dict):
        return (value,)
    return tuple(value)


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


NODE_KEYS = {
    "people": {"id", "given", "surname", "gender"},
    "places": {"id", "title"},
    "events": {"id", "type", "date", "place", "people", "family", "role", "description"},
    "source": {"id", "title", "author", "pubinfo"},
    "citations": {"id", "source", "page", "attach_to"},
    "families": {"id", "parents", "children"},
    "notes": {"text", "attach_to"},
}
"""⛔ **Exactly what each node group accepts. Anything else is REFUSED, by name.**

⚠️ **Refused rather than ignored, and rather than warned.** An unrecognised key
used to be dropped in silence: ``people[].events`` -- a natural guess, being the
reverse of the supported ``events[].people`` -- created no link, raised nothing,
and appeared nowhere in the approval dialog. The owner then approved a preview
that was **accurate about what would be written and silent about the fact he had
asked for something else.** A warning would be the same silence one indirection
away, because a warning in a log nobody reads is not told to anybody.

⭐ **This is the inverse of R3.** R3 says no byte reaches the tree unrendered;
this says no byte is accepted and then quietly dropped. One slightly wrong key is
the likeliest way a real document loses a fact.

⚠️ ``gramps_id`` is deliberately absent from every set and allowed separately:
the kinds that may not carry one are refused by ``ATTACHABLE``'s complement,
whose message says *why* rather than merely *unknown key*. **A general check must
not shadow a specific refusal.**
"""


def _only_known_keys(group: str, index: int, entry: Any) -> None:
    """⛔ Refuse a key this group does not accept, naming the key AND the node.

    ⚠️ The caller has to find one node in its own graph to fix it, so the message
    carries the group, which entry it was, that entry's ``id`` when it has one,
    and what the group does accept.
    """
    if not isinstance(entry, dict):
        return
    allowed = NODE_KEYS[group] | {"gramps_id"}
    unknown = sorted(key for key in entry if key not in allowed)
    if not unknown:
        return
    named = entry.get("id")
    where = f"{group}[{index}]" + (f" (id {named!r})" if isinstance(named, str) and named else "")
    raise GraphInvalid(
        f"{where} carries "
        + ("keys " if len(unknown) > 1 else "a key ")
        + ", ".join(repr(key) for key in unknown)
        + f", which {group!r} does not accept. It would have been dropped in "
        f"silence and nothing in the approval dialog would have shown that you "
        f"asked for it. {group!r} accepts: "
        + ", ".join(repr(key) for key in sorted(NODE_KEYS[group] | {"gramps_id"}))
        + "."
    )


LOOKUP_TOOLS = {
    "person": "find_people",
    "place": "find_place",
    "source": "find_source",
    "family": "find_families",
    "event": (
        "list_events for a person's own events, or find_families then "
        "list_family_events for a couple's -- a marriage is owned by the family, "
        "not by either spouse"
    ),
}
"""Which tool finds a record of each kind. ⛔ **One entry per ``ATTACHABLE`` kind.**

⚠️ The refusal used to name ``find_people / find_place / find_source`` only, so a
caller with an unresolvable event or family id was told to use tools that cannot
find one. Events and families became attachable without this sentence moving.
"""


def how_to_resolve_them() -> str:
    """⛔ What to do about a ``gramps_id`` that did not resolve. **ONE copy.**

    ⚠️ **Two messages said this, and one of them was wrong.** The MCP tool and
    ``Resolution.refusal()`` carried the same sentence by duplication rather than
    by sharing it, which is the drift shape: the advice had to change when events
    became attachable and only the tool description was updated.

    ⛔ **The second half was not merely under-specified, it was harmful.** It said
    *"leave gramps_id out to create a new record"*, and following that literally
    on an event being cited produces a second copy of that event -- the exact
    duplication this whole feature exists to prevent, recommended by the feature's
    own refusal text.

    ⭐ **The rule is ONE property, not a branch per kind:** *dropping the
    ``gramps_id`` creates a new record, and that is right only when the node also
    DESCRIBES one.* Measured, rather than assumed -- a node carrying nothing but a
    ``gramps_id`` renders as ``Person (no name given)``, ``Place ?``, ``Source
    Untitled document`` or ``Event  Event`` once the id is dropped. Only a family
    refuses, because it requires parents, children or an id to be written at all.

    ⚠️ So events are **not** the sole exception, though they are the sharpest one:
    an attached event cannot carry content by construction, since its type, date,
    place and description are read from the tree and dropped from the payload.
    Stating the property this way means a sixth attachable kind inherits the
    correct half by its nature rather than by someone remembering it.
    """
    named = "; ".join(f"{kind} -> {tool}" for kind, tool in sorted(LOOKUP_TOOLS.items()))
    return (
        "Look it up again -- an id that does not resolve is usually stale or "
        f"mistyped, and these are the tools that find one: {named}. "
        "Do NOT simply leave the gramps_id out. That creates a NEW record, which "
        "is right only when the node also describes one -- a person with a name, "
        "a place with a title. A node whose only content was the gramps_id "
        "becomes an empty placeholder; and an attached event carries no content "
        "at all, because its type, date and place are read from the tree -- so "
        "dropping its id writes a second copy of the very event you were citing."
    )


def _writes_anything(
    groups: tuple[tuple[str, Sequence[dict[str, Any]]], ...],
    source: dict[str, Any] | None,
) -> bool:
    """⛔ Does this graph produce **at least one committed change**?

    ⭐ **The rule that replaces ``people`` non-empty**, which was a PROXY for it.
    The proxy answered its own question correctly and then answered a different
    one once events became attachable: a graph naming a source, a citation and an
    existing event has plenty to write and no person in it, and was refused as
    having *"nothing to write"*. Third proxy of its kind on this project.

    A committed change is either:

    * a **created** node -- any node in any group with no ``gramps_id``. Citations
      and notes never carry one, so any citation or note is a creation; or
    * an **attachment edge** that lands on something -- a citation's or note's
      ``attach_to``, or children joining a family.

    ⚠️ ``events[].people`` and ``events[].family`` are deliberately NOT listed.
    They exist only on a *created* event -- ``parse`` refuses them on an attached
    one -- so the created event already made this true, and listing them would be
    a second reason for a fact already covered.

    ⛔ **This does NOT ask whether created objects are REACHABLE.** A source
    nobody cites is created and reachable in Gramps' own lists; a note attached to
    nothing is an orphan, and orphans are real enough here that ``find_orphans``
    exists. Those two want opposite answers, so reachability is not a uniform
    property and does not belong bolted onto this one -- it is filed separately.
    """
    for _group, items in groups:
        for item in items:
            if not item.get("gramps_id"):
                return True
    if source is not None and not source.get("gramps_id"):
        return True
    # ⛔ ``children`` only. ``attach_to`` was here and was DEAD CODE: only
    # citations and notes take it, neither may carry a ``gramps_id``, so any node
    # with an ``attach_to`` was already counted as created above. A negative
    # control stayed SILENT on it, which is how it was found rather than reasoned
    # about -- and an unreachable branch inside a safety rule is exactly the thing
    # this project keeps paying for.
    #
    # ⭐ ``children`` IS reachable: an existing family gaining existing people is
    # a committed change with nothing created anywhere in the graph.
    for _group, items in groups:
        for item in items:
            if item.get("children"):
                return True
    return False


def _claim_the_record(
    claimed: dict[tuple[str, str], str],
    group: str,
    kind: str,
    local: str,
    entry: dict[str, Any],
) -> None:
    """⛔ One local id per resolved record. Refuses the second claim, naming both.

    ⭐ **Driven off ``ATTACHABLE``**, so a sixth attachable kind inherits the rule
    rather than needing a branch here. A group that cannot carry a ``gramps_id``
    is refused earlier and never reaches this.

    ⚠️ The message names **both local ids and the ``gramps_id`` they share**,
    because the caller has to find two nodes in its own graph to fix it and
    "duplicate gramps_id" alone does not say which two.
    """
    if group not in ATTACHABLE:
        return
    gramps_id = entry.get("gramps_id")
    if not gramps_id:
        return
    key = (kind, str(gramps_id))
    first = claimed.get(key)
    if first is not None:
        raise GraphInvalid(
            f"the local ids {first!r} and {local!r} both name {kind} "
            f"{str(gramps_id)!r}. One local id per record: give the {kind} a "
            f"single id and point everything at it, because two ids for one "
            f"record make the approval dialog and the write disagree about how "
            f"many times something is attached."
        )
    claimed[key] = local


def parse(body: Any, *, writes: bool = True) -> Graph:
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

    # ⛔ **An unknown top-level key drops a WHOLE GROUP in silence**, which is the
    # worst version of this: ``peple`` or ``event`` costs every node in it, and
    # the preview is entirely consistent about the nodes that survived.
    unknown_groups = sorted(key for key in body if key not in GROUPS)
    if unknown_groups:
        raise GraphInvalid(
            "the graph carries "
            + ("keys " if len(unknown_groups) > 1 else "a key ")
            + ", ".join(repr(key) for key in unknown_groups)
            + ", which is not a node group. Everything in it would have been "
            "dropped in silence. The groups are: "
            + ", ".join(repr(group) for group in GROUPS)
            + "."
        )

    people = _sequence(body, "people")
    places = _sequence(body, "places")
    events = _sequence(body, "events")
    citations = _sequence(body, "citations")
    families = _sequence(body, "families")
    notes = _sequence(body, "notes")

    source = body.get("source")
    if source is not None and not isinstance(source, dict):
        raise GraphInvalid("'source' must be an object")
    # ⛔ **A citation must be able to reach a source, or it writes nothing.**
    #
    # ⚠️ The writer resolves ``handles.get(spec["source"]) or source_handle`` and
    # ``continue``s when both are empty -- so a citation naming no source, in a
    # graph with no top-level ``source``, is silently skipped. The preview
    # meanwhile rendered ``Citation -> None`` and the dialog promised it.
    #
    # ⛔ **A promise the write does not keep, on the surface the whole safety
    # argument rests on.** Refused here so the state cannot occur, rather than
    # taught to one consumer at a time.
    #
    # ⭐ The general shape it came from: the committed-change rule asked whether a
    # node was of a creatable KIND, not whether it could actually be created.
    # A citation never carries a ``gramps_id``, so it counted unconditionally.
    for one_citation in citations:
        if not one_citation.get("source") and source is None:
            named = one_citation.get("id")
            raise GraphInvalid(
                f"citation {named!r} names no 'source' and the graph has no "
                "top-level 'source' for it to fall back on, so nothing would be "
                "written for it and the approval dialog would promise a citation "
                "that never happens. Give it a 'source', or add the source node."
            )

    if source is not None:
        # ⛔ The source is a single node rather than a list -- the one structural
        # exception in the graph -- so it needs its own call. Index 0 because
        # there is only ever one.
        _only_known_keys("source", 0, source)

    # ⛔ **Notes too.** They are the one group with no ``id``, so a caller giving
    # them one -- which is the natural habit, every other node has one -- was
    # having it silently dropped. Refused now, and the message says what a note
    # accepts.
    for index, one_note in enumerate(notes):
        _only_known_keys("notes", index, one_note)

    known: set[str] = set()
    # ⛔ **ONE local id per resolved record.** ``(kind, gramps_id) -> the local id
    # that claimed it first``, so a second claim can name both in the refusal.
    #
    # ⚠️ **Refused at the door rather than tolerated and deduplicated downstream,
    # because the alias is a TWO-SIDED description and every consumer has to
    # defend against it separately.** It produced two defects on one branch: the
    # writer attached a citation twice (fixed by routing the attach path through
    # ``_unique``), and then the preview rendered it twice while the writer wrote
    # once -- the preview/writer disagreement class, created *by* the first fix,
    # because correcting one side of a two-sided description is what makes that
    # class. Refusing removes the two-sidedness: neither renderer nor writer can
    # disagree about an input the parser never accepted.
    #
    # ⭐ The alias is reachable, and it is the ordinary census shape: a document
    # naming one person twice -- as head of household, then again in a
    # relationship column -- gives an agent building from two places in the page
    # two locals carrying one ``gramps_id``.
    seen_gramps: dict[tuple[str, str], str] = {}
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
        for index, item in enumerate(items):
            _only_known_keys(group, index, item)
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
            _claim_the_record(seen_gramps, group, kind_of[local], local, item)
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
        # ⛔ The source goes through the same claim, though it is a single node
        # and cannot collide with itself today. Driving it off ``ATTACHABLE``
        # rather than exempting it means a second source node -- if the graph
        # ever grows one -- inherits the rule instead of needing to be
        # remembered.
        _claim_the_record(seen_gramps, "source", "source", source_id, source)

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

    # ⛔ A family that names nobody and no gramps_id is never written -- the
    # writer skips it at ``if not parents and not children`` -- while the preview
    # promises to create it. **That divergence produced an ORPHAN EVENT**: the
    # marriage was created, the family was not, and the approved text said
    # otherwise. Refusing here is the honest end of it, and it also closes the
    # older case where an empty family node silently wrote nothing at all.
    for family in families:
        # ⛔ Members that are USABLE, not merely present.
        #
        # ⚠️ Testing the lists for truthiness left the refusal bypassable by a
        # single JSON null: ``parents: [null]`` is a non-empty list, so the check
        # passed -- and the writer then drops the null, skips the now-empty
        # family, and any event targeting it orphans, with the preview having
        # promised both. **A guard defeated by a value the writer silently
        # discards.**
        members = [
            member
            for member in list(family.get("parents") or []) + list(family.get("children") or [])
            if str(member or "").strip()
        ]
        if family.get("gramps_id") or members:
            continue
        raise GraphInvalid(
            f"family {family.get('id')!r} names no parents, no children and no "
            "gramps_id, so nothing would be written for it. Give it somebody, or "
            "leave it out."
        )

    # ⛔ A null or blank entry is refused in EVERY list of local ids, not just
    # the one a reviewer last pointed at.
    #
    # ⚠️ **Fixing this per-list did not fix it.** ``parents``/``children`` were
    # hardened first; the very next round found the identical bypass in an
    # event's ``people`` -- ``[null]`` is a non-empty list, ``check`` treats a
    # null as absent, and the writer drops it at ``handles.get(None)``.
    # **Anything the writer discards without saying so is something the preview
    # can promise and the write can skip**, which is the whole of #106, so the
    # rule is applied to the vocabulary rather than to the instance.
    for holder, slots, what in (
        (families, ("parents", "children"), "family"),
        (events, ("people",), "event"),
        (citations, ("attach_to",), "citation"),
        (notes, ("attach_to",), "note"),
    ):
        for entry in holder:
            for slot in slots:
                for member in entry.get(slot) or []:
                    if not str(member or "").strip():
                        raise GraphInvalid(
                            f"{what} {entry.get('id')!r} lists an empty entry in "
                            f"{slot!r}, which would be silently dropped. Name "
                            "something, or shorten the list."
                        )

    for event in events:
        # ⛔ **An ATTACHED event may not also name participants.**
        #
        # ⚠️ Without this the graph parsed, the preview rendered a ``+`` for the
        # event under each named person, and the writer's attach path skipped both
        # the person ``EventRef`` loop and the deferred family attachment
        # entirely -- **so the owner approved a relationship that was never
        # written.** That is the preview and the writer disagreeing, which is the
        # class this project has six recorded instances of, in code added for the
        # feature above.
        #
        # ⭐ **Refused rather than dropped-and-reported.** Dropping would leave the
        # caller believing it can express participation on an existing event and
        # leave the rendering to suppress separately; refusing makes the
        # disagreement impossible rather than merely announced, and the message
        # says what to do instead.
        if event.get("gramps_id") and (
            event.get("people") or event.get("family") or event.get("role")
        ):
            raise GraphInvalid(
                f"event {event.get('id')!r} names an existing event by gramps_id and "
                "also names 'people', 'family' or 'role'. An event already in the "
                "tree keeps the participants it has -- attach a citation or a note "
                "to it instead, and drop those fields."
            )
        check(f"event {event.get('id')!r}'s place", event.get("place"), must_be="place")
        for person in event.get("people") or []:
            check(f"event {event.get('id')!r}", person, must_be="person")
        # ⭐ A marriage belongs to a FAMILY, and until now nothing could say so.
        check(f"event {event.get('id')!r}'s family", event.get("family"), must_be="family")
        # ⛔ A role with nobody to carry it is a role that gets discarded.
        #
        # ⚠️ The FAMILY reference's role is fixed at ``FAMILY`` -- it must be, or
        # two inputs render identically and write differently -- so a role on an
        # event with no ``people`` reaches nothing at all. The preview promised
        # "as Witness" and the writer applied it nowhere: **the approved account
        # and the write disagreeing for the third time on this branch**, which is
        # what #106 is filed about.
        role = str(event.get("role") or "").strip()
        carriers = [who for who in (event.get("people") or []) if str(who or "").strip()]
        if role and role.casefold() != "primary" and not carriers:
            raise GraphInvalid(
                f"event {event.get('id')!r} gives the role {role!r} but names no "
                "people, so nothing would carry it -- a family's own reference "
                "always uses the family role. Name the people it applies to, or "
                "leave the role out."
            )
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
    # ⛔ **The COMPLEMENT of ``ATTACHABLE``, computed rather than listed.**
    #
    # ⚠️ Two lists that must stay opposite is two things to keep in step, and this
    # file has already paid for that shape. **Declaring a kind attachable stops it
    # being refused here in the same edit**, and a kind that is neither declared
    # nor refused cannot exist because the set is derived from ``GROUPS``.
    # ⛔ Built HERE, from the parsed values, so every group in ``GROUPS`` is
    # reachable by name rather than by a local variable happening to match.
    #
    # ⚠️ This used ``locals()``, and the failure was silent and immediate: the
    # refusal fired for notes and citations and **not for events**, so a kind
    # removed from ``ATTACHABLE`` was neither resolved nor refused — its
    # ``gramps_id`` simply ignored. Caught by a control that did not fire when it
    # should have, which is the only reason it was found.
    by_group: dict[str, tuple[dict[str, Any], ...]] = {
        "people": people,
        "places": places,
        "events": events,
        "citations": citations,
        "families": families,
        "notes": notes,
        "source": (source,) if isinstance(source, dict) else (),
    }
    missing = set(GROUPS) - set(by_group)
    if missing:  # pragma: no cover -- the consistency test pins this
        raise GraphInvalid(f"internal: no entries mapped for {sorted(missing)}")

    for group, one in GROUPS.items():
        if group in ATTACHABLE:
            continue
        for item in by_group[group]:
            if item.get("gramps_id"):
                raise GraphInvalid(
                    f"{one} {item.get('id')!r} carries a 'gramps_id', but "
                    f"{group} are always created. Only {', '.join(ATTACHABLE)} may "
                    "name something that already exists."
                )

    # ⛔ **LAST, so a specific refusal is never shadowed by this one.**
    #
    # ⚠️ Checked first, it reported *nothing to write* for a graph whose real
    # problem was a refused ``role`` or an unknown key -- true, and useless,
    # because the caller needed the specific fault named. Same rule as
    # ``gramps_id`` passing the unknown-key check so its own refusal survives.

    # ⛔ **At least one committed change** -- skipped only for a READ.
    #
    # ⚠️ ``resolve_nodes`` and the ``/resolve`` route ask *what do these ids point
    # at?* and write nothing, so requiring a committed change of them is a
    # category error. **The old proxy had the same error and simply did not bite**,
    # because a resolution usually names people; replacing it with the honest rule
    # is what exposed it.
    #
    # ⭐ The polarity is deliberate: ``parse`` stays STRICT by default and a
    # reader opts out by name, so a write path added later that forgets gets the
    # strict answer rather than the permissive one.
    #
    # ⚠️ This replaces ``people`` non-empty, which was a proxy for it: a graph of
    # a source, a citation and an existing event writes plenty and names nobody,
    # and was refused as having "nothing to write". A caller's only escape was to
    # bolt on an unrelated person -- who then appeared in the approval dialog,
    # putting a record in front of the owner that had nothing to do with the
    # proposal.
    if writes and not _writes_anything(
        (
            ("people", people),
            ("places", places),
            ("events", events),
            ("citations", citations),
            ("families", families),
            ("notes", notes),
        ),
        source if isinstance(source, dict) else None,
    ):
        raise GraphInvalid(
            "this graph would not change the tree. Every node it names already "
            "exists and nothing is attached to any of them, so approving it would "
            "write nothing. Name something to create -- a person, an event, a "
            "source -- or attach a citation or a note to something with "
            "'attach_to'."
        )

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
    # ⛔ **Rendered, because the writer applies it.** A census line's occupation,
    # relationship to head or marital status has nowhere else structured to go,
    # and the tree's own events already carry such strings. **A description
    # written and not shown is the preview/writer class**, which this file has six
    # recorded instances of.
    described = str(event.get("description") or "").strip()
    # ⛔ The household the event JOINS, named. R3's criterion is that no byte
    # reaches the tree unrendered, and a marriage attaching to a family the owner
    # never saw named is that criterion failing -- the write is small, this line
    # is the reason the slice exists.
    if event.get("family"):
        bits.append("on the family " + named(event["family"]))
    line = ", ".join(bits)
    # ⛔ Appended after the join, not as another comma-separated bit: a
    # description is prose and reads as a trailing clause, not as another field.
    return f"{line} -- {described}" if described else line


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
    events_by_id = {str(e.get("id")): e for e in graph.events if e.get("id")}
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
            # ⛔ An attached EVENT is recorded as rendered here.
            #
            # ⚠️ Without this it rendered under ATTACHING TO EXISTING **and again
            # under ALSO WRITTEN**, with its citation counted twice -- the
            # preview asserting two additions where the writer makes one. Caught
            # by the completeness backstop before this shipped, which is that
            # backstop doing exactly what it is for.
            for index, event in enumerate(graph.events):
                if event.get("id") == node.local_id:
                    shown_events.add(index)
            entry = (
                people_by_id.get(node.local_id)
                or places_by_id.get(node.local_id)
                or families_by_id.get(node.local_id)
                or events_by_id.get(node.local_id)
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
    backup_path: str = "",
    backup_utc: str = "",
    totals_before: dict[str, int] | None = None,
) -> dict[str, Any]:
    """What was written, in enough detail to reverse it by hand.

    ⭐ **Every object created is named by its Gramps ID**, which is what somebody
    types into Gramps to find it again. The graph goes in beside it so the record
    also says what was *asked for*, not only what resulted.

    ``attached`` records the existing objects that gained something -- reversing
    those means removing a reference rather than deleting a record, and the two
    are different jobs.

    ⭐ **The backup is named HERE, and that is R4's precondition 4** -- *the
    backup's age relative to the write is visible without archaeology*. Asking
    *which copy predates this write* is then reading one field, rather than
    comparing file times and hoping.

    ⛔ **``totals_before`` exists because the restore procedure asks for it.** The
    owner is told to reopen Gramps after replacing the file and check the counts;
    without the counts recorded at backup time there is nothing to check against,
    and that step could not be performed. ``accessor.tree_totals()`` produces them
    in O(1), so this is a field to store rather than a walk to add.
    """
    return {
        "record": JOURNAL_FORMAT,
        "written_utc": written_utc,
        "tree": tree_dir,
        "created": {kind: list(ids) for kind, ids in created.items() if ids},
        "attached_to_existing": {kind: list(ids) for kind, ids in attached.items() if ids},
        "graph": graph.as_dict(),
        "approved_preview": approved_preview,
        "backup": {
            "path": backup_path,
            "taken_utc": backup_utc,
            "totals_before": totals_before or {},
        },
    }


def write_journal(tree_dir: str, record: dict[str, Any], *, stem: str) -> tuple[str, str]:
    """Put the record in the tree's own undo directory and return where it landed.

    ⚠️ **``fsync`` before returning**, for the reason ``core/apply`` gives: "the
    record was written" must not mean "the record is in a buffer" while the
    database change reaches the disk.

    ⛔ **And the DIRECTORY is synced too, where the platform allows it.** Syncing
    only the file leaves the directory entry itself unflushed on POSIX, so a
    power loss after the database commit can preserve the tree change and lose
    the record naming its backup -- *the file was durable and its name was not.*
    ⚠️ Windows cannot open a directory for ``fsync``; ``directory_synced`` in the
    returned record says which happened rather than letting a platform silently
    stand in for a guarantee.
    """
    directory = os.path.join(tree_dir, UNDO_DIRECTORY)
    # ⛔ Creating and flushing are one decision -- see ``paths.create_directory``.
    created_levels = paths.create_directory(directory)
    path = os.path.join(directory, stem + ".json")

    # ⛔ **Written beside the target and MOVED into place, never opened over it.**
    #
    # ⚠️ Completion re-uses the intent's stem deliberately -- the completed record
    # must replace the intent, not sit beside it as a second file. But ``open(...,
    # "w")`` TRUNCATES FIRST: for the whole span between that truncation and the
    # fsync below, the only durable link between the committed database change and
    # its backup was a zero-length file. A crash there loses the mapping A4 exists
    # to keep, and loses it *after* the write has already landed.
    #
    # ⭐ ``os.replace`` is atomic on both POSIX and Windows, so at every instant the
    # name holds either the intact intent or the intact completion -- the same bound
    # the backup's own publication uses, for the same reason.
    partial = path + ".partial"
    # ⛔ Owner-only, for the same reason the backup copy is. ⚠️ The bot named the
    # backup; this file is the SAME exposure in a second place -- it carries the
    # approved preview, which is the names and dates the owner just read on
    # screen. Fixing only the site that was named is the enumeration this project
    # keeps paying for, so the rule is *anything this code creates that holds
    # tree data is owner-only*.
    paths.create_file_owner_only(partial)
    with open(partial, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)
    # ⛔ The result is RETURNED, not discarded. An earlier version called this
    # and threw the answer away, so ``write_journal`` reported a durable record
    # on every Windows write -- a check performed and then ignored, which is
    # exactly the same defect as not performing it.
    return path, paths.durable_directory(created_levels)


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
    # ⛔ Events are attachable, so this preview has to say so too.
    #
    # ⚠️ It reported EVERY event as created new. For a proposal that correctly
    # named an existing event, the agent's immediate answer contradicted both the
    # approval dialog and the writer -- so a caller could abandon or "fix" a
    # proposal that was already right, and produce the duplicate by fixing it.
    attaching_events = [e for e in graph.events if e.get("gramps_id")]
    creating_people = [p for p in graph.people if not p.get("gramps_id")]
    creating_places = [p for p in graph.places if not p.get("gramps_id")]
    creating_source = graph.source if graph.source and not graph.source.get("gramps_id") else None

    out: list[str] = []
    if attaching_people or attaching_places or attaching_source or attaching_events:
        out.append("ATTACHING TO EXISTING RECORDS")
        for entry in attaching_people:
            out.append(f"  person  {entry['gramps_id']}")
        for entry in attaching_events:
            out.append(f"  event   {entry['gramps_id']}")
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

    # ⛔ Events are no longer always created new, so the count is split the same
    # way families' already is. **Saying "always created new" about a node the
    # caller correctly attached is a false statement about its own proposal**, and
    # the caller acting on it produces the duplicate.
    new_events = [e for e in graph.events if not e.get("gramps_id")]
    if new_events:
        out.append(f"  {len(new_events)} events (created new)")
    if attaching_events:
        out.append(
            f"  {len(attaching_events)} events (attaching to an event already in the "
            "tree; its type, date and place are left exactly as they are)"
        )
    for label, items in (
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
