"""Starting the host, and making a failed start visible.

⚠️ **``start_and_report`` exists because ``load_on_reg`` swallows exceptions.**
Gramps prints the traceback and carries on, and the all-in-one build has no
console for it to land in -- so a host that failed to start does so invisibly.
Everything that can go wrong is caught here and written to ``host.log`` as an
``ERROR`` line, which is the only observation a client or an owner can make.

⭐ **What the plugin supplies and this module never imports.** ``schedule`` is
``GLib.idle_add`` and the ``dbstate`` goes straight into the accessor. Neither
``gramps`` nor ``gi`` is named anywhere in this package, which is what lets every
line below run under CI.
"""

from __future__ import annotations

import contextlib
import functools
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gramps_live_api.host import (
    accessor,
    document,
    httpd,
    log,
    mainthread,
    paths,
    reads,
    status,
    tokens,
)

THREAD_NAME = "gramps-live-api-host"


@dataclass(frozen=True)
class Host:
    """A running listener, and where it wrote itself down."""

    server: httpd.HostServer
    thread: threading.Thread
    port: int
    token: str
    directory: Path

    @property
    def log_file(self) -> Path:
        return paths.log_path(self.directory)

    def note(self, level: str, message: str) -> None:
        log.record(self.log_file, level, message)

    def stop(self) -> None:
        """Shut the listener down and take the ``port`` file with it.

        The port file is a claim that something is listening, so it goes when the
        listener does. Called from Gramps' quit path, and from tests.
        """
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
        _forget_the_port(self.directory)


def start(
    *,
    schedule: Callable[[Callable[[], bool]], Any],
    environ: Mapping[str, str],
    platform: str = sys.platform,
    timeout: float = mainthread.DEFAULT_TIMEOUT_SECONDS,
    run: Callable[[list[str]], tokens.CommandResult] | None = None,
    present: Callable[[dict[str, Any]], None] | None = None,
) -> Host:
    """Mint a token, bind loopback, serve on a daemon thread, and write it all down.

    The ordering is the contract, not an implementation detail: the ``port`` file
    is removed FIRST and written LAST, after a successful bind. So its presence
    means a listener answered, and its absence sends a client to the log instead
    of to a stale number.
    """
    directory = paths.state_directory(environ, platform=platform)
    directory.mkdir(parents=True, exist_ok=True)
    _forget_the_port(directory)

    token = tokens.new_token()
    protection = tokens.write_token(
        paths.token_path(directory),
        token,
        platform=platform,
        environ=environ,
        run=run,
    )

    marshal = mainthread.Marshal(schedule=schedule, timeout=timeout)
    context = httpd.Context(
        token=token,
        # The two things this host puts on the GTK loop from a request, and both
        # are one cheap callable. R8's accepted risk 4 is that long work inside
        # idle_add blocks that loop; the cap is what gets scheduled, so this one
        # reads two O(1) values and the next fetches exactly one person.
        snapshot=functools.partial(marshal.call, accessor.tree_status),
        person=functools.partial(_person, marshal),
        note=functools.partial(_note, paths.log_path(directory)),
        write_document=functools.partial(_document, marshal, schedule, present),
        # ⭐ Five live reads, each one marshalled onto the GTK loop as a single
        # cheap callable. Measured: a full name walk of a 2,933-person tree
        # costs ~48 ms, inside what one callback may take -- so R8's accepted
        # risk 4 is respected by measurement rather than by hope.
        read=functools.partial(_read, marshal),
    )

    server = httpd.build(context)
    thread = threading.Thread(target=server.serve_forever, name=THREAD_NAME, daemon=True)
    thread.start()

    port = httpd.bound_port(server)
    paths.port_path(directory).write_text(str(port), encoding="utf-8")

    log.record(
        paths.log_path(directory),
        log.INFO,
        f"listening on {httpd.LOOPBACK}:{port}; token protection={protection.kind} "
        f"({protection.detail})",
    )

    return Host(server=server, thread=thread, port=port, token=token, directory=directory)


def start_and_report(
    *,
    schedule: Callable[[Callable[[], bool]], Any],
    environ: Mapping[str, str],
    platform: str = sys.platform,
    timeout: float = mainthread.DEFAULT_TIMEOUT_SECONDS,
    run: Callable[[list[str]], tokens.CommandResult] | None = None,
    present: Callable[[dict[str, Any]], None] | None = None,
) -> Host | None:
    """``start``, with the failure written down instead of thrown into a hook that eats it.

    Returns ``None`` when the host did not start. The ``ERROR`` line it leaves is
    what distinguishes "the host errored" from "the host was never there" -- and
    if even the directory could not be resolved there is nowhere to write, which
    is the one failure that stays invisible and is recorded as such.
    """
    try:
        directory = paths.state_directory(environ, platform=platform)
    except Exception:
        return None

    try:
        return start(
            schedule=schedule,
            environ=environ,
            platform=platform,
            timeout=timeout,
            run=run,
            present=present,
        )
    except Exception as failure:
        log.record(
            paths.log_path(directory),
            log.ERROR,
            f"startup failed: {type(failure).__name__}: {failure}",
        )
        return None


