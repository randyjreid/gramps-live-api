"""The one module that touches the Gramps database. Everything here refuses the wrong thread.

⚠️ **This file is load-bearing by being the ONLY one.** R8: *"one accessor
module owns the boundary, and a test asserts that calling any DB helper from a
non-main thread raises."* ``tests/unit/test_host_thread_boundary.py`` asserts
both halves -- every public ``def`` here refuses a non-main thread, and no other
file the host consists of spells the database at all.

**So two rules apply to edits here, and both are checked:**

1. Every public function wears ``@on_main_thread``. It is not a reminder; the
   test calls each one from a spawned thread and requires ``WrongThread``.
2. Nothing callable is imported into this namespace. Import the module and reach
   through it -- ``status.TreeStatus``, never ``from .status import TreeStatus``
   -- because the test discovers helpers by reading this file's ``def``s, and an
   imported callable would be reachable on the module and invisible to that
   read.

⭐ **The database is read live, not cached from the signal.** ``dbstate.db`` is
rebound by Gramps itself before ``database-changed`` is emitted, so asking for it
at the moment of the request is both simpler and safer than mirroring it here: a
signal this host never received -- because it subscribed late, or because a
handler raised -- would otherwise leave ``/health`` confidently describing a tree
that is no longer open. The subscription's job is the log and the record, not the
answer.
"""

from __future__ import annotations

import sqlite3
import typing

from gramps_live_api.host import document, log, mainthread, reads, status

# ⚠️ Every import here is a MODULE, including ``typing``. Rule 2 above is
# checked with no exemption list, and ``from typing import Any`` would need one
# -- which is the enumeration failure this project refuses everywhere else: an
# exemption for a callable that is obviously harmless is an exemption the next
# callable slips through behind.

_DBSTATE: typing.Any = None
"""Gramps' ``DbState``, handed over once by the plugin at ``load_on_reg``.

Deliberately private and deliberately module-level: a caller that cannot name it
cannot pass the database to a thread, and the boundary test refuses this spelling
in every other file the host consists of.
"""


@mainthread.on_main_thread
def bind(dbstate: typing.Any) -> None:
    """Take Gramps' ``DbState``. Called once, from ``load_on_reg``, on the main thread."""
    global _DBSTATE
    _DBSTATE = dbstate


@mainthread.on_main_thread
def forget() -> None:
    """Drop it again -- used at shutdown, and by tests that need a known state."""
    global _DBSTATE
    _DBSTATE = None


@mainthread.on_main_thread
def tree_status() -> status.TreeStatus:
    """Whether a tree is open, and if so its name and how many people it holds.

    ⚠️ **Both reads are O(1) and that is a requirement, not an observation.**
    This is the only thing the host ever schedules onto the GTK loop, and R8's
    accepted risk 4 is that long work inside ``idle_add`` blocks that loop.
    ``get_dbname`` reads a cached string and ``get_number_of_people`` a table
    count; anything that walks people belongs behind a route this slice does not
    have.

    ⛔ **No tree text leaves here.** A name and a count, which is what keeps this
    slice unblocked by R3.

    ``load_on_reg`` fires with no tree open and ``dbstate.db`` a ``DummyDb``,
    which is the state this must start in -- so "closed" is the ordinary answer
    and not an error.
    """
    if _DBSTATE is None:
        return status.TreeStatus(open=False)

    database = _DBSTATE.db
    if database is None or not database.is_open():
        return status.TreeStatus(open=False)

    return status.TreeStatus(
        open=True,
        name=database.get_dbname(),
        people=database.get_number_of_people(),
    )


def _public(obj: typing.Any) -> typing.Any:
    """``obj``, or ``None`` if the tree marks it private. ⛔ EVERY fetch goes through this.

    ⭐ **The bound is on the whole reachable graph, not on the object asked for.**
    Two leaks of one class got through review as separate patches -- a public
    person leaking a PRIVATE birth event's date, and a public event leaking a
    PRIVATE place's name -- because the criterion asked *is the thing being
    returned private?* and the leaks were in what it **pointed at**. A third
    instance was then found by audit rather than by review, which is the
    signature of a rule that is enumerated rather than bounded.

    ⚠️ **A helper alone would not bound it**, because the next read route is
    written by somebody who has to remember. ``tests/unit/test_accessor_privacy_gate.py``
    reads THIS FILE and asserts that every ``get_*_from_handle`` and
    ``get_*_from_gramps_id`` call is wrapped here -- the same shape as the
    thread-boundary test, which discovers accessor helpers by reading the source
    instead of trusting a list. **A new route inherits the bound by being
    written, not by being remembered.**

    ⛔ **``None`` carries TWO facts and a direct target must tell them apart.**
    *Absent* and *present but private* are different answers, and collapsing them
    is ruling 1's second enforcement point broken. Adding this gate DID break it
    -- ``list_events`` on a private person started answering 200/empty instead of
    403 -- so a route with a direct target keeps the ungated fetch beside the
    gated one purely to distinguish, and reads only from the gated one.

    ⚠️ **A gate that answers two questions with one value is a gate that will be
    got wrong again**, which is why it is written down here rather than left to
    each call site to remember.
    """
    if obj is None:
        return None
    try:
        if obj.get_privacy():
            return None
    except AttributeError:
        # Not everything Gramps returns carries the flag. A thing that cannot be
        # private cannot be leaked by being private.
        return obj
    return obj


WITHHELD = "(name withheld)"
"""What a private name renders as.

⛔ **The person may be public while their NAME is not** -- the frozen checklist
records ``name/priv`` beside ``person/priv``. There is no way to show a name that
is marked private, so the identity check the display exists for degrades to *you
cannot confirm this, so do not proceed*. That is the correct failure: the owner
cancels. ⚠️ It is NOT the same as the private-birth-date case, where hiding the
date must never cost the name -- here the name itself is the private thing."""


def _name_spellings(name: typing.Any) -> list[str]:
    """Every spelling inside one ``Name``, or nothing if that name is private.

    ⛔ **This is the INDEXING half, and it is the subtler leak.** The search
    corpus was built from the primary name and every alternate, ungated -- so a
    private alternate spelling was *searchable*. The name itself never reached
    the wire, which is exactly what made it hard to see: **the route became an
    oracle for a name marked private**, and nothing on the wire looked wrong.
    """
    if _public(name) is None:
        return []
    out = [name.get_first_name(), name.get_surname()]
    for surname in name.get_surname_list() or []:
        out.append(surname.get_surname())
    return [part for part in out if part]


def _name_shown(name: typing.Any) -> str:
    """One ``Name`` as the owner reads it, or ``WITHHELD``. ⛔ The RENDERING half."""
    if _public(name) is None:
        return WITHHELD
    parts = [part for part in (name.get_surname(), name.get_first_name()) if part]
    return ", ".join(parts) or "(no name)"


