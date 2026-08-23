"""R7's backup: it takes a copy, or it refuses -- and it never does neither.

⭐ **This is R4's replacement guarantee.** The downgrade R4 approved --
*"unwritable-by-construction to recoverable-after"* -- is payable only if a backup
exists and can be restored. Everything here exists to make that true rather than
asserted.

⚠️ **Nothing here needs Gramps.** The module takes a path.
"""

from __future__ import annotations

import sqlite3
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


def test_the_page_budget_is_a_real_limit(tmp_path: Path, monkeypatch) -> None:
    """⛔ A3's page budget, and it has to be a NUMBER something can exceed.

    ⚠️ The plan first described ``PAGES_PER_STEP`` as though it were the budget.
    It is the step size: a callback that only counts steps has no count at which
    it fails, which made the criterion unimplementable.
    """
    source = _tree(tmp_path / "sqlite.db", rows=4000)
    monkeypatch.setattr(backup, "PAGE_BUDGET_MULTIPLE", 0.001)
    monkeypatch.setattr(backup, "PAGES_PER_STEP", 1)

    outcome = backup.take(str(source), str(tmp_path / "out" / "c.sqlite"))

    assert not outcome.ok
    assert "budget" in outcome.message
    assert "written faster than it can be read" in outcome.message


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
