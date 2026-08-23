"""A byte-level copy of the open tree, taken before a write.

⭐ **This is R4's replacement guarantee, not a convenience.** R4 approved the
downgrade in these words -- *"the guarantee changes from
unwritable-by-construction to recoverable-after"* -- and *recoverable-after* is
true only if a backup exists, predates the damage, and can be restored. **The
backup is the whole of what replaced the old guarantee.**

⛔ **A SECOND, read-only ``sqlite3`` connection to the tree's file, opened on the
thread that uses it.** Not Gramps' own connection. R7 accepted reaching
``db.dbapi._Connection__connection`` as a cost; this does not incur it, because a
backup copies pages and needs none of the functions and collations Gramps
registers on its own connection.

⚠️ **Nothing here imports ``gramps`` or ``gi``, so all of it runs under CI.** It
takes a path and returns a result; it has never heard of a tree.

⛔ **Nothing here decides whether a write may proceed.** It reports what happened.
The refusal lives at the call site, next to the blessing check, because that is
where the owner is told.
"""

from __future__ import annotations

import contextlib
import datetime
import os
import sqlite3
import time
from dataclasses import dataclass

PAGES_PER_STEP = 1024
"""How many pages one internal copy step moves.

⚠️ **This is the STEP SIZE and not the budget.** An earlier draft of the plan
described it as though it were the budget, which made the page-budget criterion
unimplementable: a progress callback that only counts steps has no count at which
it fails. The budget is ``PAGE_BUDGET_MULTIPLE`` below."""

PAGE_BUDGET_MULTIPLE = 4
"""The copy may move this many times the source's own page count before failing.

⭐ **Derived rather than picked.** A clean copy touches each page about once, so
four times tolerates several restarts and still terminates. SQLite restarts the
copy when the source is written during it, so a budget in *pages moved* is what
catches a source being rewritten faster than it can be read."""

SECONDS_PER_ATTEMPT = 5.0
"""⭐ Also derived: the owner's real tree copies in **120 ms**, so five seconds is
roughly forty times the observed cost. A run that has not finished by then is not
slow -- it is being restarted by a writer, which is the livelock below.

⚠️ **Falsifier, recorded so this is a measurement rather than a feeling:** if a
legitimate backup of a larger tree ever exceeds this, the budget is wrong and
must be re-derived from a new measurement, not raised because it fired."""

ATTEMPTS = 2
"""One retry absorbs a single write burst. A second failure is a pattern.

⛔ **Measured, and the reason both limits exist: under a CONTINUOUSLY committing
writer, ``backup()`` did not converge in ten minutes.** Gramps writes in bursts
rather than continuously, so this is probably not the real case -- and *probably*
is not a bound."""

RETAIN = 20
"""How many backups to keep per tree. At ~24 MB that is roughly 480 MB, which is
the trade being made explicitly rather than discovered later."""


class BackupRefused(Exception):
    """The copy could not be taken. ⛔ The write must not proceed."""


@dataclass(frozen=True)
class Outcome:
    """What happened, in terms the owner can be told."""

    ok: bool
    path: str | None
    message: str
    pages: int = 0
    attempts: int = 0
    seconds: float = 0.0
    taken_utc: str = ""
    """When the copy completed, ISO-8601 UTC.

    ⭐ **R4 precondition 4 lives on this field**: *the backup's age relative to
    the write is visible without archaeology*. The journal stores it beside the
    write's own timestamp, so *which copy predates this write* is one comparison
    rather than a forensic exercise over file times."""