def _person_names(person: typing.Any) -> list[str]:
    """Every spelling of a person's name the tree holds -- primary AND alternates.

    ⭐ **The alternates are the point, and it is confirmed against the tree.** A
    search for one spelling misses somebody whose PRIMARY name uses another and
    who carries the searched spelling only as an alternate name. Measured on the
    owner's copy: one person's primary surname uses an umlaut while the ``ue``
    spelling sits in her alternate names, so a primary-only search does not find
    her -- one step from entering a duplicate mother.
    """
    out: list[str] = []
    for name in [person.get_primary_name(), *person.get_alternate_names()]:
        if name is None:
            continue
        out.extend(_name_spellings(name))
    return out


def _person_display(person: typing.Any, database: typing.Any) -> str:
    shown = _name_shown(person.get_primary_name())
    try:
        birth = person.get_birth_ref()
        # ⛔ The REFERENCE carries its own ``priv``, separately from the event
        # it points at. A public person joined to a public event by a PRIVATE
        # EventRef was leaking the date the reference was marked to hide.
        if birth is not None and _public(birth) is not None:
            event = _public(database.get_event_from_handle(birth.ref))
            # ⛔ The EVENT's own flag, not just the person's. A public person
            # whose birth event is marked private was leaking that event's date
            # through the person's display -- private text reached the wire via
            # a public related record, which is the `priv` bound bypassed rather
            # than enforced.
            if event is not None and not event.get_privacy():
                date = event.get_date_object()
                if date is not None and not date.is_empty():
                    shown += f"  (b. {date.get_year() or date})"
    except Exception:
        pass
    return shown


@mainthread.on_main_thread
def find_people(term: str) -> reads.Found:
    """People whose name contains ``term``, private ones excluded and uncounted.

    ⭐ **Measured live, and ACCEPTED at the measured cost.** A full walk of the
    owner's 2,933-person tree through this route takes **343-402 ms**. An earlier
    proxy said ~48 ms; that was raw sqlite plus ``json.loads`` and Gramps' own
    ``Person`` construction is roughly seven times it. **The proxy was wrong and
    the live number is the one that counts.**

    ⛔ **It is not optimised, and the ~200 ms figure it exceeds has been
    withdrawn.** That threshold came from R8's general caution about blocking the
    GTK loop, not from how this route is used: a handful of searches per
    document, driven by an agent, while the owner is reading a chat window and
    not looking at Gramps.

    ⛔ **The fast alternatives are refused on correctness, not on effort.** The
    indexed ``given_name``/``surname`` columns read all 2,933 rows in ~7 ms but
    hold no alternate names -- which is the entire reason this walk exists. And a
    hybrid that queried the index first and fell back to the walk only on an
    empty result would stop after finding three primary-name matches and silently
    miss a fourth carrying the name only as an alternate: **the ``Kuenkele``
    failure wearing a performance costume.**

    **If a third-of-a-second hitch turns out to annoy the owner while he is
    working in Gramps, that is the use-derived trigger to chunk this across
    callbacks. Not before.**
    """
    wanted = reads.require_term(term)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    rows = []
    for person in database.iter_people():
        if not reads.matches_term(wanted, *_person_names(person)):
            continue
        rows.append(
            (
                bool(person.get_privacy()),
                reads.Match(
                    gramps_id=person.get_gramps_id(),
                    display=_person_display(person, database),
                ),
            )
        )
    return reads.bound(rows)


@mainthread.on_main_thread
def find_place(term: str) -> reads.Found:
    """Places whose name contains ``term``. Five Unterensingen variants already exist."""
    wanted = reads.require_term(term)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    rows = []
    for place in database.iter_places():
        name = place.get_name().get_value() or place.get_title() or ""
        if not reads.matches_term(wanted, name, place.get_title()):
            continue
        rows.append((bool(place.get_privacy()), reads.Match(place.get_gramps_id(), name)))
    return reads.bound(rows)


@mainthread.on_main_thread
def find_source(term: str) -> reads.Found:
    """Sources whose title or author contains ``term``."""
    wanted = reads.require_term(term)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    rows = []
    for source in database.iter_sources():
        title = source.get_title() or ""
        author = source.get_author() or ""
        if not reads.matches_term(wanted, title, author):
            continue
        shown = f"{title} -- {author}" if author else title
        rows.append((bool(source.get_privacy()), reads.Match(source.get_gramps_id(), shown)))
    return reads.bound(rows)


@mainthread.on_main_thread
def find_citation(source_gramps_id: str, page: str = "") -> reads.Found:
    """⭐ *Has this document already been entered?* -- the question whose absence
    caused three documents to be entered twice.

    Citations of one source, optionally narrowed by page. ⚠️ **The source id is
    the search term here**, so this is not a way to list every citation.
    """
    wanted = reads.require_term(source_gramps_id)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    # ⚠️ ``_public`` returns None for TWO different facts -- absent, and present
    # but private -- and a direct target must tell them apart. Collapsing them is
    # ruling 1's second enforcement point broken, so the raw fetch is kept to
    # distinguish, and only the gated one is ever read from.
    raw = database.get_source_from_gramps_id(wanted)
    source = _public(raw)
    if raw is not None and source is None:
        raise reads.TargetIsPrivate(f"source {wanted} is marked private in this tree")
    if source is None:
        return reads.Found()
    handle = source.get_handle()
    narrow = str(page or "").strip()
    rows = []
    for citation in database.iter_citations():
        if citation.get_reference_handle() != handle:
            continue
        this_page = citation.get_page() or ""
        if narrow and not reads.matches_term(narrow, this_page):
            continue
        rows.append(
            (
                bool(citation.get_privacy()),
                reads.Match(citation.get_gramps_id(), this_page or "(no page)"),
            )
        )
    return reads.bound(rows)


