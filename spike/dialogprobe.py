"""THROWAWAY PROBE. One question, self-terminating, blessed copy only.

⚠️ **The question.** F1 measured ``GLib.idle_add`` firing 0.0002 s later *under*
an already-open modal dialog. **Nobody has shown a dialog FROM an idle_add
callback**, and nobody has shown that a database write lands after the user
answers it. The whole write design rests on that, so it is proved before
anything is built on it.

**The shape under test is exactly the real one:**

    worker thread  ->  GLib.idle_add(callback)  ->  callback shows a MODAL dialog
                   ->  dialog.run() spins a nested main loop
                   ->  the answer comes back
                   ->  DbTxn writes one note
                   ->  commit, and the tree is re-read to prove it landed

**Self-terminating.** A ``GLib.timeout_add`` answers the dialog for us after a
few seconds, so no human is needed and nothing waits forever. A physical click
and ``dialog.response()`` reach ``dialog.run()``'s return by the same path, so
what is proved is the mechanism rather than the mouse.

⛔ **Blessed copy only**, checked on the open tree's own save path. ⛔ Nothing is
deleted; one note is added, and it says in its own text that it is a probe
artifact.
"""

import os
import threading
import time
import traceback

DIRECTORY_NAME = "gramps-live-api"
REPORT = "dialogprobe.txt"
SENTINEL = ".gramps-live-api-copy"
NAME_FILE = "name.txt"

ANSWER_AFTER_SECONDS = 4

_DONE = {"ran": False}


def _report_path():
    base = os.environ.get("APPDATA", "")
    return os.path.join(base, DIRECTORY_NAME, REPORT)


def _say(line):
    try:
        path = _report_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%H:%M:%S") + " " + line + "\n")
    except Exception:
        pass


def _blessed(tree_dir):
    if not tree_dir:
        return False
    return os.path.exists(os.path.join(tree_dir, NAME_FILE)) and os.path.exists(
        os.path.join(tree_dir, SENTINEL)
    )


def load_on_reg(dbstate, uistate=None, plugin=None, *rest):
    """Arm the experiment. It runs once, when a blessed tree is open."""
    try:
        _say("=" * 70)
        _say("PROBE ARMED -- waiting for a blessed tree to open")
        dbstate.connect("database-changed", lambda *ignored: _maybe_run(dbstate, uistate))
    except Exception:
        _say("arming failed: " + traceback.format_exc())


def _maybe_run(dbstate, uistate):
    if _DONE["ran"]:
        return
    try:
        database = dbstate.db
        if database is None or not database.is_open():
            _say("database-changed: no tree open")
            return
        tree_dir = database.get_save_path()
        if not _blessed(tree_dir):
            _say("REFUSED -- the open tree is not the blessed copy. Nothing was touched.")
            return
        _DONE["ran"] = True
        _say("blessed tree open. starting the worker thread.")
        _say("main thread is %r" % threading.current_thread().name)
        threading.Thread(target=_worker, args=(dbstate,), daemon=True).start()
    except Exception:
        _say("maybe_run failed: " + traceback.format_exc())


def _worker(dbstate):
    """Stands in for the HTTP thread. Schedules and does NOT wait."""
    from gi.repository import GLib

    _say("worker thread is %r -- scheduling the dialog via GLib.idle_add" % threading.current_thread().name)
    scheduled = time.perf_counter()
    GLib.idle_add(_show_and_write, dbstate, scheduled)
    _say("worker: idle_add returned; the worker is NOT waiting for the answer")


def _show_and_write(dbstate, scheduled):
    """Runs on the main thread. Shows a modal dialog, writes on OK.

    ⚠️ **This is the whole question.** ``dialog.run()`` spins its own nested main
    loop from inside an idle callback. If GTK refuses that, or if the write after
    it cannot reach the database, the design is wrong and this says so.
    """
    from gi.repository import GLib, Gtk

    try:
        crossed = time.perf_counter() - scheduled
        _say("callback running on %r, %.4f s after scheduling" % (threading.current_thread().name, crossed))
        _say("main loop depth before the dialog: %d" % Gtk.main_level())

        dialog = Gtk.Dialog(title="gramps-live-api probe", modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        dialog.set_default_size(460, 160)
        label = Gtk.Label(
            label="\nThis dialog was opened from inside a GLib.idle_add callback,\n"
            "scheduled from a worker thread.\n\n"
            "It answers itself in %d seconds. Nothing is expected of you.\n" % ANSWER_AFTER_SECONDS
        )
        dialog.get_content_area().pack_start(label, True, True, 8)
        dialog.show_all()

        def answer_it():
            _say("timeout firing: answering the dialog OK on our own behalf")
            dialog.response(Gtk.ResponseType.OK)
            return False

        GLib.timeout_add_seconds(ANSWER_AFTER_SECONDS, answer_it)

        _say("about to call dialog.run() -- a NESTED main loop, from inside idle_add")
        before = time.perf_counter()
        answer = dialog.run()
        held = time.perf_counter() - before
        _say("dialog.run() RETURNED %r after %.3f s -- the nested loop worked" % (answer, held))
        _say("main loop depth inside the dialog was: %d" % (Gtk.main_level(),))
        dialog.destroy()

        if answer != Gtk.ResponseType.OK:
            _say("answer was not OK -- writing nothing, as designed")
            return False

        _write_one_note(dbstate)
    except Exception:
        _say("THE CALLBACK RAISED:\n" + traceback.format_exc())
    return False


def _write_one_note(dbstate):
    """One note, one DbTxn, then read it back."""
    from gramps.gen.db import DbTxn
    from gramps.gen.lib import Note, NoteType

    database = dbstate.db
    _say("writing: opening DbTxn on the main thread")
    try:
        with DbTxn("gramps-live-api dialog probe", database) as trans:
            note = Note()
            note.set(
                "GRAMPS-LIVE-API PROBE ARTIFACT -- SAFE TO DELETE. Written by the "
                "throwaway dialog probe to prove that a write lands after a modal "
                "dialog shown from inside a GLib.idle_add callback."
            )
            note.set_type(NoteType(NoteType.RESEARCH))
            handle = database.add_note(note, trans)
        _say("DbTxn committed. note handle=%s" % handle)

        # Read it back through the database rather than trusting the write.
        back = database.get_note_from_handle(handle)
        _say(
            "READ BACK: gramps_id=%s  text_ok=%s"
            % (back.get_gramps_id(), back.get().startswith("GRAMPS-LIVE-API PROBE"))
        )
        _say("total notes now: %d" % database.get_number_of_notes())
        _say("*** THE WRITE LANDED. The design holds. ***")
    except Exception:
        _say("THE WRITE FAILED:\n" + traceback.format_exc())
