"""The hook Gramps fires at startup, and the smallest thing it could be.

⚠️ **Nothing here is imported at module level from ``gramps`` or ``gi``, and that
is deliberate rather than tidy.** Every Gramps-shaped line lives inside
``load_on_reg``, so this module imports on an ordinary machine and
``tests/unit/test_host_plugin.py`` exercises ``start_host`` -- the whole plugin
half except the three lines that reach ``gi`` and Gramps' signal. What CI cannot
cover is then three lines instead of a file.

⚠️ **``load_on_reg`` swallows exceptions and the all-in-one build has no
console.** R8's accepted risk 2. So this never raises: the ordinary failure goes
to ``host.log`` through ``service.start_and_report``, and the failure that
happens BEFORE the package is importable -- a wrong junction, a moved checkout --
goes through ``_last_resort_note``, which is the only reason this file computes a
path of its own.

⚠️ **The hook fires with NO TREE OPEN.** ``uistate`` is ``None`` and
``dbstate.db`` is a ``DummyDb``; the probe measured both. So the host starts in
that state and learns about a tree from ``database-changed``.

⚠️ **This source must parse on Python 3.10 and will execute on Python 3.14.** The
AIO ships 3.14.4 and this repository's gates run 3.10-3.12, so neither end is
observable from the other. The stdlib used here is deliberately ancient -- ``os``,
``sys``, ``traceback`` -- because ``mypy src`` does not reach this directory and
nothing else would catch a call that arrived after the floor.
"""

import os
import sys
import traceback

DIRECTORY_NAME = "gramps-live-api"
LOG_FILE = "host.log"
"""⚠️ Duplicated from ``gramps_live_api.host.paths`` ON PURPOSE, and pinned by
test. The one failure this file exists to make visible is the one where that
module cannot be imported, so the last-resort writer cannot ask it where to
write. ``tests/unit/test_host_plugin.py`` asserts the two answers agree, which is
what stops the copy drifting into a second directory nobody looks in."""

_RUNNING = {}
"""The started host, kept so a later slice has something to stop. Gramps' exit
takes the daemon thread with it, so nothing here needs to."""


def load_on_reg(dbstate, uistate=None, plugin=None, *rest):
    """Gramps' startup hook. Runs on the main thread, before any tree is open.

    Never raises. There is nowhere for an exception to go: the caller prints a
    traceback into a console the all-in-one build does not have, and startup
    carries on as though the plugin were fine.

    ⚠️ **The trailing parameters are defaulted and open-ended deliberately.** A
    signature mismatch raises in GRAMPS' code, before this body -- so the
    ``try`` below cannot catch it, ``host.log`` never gets a line, and the whole
    slice fails in the one way nothing here can report. Nothing on this machine
    can check what Gramps actually passes, so the call is made impossible to get
    wrong instead of being got right by guessing. ``uistate`` is ``None`` at this
    point anyway, which the probe measured.
    """
    try:
        _put_the_package_on_the_path()

        # gi is imported HERE rather than at module level so this file stays
        # importable, and therefore testable, on a machine with no GTK.
        from gi.repository import GLib

        started = start_host(dbstate, GLib.idle_add, uistate)
        if started is not None:
            from gramps_live_api.host import service

            # ⚠️ ``*ignored`` for the reason load_on_reg's signature is open:
            # Gramps' Callback.emit unpacks whatever the emitter passed, and a
            # handler that disagreed about the count would raise inside the
            # signal rather than anywhere this can report. The argument is not
            # wanted in any case -- the accessor reads dbstate live.
            dbstate.connect(
                "database-changed",
                lambda *ignored: service.database_changed(started),
            )
    except Exception:
        traceback.print_exc()
        _last_resort_note(traceback.format_exc())


def start_host(dbstate, schedule, uistate=None):
    """Hand Gramps' possessions to the package and start listening.

    ``dbstate`` goes straight into the accessor -- the one module allowed to
    spell the database -- and ``schedule`` is ``GLib.idle_add``, which is how
    anything gets back onto this thread. Returns the running host, or ``None``
    if it did not start, in which case ``host.log`` says why.

    ⭐ **``present`` is the third possession and the newest.** The package can
    validate a graph and render it as prose, but it cannot show a window: the
    Gtk classes live here. So the host is handed a callable that takes a graph,
    puts it in front of the owner, and writes it if he says yes.
    """
    from gramps_live_api.host import accessor, service

    accessor.bind(dbstate)
    host = service.start_and_report(
        schedule=schedule,
        environ=os.environ,
        present=lambda graph: _present(dbstate, uistate, graph),
    )
    _RUNNING["host"] = host
    return host