@mainthread.on_main_thread
def list_events(person_gramps_id: str) -> reads.Found:
    """One person's events, so citing an existing one stops meaning duplicating it.

    ⛔ **Refused BY NAME if that person is private** -- ruling 1's second
    enforcement point. Reporting them absent would leave the caller unable to
    tell *no such person* from *that person is private*.
    """
    wanted = reads.require_term(person_gramps_id)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    # ⚠️ Same as ``find_citation``: absent and private are different answers and
    # the gate cannot carry the difference on its own.
    raw = database.get_person_from_gramps_id(wanted)
    person = _public(raw)
    if raw is not None and person is None:
        raise reads.TargetIsPrivate(
            f"{wanted} is marked private in this tree, so their events cannot be listed"
        )
    if person is None:
        return reads.Found()
    rows = []
    for ref in person.get_event_ref_list():
        if _public(ref) is None:
            continue
        event = _public(database.get_event_from_handle(ref.ref))
        if event is None:
            continue
        date = event.get_date_object()
        place = ""
        if event.get_place_handle():
            found = _public(database.get_place_from_handle(event.get_place_handle()))
            # ⛔ The PLACE's own flag too. A public event referencing a private
            # place was putting that place's name on the wire -- the same bypass
            # as the birth date above, one relation further out.
            if found is not None and not found.get_privacy():
                place = found.get_name().get_value() or found.get_title() or ""
        shown = " ".join(
            part for part in (str(event.get_type()), str(date) if date else "", place) if part
        )
        rows.append((bool(event.get_privacy()), reads.Match(event.get_gramps_id(), shown)))
    return reads.bound(rows)


def _family_display(database: typing.Any, family: typing.Any) -> str:
    """A family as the owner recognises it: the couple, and how many children."""
    parts = []
    for handle in (family.get_father_handle(), family.get_mother_handle()):
        if not handle:
            continue
        person = _public(database.get_person_from_handle(handle))
        if person is not None:
            parts.append(_person_display(person, database))
    shown = " + ".join(parts) or "(no parents recorded)"
    # ⛔ Counted through the gate, exactly like the parents above. A raw
    # ``len(get_child_ref_list())`` on a PUBLIC family reports its private
    # children too -- "[3 children]" where two are public announces that a
    # hidden one exists. That is the leak by arithmetic ``reads.bound`` is built
    # to prevent, arriving through a display string instead of through a count.
    children = 0
    for ref in family.get_child_ref_list():
        if _public(ref) is None:
            continue
        if _public(database.get_person_from_handle(ref.ref)) is not None:
            children += 1
    return shown + (f"  [{children} children]" if children else "")


def _membership_is_public(family: typing.Any, person_handle: typing.Any) -> bool:
    """Whether this person's membership of this family may be shown at all.

    ⛔ **The backlink carries no reference, which is why this is needed.**
    ``get_parent_family_handle_list()`` returns HANDLES, so the ``ChildRef``
    marked private lives on the FAMILY's side and nothing on the person's side
    points at it. Walking from the child therefore reached a public family with
    public parents and returned it, publishing the one fact that was marked
    private: **that this child belongs to this household.**

    ⚠️ **The reference gate does not cover this, and the difference is worth
    stating.** ``test_every_reference_is_gated_before_it_is_followed`` bounds
    dereferences of a ``.ref``; there is no ``.ref`` on this path. A rule about
    how references are followed cannot see a leak that follows a bare handle.

    Returns True when the person is not a child of this family -- a spouse link
    is two handle slots on the family and carries no privacy flag of its own.
    """
    for ref in family.get_child_ref_list():
        if ref.ref == person_handle:
            return _public(ref) is not None
    return True


@mainthread.on_main_thread
def find_families(person_gramps_id: str) -> reads.Found:
    """The families one person belongs to, as spouse or as child.

    ⭐ **This is what closes the gap that a Marriage License exposed.** A marriage
    belongs to a FAMILY, and ``list_events`` takes a person -- so the state of a
    family-level record could not be determined at all, and the same wall stands
    in front of every household census.

    ⛔ **Refused BY NAME if the person is private**, and a private family is
    dropped from the listing rather than reported -- ruling 1's two enforcement
    points, as everywhere else.
    """
    wanted = reads.require_term(person_gramps_id)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    existed, person = _by_gramps_id(database, "person", wanted)
    if existed and person is None:
        raise reads.TargetIsPrivate(
            f"{wanted} is marked private in this tree, so their families cannot be listed"
        )
    if person is None:
        return reads.Found()

    rows = []
    seen = set()
    for handle in [
        *person.get_family_handle_list(),
        *person.get_parent_family_handle_list(),
    ]:
        if handle in seen:
            continue
        seen.add(handle)
        raw = database.get_family_from_handle(handle)
        family = _public(raw)
        if family is None:
            continue
        # ⛔ The MEMBERSHIP can be private while both ends are public.
        if not _membership_is_public(family, person.get_handle()):
            continue
        rows.append((False, reads.Match(family.get_gramps_id(), _family_display(database, family))))
    return reads.bound(rows)


@mainthread.on_main_thread
def list_family_events(family_gramps_id: str) -> reads.Found:
    """A family's own events -- marriage, and anything else recorded on the couple.

    ⚠️ **Marriages are not on either person.** Asking a person for their events
    and concluding there is no marriage is how a second marriage record gets
    entered for a couple who already have one.
    """
    wanted = reads.require_term(family_gramps_id)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    existed, family = _by_gramps_id(database, "family", wanted)
    if existed and family is None:
        raise reads.TargetIsPrivate(f"family {wanted} is marked private in this tree")
    if family is None:
        return reads.Found()

    rows = []
    for ref in family.get_event_ref_list():
        if _public(ref) is None:
            continue
        raw = database.get_event_from_handle(ref.ref)
        event = _public(raw)
        if event is None:
            continue
        date = event.get_date_object()
        place = ""
        if event.get_place_handle():
            found = _public(database.get_place_from_handle(event.get_place_handle()))
            if found is not None:
                place = found.get_name().get_value() or found.get_title() or ""
        shown = " ".join(
            part for part in (str(event.get_type()), str(date) if date else "", place) if part
        )
        rows.append((False, reads.Match(event.get_gramps_id(), shown)))
    return reads.bound(rows)


@mainthread.on_main_thread
def list_notes(gramps_id: str, kind: str = "person") -> reads.Found:
    """The notes attached to one record, so a manual cleanup can name them.

    ⚠️ **Written because the note IDs for a cleanup could not be produced at
    all** -- they were reachable only by reading an export by hand.
    """
    wanted = reads.require_term(gramps_id)
    asked = str(kind or "person")
    if asked not in NOTE_KINDS:
        # ⛔ Refuse rather than default to "person". Silently retargeting means a
        # misspelt kind answers about a different object entirely, and "no
        # notes" is a result a caller acts on.
        raise reads.UnknownKind(
            f"{asked!r} is not a kind of record this can look up. "
            "Use one of: " + ", ".join(NOTE_KINDS)
        )
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    existed, obj = _by_gramps_id(database, asked, wanted)
    if existed and obj is None:
        raise reads.TargetIsPrivate(f"{wanted} is marked private in this tree")
    if obj is None:
        return reads.Found()

    rows = []
    for handle in obj.get_note_list():
        raw = database.get_note_from_handle(handle)
        note = _public(raw)
        if note is None:
            continue
        text = " ".join((note.get() or "").split())
        rows.append(
            (
                False,
                reads.Match(note.get_gramps_id(), text[:200] + ("..." if len(text) > 200 else "")),
            )
        )
    return reads.bound(rows)


