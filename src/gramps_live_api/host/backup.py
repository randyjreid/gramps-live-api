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
import hashlib
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass

from gramps_live_api.host import paths

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

ATTEMPTS = 1
"""⛔ **ONE attempt. The retry is gone.**

⚠️ **It froze the GTK loop for the whole budget on every failure.** Two five-second
attempts run inside one ``GLib.idle_add`` callback, so Gramps was unresponsive for
about **ten seconds** before it could show the refusal -- and the 108 ms
measurement bounds the SUCCESS path, saying nothing about the failure path the
timeout exists for. **That gap is exactly why this was invisible.**

⭐ Refuse-to-arm already exists and is the right answer to a failed backup. A
retry buys a rare success at the cost of a ten-second freeze every time one
fails, and the owner can simply propose again."""

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
    directory_synced: str = ""
    """``SYNCED``, ``UNSUPPORTED`` or ``FAILED`` for the backup's DIRECTORY ENTRY.

    ⛔ **Three answers, and the caller must READ it.** An earlier version added
    this field as a boolean and then never looked at it -- reporting a fact and
    ignoring it, which is the same defect as not measuring it. ``os.replace`` is
    atomic everywhere so the file is never half visible; what varies is whether
    the new directory entry survives a power loss."""

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

    # ⛔ Keyed on the FULL normalised directory, hashed -- not on its basename and
    # not on the display name.
    #
    # ⚠️ Basename plus display name is two weak keys, not one strong one: two
    # trees with the same basename under different roots still merge, and
    # renaming a tree splits its own retention across folders. A digest of the
    # absolute path cannot change under either.
    if tree_dir:
        absolute = os.path.normcase(os.path.abspath(os.path.normpath(tree_dir)))
        identity = hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:12]
        folder = f"{safe}-{identity}"
    else:
        folder = safe

    # ⛔ A collision-free suffix, and deliberately NOT more timestamp digits --
    # that is the same proxy failing at finer resolution, which is how the page
    # budget failed three times. Two previews in one second are two DIFFERENT
    # operations, so they get different identities rather than a finer clock.
    unique = uuid.uuid4().hex[:8]
    return os.path.join(directory, folder, f"{stamp}-{unique}-{safe}.sqlite")


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

    # ⛔ Copied under a name RETENTION DOES NOT COUNT, then published by rename.
    #
    # ⚠️ Writing straight to the final name meant a crash, a power loss or a
    # killed process during ``reader.backup()`` left a truncated file called
    # ``....sqlite`` -- **indistinguishable from a verified backup**, counted by
    # pruning, and offered to the owner as a recovery point. Exception cleanup
    # cannot help: the process is gone.
    #
    # ⭐ **A file under the final name now means COMPLETE, by construction.**
    partial = destination + ".partial"

    last = "no attempt was made"
    for attempt in range(1, ATTEMPTS + 1):
        moved = 0
        try:
            moved = _one_attempt(source, partial)
        except _TookTooLong as refusal:
            last = str(refusal)
            discard(partial)
            continue
        except Exception as failure:  # noqa: BLE001 -- reported, never swallowed
            last = f"{type(failure).__name__}: {failure}"
            discard(partial)
            continue

        # ⛔ Verified BEFORE publication, so an unsound copy never wears the
        # final name even for an instant.
        if not verify(partial):
            last = "the copy was taken and did not pass integrity_check"
            discard(partial)
            continue
        try:
            entry_durable = _publish(partial, destination)
        except OSError as failure:
            last = f"the copy could not be published: {failure}"
            discard(partial)
            continue
        return Outcome(
            ok=True,
            path=destination,
            message="backup taken",
            pages=moved,
            attempts=attempt,
            seconds=time.monotonic() - started,
            taken_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            directory_synced=entry_durable,
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


def _publish(partial: str, destination: str) -> str:
    """Make the finished copy visible under its final name. Returns
    ``paths.SYNCED``, ``paths.UNSUPPORTED`` or ``paths.FAILED`` for the DIRECTORY
    ENTRY.

    ⛔ **fsync THEN rename.** A rename is atomic, but it can be reordered ahead of
    the data on a crash -- which would publish a name whose contents are not
    there yet, the very state this exists to prevent.
    """
    # ⚠️ O_RDWR, not O_RDONLY. On Windows ``os.fsync`` requires a descriptor
    # opened for WRITING and fails with EBADF otherwise -- an
    # interpreter-and-platform-dependent behaviour, which is this project's
    # class 4, caught here by the test rather than by CI.
    # ⚠️ O_RDWR, not O_RDONLY. On Windows ``os.fsync`` requires a descriptor
    # opened for WRITING and fails with EBADF otherwise -- an
    # interpreter-and-platform-dependent behaviour, caught here by test.
    handle = os.open(partial, os.O_RDWR)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    os.replace(partial, destination)

    # ⛔ Whether the directory entry was made durable is REPORTED, not assumed.
    #
    # ⚠️ This previously suppressed every failure as an unsupported platform and
    # returned success -- **and Windows always takes that path**, because it
    # cannot open a directory as a descriptor at all. So the durability guarantee
    # was unverified on the only platform this actually runs on: a check
    # succeeding for a reason unrelated to the property it names, inside the
    # guarantee itself.
    #
    # ⭐ ``os.replace`` is atomic on both platforms -- the file is never half
    # visible. What is NOT established on Windows is that the new directory entry
    # survives a power loss, and the caller is told which it got rather than
    # being allowed to believe the stronger one.
    # ⛔ The whole created path, not just the leaf. A tree's FIRST backup creates
    # both ``backups/`` and ``backups/<tree>/``, and syncing only the leaf leaves
    # the entry for that leaf unflushed in its own parent.
    return paths.durable_directory(os.path.dirname(destination))


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