def _present(dbstate, uistate, graph):
    """Show what would be written, and write it if the owner says so.

    ⚠️ **Runs on the GTK main thread, inside a ``GLib.idle_add`` callback**, and
    ``confirm`` spins a nested main loop there. ``spike/dialogprobe.py`` measured
    that working before anything was built on it: dialog shown from inside the
    callback, answer returned after 3.9 s, ``DbTxn`` committed and read back.

    ⭐ **The preview is rendered from the graph that arrived**, which the MCP
    server loaded from its own stored record -- never from anything an agent
    passed at approval time. That is what carries the approval binding across
    from the console to this dialog.

    Never raises. It is reached from a hook whose exceptions go nowhere, so
    everything lands in ``host.log`` instead.
    """
    from gramps_live_api.host import document

    host = _RUNNING.get("host")

    def note(level, message):
        if host is not None:
            host.note(level, message)

    try:
        import gramps_live_api_writer as writer

        parsed = document.parse(graph)

        # ⭐ The names in the dialog are read from the TREE, not from the graph.
        # If the model picked the wrong Gramps ID the owner sees the wrong
        # person and cancels, and that is the only check there is. Resolving
        # here rather than trusting what the route resolved keeps the lookup
        # adjacent to the rendering it feeds.
        from gramps_live_api.host import accessor

        resolution = accessor.resolve_nodes(graph)
        # ⛔ ``refusal()`` and not ``missing``. This re-resolve happens AFTER the
        # route's, so a target can have become private in between -- and checking
        # ``missing`` alone reported it as absent, losing ruling 1's second
        # enforcement point to a call-site convention. The order lives in the
        # method now, so this site cannot get it wrong.
        refusal = resolution.refusal()
        if refusal is not None:
            note("ERROR", "document: refusing: " + refusal)
            writer.tell(uistate, "Nothing was written", refusal)
            return

        note("INFO", "document: showing " + document.summary(parsed))

        if not writer.confirm(uistate, document.preview(parsed, resolution)):
            note("INFO", "document: the owner said no. Nothing was written.")
            return

        # ⛔ The blessing is checked AGAIN here, on the main thread, immediately
        # before the transaction. The route checked it too -- but that was a
        # different moment and a tree can be closed or swapped while a dialog is
        # open. This is the check that is adjacent to the write.
        #
        # ⚠️ Through the ACCESSOR, not through ``dbstate.db``. This file is host
        # code by the rule in ``tests/fixtures/host_sources.py`` -- it imports the
        # host package -- so reaching the database here is exactly the trespass
        # the boundary test refuses, and it caught this on the first run.
        from gramps_live_api.host import accessor

        outcome = accessor.blessing()
        if not outcome.blessed:
            note("ERROR", "document: refused at write time: " + outcome.message)
            writer.tell(uistate, "Nothing was written", outcome.message)
            return

        approved = document.preview(parsed, resolution)
        result = writer.write(dbstate, graph)
        # ⛔ Summarised HERE, from what the write actually created. The writer
        # cannot do it: importing the host package would make it host code and
        # forbid it the database access it exists for.
        summary = document.summarise_created(result["created"])
        note("INFO", "document: wrote " + summary)

        # ⛔ Journal it. Gramps' own undo is a process-local list discarded on
        # close, so without this a six-object write is unrecoverable the moment
        # Gramps quits -- which has already cost one manual cleanup.
        # ⚠️ AFTER the commit, deliberately: a record of a write that did not
        # happen is worse than no record, and the transaction has returned by here.
        journal = "(not written)"
        try:
            import datetime

            written_utc = datetime.datetime.now(datetime.timezone.utc)
            journal = document.write_journal(
                outcome.message,
                document.journal_record(
                    parsed,
                    result["created"],
                    result["attached"],
                    tree_dir=outcome.message,
                    written_utc=written_utc.isoformat(),
                    approved_preview=approved,
                ),
                stem=written_utc.strftime("%Y%m%dT%H%M%SZ") + "-document",
            )
            note("INFO", "document: journalled to " + journal)
        except Exception:
            # ⚠️ A failed journal must not un-write the tree, and must not be
            # silent either. The write happened; say where it is not recorded.
            note("ERROR", "document: THE WRITE IS NOT JOURNALLED: " + traceback.format_exc())

        writer.tell(
            uistate,
            "Written",
            summary
            + "\n\nUndo record: "
            + journal
            + "\n\nEdit > Undo in Gramps also works, until Gramps closes.",
        )
    except Exception:
        note("ERROR", "document: the write failed: " + traceback.format_exc())
        try:
            import gramps_live_api_writer as writer

            writer.tell(uistate, "The document could not be written", traceback.format_exc()[:2000])
        except Exception:
            pass