@mainthread.on_main_thread
def list_associations(person_gramps_id: str) -> reads.Found:
    """A person's associations -- godparents and the like. ⛔ READ ONLY.

    ⚠️ **Stored as ``personref`` with a relationship string**, and findable until
    now only by grepping an export. Exposing them prevents entering a godparent
    who is already recorded; ⛔ **writing them is a vocabulary change and has no
    use-derived trigger**, so this reads and nothing more.
    """
    wanted = reads.require_term(person_gramps_id)
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    existed, person = _by_gramps_id(database, "person", wanted)
    if existed and person is None:
        raise reads.TargetIsPrivate(
            f"{wanted} is marked private in this tree, so their associations cannot be listed"
        )
    if person is None:
        return reads.Found()

    rows = []
    for ref in person.get_person_ref_list():
        if _public(ref) is None:
            continue
        raw = database.get_person_from_handle(ref.ref)
        other = _public(raw)
        if other is None:
            continue
        relation = ref.get_relation() or "(unspecified)"
        rows.append(
            (
                False,
                reads.Match(
                    other.get_gramps_id(), f"{relation}: {_person_display(other, database)}"
                ),
            )
        )
    return reads.bound(rows)


@mainthread.on_main_thread
def resolve_nodes(graph: dict[str, typing.Any]) -> document.Resolution:
    """Look up every node that says it already exists, and read its name from the TREE.

    ⭐ **The display string comes from Gramps, never from the graph.** If the
    model picked the wrong Gramps ID, the owner reads the wrong person's name in
    the dialog and cancels -- echoing back the name the model supplied would
    defeat the only check there is.

    ⚠️ **One O(1) lookup per requested node, plus a birth date for a person.**
    R8's accepted risk 4 caps what a single ``idle_add`` callback may do; a
    document names a handful of people, not a tree's worth.

    A node that does not resolve comes back with ``found=False`` rather than
    raising, so the caller can refuse the **whole batch** naming every missing
    id at once instead of one per round trip.
    """
    parsed = document.parse(graph)
    if _DBSTATE is None:
        return document.Resolution(
            nodes=tuple(
                document.Resolved(r.local_id, r.gramps_id, r.kind, found=False)
                for r in document.requested(parsed)
            )
        )
    database = _DBSTATE.db
    found: list[document.Resolved] = []
    for request in document.requested(parsed):
        # ⛔ The gate lives inside the fetch now, so nothing ungated arrives here.
        # ``/resolve`` used to answer found=True for a private record, which
        # confirmed its existence to the agent -- the same class as the display
        # leaks, on the WRITE path rather than a read.
        existed, obj = _by_gramps_id(database, request.kind, request.gramps_id)
        private = existed and obj is None
        found.append(
            document.Resolved(
                local_id=request.local_id,
                gramps_id=request.gramps_id,
                kind=request.kind,
                found=obj is not None,
                display=_display_of(database, request.kind, obj) if obj is not None else "",
                private=private,
            )
        )
    return document.Resolution(nodes=tuple(found))


NOTE_KINDS = ("person", "place", "source", "family")
"""Every kind ``_by_gramps_id`` can look up, and therefore every kind a read may
name.

⚠️ **This is a second list of something the code below already spells**, which is
precisely the shape that produced the counter bug this branch also fixes -- two
tallies with nothing making them agree. It is not derived here because deriving
it at import time would mean parsing our own source to answer a constant. So it
is **pinned by test instead**: ``tests/unit/test_accessor_reads.py`` reads
``_by_gramps_id``'s branches and fails if the two ever disagree."""


def _by_gramps_id(database: typing.Any, kind: str, gramps_id: str) -> tuple[bool, typing.Any]:
    """``(it exists, the GATED object)`` for a Gramps ID. ⛔ Never creates anything.

    ⭐ **No raw object leaves this function**, and that is the point of the return
    shape. It used to hand one back and rely on ``resolve_nodes`` to gate it --
    issue #103's first bullet, where a future edit to the caller would remove the
    protection and nothing would fire.

    The boolean carries the one fact the caller needs that the gated object
    cannot: **present-but-private** looks exactly like **absent** once gated, and
    ruling 1 requires those two to stay distinguishable.

    ⚠️ **Explicit branches rather than a ``getattr`` dispatch**, also deliberate:
    the dispatch was invisible to ``tests/unit/test_accessor_privacy_gate.py``,
    whose pattern needs a call whose callee is syntactically an attribute.
    Spelled out, every fetch here is one the guard can see.
    """
    try:
        if kind == "person":
            obj = database.get_person_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
        if kind == "place":
            obj = database.get_place_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
        if kind == "source":
            obj = database.get_source_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
        if kind == "family":
            obj = database.get_family_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
        if kind == "event":
            obj = database.get_event_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
        if kind == "citation":
            obj = database.get_citation_from_gramps_id(gramps_id)
            return obj is not None, _public(obj)
    except Exception:
        return False, None
    return False, None


def _display_of(database: typing.Any, kind: str, obj: typing.Any) -> str:
    """How the owner will recognise it: the name Gramps holds, and a birth year.

    ⚠️ **A birth year is what makes two people with one name distinguishable**, so
    it is worth the extra lookup -- it is the difference between *Standlake,
    Peregrine* and *the right Standlake, Peregrine*.
    """
    try:
        if kind == "person":
            shown = _name_shown(obj.get_primary_name())
            birth = obj.get_birth_ref()
            if birth is not None and _public(birth) is not None:
                event = _public(database.get_event_from_handle(birth.ref))
                # ⛔ ``None`` here means the birth event is PRIVATE, and only the
                # DATE is dropped for it -- never the name.
                #
                # ⚠️ Letting that ``None`` fall through raised, the broad handler
                # below caught it, and the whole display became "(could not read
                # its name)". ``document.preview`` relies on this tree-read name
                # for the owner to notice he is attaching to the WRONG person, so
                # hiding a private date was silently disabling the identity check
                # on the write path. **A privacy fix must not cost a safety
                # check.**
                if event is not None:
                    date = event.get_date_object()
                    if date is not None and not date.is_empty():
                        shown += f"  (b. {date.get_year() or date})"
            return shown
        if kind == "place":
            # ⭐ ``name.value`` FIRST, ``title`` only as a fallback. Measured on
            # the owner's copy: of 2,256 places, 7 differ between the two, and
            # ``title`` carries an umlaut in NONE of them while ``name.value``
            # does in four -- so where they differ, ``title`` is the damaged
            # one. ⚠️ And four places have a ``name.value`` with no ``title`` at
            # all, which rendered as nothing.
            return str(obj.get_name().get_value() or obj.get_title() or "(unnamed place)")
        if kind == "source":
            title = str(obj.get_title() or "(untitled)")
            author = str(obj.get_author() or "")
            return f"{title} -- {author}" if author else title
        if kind == "family":
            # ⛔ Without this branch a resolved family fell through to "(could
            # not read its name)" while ``preview`` ALSO listed it under CREATING
            # NEW -- so the dialog described creating a household that the writer
            # was going to append children to. **The owner would have approved a
            # different operation from the one that runs**, which is R3's whole
            # criterion. ``document.preview`` is what renders this.
            return _family_display(database, obj)
    except Exception:
        # A display string is not worth failing a lookup over. The id resolved;
        # that is the load-bearing fact.
        return "(could not read its name)"
    return ""


