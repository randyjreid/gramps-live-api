"""The Gramps half of the document write: the dialog, and the objects.

⚠️ **This file exists here rather than in ``src/`` because it is the only part
that must name Gramps classes.** The host package never imports ``gramps`` or
``gi`` -- that is what lets it run under CI -- so the graph is validated and
rendered there, and the Gramps API calls happen here, exactly the way
``schedule`` and ``dbstate`` are already injected rather than imported.

⚠️ **Everything in this module runs on the GTK main thread.** It is reached from
a ``GLib.idle_add`` callback, never from the HTTP thread.

⭐ **Measured before it was built on** (``spike/dialogprobe.py``, 2026-08-21): a
modal dialog shown from inside an ``idle_add`` callback spins its own nested main
loop, ``dialog.run()`` returns the answer, and a ``DbTxn`` opened afterwards
commits and reads back. The whole design rests on that and it was proved rather
than assumed.

⛔ **Local ids resolve to handles INSIDE the transaction.** Nothing that
constructs a graph has ever seen the tree, so ``p1`` is the only name it can use
for a person it is also citing and marrying.
"""

import os
import traceback

SENTINEL = ".gramps-live-api-copy"
NAME_FILE = "name.txt"


def blessing(tree_dir):
    """(blessed, message) for a tree directory. The message names the tree.

    Inlined rather than imported from ``gramps_live_api.core.apply`` for the
    reason the spike inlined it: the plugin must not depend on the package
    resolving on Gramps' ``sys.path`` for a two-line check.
    """
    if not tree_dir:
        return False, "The open database reports no save path."
    if not os.path.exists(os.path.join(tree_dir, NAME_FILE)):
        return False, tree_dir + " is not a Gramps family tree directory."
    if not os.path.exists(os.path.join(tree_dir, SENTINEL)):
        return False, (
            tree_dir
            + " has not been blessed for writing. Create a file named "
            + SENTINEL
            + " inside that directory if this is a copy you are willing to have"
            " written to. Nothing was touched."
        )
    return True, tree_dir


def confirm(uistate, text):
    """Show the preview and return True only for an explicit OK.

    ⭐ **The text is rendered from the stored record**, upstream of here. This
    function is deliberately incapable of showing anything else: it takes the
    finished string and has no access to whatever an agent sent at approval time.
    """
    from gi.repository import Gtk

    parent = getattr(uistate, "window", None)
    dialog = Gtk.Dialog(title="gramps-live-api -- confirm before writing", transient_for=parent)
    dialog.set_modal(True)
    dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Write it", Gtk.ResponseType.OK)
    dialog.set_default_size(780, 640)

    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_left_margin(10)
    view.set_right_margin(10)
    view.set_monospace(True)
    # ⛔ WRAP, never scroll sideways. A line running off the right edge behind a
    # horizontal scrollbar is content approved unseen -- the slice-1 elision
    # defect in a new costume. WORD_CHAR also breaks a single unbroken 400
    # character token rather than letting it push the line off the edge.
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_buffer().set_text(text)

    scroller = Gtk.ScrolledWindow()
    # ⛔ NEVER horizontal. The renderer wraps and so does the view; a horizontal
    # policy of AUTOMATIC would silently re-enable the thing both of them exist
    # to prevent.
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(view)
    dialog.get_content_area().pack_start(scroller, True, True, 0)
    dialog.show_all()

    answer = dialog.run()
    dialog.destroy()
    return answer == Gtk.ResponseType.OK


def tell(uistate, title, body):
    """Say what happened, or what refused to happen."""
    from gi.repository import Gtk

    parent = getattr(uistate, "window", None)
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(body)
    dialog.run()
    dialog.destroy()


