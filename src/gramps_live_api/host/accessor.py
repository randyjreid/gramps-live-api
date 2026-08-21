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

from gramps_live_api.host import document, log, mainthread, status

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
