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
    view.get_buffer().set_text(text)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
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
    from gramps.gen.lib import EventRoleType

    key = (name or "PRIMARY").strip().upper().replace(" ", "_")
    if hasattr(EventRoleType, key):
        value = getattr(EventRoleType, key)
        if isinstance(value, int):
            return EventRoleType(value)
    return EventRoleType(EventRoleType.PRIMARY)


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
    counts = {"people": 0, "events": 0, "places": 0, "families": 0, "citations": 0, "notes": 0}

    genders = {"male": Person.MALE, "female": Person.FEMALE}
    source_spec = graph.get("source") or None
    title = (source_spec or {}).get("title") or "Document"

    with DbTxn(("Document: " + str(title))[:80], database) as trans:
        # --- the source ------------------------------------------------------
        source_handle = None
        if source_spec:
            source = Source()
            source.set_title(str(source_spec.get("title") or "Untitled document"))
            if source_spec.get("author"):
                source.set_author(str(source_spec["author"]))
            if source_spec.get("pubinfo"):
                source.set_publication_info(str(source_spec["pubinfo"]))
            source_handle = database.add_source(source, trans)
            if source_spec.get("id"):
                handles[source_spec["id"]] = source_handle
                kinds[source_spec["id"]] = "source"

        # --- places ----------------------------------------------------------
        for spec in graph.get("places") or []:
            place = Place()
            place.set_title(str(spec.get("title") or ""))
            place_name = PlaceName()
            place_name.set_value(str(spec.get("title") or ""))
            place.set_name(place_name)
            handle = database.add_place(place, trans)
            handles[spec["id"]] = handle
            kinds[spec["id"]] = "place"
            counts["places"] += 1

        # --- people ----------------------------------------------------------
        for spec in graph.get("people") or []:
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
            handles[spec["id"]] = handle
            kinds[spec["id"]] = "person"
            counts["people"] += 1

        # --- events, and the people they happened to -------------------------
        for spec in graph.get("events") or []:
            event = Event()
            event.set_type(_event_type(spec.get("type")))
            parsed = _gramps_date(spec.get("date"))
            if parsed is not None:
                event.set_date_object(parsed)
            elif spec.get("date"):
                event.set_description("date as written: " + str(spec["date"]))
            place_local = spec.get("place")
            if place_local and place_local in handles:
                event.set_place_handle(handles[place_local])
            event_handle = database.add_event(event, trans)
            handles[spec["id"]] = event_handle
            kinds[spec["id"]] = "event"
            counts["events"] += 1

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
            parents = [handles[p] for p in (spec.get("parents") or []) if p in handles]
            children = [handles[c] for c in (spec.get("children") or []) if c in handles]
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
            handles[spec["id"]] = family_handle
            kinds[spec["id"]] = "family"
            counts["families"] += 1

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

        # --- citations, attached to whatever they support --------------------
        for spec in graph.get("citations") or []:
            target_source = handles.get(spec.get("source")) or source_handle
            if not target_source:
                continue
            citation = Citation()
            citation.set_reference_handle(target_source)
            citation.set_page(str(spec.get("page") or ""))
            citation_handle = database.add_citation(citation, trans)
            handles[spec["id"]] = citation_handle
            kinds[spec["id"]] = "citation"
            counts["citations"] += 1
            for local in spec.get("attach_to") or []:
                _attach(database, trans, handles, kinds, local, "citation", citation_handle)

        # --- notes -----------------------------------------------------------
        for spec in graph.get("notes") or []:
            note = Note()
            note.set(str(spec.get("text") or ""))
            note.set_type(NoteType(NoteType.TRANSCRIPT))
            note_handle = database.add_note(note, trans)
            counts["notes"] += 1
            for local in spec.get("attach_to") or []:
                _attach(database, trans, handles, kinds, local, "note", note_handle)

    return ", ".join(f"{value} {label}" for label, value in counts.items() if value) or "nothing"


_COMMIT = {
    "person": ("get_person_from_handle", "commit_person"),
    "event": ("get_event_from_handle", "commit_event"),
    "place": ("get_place_from_handle", "commit_place"),
    "family": ("get_family_from_handle", "commit_family"),
    "source": ("get_source_from_handle", "commit_source"),
    "citation": ("get_citation_from_handle", "commit_citation"),
}


def _attach(database, trans, handles, kinds, local, what, handle):
    """Put a citation or a note onto whatever the graph pointed at.

    ⚠️ **Fetch, modify, commit.** Gramps derives the backlink from the reference
    when the OWNING object is committed -- the same reason the apply tool commits
    the person to attach a note rather than committing the note.
    """
    target = handles.get(local)
    kind = kinds.get(local)
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
