"""R7's backup: it takes a copy, or it refuses -- and it never does neither.

⭐ **This is R4's replacement guarantee.** The downgrade R4 approved --
*"unwritable-by-construction to recoverable-after"* -- is payable only if a backup
exists and can be restored. Everything here exists to make that true rather than
asserted.

⚠️ **Nothing here needs Gramps.** The module takes a path.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
from pathlib import Path

from gramps_live_api.host import backup


def _tree(path: Path, rows: int = 500) -> Path:
    """A stand-in for a tree file: a real SQLite database with real pages."""
    connection = sqlite3.connect(path)
    connection.execute("create table person (handle text primary key, blob text)")
    connection.executemany(
        "insert into person values (?, ?)",
        [(f"h{n}", "x" * 200) for n in range(rows)],
    )
    connection.commit()
    connection.close()
    return path


def test_a_backup_is_taken_and_reads_back_sound(tmp_path: Path) -> None:
    source = _tree(tmp_path / "sqlite.db")
    destination = tmp_path / "out" / "copy.sqlite"

    outcome = backup.take(str(source), str(destination))

    assert outcome.ok, outcome.message
    assert destination.exists()
    assert backup.verify(str(destination)), "the copy does not pass integrity_check"


def test_every_row_survives_the_copy(tmp_path: Path) -> None:
    """⭐ A backup that loses rows is worse than none -- it looks like a backup."""
    source = _tree(tmp_path / "sqlite.db", rows=1200)
    destination = tmp_path / "out" / "copy.sqlite"

    assert backup.take(str(source), str(destination)).ok

    taken = sqlite3.connect(destination)
    original = sqlite3.connect(source)
    try:
        assert (
            taken.execute("select count(*) from person").fetchone()[0]
            == original.execute("select count(*) from person").fetchone()[0]
            == 1200
        )
    finally:
        taken.close()
        original.close()


def test_a_failed_backup_leaves_no_file_behind(tmp_path: Path, monkeypatch) -> None:
    """⛔ A truncated copy must never be mistaken for a backup.

    That is the one way *recoverable-after* fails **silently**: the owner sees a
    file, believes he is covered, and finds out otherwise at restore time.
    """
    source = _tree(tmp_path / "sqlite.db")
    destination = tmp_path / "out" / "copy.sqlite"

    monkeypatch.setattr(backup, "SECONDS_PER_ATTEMPT", -1.0)

    outcome = backup.take(str(source), str(destination))

    assert not outcome.ok
    assert not destination.exists(), "a partial copy was left on disk"
    assert "Nothing was written" in outcome.message


def test_the_clock_bound_fires_and_reports_why(tmp_path: Path, monkeypatch) -> None:
    source = _tree(tmp_path / "sqlite.db")
    monkeypatch.setattr(backup, "SECONDS_PER_ATTEMPT", -1.0)

    outcome = backup.take(str(source), str(tmp_path / "out" / "c.sqlite"))

    assert not outcome.ok
    assert "did not finish" in outcome.message
    assert outcome.attempts == backup.ATTEMPTS, "both attempts should have been spent"


def test_the_clock_is_the_ONLY_bound_and_it_fires(tmp_path: Path, monkeypatch) -> None:
    """⛔ The page budget is deleted. This is the test the demo could not be.

    A budget was written three times and **never once fired** -- and the
    in-Gramps demo passed all five of its checks anyway, **because the budget
    only failed under a continuously committing writer that no demo produced.**
    Green evidence over a dead bound.

    ⭐ So whatever replaces it needs a test that FIRES it. This one does: the
    clock is driven negative and the refusal must appear, by that name, on the
    owner-facing message.
    """
    source = _tree(tmp_path / "sqlite.db", rows=1200)
    monkeypatch.setattr(backup, "SECONDS_PER_ATTEMPT", -1.0)

    outcome = backup.take(str(source), str(tmp_path / "out" / "c.sqlite"))

    assert not outcome.ok
    assert "did not finish within" in outcome.message
    assert outcome.attempts == backup.ATTEMPTS, "both attempts should have been spent"
    assert not (tmp_path / "out" / "c.sqlite").exists(), "a partial copy survived"


def test_there_is_no_page_budget_left_to_get_wrong() -> None:
    """⛔ Structural: the mechanism is gone, not merely bypassed.

    Three rewrites of a bound that could not fire is a statement about the
    approach. A fourth version would be the fourth attempt at a proxy that
    infers *too long* from bookkeeping SQLite resets on every restart.
    """
    body = Path(backup.__file__).read_text(encoding="utf-8") if hasattr(backup, "__file__") else ""
    assert "PAGE_BUDGET_MULTIPLE" not in body
    assert "_page_count" not in body
    assert "_OverBudget" not in body


def test_a_missing_source_refuses_rather_than_raising(tmp_path: Path) -> None:
    """⛔ A refusal is a RESULT. The caller has to tell the owner either way."""
    outcome = backup.take(str(tmp_path / "nope.db"), str(tmp_path / "out" / "c.sqlite"))

    assert not outcome.ok
    assert outcome.path is None


def test_the_copy_is_taken_while_a_reader_holds_the_source(tmp_path: Path) -> None:
    """⭐ The whole point: Gramps has the tree open while this runs.

    Measured against the owner's real tree at 24 MB in 120 ms with Gramps holding
    it. This is the same shape, small enough for CI.
    """
    source = _tree(tmp_path / "sqlite.db", rows=800)
    holder = sqlite3.connect(source)
    holder.execute("select count(*) from person").fetchone()
    try:
        outcome = backup.take(str(source), str(tmp_path / "out" / "c.sqlite"))
    finally:
        holder.close()

    assert outcome.ok, outcome.message
    assert backup.verify(str(tmp_path / "out" / "c.sqlite"))


def test_it_runs_on_a_worker_thread(tmp_path: Path) -> None:
    """⚠️ ``sqlite3`` refuses a connection made on another thread.

    The connection is opened inside ``take`` for exactly this reason, and the call
    site runs it off the GTK loop -- so this is the shape that must work.
    """
    source = _tree(tmp_path / "sqlite.db")
    result: list[backup.Outcome] = []

    worker = threading.Thread(
        target=lambda: result.append(backup.take(str(source), str(tmp_path / "o" / "c.sqlite")))
    )
    worker.start()
    worker.join(timeout=30)

    assert not worker.is_alive(), "the worker did not finish"
    assert result and result[0].ok, result[0].message if result else "no outcome"


def test_pruning_keeps_the_newest(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    for n in range(6):
        (directory / f"2026-08-2{n}T000000Z-tree.sqlite").write_text("x", encoding="utf-8")

    removed = backup.prune(str(directory), keep=2)

    left = sorted(p.name for p in directory.iterdir())
    assert left == [
        "2026-08-24T000000Z-tree.sqlite",
        "2026-08-25T000000Z-tree.sqlite",
    ], f"pruning kept the wrong ones: {left}"
    assert len(removed) == 4


def test_pruning_orders_by_name_not_mtime(tmp_path: Path) -> None:
    """⚠️ A copied file's mtime is not its age.

    The names begin with a UTC timestamp precisely so ordering does not depend on
    a filesystem attribute that copying, syncing or restoring can rewrite.
    """
    directory = tmp_path / "backups"
    directory.mkdir()
    old = directory / "2026-01-01T000000Z-tree.sqlite"
    new = directory / "2026-12-31T000000Z-tree.sqlite"
    new.write_text("x", encoding="utf-8")
    time.sleep(0.01)
    old.write_text("x", encoding="utf-8")  # older NAME, newer mtime

    backup.prune(str(directory), keep=1)

    assert new.exists() and not old.exists(), (
        "pruning followed mtime, so the newest backup by name was deleted"
    )


def test_destination_names_sort_chronologically(tmp_path: Path) -> None:
    first = backup.destination_for(str(tmp_path), "RandyReid-Testing", "2026-08-22T010101Z")
    second = backup.destination_for(str(tmp_path), "RandyReid-Testing", "2026-08-23T010101Z")

    assert first < second, "lexical order must be chronological order"
    assert "RandyReid-Testing" in first


def test_a_tree_name_cannot_escape_its_directory(tmp_path: Path) -> None:
    """⛔ The name comes from the tree, and a path separator in it would put a
    backup somewhere nobody looks -- or somewhere that matters."""
    hostile = backup.destination_for(str(tmp_path), "../../etc", "2026-08-22T000000Z")

    assert ".." not in Path(hostile).relative_to(tmp_path).parts


def test_verify_rejects_something_that_is_not_a_database(tmp_path: Path) -> None:
    rubbish = tmp_path / "not.sqlite"
    rubbish.write_text("this is not a database", encoding="utf-8")

    assert not backup.verify(str(rubbish))
    assert not backup.verify(str(tmp_path / "absent.sqlite"))


# ⛔ ``test_pages_accumulate_across_restarts`` was DELETED with the page budget it
# served. Accumulating pages across restarts was only ever needed so a
# page-count multiple could be exceeded; with the bound gone, the accounting it
# tested has no consumer. **A test kept for a deleted mechanism is a test that
# passes about nothing.**


def test_a_path_with_uri_punctuation_is_not_silently_truncated(tmp_path: Path) -> None:
    """⛔ A path is not a URI.

    ``?`` and ``#`` are legal in a filename and not exotic in a genealogy folder.
    Interpolated into ``file:{path}?mode=ro`` they are parsed as a query string
    and a fragment, so the connection opens **a different file** -- the truncated
    prefix. That can refuse a valid tree, or **verify a copy of the wrong
    database** while the intended tree is written to.
    """
    # ⚠️ ``?`` is legal in a filename on Unix and ILLEGAL on Windows, so the full
    # case is only reachable on CI's Linux legs. ``#`` is legal on both, and it
    # is the fragment half of the same defect -- so something real is tested
    # everywhere and the whole of it is tested where it can be.
    name = "why not#here" if sys.platform == "win32" else "why? not#here"
    awkward = tmp_path / name
    awkward.mkdir()
    source = _tree(awkward / "sqlite.db", rows=300)
    destination = tmp_path / "out" / "copy.sqlite"

    outcome = backup.take(str(source), str(destination))

    assert outcome.ok, outcome.message
    assert backup.verify(str(destination))

    taken = sqlite3.connect(destination)
    try:
        assert taken.execute("select count(*) from person").fetchone()[0] == 300, (
            "the copy does not hold the source's rows -- a different file was opened"
        )
    finally:
        taken.close()


def test_two_trees_sharing_a_display_name_do_not_share_a_backup_folder() -> None:
    """⛔ ``name.txt`` is not unique, and the ordinary case here is two copies.

    Grouping by display name alone put a tree and its copy in one folder, so
    twenty backups of the second would prune away the first's recovery points
    **and leave its journal records pointing at files that no longer exist.**
    """
    import os

    live = backup.destination_for(
        "/bk", "RandyReid", "20260823T000000Z", os.path.join("g", "6a77aa4a")
    )
    copy = backup.destination_for(
        "/bk", "RandyReid", "20260823T000000Z", os.path.join("g", "6a821852")
    )

    assert os.path.dirname(live) != os.path.dirname(copy), (
        "a tree and its copy share a backup folder, so pruning one deletes the other's"
    )
    # ⭐ The display name survives in the folder, because the owner has to
    # recognise it under stress; the directory id is what makes it unique.
    assert "RandyReid" in os.path.dirname(live)
    assert "6a77aa4a" in os.path.dirname(live)
