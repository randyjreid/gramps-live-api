"""The invariant the whole design rests on, asserted so a FOURTH helper cannot escape.

> No Gramps database object and no GTK object is ever touched from the HTTP
> thread.

Gramps opens its SQLite connection with a bare ``sqlite3.connect()`` and never
passes ``check_same_thread``, so the default applies and a cross-thread call
raises ``sqlite3.ProgrammingError``. ``Callback.emit()`` dispatches handlers
synchronously in the emitting thread. R8 records both, and records that this is
"the property a future agent will violate by accident".

⚠️ **A test that names today's helpers will not catch tomorrow's.** So nothing
here enumerates. Two rules, and they close different doors:

``test_every_database_helper_refuses_a_non_main_thread``
    discovers the accessor's helpers **from its own source**, and calls every one
    of them from a spawned thread. A fourth helper added to that module is
    discovered the moment it is written, whatever it is called and whatever its
    signature.

``test_nothing_outside_the_accessor_reaches_the_database``
    closes the other door -- the helper added somewhere else, which the first
    rule would never see because it is not in the module being read. The database
    arrives as ``dbstate.db`` and lives in one module-private name; both
    spellings are refused everywhere else, in the package and in the plugin.

⚠️ **The second rule is SYNTACTIC and its bound is stated rather than implied.**
It reads the attribute spelling, so ``getattr(dbstate, "db")`` and
``vars(dbstate)["db"]`` escape it. That is a bypass somebody has to write on
purpose; the rule is aimed at the helper somebody adds by accident.
"""

from __future__ import annotations

import ast
import inspect
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from gramps_live_api.host import accessor
from gramps_live_api.host.mainthread import WrongThread
from tests.fixtures.host_sources import ACCESSOR, host_sources

# The database reaches this process as an attribute of Gramps' dbstate, and the
# accessor keeps it in one module-private name. Nothing else may spell either.
DATABASE_ATTRIBUTE = "db"
DATABASE_BINDING = "_DBSTATE"


def defined_functions(path: Path) -> list[str]:
    """Every top-level ``def`` in this file whose name is public.

    Read from the source rather than from the module's namespace, so a helper is
    found by being WRITTEN rather than by surviving whatever a decorator did to
    it. ``__module__`` filtering would miss a helper whose decorator returns
    something built elsewhere -- which is precisely the shape a bypass takes.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def public_callables(module: Any) -> dict[str, Callable[..., Any]]:
    """Everything callable a caller can reach on the module, by its public name."""
    return {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_") and callable(value)
    }


def called_off_the_main_thread(helper: Callable[..., Any]) -> BaseException | None:
    """Call it from a spawned thread with sentinels, and hand back what it raised.

    The arguments are ``object()`` placeholders built from the signature. That is
    safe for any helper the rule is meant to catch: the guard runs before the
    body, so a sentinel is never touched -- and a helper that reaches its body
    far enough to trip over one has already failed the assertion for the right
    reason.
    """
    empty = inspect.Parameter.empty
    positional = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    signature = inspect.signature(helper)
    arguments = [
        object()
        for parameter in signature.parameters.values()
        if parameter.kind in positional and parameter.default is empty
    ]

    raised: list[BaseException] = []

    def attempt() -> None:
        try:
            helper(*arguments)
        except BaseException as failure:  # noqa: BLE001 -- the failure IS the result
            raised.append(failure)

    thread = threading.Thread(target=attempt, name="not-the-main-thread")
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), f"{helper} never returned from a non-main thread"

    return raised[0] if raised else None


def test_the_accessor_exposes_nothing_callable_it_did_not_define() -> None:
    """The discovery above reads one file, so nothing callable may arrive from another.

    Without this, the rule below is bypassed by writing the helper elsewhere and
    importing it into the accessor's namespace: callers reach it as
    ``accessor.something``, and a scan of the accessor's own ``def``s never sees
    it. Import the module and reach through it -- ``status.TreeStatus`` -- rather
    than importing the name.
    """
    imported = sorted(set(public_callables(accessor)) - set(defined_functions(ACCESSOR)))

    assert imported == [], (
        "these callables are reachable on the accessor but are not defined in it, so "
        "the non-main-thread rule below cannot discover them: "
        f"{imported} -- import the MODULE and reach through it instead"
    )


def test_every_database_helper_refuses_a_non_main_thread() -> None:
    """Called off the main thread, every accessor helper raises. Discovered, not listed.

    This is the whole slice in one assertion. It is written over the set of
    helpers rather than over three names, so the fourth helper somebody adds is
    covered by the act of adding it.
    """
    helpers = defined_functions(ACCESSOR)
    assert helpers, (
        "the accessor defines no public helpers at all -- this test has stopped "
        "watching anything, which is the failure mode it exists to prevent"
    )

    unguarded = []
    for name in helpers:
        failure = called_off_the_main_thread(getattr(accessor, name))
        if not isinstance(failure, WrongThread):
            unguarded.append(f"{name} raised {failure!r}")

    assert unguarded == [], (
        "these accessor helpers did not refuse a non-main thread, so a request "
        "arriving on the HTTP thread can reach Gramps' SQLite connection directly: "
        f"{unguarded}"
    )


def test_a_helper_still_works_on_the_main_thread() -> None:
    """The guard must refuse the wrong thread, not every thread.

    Its seam twin is test_every_database_helper_refuses_a_non_main_thread: that
    one proves the guard fires, this one proves it is not a guard that fires
    always, which would pass that test while making the host useless.
    """
    accessor.forget()

    assert accessor.tree_status().open is False


def database_references(path: Path) -> list[str]:
    """Every place this file spells the database, as ``file:line``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == DATABASE_ATTRIBUTE:
            found.append(f"{path.name}:{node.lineno} .{DATABASE_ATTRIBUTE}")
        elif isinstance(node, ast.Name) and node.id == DATABASE_BINDING:
            found.append(f"{path.name}:{node.lineno} {DATABASE_BINDING}")
    return found


