"""The shim Gramps loads: it adapts a Gramps database to ``core.apply.Tree``.

⚠️ **The only file in this project that imports ``gramps``**, and it is
deliberately thin. Every decision -- what may be written, in what order, what is
recorded before the transaction opens -- lives in ``gramps_live_api.core.apply``,
which imports no Gramps and is therefore covered by ordinary unit tests. What is
here is the translation, and translation is the part that cannot be covered
anywhere but on a machine with Gramps.

**Nothing reaches this through ``-p``.** Gramps parses that options string by
splitting on commas and then on equals signs, with no quoting, so a note
carrying either would silently discard the whole string. Everything arrives
through the environment, which has no such parsing.

⚠️ **EVERY failure is caught and reported as a result marker.**
``gramps/gui/plug/tool.py`` wraps the tool invocation in a bare ``except`` that
logs and returns, so an exception escaping here becomes a process that exits
normally having done nothing and said nothing. Catching it ourselves is what
turns "the run failed silently" into "this tree has not been blessed for
writing", which is a sentence the owner can act on.
"""

import json
import os
import sys
import traceback

from gramps.gen.db import DbTxn
from gramps.gen.lib import Note, NoteType, StyledText
from gramps.gui.plug import tool
from gramps.version import VERSION


def _put_the_package_on_the_path():
    """Make ``gramps_live_api`` importable inside Gramps' frozen interpreter.

    Gramps runs on its own Python with its own ``sys.path``, and nothing this
    project installs is on it. The front end passes the directory; prepending it
    here is why the tool works straight from a checkout with no install step.
    """
    source = os.environ.get("GRAMPS_LIVE_API_SRC")
    if source and source not in sys.path:
        sys.path.insert(0, source)


class ApplyTool(tool.Tool):
    """One operation, in or out, and a single line of result on stdout.

    The work happens in ``__init__`` because that is where ``cli_tool`` calls
    us -- ``gramps/gui/plug/tool.py`` constructs the class and never calls
    anything on it.
    """

    def __init__(self, dbstate, user, options_class, name, callback=None):
        tool.Tool.__init__(self, dbstate, options_class, name)
        _put_the_package_on_the_path()
        try:
            payload = self._decide(dbstate)
        except Exception as failure:
            # The traceback goes to stderr, where the front end prints it when a
            # run fails. The message goes in the marker, where the owner reads
            # it. Neither is an exception escaping into Gramps' bare except.
            traceback.print_exc()
            payload = {"ok": False, "error": f"{type(failure).__name__}: {failure}"}
        self._report(payload)

    def _report(self, payload):
        """Print the one line the front end reads. Nothing else goes to stdout.

        ⚠️ **The marker's spelling is imported rather than repeated**, because
        two spellings of a protocol constant on either side of a process
        boundary is how the two ends stop agreeing. If even that import fails
        there is nothing to print with, and stderr carries the traceback -- the
        front end reports the absent marker and shows it.
        """
        try:
            from gramps_live_api.invocation import emit_marker

            print(emit_marker(payload), flush=True)
        except Exception:
            traceback.print_exc()

    def _decide(self, dbstate):
        from gramps_live_api.core import apply as core
        from gramps_live_api.core.schema import from_dict

        database = dbstate.db
        tree = GrampsTree(database)
        # ⚠️ The path comes from the OPEN database, never from an argument. A
        # wrong -O therefore produces a refusal naming the path, not a write.
        copy = core.authorise(database.get_save_path())
        operation = from_dict(json.loads(os.environ["GRAMPS_LIVE_API_OP"]))
        mode = os.environ.get("GRAMPS_LIVE_API_MODE")

        if mode == "verify":
            handles = json.loads(os.environ["GRAMPS_LIVE_API_HANDLES"])
            seen = core.verify_operation(
                operation,
                copy,
                tree,
                note_handle=handles["note_handle"],
                person_handle=handles["person_handle"],
            )
            return {
                "ok": True,
                "text_matches": seen.text_matches,
                "attached": seen.attached,
                "text": seen.text,
            }

        applied = core.apply_operation(
            operation,
            copy,
            tree,
            approved_preview=os.environ["GRAMPS_LIVE_API_APPROVED"],
            approved_digest=os.environ["GRAMPS_LIVE_API_APPROVED_DIGEST"],
            gramps_version=VERSION,
        )
        return {
            "ok": True,
            "note_handle": applied.written.note_handle,
            "note_gramps_id": applied.written.note_gramps_id,
            "person_handle": applied.written.person_handle,
            "record": applied.record,
            "record_error": applied.record_error,
        }


class GrampsTree:
    """``core.apply.Tree``, spoken to a real Gramps database.

    Every method is a translation and nothing more. There is no policy here on
    purpose: policy that lives behind a Gramps import is policy no test on a CI
    runner can reach.
    """

    def __init__(self, database):
        self._db = database

    def save_path(self):
        return self._db.get_save_path()

    def person_handle_of(self, gramps_id):
        person = self._db.get_person_from_gramps_id(gramps_id)
        return None if person is None else person.get_handle()

    def note_type_value(self, note_type):
        """What THIS Gramps holds under that ``NoteType`` attribute name.

        ⛔ One getattr, and no verdict. Whether what comes back is something a
        note can be filed under is decided in ``core.apply._spellable``, which
        runs under ordinary unit tests; deciding it here would put the check
        behind the Gramps import, where nothing on a CI runner can reach it.
        """
        return getattr(NoteType, note_type, None)

    def transaction(self, message):
        return DbTxn(message, self._db)

    def add_note_to_person(self, person_handle, note_type, text, transaction):
        from gramps_live_api.core.apply import NoteIdentity

        note = Note()
        note.set_styledtext(StyledText(text))
        # ⚠️ getattr on the ATTRIBUTE NAME, never a pinned integer. Gramps'
        # numbering is an implementation detail, and a rename fails loudly here
        # instead of filing every note under whatever now holds that number.
        #
        # ⛔ **Unguarded on purpose, and it is no longer the guard.**
        # ``core.apply`` asks ``note_type_value`` about this same name before it
        # writes the undo record and before this transaction was opened, so a
        # drifted type is refused with nothing journalled and nothing written.
        # Reaching a failure here would mean the class answered one way then and
        # another way now, and failing loudly is the right thing to do about it.
        note.set_type(NoteType(getattr(NoteType, note_type)))
        note_handle = self._db.add_note(note, transaction)

        # Gramps derives the backlink from the reference on commit, so the note
        # is attached by committing the PERSON -- adding the note alone would
        # produce a note attached to nothing and a tree that fails Check and
        # Repair later.
        person = self._db.get_person_from_handle(person_handle)
        person.add_note(note_handle)
        self._db.commit_person(person, transaction)

        return NoteIdentity(
            handle=note_handle, gramps_id=self._db.get_note_from_handle(note_handle).get_gramps_id()
        )

    def note_on_person(self, note_handle, person_handle):
        from gramps_live_api.core.apply import NoteSighting

        note = self._db.get_note_from_handle(note_handle)
        person = self._db.get_person_from_handle(person_handle)
        return NoteSighting(
            text="" if note is None else str(note.get_styledtext()),
            attached=person is not None and note_handle in person.get_note_list(),
        )


class ApplyToolOptions(tool.ToolOptions):
    """No options. Everything this tool needs arrives in the environment."""

    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
        self.options_dict = {}
        self.options_help = {}