def _gramps_date(text):
    """Gramps' own parser, or nothing.

    ⛔ **Not a date parser.** Gramps ships one. Where it cannot read what the
    document said, the text is kept on the event instead of a date being guessed.
    """
    if not text:
        return None
    try:
        from gramps.gen.datehandler import parser

        parsed = parser.parse(str(text))
        if parsed is not None and not parsed.is_empty():
            return parsed
    except Exception:
        return None
    return None


def _event_type(name):
    """⚠️ ``getattr`` on the attribute NAME, never a pinned integer.

    Gramps' numbering is an implementation detail; the apply tool uses the same
    discipline for ``NoteType``. Anything unrecognised becomes a CUSTOM type
    carrying the document's own word.
    """
    from gramps.gen.lib import EventType

    key = (name or "").strip().upper().replace(" ", "_")
    if key and hasattr(EventType, key):
        value = getattr(EventType, key)
        if isinstance(value, int):
            return EventType(value)
    return EventType((EventType.CUSTOM, (name or "Event").strip()))


def _event_role(name):
    """The role to write. ⛔ **What the dialog showed is what gets written.**

    ⚠️ **This silently fell back to PRIMARY**, and rendering the role in the
    dialog turned that from invisible into a lie: the owner read *as Godparent*
    and an ``EventRef`` with role PRIMARY was written. A preview that does not
    match the write is the defect the preview exists to prevent, and making the
    role visible is what exposed it.

    An unrecognised role now becomes a **CUSTOM** role carrying the document's
    own word -- the same discipline ``_event_type`` uses -- so the string the
    owner approved is the string Gramps stores.
    """
    from gramps.gen.lib import EventRoleType

    wanted = (name or "").strip()
    if not wanted:
        return EventRoleType(EventRoleType.PRIMARY)
    key = wanted.upper().replace(" ", "_")
    if hasattr(EventRoleType, key):
        value = getattr(EventRoleType, key)
        if isinstance(value, int):
            return EventRoleType(value)
    return EventRoleType((EventRoleType.CUSTOM, wanted))


_BY_GRAMPS_ID = {
    "person": "get_person_from_gramps_id",
    "place": "get_place_from_gramps_id",
    "source": "get_source_from_gramps_id",
    "family": "get_family_from_gramps_id",
    # ⛔ Events are attachable. Their handles are invisible in the UI, which is
    # why they were excluded -- but a Gramps ID is visible and ``list_events``
    # returns one, so the exclusion was enforcing a premise that had expired.
    "event": "get_event_from_gramps_id",
}


def _existing(database, kind, spec):
    """The handle a node's ``gramps_id`` names, or ``None`` if it has none.

    ⛔ **Raises if an id was supplied and does not resolve.** Falling back to
    creating would produce exactly the duplicate the id was there to prevent,
    and it would do it silently. The route resolves every id before the dialog
    opens, so reaching this raise means the tree changed underneath -- rare,
    and still not a reason to guess.
    """
    gramps_id = spec.get("gramps_id")
    if not gramps_id:
        return None
    getter = _BY_GRAMPS_ID.get(kind)
    obj = getattr(database, getter)(str(gramps_id)) if getter else None
    if obj is None:
        raise ValueError(f"the graph names {kind} {gramps_id!r}, which is not in this tree")
    return obj.get_handle()


def _unique(handles):
    """The same handles, first occurrence order kept, duplicates dropped.

    Order matters and a set does not keep it. Children are written in the
    order the document listed them, which is usually the order they were
    recorded on the page.
    """
    seen = set()
    out = []
    for handle in handles:
        if handle in seen:
            continue
        seen.add(handle)
        out.append(handle)
    return out