@mainthread.on_main_thread
def blessing() -> document.Blessing:
    """Whether the OPEN tree may be written to, and the message if it may not.

    ⚠️ **The path comes from the open database, never from an argument**, the
    same rule ``core/apply`` follows: a refusal then names the tree that is
    actually open rather than one a caller nominated.

    ⛔ **Two files, both required** -- ``name.txt`` says it is a Gramps tree at
    all, and the sentinel says the owner is willing to have it written to. Same
    two conditions ``core/apply.authorise`` applies.
    """
    if _DBSTATE is None:
        return document.Blessing(blessed=False, message="no tree is open")
    database = _DBSTATE.db
    if database is None or not database.is_open():
        return document.Blessing(blessed=False, message="no tree is open")
    return document.blessing_of(database.get_save_path())


@mainthread.on_main_thread
def person_status(gramps_id: str) -> status.PersonStatus:
    """Whether that Gramps ID names somebody, and whether they are private.

    ⭐ **The Person object is MATERIALISED, and that is the whole point of this
    helper.** ``get_person_from_gramps_id`` fetches the record; both booleans are
    then read off what came back. An answer taken from an index without the fetch
    would be cheaper, would look identical on the wire, and would **measure
    nothing** -- and measuring is what this route is for: it is F3's falsifier,
    *a single-person read round trip through the main-thread hop exceeds ~2 s*,
    which the ``/health`` timing could not touch because ``tree_status`` reads two
    O(1) values and walks nothing.

    ⚠️ **This is a keyed fetch, not a walk.** ``tree_status``'s note that
    "anything that walks people belongs behind a route this slice does not have"
    is about scanning the table; one lookup by Gramps ID is the smallest read
    that exists and is still one lookup, which is what keeps R8's accepted risk 4
    -- long work inside ``idle_add`` blocking the GTK loop -- where it was.

    ⭐ **The flag is REPORTED here and the response is decided above**, which is
    the separation ``core/people.py`` already draws: its reader returns private
    people and its ``search`` filters them, deliberately, so that ruling 1's two
    enforcement points can be answered independently. A2 is a target lookup, so
    it is the second point -- *a target is refused BY NAME rather than reported
    absent* -- and an accessor that dropped private people here could only answer
    it wrongly.

    ⚠️ **A CLOSED TREE IS ANSWERED ``found: false``, and that is a decision this
    slice's brief did not make.** It is recorded rather than presented as
    settled. The reasoning taken: no Gramps ID names a person in a tree that is
    not open, so the answer is true as stated; ``/health`` is the route that says
    whether one is open, so nothing is unanswerable from the pair; and the
    alternatives -- a fourth payload state, a fourth status code, or an exception
    turning an ordinary startup state into a 500 -- each add vocabulary that R3
    or a ruling would have to settle. **``load_on_reg`` fires with no tree open,
    so this branch is reached on every launch and could not be left undefined.**
    """
    if _DBSTATE is None:
        return status.PersonStatus(found=False)

    database = _DBSTATE.db
    if database is None or not database.is_open():
        return status.PersonStatus(found=False)

    person = database.get_person_from_gramps_id(gramps_id)
    if person is None:
        return status.PersonStatus(found=False)

    # ``get_privacy`` rather than the ``private`` attribute beside it: Gramps'
    # ``PrivacyBase`` exposes both, and the accessor is the one reader, so it
    # reads through the documented one.
    return status.PersonStatus(found=True, private=bool(person.get_privacy()))


@mainthread.on_main_thread
def note_connection_shape(note: typing.Callable[[str, str], None]) -> None:
    """Report-only, for R7: what the open database keeps its connection in, if anything.

    ⛔ **Nothing is written, nothing is backed up, and nothing depends on the
    answer.** R7 -- what takes a backup of a tree Gramps is holding open -- is
    unruled and is the owner's. What it lacked was a fact: whether a process that
    already holds the handle can reach the connection object at all. This writes
    one INFO line saying what it found, and the slice ships whichever way that
    reads.

    ⚠️ **Best-effort by construction, and "I could not find one" is a RESULT.**
    The attribute path into Gramps' DB-API backend is unknown from this
    repository, so this never names one: naming a path would measure our guess
    rather than the tree. It walks instance dictionaries instead -- see
    ``_reachable_connections`` for why that and not ``getattr`` -- and reports
    the types it reached, never a value, a repr or a filename.

    ⛔ **It may not raise, and the guard is here rather than inside.** This rides
    on ``database-changed``, whose handlers Gramps dispatches inside its own
    ``emit`` -- so an exception escaping a report-only probe would land in the
    signal, where nothing this project owns can report it. Catching at the one
    place that has somewhere to write means every step below is covered,
    including ``is_open`` itself, and not merely the walk.
    """
    try:
        shape = _connection_shape()
    except Exception as failure:  # noqa: BLE001 -- report-only; the failure IS the result
        shape = f"the probe failed with {type(failure).__name__}"
    note(log.INFO, "connection probe: " + shape)


_PROBE_DEPTH = 4
"""How far below the database object the probe will look. Bounded so an object
graph with a cycle in it cannot make a report-only walk run forever."""

_PROBE_OBJECTS = 500
"""And how many objects it will look at, for the same reason from the other side.
Depth alone does not bound a wide graph."""

_PROBE_REPORTED = 5
"""How many candidates reach the log line. A report nobody can read is not one."""

_CONNECTION_METHODS = ("close", "commit", "cursor")
"""What makes an object a connection, taken from PEP 249's own Connection object.

⚠️ **Not an enumeration of Gramps internals**, which is what this rule refuses
everywhere else: it is a published, externally specified interface, on the same
footing as the other tables here that are derived rather than remembered. A
wrapper that satisfies it is worth reporting whether or not it is the bottom of
the stack -- which is why the walk descends THROUGH a match rather than stopping
at one.
"""