def _put_the_package_on_the_path():
    """Make ``gramps_live_api`` importable inside Gramps' own frozen interpreter.

    Gramps runs on its own Python with its own ``sys.path``, and nothing this
    project installs is on it. Two answers, in order:

    ``GRAMPS_LIVE_API_SRC``
        an explicit directory, for an owner who put the checkout somewhere this
        cannot infer.
    the checkout beside this file
        the plugin directory is a hand-made junction into the checkout, so
        resolving symbolic links and stepping up one level lands on the checkout
        root. ``realpath`` is what follows the junction; ``dirname(__file__)``
        alone would land in Gramps' plugin folder, where there is no ``src``.

    ⚠️ **And this directory itself, which is the third answer and was learned
    the hard way.** Gramps ``exec``s a plugin rather than importing it, so the
    plugin folder is NOT on ``sys.path`` and a sibling module -- the writer --
    cannot be imported by name. Observed as ``ModuleNotFoundError: No module
    named 'gramps_live_api_writer'`` on the first real request, with the route
    already answered 202 and the failure visible only in ``host.log``.
    """
    named = os.environ.get("GRAMPS_LIVE_API_SRC")
    here = os.path.dirname(os.path.realpath(__file__))
    for candidate in (named, os.path.join(os.path.dirname(here), "src"), here):
        if candidate and os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


def last_resort_log_path(environ, platform):
    """Where to write when ``gramps_live_api`` itself could not be imported.

    Public, and only so a test can pin it against the real one. See the note on
    ``DIRECTORY_NAME`` above for why the copy exists at all.
    """
    if platform == "win32":
        base = environ.get("APPDATA", "")
    else:
        base = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME", ""), ".config")
    return os.path.join(base, DIRECTORY_NAME, LOG_FILE)


def _inside_gramps():
    """Whether this module is really executing inside a Gramps process.

    ⛔ **``host.log`` is the ONLY place a genuinely failed start is visible.**
    ``load_on_reg`` swallows exceptions and the all-in-one build has no console
    -- R8's accepted risk 2 -- so a line in that file has to mean something
    happened to the real host.

    ⚠️ **It stopped meaning that.** The unit suite calls ``load_on_reg(None)`` to
    assert the hook never raises, which is exactly right; the hook then fails at
    ``from gi.repository import GLib`` and reported it to the PRODUCTION log.
    Sixty-eight such tracebacks accumulated against twenty-five real lines --
    **and a reader came one message from reporting the host down because of
    them.** A log that cries wolf is the same defect as a guard that fires on
    every route literal: it trains the reader to skip the one that matters.

    ``gramps`` is in ``sys.modules`` whenever Gramps' own code is running, and
    is not importable at all in this project's environment, so the check costs
    nothing and cannot be satisfied by accident. A failure that IS inside Gramps
    still reports, because Gramps got far enough to exec this file.
    """
    return "gramps" in sys.modules


def _last_resort_note(detail):
    """One ERROR line, written with nothing but built-ins. Silent if even that fails.

    ⛔ Refuses outside Gramps -- see ``_inside_gramps``. The traceback still
    reaches stderr through ``load_on_reg``, which is where a test or a probe
    should be reading it from anyway.
    """
    if not _inside_gramps():
        return
    try:
        path = last_resort_log_path(os.environ, sys.platform)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("ERROR the host plugin could not start: " + detail.strip() + "\n")
    except Exception:
        # There is genuinely nowhere left to report this, and raising would put
        # the exception back into the hook that eats it.
        pass