def write(dbstate, graph):
    """Write the whole graph in ONE transaction. Returns a one-line summary.

    Order is forced by the references: everything that can be pointed AT is
    created first, then the pointers are attached. A citation cannot be put on a
    person who does not exist yet, and a family cannot hold a handle that has not
    been minted.
    """
    from gramps.gen.db import DbTxn
    from gramps.gen.lib import (
        ChildRef,
        Citation,
        Event,
        EventRef,
        Family,
        Name,
        Note,
        NoteType,
        Person,
        Place,
        PlaceName,
        Source,
        Surname,
    )

    database = dbstate.db
    handles = {}
    kinds = {}
    # ⭐ What was created, by Gramps ID -- which is what somebody types into
    # Gramps to find it again, and therefore what a journal record is for.
    created = {
        k: [] for k in ("people", "events", "places", "families", "citations", "notes", "sources")
    }
    attached = {k: [] for k in ("people", "places", "sources", "families", "events")}
    # ⛔ Family event attachments are DEFERRED. The events loop runs before
    # families exist, so the handle to attach to is not minted yet -- the same
    # reason everything pointable is created before any pointer is written.
    pending_family_events = []

    def note_created(kind, handle_, getter):
        try:
            created[kind].append(getattr(database, getter)(handle_).get_gramps_id())
        except Exception:
            created[kind].append(handle_)

    genders = {"male": Person.MALE, "female": Person.FEMALE}
    source_spec = graph.get("source") or None
    title = (source_spec or {}).get("title") or "Document"

    with DbTxn(("Document: " + str(title))[:80], database) as trans:
        # --- the source ------------------------------------------------------
        source_handle = None
        if source_spec:
            source_handle = _existing(database, "source", source_spec)
        if source_spec and source_handle is None:
            source = Source()
            source.set_title(str(source_spec.get("title") or "Untitled document"))
            if source_spec.get("author"):
                source.set_author(str(source_spec["author"]))
            if source_spec.get("pubinfo"):
                source.set_publication_info(str(source_spec["pubinfo"]))
            source_handle = database.add_source(source, trans)
            note_created("sources", source_handle, "get_source_from_handle")
        elif source_spec:
            attached["sources"].append(str(source_spec.get("gramps_id")))
        if source_spec and source_spec.get("id"):
            handles[source_spec["id"]] = source_handle
            kinds[source_spec["id"]] = "source"

        # --- places ----------------------------------------------------------
        for spec in graph.get("places") or []:
            existing = _existing(database, "place", spec)
            if existing is not None:
                handles[spec["id"]] = existing
                kinds[spec["id"]] = "place"
                attached["places"].append(str(spec.get("gramps_id")))
                continue
            place = Place()
            place.set_title(str(spec.get("title") or ""))
            place_name = PlaceName()
            place_name.set_value(str(spec.get("title") or ""))
            place.set_name(place_name)
            handle = database.add_place(place, trans)
            note_created("places", handle, "get_place_from_handle")
            handles[spec["id"]] = handle
            kinds[spec["id"]] = "place"

        # --- people ----------------------------------------------------------
        for spec in graph.get("people") or []:
            existing = _existing(database, "person", spec)
            if existing is not None:
                # ⛔ Attached to, never altered. The graph's given/surname/gender
                # are deliberately NOT applied -- see IGNORED_WHEN_ATTACHING.
                handles[spec["id"]] = existing
                kinds[spec["id"]] = "person"
                attached["people"].append(str(spec.get("gramps_id")))
                continue
            person = Person()
            name = Name()
            if spec.get("given"):
                name.set_first_name(str(spec["given"]))
            if spec.get("surname"):
                surname = Surname()
                surname.set_surname(str(spec["surname"]))
                name.add_surname(surname)
            person.set_primary_name(name)
            person.set_gender(genders.get(str(spec.get("gender") or "").lower(), Person.UNKNOWN))
            handle = database.add_person(person, trans)
            note_created("people", handle, "get_person_from_handle")
            handles[spec["id"]] = handle
            kinds[spec["id"]] = "person"

        # --- events, and the people they happened to -------------------------
        for spec in graph.get("events") or []:
            existing = _existing(database, "event", spec)
            if existing is not None:
                # ⛔ **Attached to, never altered.** The graph's type, date, place,
                # description and role are deliberately NOT applied -- see
                # ``IGNORED_WHEN_ATTACHING``, and the preview names them as
                # dropped so the owner approves the write that actually happens.
                #
                # ⚠️ No ``add_event`` and no ``commit_event`` on this path: an
                # existing event is a record the owner asked to attach TO, and
                # editing it is the one thing attaching is defined not to do.
                handles[spec["id"]] = existing
                kinds[spec["id"]] = "event"
                attached["events"].append(str(spec.get("gramps_id")))
                continue
            event = Event()
            event.set_type(_event_type(spec.get("type")))
            parsed = _gramps_date(spec.get("date"))
            if parsed is not None:
                event.set_date_object(parsed)
            # ⛔ **The description, and the unparsed-date fallback, share one
            # field.** Gramps' Event has one description, and this file already
            # used it to preserve a date it could not parse. Writing both would
            # have had the later call silently discard the earlier -- so they are
            # JOINED, and the owner sees in the preview whichever parts exist.
            described = [str(spec["description"]).strip()] if spec.get("description") else []
            if parsed is None and spec.get("date"):
                described.append("date as written: " + str(spec["date"]))
            if described:
                event.set_description("; ".join(described))
            place_local = spec.get("place")
            if place_local and place_local in handles:
                event.set_place_handle(handles[place_local])
            event_handle = database.add_event(event, trans)
            note_created("events", event_handle, "get_event_from_handle")
            handles[spec["id"]] = event_handle
            kinds[spec["id"]] = "event"

            # ⛔ A family event cannot be attached HERE. Families are created in
            # the loop below, so the handle does not exist yet -- the same reason
            # this file creates everything pointable before attaching pointers.
            # The intent is recorded and honoured in a third pass.
            if spec.get("family"):
                pending_family_events.append((event_handle, spec["family"]))

            role = _event_role(spec.get("role"))
            for person_local in spec.get("people") or []:
                person_handle = handles.get(person_local)
                if not person_handle:
                    continue
                ref = EventRef()
                ref.ref = event_handle
                ref.set_role(role)
                person = database.get_person_from_handle(person_handle)
                kind = event.get_type()
                # Birth and death are not ordinary event references in Gramps --
                # a person has one of each and the views read those slots.
                from gramps.gen.lib import EventType

                if kind == EventType.BIRTH and person.get_birth_ref() is None:
                    person.set_birth_ref(ref)
                elif kind == EventType.DEATH and person.get_death_ref() is None:
                    person.set_death_ref(ref)
                else:
                    person.add_event_ref(ref)
                database.commit_person(person, trans)

        # --- families --------------------------------------------------------
        for spec in graph.get("families") or []:
            parents = _unique([handles[p] for p in (spec.get("parents") or []) if p in handles])
            # ⛔ De-duplicated HERE, once, so both branches below get it. A graph
            # may name the same child twice -- ``children: ["p1", "p1"]`` is a
            # valid proposal, and two local ids can resolve to one handle -- and
            # every loop below appends per entry. Left alone that writes two
            # ChildRefs and two parent-family handles for one child, which is a
            # malformed record Gramps' own Check and Repair has to clean up.
            children = _unique([handles[c] for c in (spec.get("children") or []) if c in handles])

            # ⭐ An EXISTING family is added to, never rebuilt. Its recorded
            # parents are left exactly as they are -- nothing already in the tree
            # is modified -- and only children the graph names that it does not
            # already hold are appended.
            existing = _existing(database, "family", spec)
            if existing is not None:
                handles[spec["id"]] = existing
                kinds[spec["id"]] = "family"
                attached["families"].append(str(spec.get("gramps_id")))
                family = database.get_family_from_handle(existing)
                known = {ref.ref for ref in family.get_child_ref_list()}
                added = 0
                for child in children:
                    if child in known:
                        continue
                    child_ref = ChildRef()
                    child_ref.ref = child
                    family.add_child_ref(child_ref)
                    added += 1
                if added:
                    database.commit_family(family, trans)
                    for child in children:
                        if child in known:
                            continue
                        person = database.get_person_from_handle(child)
                        person.add_parent_family_handle(existing)
                        database.commit_person(person, trans)
                continue

            if not parents and not children:
                continue
            family = Family()
            # Whoever is named first and is male becomes the father; Gramps has
            # two slots and the graph has a list, so the mapping is stated rather
            # than guessed at read time.
            father = mother = None
            for handle in parents:
                person = database.get_person_from_handle(handle)
                if person.get_gender() == Person.MALE and father is None:
                    father = handle
                elif mother is None:
                    mother = handle
                elif father is None:
                    father = handle
            if father:
                family.set_father_handle(father)
            if mother:
                family.set_mother_handle(mother)
            for child in children:
                child_ref = ChildRef()
                child_ref.ref = child
                family.add_child_ref(child_ref)
            family_handle = database.add_family(family, trans)
            note_created("families", family_handle, "get_family_from_handle")
            handles[spec["id"]] = family_handle
            kinds[spec["id"]] = "family"

            # Both sides of every link are written explicitly. A family holding
            # handles that do not point back fails Gramps' own Check and Repair.
            for handle in (father, mother):
                if handle:
                    person = database.get_person_from_handle(handle)
                    person.add_family_handle(family_handle)
                    database.commit_person(person, trans)
            for child in children:
                person = database.get_person_from_handle(child)
                person.add_parent_family_handle(family_handle)
                database.commit_person(person, trans)

        # --- family events, now that the families exist ----------------------
        #
        # ⭐ This is what closes the loop `list_family_events` opened. Before it,
        # a marriage could only be written onto the two spouses -- so the lookup
        # reported no marriage, one was proposed, it landed on the people, and
        # the lookup still reported none. Forever.
        for event_handle, family_local in pending_family_events:
            family_handle = handles.get(family_local)
            if not family_handle:
                continue
            from gramps.gen.lib import EventRoleType

            ref = EventRef()
            ref.ref = event_handle
            # ⛔ FAMILY, ALWAYS -- the supplied role governs PERSON refs only.
            #
            # ⚠️ Honouring it here made two inputs indistinguishable in the
            # dialog and different in the tree: ``_event_line`` suppresses an
            # explicit "Primary", so role:"Primary" and no role at all render
            # identically while writing a PRIMARY ref and a FAMILY ref
            # respectively. **The approved text and the write disagreeing, on a
            # difference the owner could not have seen.**
            ref.set_role(EventRoleType(EventRoleType.FAMILY))
            family = database.get_family_from_handle(family_handle)
            family.add_event_ref(ref)
            database.commit_family(family, trans)

        # --- citations, attached to whatever they support --------------------
        for spec in graph.get("citations") or []:
            target_source = handles.get(spec.get("source")) or source_handle
            if not target_source:
                continue
            citation = Citation()
            citation.set_reference_handle(target_source)
            citation.set_page(str(spec.get("page") or ""))
            citation_handle = database.add_citation(citation, trans)
            note_created("citations", citation_handle, "get_citation_from_handle")
            handles[spec["id"]] = citation_handle
            kinds[spec["id"]] = "citation"
            for target, kind in _attachment_targets(handles, kinds, spec.get("attach_to")):
                _attach(database, trans, target, kind, "citation", citation_handle)

        # --- notes -----------------------------------------------------------
        for spec in graph.get("notes") or []:
            note = Note()
            note.set(str(spec.get("text") or ""))
            note.set_type(NoteType(NoteType.TRANSCRIPT))
            note_handle = database.add_note(note, trans)
            note_created("notes", note_handle, "get_note_from_handle")
            for target, kind in _attachment_targets(handles, kinds, spec.get("attach_to")):
                _attach(database, trans, target, kind, "note", note_handle)

    # ⛔ No summary is computed here, and that is not an omission.
    #
    # ⚠️ Summarising meant importing the package, and a plugin file that reaches
    # into it IS host code by the rule in ``tests/fixtures/host_sources.py`` --
    # at which point this file may not touch ``.db`` at all, which is its entire
    # job. The boundary test caught it immediately.
    #
    # ⚠️ **And that rule is a SUBSTRING SEARCH of the file's text**, so the first
    # wording of this very comment -- which named the package in full --
    # classified this file as host code and failed the boundary test on a
    # comment. Named obliquely here on purpose.
    #
    # So the caller summarises. It already imports ``document``, it is already
    # host code, and it never touches the database.
    return {"created": created, "attached": attached}