def destination_for(directory: str, tree_name: str, stamp: str) -> str:
    """Where one backup lands. ⛔ Timestamp first, so lexical order is chronological."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tree_name) or "tree"
    return os.path.join(directory, safe, f"{stamp}-{safe}.sqlite")


def take(source: str, destination: str) -> Outcome:
    """Copy ``source`` to ``destination``. ⛔ **Call this ON the worker thread.**

    ⚠️ ``sqlite3`` refuses a connection object created on another thread, which is
    not an obstacle but a reminder: **nothing here is shared with Gramps.**

    Never raises for an ordinary failure -- a refusal is a result, because the
    caller has to tell the owner either way.
    """
    started = time.monotonic()
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    last = "no attempt was made"
    for attempt in range(1, ATTEMPTS + 1):
        moved = 0
        try:
            moved = _one_attempt(source, destination)
        except _OverBudget as refusal:
            last = str(refusal)
            _discard(destination)
            continue
        except Exception as failure:  # noqa: BLE001 -- reported, never swallowed
            last = f"{type(failure).__name__}: {failure}"
            _discard(destination)
            continue
        return Outcome(
            ok=True,
            path=destination,
            message="backup taken",
            pages=moved,
            attempts=attempt,
            seconds=time.monotonic() - started,
            taken_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    return Outcome(
        ok=False,
        path=None,
        message=(
            f"the backup could not be taken after {ATTEMPTS} attempts: {last}. Nothing was written."
        ),
        attempts=ATTEMPTS,
        seconds=time.monotonic() - started,
    )


class _OverBudget(Exception):
    """A single attempt exceeded its page budget or its clock."""


def _one_attempt(source: str, destination: str) -> int:
    """One copy, bounded two ways. Returns the pages moved.

    ⛔ **Both bounds are enforced from inside the progress callback**, because
    ``Connection.backup()`` runs to completion in a single call -- ``pages`` sets
    the step size and does **not** make it return partway. Raising from the
    callback is the only way to stop it.
    """
    deadline = time.monotonic() + SECONDS_PER_ATTEMPT
    moved = 0
    budget = 0

    # ⛔ Read-only, and opened HERE so it belongs to the calling thread.
    with contextlib.closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as reader:
        budget = _page_count(reader) * PAGE_BUDGET_MULTIPLE

        def progress(status: int, remaining: int, total: int) -> None:
            nonlocal moved
            moved = total - remaining if total >= remaining else moved + PAGES_PER_STEP
            if budget and moved > budget:
                raise _OverBudget(
                    f"the copy moved {moved} pages against a budget of {budget}, "
                    "which means the tree is being written faster than it can be read"
                )
            if time.monotonic() > deadline:
                raise _OverBudget(f"the copy did not finish within {SECONDS_PER_ATTEMPT:g} s")

        with contextlib.closing(sqlite3.connect(destination)) as writer:
            reader.backup(writer, pages=PAGES_PER_STEP, progress=progress)
    return moved


def _page_count(connection: sqlite3.Connection) -> int:
    """The source's own page count, for the budget. ``0`` if it cannot be read."""
    try:
        row = connection.execute("PRAGMA page_count").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _discard(path: str) -> None:
    """Remove a failed copy.

    ⛔ **A truncated file must never be mistaken for a backup**, which is the one
    way a *recoverable-after* guarantee fails silently. ⚠️ This deletes **this
    module's own output** on a path it just built -- never a tree file, and never
    anything the owner made.
    """
    with contextlib.suppress(OSError):
        os.remove(path)


def verify(path: str) -> bool:
    """Whether the copy reads as a sound database. ⛔ A copy nobody checked is a hope."""
    try:
        with contextlib.closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as taken:
            row = taken.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
    except Exception:
        return False


def prune(directory: str, keep: int = RETAIN) -> list[str]:
    """Drop all but the newest ``keep`` backups. Returns what was removed.

    ⛔ **Called only AFTER a successful backup**, so a failed one can never
    destroy the last good copy. ⚠️ Ordered by NAME rather than mtime, because the
    names begin with a UTC timestamp and a copied file's mtime is not its age.
    """
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".sqlite"))
    except OSError:
        return []
    removed = []
    for name in names[: max(0, len(names) - keep)]:
        target = os.path.join(directory, name)
        with contextlib.suppress(OSError):
            os.remove(target)
            removed.append(target)
    return removed
