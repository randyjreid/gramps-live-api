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

import typing

from gramps_live_api.host import mainthread, status

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