_COMMIT = {
    "person": ("get_person_from_handle", "commit_person"),
    "event": ("get_event_from_handle", "commit_event"),
    "place": ("get_place_from_handle", "commit_place"),
    "family": ("get_family_from_handle", "commit_family"),
    "source": ("get_source_from_handle", "commit_source"),
    "citation": ("get_citation_from_handle", "commit_citation"),
}


def _attachment_targets(handles, kinds, locals_):
    """The records some ``attach_to`` list points at, **deduplicated by HANDLE.**

    ⛔ **By the resolved handle, not by the local id.** ``parse`` explicitly
    permits two local ids to carry the same ``gramps_id``, so ``e1`` and ``e2``
    can name one record -- and a citation listing both then had ``_attach`` run
    twice on that record and ``add_citation`` the same handle twice. A supported
    input, not an edge case: every citation, note and future attachment type
    reaches this.

    ⭐ **Through ``_unique``, which is this file's ONE deduplication.** The
    family-child path already deduplicates resolved handles that way; the attach
    path simply was not going through it. A second implementation here is the
    thing being prevented, not a shortcut around it.

    ⛔ **``parse`` now REFUSES two local ids naming one record, so this dedup is
    currently unreachable for that input. It stays anyway -- do not "simplify" it
    away.** Its justification is no longer *"aliases happen"* but *"if the parse
    rule is ever relaxed, this is what stops the relaxation from silently
    attaching twice."* A guard left without its reason stated reads as dead code
    to the next reader, which is how a defence gets deleted one change before the
    rule it depended on moves.

    ⚠️ It is still reachable by the *other* duplicate: one local id listed twice
    in a single ``attach_to``. ``parse`` permits that -- it is one node, named
    twice -- and this is what collapses it.

    ⭐ ``tests/unit/test_attachable_bound.py`` asserts the belt and the braces
    agree, so the two cannot drift apart unnoticed.

    ⚠️ ``_unique`` keeps first-occurrence order, which matters for the same
    reason it does for children: the document's order is usually the page's.
    """
    resolved = [(handles[local], kinds.get(local)) for local in (locals_ or []) if local in handles]
    kind_of = dict(resolved)
    return [(target, kind_of[target]) for target in _unique([target for target, _ in resolved])]


def _attach(database, trans, target, kind, what, handle):
    """Put a citation or a note onto whatever the graph pointed at.

    ⚠️ **Fetch, modify, commit.** Gramps derives the backlink from the reference
    when the OWNING object is committed -- the same reason the apply tool commits
    the person to attach a note rather than committing the note.

    ⛔ Takes an already-RESOLVED target, so the caller must have gone through
    ``_attachment_targets`` -- which is where the deduplication lives. Resolving
    here per local id is what allowed one record to be attached to twice.
    """
    if not target or kind not in _COMMIT:
        return
    getter, committer = _COMMIT[kind]
    try:
        obj = getattr(database, getter)(target)
        if what == "citation":
            obj.add_citation(handle)
        else:
            obj.add_note(handle)
        getattr(database, committer)(obj, trans)
    except Exception:
        # One unattachable reference must not cost the whole document. The
        # objects are already written; what is lost is one edge.
        traceback.print_exc()
