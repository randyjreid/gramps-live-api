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

⚠️ **A step size, and there is no page budget any more.** One was written three
times and never once fired; see ``_one_attempt``. The only bound is a wall
clock."""

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


def destination_for(directory: str, tree_name: str, stamp: str, tree_dir: str = "") -> str:
    """Where one backup lands. ⛔ Timestamp first, so lexical order is chronological.

    ⛔ **Keyed on the tree DIRECTORY, not its display name.** ``name.txt`` is not
    unique: a working tree and a copy of it share one, which is the ordinary case
    here -- ``RandyReid`` and its testing copy. Grouping by name alone put two
    trees in one folder, so twenty backups of the second would prune away the
    first's recovery points **and leave its journal records pointing at files
    that no longer exist.**

    ⭐ The display name is kept in the folder name because the owner has to
    recognise it under stress; the directory's own identity is what makes it
    unique. Gramps names each tree directory with an opaque id, which is exactly
    the stable identity wanted here.
    """
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tree_name) or "tree"
    identity = os.path.basename(os.path.normpath(tree_dir)) if tree_dir else ""
    identity = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in identity)
    folder = f"{safe}-{identity}" if identity else safe
    return os.path.join(directory, folder, f"{stamp}-{safe}.sqlite")


def _uri(path: str) -> str:
    """A read-only SQLite URI for ``path``, with the path PERCENT-ENCODED.

    ⛔ **A path is not a URI.** One containing ``?`` or ``#`` -- both legal in a
    filename on Unix, and neither exotic in a genealogy folder -- is parsed as a
    query string or a fragment, so the connection silently opens **a different
    file**: the truncated prefix. That can refuse a valid tree, or worse,
    successfully verify a copy of the wrong database while the intended tree is
    written to.
    """
    from urllib.parse import quote

    return "file:" + quote(str(path).replace("\\", "/"), safe="/:") + "?mode=ro"


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
        except _TookTooLong as refusal:
            last = str(refusal)
            discard(destination)
            continue
        except Exception as failure:  # noqa: BLE001 -- reported, never swallowed
            last = f"{type(failure).__name__}: {failure}"
            discard(destination)
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


class _TookTooLong(Exception):
    """A single attempt ran past its wall clock. ⛔ There is no page budget."""


def _one_attempt(source: str, destination: str) -> int:
    """One copy, bounded by a wall clock. Returns the pages moved in the last pass.

    ⛔ **THE PAGE BUDGET IS DELETED, AND WAS NOT REPLACED IN KIND.** It was
    rewritten three times and never once fired:

    1. ``pages`` was the step SIZE, described as the budget;
    2. ``total - remaining`` is per-pass, so it never accumulated;
    3. a restart at exactly one chunk gives ``progressed == this_pass``, not
       less, so the discarded pass was never banked.

    ⚠️ **Each fix was correct about the previous defect and the mechanism still
    could not fire**, because it was a PROXY: it inferred *this is taking too
    long* from SQLite's restart bookkeeping, where ``total`` and ``remaining``
    reset on every restart. **A quantity that resets cannot accumulate a bound.**

    ⭐ **A wall clock says the thing directly** -- *do not hang the owner* -- in
    one comparison against ``time.monotonic()``, and the refuse-to-arm path
    already turns that into a refusal the owner sees.

    ⚠️ **The trade, recorded rather than glossed: a clock cannot distinguish
    SLOW from LIVELOCKED.** It does not need to. The outcome is identical -- the
    write does not proceed and the owner is told -- and the measured real
    workload restarts **zero** times: 24 MB, 113 ms, attempt 1, one page each.
    The livelock was only ever produced by an artificial continuous writer
    against a scratch copy.

    ⛔ Enforced from inside the progress callback because ``Connection.backup()``
    runs to completion in a single call: ``pages`` sets the step size and does
    **not** make it return partway, so raising is the only way to stop it.
    """
    deadline = time.monotonic() + SECONDS_PER_ATTEMPT
    moved = 0

    # ⛔ Read-only, and opened HERE so it belongs to the calling thread.
    with contextlib.closing(sqlite3.connect(_uri(source), uri=True)) as reader:

        def progress(status: int, remaining: int, total: int) -> None:
            nonlocal moved
            moved = max(0, total - remaining)
            if time.monotonic() > deadline:
                raise _TookTooLong(
                    f"the copy did not finish within {SECONDS_PER_ATTEMPT:g} s. "
                    "Either the tree is very large or it is being written to "
                    "faster than it can be read."
                )

        with contextlib.closing(sqlite3.connect(destination)) as writer:
            reader.backup(writer, pages=PAGES_PER_STEP, progress=progress)
    return moved


def discard(path: str) -> None:
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
        with contextlib.closing(sqlite3.connect(_uri(path), uri=True)) as taken:
            row = taken.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
    except Exception:
        return False


def prune(directory: str, keep: int | None = None) -> list[str]:
    """Drop all but the newest ``keep`` backups. Returns what was removed.

    ⛔ **Called only AFTER a successful backup**, so a failed one can never
    destroy the last good copy. ⚠️ Ordered by NAME rather than mtime, because the
    names begin with a UTC timestamp and a copied file's mtime is not its age.

    ⚠️ **``keep`` defaults to ``None`` and resolves to ``RETAIN`` HERE, not in the
    signature.** A default bound at definition time cannot be changed by setting
    the module constant -- so the retention limit would have been unadjustable in
    practice, and a test that set ``RETAIN`` would have passed while proving
    nothing.
    """
    if keep is None:
        keep = RETAIN
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
