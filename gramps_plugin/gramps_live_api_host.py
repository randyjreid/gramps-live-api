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


def load_on_reg(dbstate, uistate, plugin):
    """Gramps' startup hook. Runs on the main thread, before any tree is open.

    Never raises. There is nowhere for an exception to go: the caller prints a
    traceback into a console the all-in-one build does not have, and startup
    carries on as though the plugin were fine.
    """
    try:
        _put_the_package_on_the_path()

        # gi is imported HERE rather than at module level so this file stays
        # importable, and therefore testable, on a machine with no GTK.
        from gi.repository import GLib

        started = start_host(dbstate, GLib.idle_add)
        if started is not None:
            from gramps_live_api.host import service

            dbstate.connect(
                "database-changed",
                lambda database: service.database_changed(started, database),
            )
    except Exception:
        traceback.print_exc()
        _last_resort_note(traceback.format_exc())


def start_host(dbstate, schedule):
    """Hand Gramps' two possessions to the package and start listening.

    ``dbstate`` goes straight into the accessor -- the one module allowed to
    spell the database -- and ``schedule`` is ``GLib.idle_add``, which is how
    anything gets back onto this thread. Returns the running host, or ``None``
    if it did not start, in which case ``host.log`` says why.
    """
    from gramps_live_api.host import accessor, service

    accessor.bind(dbstate)
    host = service.start_and_report(schedule=schedule, environ=os.environ)
    _RUNNING["host"] = host
    return host


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
    """
    named = os.environ.get("GRAMPS_LIVE_API_SRC")
    here = os.path.dirname(os.path.realpath(__file__))
    for candidate in (named, os.path.join(os.path.dirname(here), "src")):
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


def _last_resort_note(detail):
    """One ERROR line, written with nothing but built-ins. Silent if even that fails."""
    try:
        path = last_resort_log_path(os.environ, sys.platform)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("ERROR the host plugin could not start: " + detail.strip() + "\n")
    except Exception:
        # There is genuinely nowhere left to report this, and raising would put
        # the exception back into the hook that eats it.
        pass