def _connection_shape() -> str:
    """One line describing what the walk found, in every case including failure."""
    if _DBSTATE is None:
        return "no dbstate is bound"

    database = _DBSTATE.db
    if database is None or not database.is_open():
        return "no tree is open"

    found = _reachable_connections(database)
    if not found:
        return (
            "nothing shaped like a PEP 249 connection was reachable through instance "
            f"attributes within depth {_PROBE_DEPTH}"
        )

    return "; ".join(
        f"{path} is {type(obj).__module__}.{type(obj).__qualname__} "
        f"(sqlite3.Connection={isinstance(obj, sqlite3.Connection)})"
        for path, obj in found
    )


def _reachable_connections(database: typing.Any) -> list[tuple[str, typing.Any]]:
    """Every connection-shaped object under ``database``, nearest first, capped.

    ⚠️ **``vars`` rather than ``getattr``, and it is the load-bearing choice.**
    Reading an instance dictionary runs none of the object's own code;
    interrogating an arbitrary object by attribute name does, because a property
    can do anything at all -- including raise, or touch the database from
    wherever this happens to be called. A report-only probe may not have side
    effects, so it never asks the object a question the object can answer with
    code.

    ⚠️ **It descends THROUGH a match rather than stopping at one**, because
    Gramps' DB-API layer wraps the real connection in one of its own and the
    wrapper satisfies the same interface. Stopping at the first would report the
    wrapper and answer the question with the wrong object.
    """
    seen = {id(database)}
    frontier: list[tuple[str, typing.Any, int]] = [("db", database, 0)]
    found: list[tuple[str, typing.Any]] = []
    visited = 0

    while frontier and len(found) < _PROBE_REPORTED and visited < _PROBE_OBJECTS:
        path, obj, depth = frontier.pop(0)
        visited += 1

        if depth and _looks_like_a_connection(obj):
            found.append((path, obj))

        if depth >= _PROBE_DEPTH:
            continue

        for name, value in _instance_attributes(obj):
            if id(value) in seen:
                continue
            seen.add(id(value))
            frontier.append((f"{path}.{name}", value, depth + 1))

    return found


def _instance_attributes(obj: typing.Any) -> list[tuple[str, typing.Any]]:
    """What ``obj`` holds in its own ``__dict__``, or nothing if it has none."""
    try:
        contents = vars(obj)
    except TypeError:
        # ``__slots__``, or a built-in. Neither is on the way to a connection.
        return []
    return list(contents.items())


def _looks_like_a_connection(obj: typing.Any) -> bool:
    """Whether ``obj`` presents PEP 249's Connection interface.

    The methods are looked up **on the type**, so a property or a descriptor on
    the instance is never evaluated -- the same restraint ``_instance_attributes``
    keeps, for the same reason.
    """
    if isinstance(obj, sqlite3.Connection):
        return True
    if isinstance(obj, (str, bytes, bytearray, int, float, bool, type(None))):
        return False
    return all(callable(getattr(type(obj), name, None)) for name in _CONNECTION_METHODS)


CITED_KINDS = ("person", "event", "family", "place", "citation")
"""What ``list_citations`` will look up.

⛔ **Pinned against ``_by_gramps_id``'s branches by test**, like ``NOTE_KINDS``.
⚠️ **It was not, at first, and the omission cost exactly what the pin exists to
prevent:** this advertised ``event`` and ``citation`` while the lookup had no
branch for either, so asking *is this event cited?* returned a **successful empty
result** -- and a caller reading *no citations* adds the duplicate this tool
exists to prevent. **A false negative here is worse than an error**, because only
one of them is visible."""


@mainthread.on_main_thread
def list_citations(gramps_id: str, kind: str = "person") -> reads.Found:
    """What cites this record, and from which source.

    ⭐ **Use-derived, and the trigger has a name: `C0012`.** A 1946 marriage
    citation was attached to **nothing** -- source and citation both present, the
    link absent -- so the record had been effectively uncited for as long as it
    had existed. **It was found by reading an export by hand**, because no tool
    could ask *is this cited?* of anything.

    ⚠️ **The question this answers is not "does a citation exist".** It is
    *does this record carry one*, which is the question whose wrong answer put a
    fact in the tree with nothing standing behind it.
    """
    wanted = reads.require_term(gramps_id)
    asked = str(kind or "person")
    if asked not in CITED_KINDS:
        raise reads.UnknownKind(
            f"{asked!r} is not a kind of record that carries citations. "
            "Use one of: " + ", ".join(CITED_KINDS)
        )
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db
    existed, obj = _by_gramps_id(database, asked, wanted)
    if existed and obj is None:
        raise reads.TargetIsPrivate(f"{wanted} is marked private in this tree")
    if obj is None:
        return reads.Found()

    rows = []
    for handle in obj.get_citation_list():
        raw = database.get_citation_from_handle(handle)
        citation = _public(raw)
        if citation is None:
            continue
        shown = citation.get_page() or "(no page)"
        source_handle = citation.get_reference_handle()
        if source_handle:
            source = _public(database.get_source_from_handle(source_handle))
            if source is not None:
                shown = f"{source.get_title() or '(untitled)'} -- {shown}"
        rows.append((False, reads.Match(citation.get_gramps_id(), shown)))
    return reads.bound(rows)


ORPHAN_KINDS = ("citation", "source", "note", "place", "repository")
"""Kinds ``find_orphans`` will sweep.

⛔ **Events and people are deliberately absent.** A person referenced by nothing
is an ordinary isolated individual, not a defect, and 10,931 events would make
the sweep the most expensive read in the host for the least meaningful answer."""


@mainthread.on_main_thread
def find_orphans(kind: str) -> reads.Found:
    """Records of ``kind`` that nothing in the tree references.

    ⭐ **Use-derived. `C0012` is what a citation orphan looks like** -- it existed,
    it was correct, and it pointed at nothing, so it did no work. Eleven such
    records were found by hand; one of them mattered.

    ⚠️ **``kind`` IS the search term, and that is a deliberate reading of P2.**
    The rule is that there is no *list everybody*, and this cannot list everybody:
    a caller must name what they are looking for, the answer is by construction
    the small set of things nothing points at, private records are excluded, and
    ``RESULT_CAP`` still applies. **A caller cannot browse the tree with this.**

    ⭐ **Backlinks, not a sweep.** ``find_backlink_handles`` reads Gramps' own
    reference table, so this costs one indexed lookup per candidate rather than
    a walk over everything that might point at it.
    """
    asked = reads.require_term(kind)
    if asked not in ORPHAN_KINDS:
        raise reads.UnknownKind(
            f"{asked!r} is not a kind this can sweep for orphans. "
            "Use one of: " + ", ".join(ORPHAN_KINDS)
        )
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db

    iterators = {
        "citation": database.iter_citations,
        "source": database.iter_sources,
        "note": database.iter_notes,
        "place": database.iter_places,
        "repository": database.iter_repositories,
    }
    rows = []
    for obj in iterators[asked]():
        visible = _public(obj)
        if visible is None:
            continue
        try:
            if any(True for _ in database.find_backlink_handles(visible.get_handle())):
                continue
        except Exception:
            # ⛔ A backlink lookup that fails must not report an orphan. Saying
            # "nothing points at this" because the question could not be asked
            # would send the owner deleting a record that is in use.
            continue
        rows.append((False, reads.Match(visible.get_gramps_id(), _orphan_display(asked, visible))))
    return reads.bound(rows)