def test_nothing_outside_the_accessor_reaches_the_database() -> None:
    """One module owns the boundary, and that is checked rather than intended.

    R8 says "one accessor module owns the boundary". A rule that only watched
    the accessor would be satisfied by a second module doing the same work
    unguarded -- so this watches everywhere else instead, on both sides of the
    Gramps boundary.
    """
    sources = host_sources()
    assert sources, "no host source files were found at all -- this test watches nothing"
    assert ACCESSOR in sources, (
        "the accessor is not among the host's sources, so the exemption below "
        "excludes a file that is not there and the rule reads the wrong set"
    )

    trespass = [
        reference for path in sources if path != ACCESSOR for reference in database_references(path)
    ]

    assert trespass == [], (
        "these files reach the database outside the one module that owns the "
        f"boundary: {trespass} -- call an accessor helper instead"
    )


def test_the_marshal_runs_work_on_the_thread_that_drains_the_queue() -> None:
    """A value crosses by being scheduled, never by being read across the boundary."""
    from gramps_live_api.host.mainthread import Marshal

    queue: list[Callable[[], bool]] = []

    marshal = Marshal(schedule=queue.append, timeout=5.0)

    result: list[int] = []

    def caller() -> None:
        result.append(marshal.call(lambda: 42))

    thread = threading.Thread(target=caller, name="the-http-thread")
    thread.start()

    # The scheduling thread has posted work and is blocked; draining it here --
    # on the main thread -- is what GLib's idle handler does in Gramps.
    while not queue:
        pass
    assert queue.pop()() is False, "an idle callback must be one-shot, not rescheduled"

    thread.join(timeout=10)
    assert result == [42]


def test_the_marshal_gives_up_rather_than_hanging() -> None:
    """A blocked GTK loop must not become a hung socket -- R8's accepted risk 4."""
    from gramps_live_api.host.mainthread import MainThreadTimeout, Marshal

    marshal = Marshal(schedule=lambda work: None, timeout=0.05)

    with pytest.raises(MainThreadTimeout):
        marshal.call(lambda: 42)


def test_the_marshal_reports_a_failure_rather_than_swallowing_it() -> None:
    """Work that raises on the main thread must raise in the caller, not time out."""
    from gramps_live_api.host.mainthread import Marshal

    def immediately(work: Callable[[], bool]) -> None:
        work()

    marshal = Marshal(schedule=immediately, timeout=5.0)

    def explode() -> int:
        raise ValueError("the database said no")

    with pytest.raises(ValueError, match="the database said no"):
        marshal.call(explode)