def database_changed(host: Host, database: Any = None) -> None:
    """Gramps' ``database-changed`` handler. Runs on the main thread, like the signal.

    ⭐ **The argument is deliberately ignored.** Gramps hands the new database to
    every subscriber, and holding on to it here would put a second copy of the
    boundary in a module that is not the accessor -- which the boundary test
    refuses, correctly. The accessor reads ``dbstate`` live at request time, so
    what this subscription is for is the RECORD: a line in the log saying a tree
    opened or closed, which is how the owner reads back what the host saw.

    That also means a signal this host never received cannot make ``/health``
    lie. The tracking is a witness, not the answer.
    """
    tree = accessor.tree_status()
    host.note(log.INFO, "database-changed: " + ("a tree is open" if tree.open else "no tree open"))

    # ⛔ REPORT ONLY, for R7. Nothing is written and nothing here depends on
    # what it says -- see ``accessor.note_connection_shape``. It rides on this
    # signal because this is the moment a tree becomes open, which is the only
    # state the question is about, and because this handler already runs on the
    # main thread the probe requires.
    accessor.note_connection_shape(host.note)


def _document(
    marshal: mainthread.Marshal,
    schedule: Callable[[Callable[[], bool]], Any],
    present: Callable[[dict[str, Any]], None] | None,
    graph: dict[str, Any],
) -> document.Blessing:
    """Check the tree may be written to, then SCHEDULE the dialog and return.

    ⚠️ **Two different crossings, and the difference is the point.**

    The blessing is a ``Marshal.call``: O(1), the caller needs the answer, and a
    refusal must reach the client instead of a dialog reaching the owner. The
    dialog is a bare ``schedule`` -- nothing waits for it, because what it waits
    on is a human. ⛔ Marshalling it would 503 after five seconds, in the middle
    of the owner deciding, and the write would then land with the client already
    told it had failed.
    """
    outcome = marshal.call(accessor.blessing)
    if not outcome.blessed:
        return outcome

    # ⛔ Every supplied Gramps ID is resolved BEFORE the dialog opens, and a
    # single miss refuses the WHOLE batch naming every one that missed.
    # Creating a new object where an id was supplied is precisely the duplicate
    # the id was there to prevent, arriving quietly.
    resolution = marshal.call(functools.partial(accessor.resolve_nodes, graph))
    if resolution.missing:
        named = ", ".join(f"{node.gramps_id} ({node.kind})" for node in resolution.missing)
        return document.Blessing(
            blessed=False,
            message=(
                f"these Gramps IDs are not in the open tree: {named}. "
                "Nothing was written and no dialog was shown. Look them up with "
                "list_people, or leave gramps_id out to create a new record."
            ),
        )

    if present is None:
        # No presenter was injected -- the host is running outside Gramps, which
        # is every test and no real session. Refuse rather than silently accept.
        return document.Blessing(blessed=False, message="this host cannot show a dialog")

    def show() -> bool:
        present(graph)
        return False

    schedule(show)
    return outcome


_READS = {
    "people": "find_people",
    "place": "find_place",
    "source": "find_source",
    "citation": "find_citation",
    "events": "list_events",
}


def _read(marshal: mainthread.Marshal, which: str, first: str, second: str = "") -> reads.Found:
    """One live read, onto the main thread and back as plain data.

    ⛔ **The handler never holds a Gramps object**, only ``reads.Found`` -- the
    same shape the boundary keeps for ``/health`` and ``/person``.
    """
    helper: Callable[..., reads.Found] = getattr(accessor, _READS[which])
    if which == "citation":
        return marshal.call(functools.partial(helper, first, second))
    return marshal.call(functools.partial(helper, first))


def _person(marshal: mainthread.Marshal, gramps_id: str) -> status.PersonStatus:
    """One person read, scheduled onto the main thread as one cheap callable.

    ``Marshal.call`` takes work of no arguments, so the Gramps ID is bound here
    rather than travelling across the boundary as a parameter -- one lookup, no
    loop and no batch, which is what keeps R8's accepted risk 4 where it was.
    """
    return marshal.call(functools.partial(accessor.person_status, gramps_id))


def _note(path: Path, level: str, message: str) -> None:
    log.record(path, level, message)


def _forget_the_port(directory: Path) -> None:
    # Absent is the ordinary case, and a port file that cannot be removed is not
    # a reason to refuse to start -- it is a reason for the log line that follows
    # to be the thing a client trusts.
    with contextlib.suppress(OSError):
        paths.port_path(directory).unlink()