def _orphan_display(kind: str, obj: typing.Any) -> str:
    """Enough to recognise the record, without reaching for a name it may not have."""
    try:
        if kind == "citation":
            return obj.get_page() or "(no page)"
        if kind == "source":
            return obj.get_title() or "(untitled)"
        if kind == "note":
            return " ".join((obj.get() or "").split())[:120] or "(empty)"
        if kind == "place":
            return obj.get_name().get_value() or obj.get_title() or "(unnamed)"
        if kind == "repository":
            return obj.get_name() or "(unnamed)"
    except Exception:
        return "(could not read it)"
    return ""


@mainthread.on_main_thread
def tree_totals() -> dict[str, int]:
    """How many of each kind the tree holds. ⭐ Every count is O(1).

    ⚠️ **``find_people`` requires a search term, so there was no way to ask how
    big the tree is at all** -- and *"did that import land?"* is not a question a
    search can answer.

    ⛔ **These totals INCLUDE private records, deliberately.** P2's arithmetic
    rule is about a listing: private people must be in neither the results nor
    the matched count, because the difference between them would reveal that
    somebody was withheld. **An aggregate over the whole tree reveals nobody** --
    and a total that excluded private records would leak by moving when one was
    marked. ``/health`` already reports the person count on the same reasoning.
    """
    if _DBSTATE is None:
        return {}
    database = _DBSTATE.db
    if database is None or not database.is_open():
        return {}
    return {
        "people": database.get_number_of_people(),
        "families": database.get_number_of_families(),
        "events": database.get_number_of_events(),
        "places": database.get_number_of_places(),
        "sources": database.get_number_of_sources(),
        "citations": database.get_number_of_citations(),
        "notes": database.get_number_of_notes(),
        "repositories": database.get_number_of_repositories(),
        "media": database.get_number_of_media(),
    }


CHANGED_COLLECTIONS = ("people", "families", "events", "places", "sources", "citations", "notes")
"""Which collections ``changed_since`` will walk.

⚠️ **Named COLLECTIONS rather than KINDS deliberately.** ``NOTE_KINDS`` and
``CITED_KINDS`` name things ``_by_gramps_id`` can look up, and a test pins them
against its branches. These are collection names -- *people*, not *person* -- so
that pin does not apply, and calling them kinds made the guard fail on correct
code. **Renaming removes the exception instead of adding one**, which is how the
next such list stays covered rather than carved out."""


@mainthread.on_main_thread
def changed_since(when: str, kind: str = "people") -> reads.Found:
    """Records of one kind whose ``change`` stamp is at or after ``when``.

    ⭐ **Use-derived:** every *"is this already entered?"* conclusion this month
    came from diffing a stale export by hand, because nothing could answer *what
    changed in this tree, and when*.

    ⚠️ **One collection per call, and that is a cost decision.** The tree holds
    17,822 walkable objects against 2,934 people. A call spanning every
    collection would be the most expensive read in the host, inside the GTK main
    thread, for a question usually asked about one kind at a time.

    ``when`` is an ISO date or date-time, and it is also the required search
    term -- so there is still no way to list everybody.
    """
    wanted = reads.require_term(when)
    asked = str(kind or "people")
    if asked not in CHANGED_COLLECTIONS:
        raise reads.UnknownKind(
            f"{asked!r} is not a collection this can walk. Use one of: "
            + ", ".join(CHANGED_COLLECTIONS)
        )
    cutoff = _as_epoch(wanted)
    if cutoff is None:
        raise reads.SearchTermRequired(
            f"{wanted!r} is not a date this can read. Use YYYY-MM-DD, or an ISO date-time."
        )
    if _DBSTATE is None:
        return reads.Found()
    database = _DBSTATE.db

    iterators = {
        "people": database.iter_people,
        "families": database.iter_families,
        "events": database.iter_events,
        "places": database.iter_places,
        "sources": database.iter_sources,
        "citations": database.iter_citations,
        "notes": database.iter_notes,
    }
    rows = []
    readable = 0
    unreadable = 0
    for obj in iterators[asked]():
        # ⛔ GATED FIRST. A private record must not reach the stamp read at all:
        # counting it as unreadable let it change the observable answer from an
        # empty 200 to a refusal, so its existence was detectable through control
        # flow -- private in the results and not in the counts, but leaking
        # through the shape of the response instead.
        visible = _public(obj)
        if visible is None:
            continue
        changed = _change_stamp(visible)
        if changed is None:
            unreadable += 1
            continue
        readable += 1
        if changed < cutoff:
            continue
        rows.append(
            (False, reads.Match(visible.get_gramps_id(), _changed_display(asked, visible, changed)))
        )

    # ⛔ If NOTHING could be read, say so instead of answering "nothing changed".
    #
    # ⚠️ This is the defect the first version shipped past. It wrapped the read in
    # ``except AttributeError: continue``, so using the wrong accessor skipped
    # every object and the route answered an empty result -- **the full walk's
    # cost and none of its answer.** *Nothing changed* is exactly the answer a
    # caller acts on, so a silent wrong one is worse than an error.
    # ⚠️ Keyed on whether any stamp was READABLE, not on whether any row matched.
    # "Nothing changed" is a real answer, and a partially readable collection
    # whose readable records are all older than the cutoff was being refused for
    # giving exactly the right one.
    if unreadable and not readable:
        raise reads.ReadRefused(
            f"none of the {unreadable} {asked} in this tree exposed a change stamp, "
            "so this cannot say what changed. Refusing rather than reporting none."
        )
    return reads.bound(rows)


def _change_stamp(obj: typing.Any) -> int | None:
    """When Gramps last changed this record, or ``None`` if it cannot be read.

    ⛔ **``None`` and zero are different answers.** A record with no stamp is not
    a record that never changed, and collapsing the two is how a walk reports
    *nothing changed* about a tree that changed this morning.
    """
    getter = getattr(obj, "get_change", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        # ⛔ ``is not None``, NOT truthiness. A stamp of 0 is a real stamp -- the
        # Unix epoch -- and this function's whole point is that zero and None are
        # different answers. Testing truthiness said the opposite of the
        # docstring directly above it, and a collection whose public records all
        # carried 0 would have produced a REFUSAL instead of an empty result.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    value = getattr(obj, "change", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def _iso_for_any_interpreter(raw: str) -> str:
    """An ISO string ``fromisoformat`` accepts on **3.10 as well as 3.12**.

    ⛔ **``fromisoformat``'s definition comes from the INTERPRETER, not from
    ISO 8601**, and this project's floor is 3.10 while its gates run on the
    developer's 3.12. **3.11 widened it to full ISO; 3.10 accepts only what
    ``isoformat()`` emits** -- no ``Z``, and a fractional second of exactly three
    or six digits.

    ⚠️ **Measured, not supposed:** ``2026-08-01T12:00:00.5`` parsed locally and
    returned ``None`` on CI's 3.10 legs, failing four jobs. That is this
    project's recorded failure shape -- *a check whose answer varies with where
    it runs, silently, because every test passes on the machine that wrote them.*

    So the input is normalised here rather than delegated: ``Z`` becomes an
    explicit offset, and a fractional second is padded or truncated to six
    digits. **The behaviour is then the interpreter's only where they agree.**
    """
    import re

    text = str(raw).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    def six_digits(match: re.Match[str]) -> str:
        digits = match.group(1)
        kept = (digits + "000000")[:6]

        # ⛔ **A discarded non-zero digit must not become no fraction at all.**
        #
        # ⚠️ ``.0000001`` truncated to six digits is ``.000000``, so an instant
        # strictly AFTER 12:00:00 normalised to exactly 12:00:00 -- and the
        # ``ceil`` in ``_as_epoch`` then had nothing to round up, so a record
        # changed AT 12:00:00 was reported for a cutoff after it. **The previous
        # fractional fix was right about the ceiling and wrong about what reaches
        # it**: truncating to a fixed width is an enumeration of precision, and
        # this is the input that falls outside it.
        #
        # ⭐ The smallest representable fraction is enough, because the only
        # consumer ceils: what has to survive is *there was a fraction*, not its
        # value. Six digits is what every supported interpreter agrees on, so the
        # width stays and the information that mattered is preserved inside it.
        if kept == "000000" and digits.strip("0"):
            kept = "000001"
        return "." + kept

    # ⛔ **Both decimal separators, normalised to the one the interpreters agree
    # on.** ISO 8601 permits a COMMA, and the interpreters disagree about it:
    # 3.11 and 3.12 accept it, the 3.10 floor rejects it. Matching only a period
    # left a comma fraction untouched, so it bypassed the discarded-digit
    # handling entirely -- measured on 3.12, ``12:00:00,0000001`` returned the
    # whole second and a record changed AT that second was reported for a cutoff
    # after it.
    #
    # ⭐ This is the third member of the set this function already handles, not a
    # new case: ``Z`` versus an explicit offset, fractional WIDTH, and now the
    # separator. **The rule is that every ISO spelling the interpreters disagree
    # about becomes the one spelling they agree on** -- which also removes the
    # 3.10-versus-3.11 divergence outright, because the interpreter never sees a
    # comma.
    return re.sub(r"[.,](\d+)", six_digits, text, count=1)


def _as_epoch(text: str) -> int | None:
    """An ISO date or date-time as a unix timestamp, or ``None``.

    ⛔ Local time, not UTC: Gramps writes ``change`` from ``time.time()``, and an
    owner asking *"since yesterday"* means his yesterday.
    """
    import datetime
    import math

    raw = str(text).strip().replace("/", "-")

    # ⛔ ``fromisoformat`` FIRST, because the tool advertises "an ISO date-time"
    # and three hand-written formats are not ISO.
    #
    # ⚠️ A caller passing ``2026-08-01T12:00:00Z``, an offset like ``+02:00``, or
    # fractional seconds was refused with a 400 -- **the documented input
    # rejected by the code that documents it.** The same shape as every other
    # enumeration in this project: a list of spellings standing in for a format.
    try:
        parsed = datetime.datetime.fromisoformat(_iso_for_any_interpreter(raw))
    except ValueError:
        parsed = None
    if parsed is not None:
        # ⭐ A naive input stays LOCAL, which is the promise above: Gramps writes
        # ``change`` from ``time.time()``, and an owner asking "since yesterday"
        # means his yesterday. An input carrying an offset is honoured as given.
        #
        # ⛔ CEIL, not int(). Gramps stamps are whole seconds, so truncating a
        # fractional cutoff moves it BACKWARDS to the start of its second -- and
        # a record changed at 12:00:00 was then reported for a cutoff of
        # 12:00:00.5, which is not "at or after" the requested instant. Ceil and
        # int agree on every whole-second input, so the ordinary case is
        # unchanged.
        return math.ceil(parsed.timestamp())

    for shape in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.datetime.strptime(raw, shape).timestamp())
        except ValueError:
            continue
    return None


def _changed_display(kind: str, obj: typing.Any, changed: int) -> str:
    """What changed and when, in a form the owner reads rather than decodes."""
    import datetime

    stamp = datetime.datetime.fromtimestamp(changed).strftime("%Y-%m-%d %H:%M")
    database = _DBSTATE.db if _DBSTATE is not None else None
    if kind == "people":
        return f"{_person_display(obj, database)}  [changed {stamp}]"
    if kind == "families":
        return f"{_family_display(database, obj)}  [changed {stamp}]"
    if kind == "events":
        return f"{_event_display(obj)}  [changed {stamp}]"
    # ⛔ An explicit map, not ``kind[:-1]``. Chopping the last letter turns
    # "families" into "familie", which no renderer answers to -- so every family
    # came back as a bare timestamp with nothing to recognise it by. **The same
    # naive singulariser had already been fixed once in ``document.py``**, and it
    # was still here: a spelling rule standing in for a vocabulary.
    singular = {
        "places": "place",
        "sources": "source",
        "citations": "citation",
        "notes": "note",
    }.get(kind, kind)
    return f"{_orphan_display(singular, obj)}  [changed {stamp}]"


def _event_display(event: typing.Any) -> str:
    """An event as the owner recognises it: what it was, and when."""
    try:
        shown = str(event.get_type() or "Event")
        date = event.get_date_object()
        if date is not None and not date.is_empty():
            shown += f" {date.get_year() or date}"
        if event.get_description():
            shown += f" -- {event.get_description()}"
        return shown
    except Exception:
        return "(could not read the event)"
