"""R7's backup: it takes a copy, or it refuses -- and it never does neither.

⭐ **This is R4's replacement guarantee.** The downgrade R4 approved --
*"unwritable-by-construction to recoverable-after"* -- is payable only if a backup
exists and can be restored. Everything here exists to make that true rather than
asserted.

⚠️ **Nothing here needs Gramps.** The module takes a path.
"""

from __future__ import annotations

import os
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
    # ⛔ **This assertion was changed, deliberately, and here is why.**
    #
    # ⚠️ It used to read ``assert "RandyReid" in os.path.dirname(live)`` -- under
    # a comment insisting it tested the PROPERTY and not the shape of the key.
    # It tested the shape. And the shape was wrong: a folder named
    # ``{display}-{digest}`` moves when the display name moves, so renaming a
    # tree sent later backups to a new directory that ``prune`` -- given ONE
    # directory -- never saw again. The retention bound was defeated by the very
    # readability this line was protecting.
    #
    # ⭐ The requirement it stood for is real and is now met by a marker file
    # INSIDE the folder; see the rename and marker tests below. What is asserted
    # here is the property this test is actually named for.
    assert os.path.dirname(live) != os.path.dirname(copy)

    # ⛔ Two trees whose directories share a BASENAME under different roots must
    # also not merge. Keying on the basename alone would have passed the first
    # assertion and failed this one.
    import os.path as ntpath

    a = backup.destination_for("/bk", "Tree", "T", ntpath.join("rootA", "6a821852"))
    b = backup.destination_for("/bk", "Tree", "T", ntpath.join("rootB", "6a821852"))
    assert os.path.dirname(a) != os.path.dirname(b), (
        "two trees sharing a directory basename merged into one backup folder"
    )


def test_a_UNC_path_does_not_become_a_URI_AUTHORITY() -> None:
    """⛔ A path is not a URI, and ``//server/share`` is where that bites hardest.

    ``"file:" + "//NAS/family/..."`` parses ``NAS`` as the URI's **authority**,
    which SQLite rejects outright -- *invalid uri authority: NAS*. Every backup
    then refuses, so **every write refuses**, reported to the owner as a copy
    failure it is not.

    ⭐ Reproducible with no share present, because the rejection happens during
    URI parsing and never reaches the network -- which is exactly why it can be
    tested here at all.

    ⚠️ **What this asserts and what it does not.** That the URI parses is
    asserted. That SQLite then resolves a real share is NOT -- there is no UNC
    share on this machine to try, and claiming otherwise would be a check
    succeeding for a reason unrelated to its property.
    """
    backslash = chr(92)
    unc = backslash * 2 + "NAS" + backslash + "family" + backslash + "sqlite.db"

    slash = chr(47)
    authority_form = "file:" + slash * 2 + "NAS"

    uri = backup._uri(unc)
    assert not uri.startswith(authority_form), f"the server name became the URI authority: {uri}"
    assert "NAS" in uri, "the server name must survive somewhere in the path"

    try:
        sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as failure:
        assert "authority" not in str(failure), f"SQLite still rejects the authority: {failure}"

    # ⛔ And an ordinary drive path still reaches the canonical three-slash drive
    # form. ⚠️ Assembled rather than written out: the repository's own guard reads
    # a literal absolute path here as a real one, and it is right to.
    drive_form = "file:" + slash * 3 + "C:" + slash
    assert backup._uri("C:" + backslash + "trees" + backslash + "x.db").startswith(drive_form)


def test_prune_sweeps_partials_nothing_else_can_reach(tmp_path: Path) -> None:
    """⛔ A killed copy leaves a full-sized file that no other path can remove.

    ``discard`` never runs -- the process is gone -- and retention never matches
    it, because retention counts names ending ``.sqlite`` and a partial does not.
    So repeated crashes accumulate ~24 MB orphans **without bound**, while RETAIN
    reports the folder as bounded. A count that means something other than what
    it names.

    ⭐ Only partials older than several attempts are swept, so a copy running in
    another process right now is never removed.
    """
    old = tmp_path / "20260801T000000Z-T.sqlite.partial"
    old.write_text("an abandoned copy", encoding="utf-8")
    import os as _os

    stale = time.time() - (backup.SECONDS_PER_ATTEMPT * 10)
    _os.utime(old, (stale, stale))

    fresh = tmp_path / "20260824T000000Z-T.sqlite.partial"
    fresh.write_text("a copy running right now", encoding="utf-8")

    keeper = tmp_path / "20260824T000000Z-T.sqlite"
    keeper.write_text("a real backup", encoding="utf-8")

    removed = backup.prune(str(tmp_path), keep=20)

    assert not old.exists(), "the abandoned partial was left to accumulate"
    assert str(old) in removed, "a sweep that removes without reporting is a silent one"
    assert fresh.exists(), (
        "a partial young enough to be an in-flight copy was deleted -- that is a "
        "running backup destroyed by the cleanup"
    )
    assert keeper.exists(), "retention must not have touched the real backup"


def test_renaming_a_tree_does_not_scatter_its_retention(tmp_path: Path) -> None:
    """⛔ The folder is the tree's stable identity and NOTHING mutable.

    ⚠️ The folder used to be ``{display}-{digest}``, and the docstring above it
    claimed that renaming could no longer split a tree's retention. **It could.**
    The digest was stable and the prefix was not, so a rename sent later backups
    to a new directory -- and ``prune`` is given ONE directory, so it never saw
    the old one again. One tree's recovery points scattered across as many
    folders as it had ever had names, each separately inside ``RETAIN`` and the
    whole never inside it.

    ⭐ **The docstring asserted the property the code did not have**, which is why
    this is asserted here instead.
    """
    tree_dir = str(tmp_path / "grampsdb" / "abcd1234")

    before = backup.destination_for(
        str(tmp_path / "b"), "Family Tree", "20260823T000000Z", tree_dir=tree_dir
    )
    after = backup.destination_for(
        str(tmp_path / "b"), "Renamed Tree", "20260824T000000Z", tree_dir=tree_dir
    )

    assert Path(before).parent == Path(after).parent, (
        "renaming the tree moved its backups to a new folder, so prune will "
        "never consider the old one again and the retention bound is defeated"
    )

    # ⛔ And two DIFFERENT trees still get different folders -- the property the
    # digest was introduced for must survive the fix to the prefix.
    other = backup.destination_for(
        str(tmp_path / "b"),
        "Family Tree",
        "20260823T000000Z",
        tree_dir=str(tmp_path / "grampsdb" / "ffff9999"),
    )
    assert Path(before).parent != Path(other).parent, (
        "two distinct trees share a folder -- pruning one would delete the other's recovery points"
    )


def test_the_owner_can_still_tell_which_tree_a_folder_holds(tmp_path: Path) -> None:
    """⛔ Recognisable under stress, without putting a mutable name in the path.

    The ruling requires the owner be able to recognise the folder; correctness
    requires the folder name never change. The marker file satisfies both, and
    is refreshed each backup so it reflects the CURRENT name.
    """
    destination = backup.destination_for(
        str(tmp_path / "b"), "Family Tree", "20260823T000000Z", tree_dir=str(tmp_path / "t")
    )
    Path(destination).parent.mkdir(parents=True, exist_ok=True)

    backup.note_which_tree(destination, "Family Tree", str(tmp_path / "t"))
    marker = Path(destination).parent / backup.TREE_MARKER
    assert marker.exists(), "an opaque folder with nothing naming its tree"
    assert "Family Tree" in marker.read_text(encoding="utf-8")

    # ⭐ Renaming rewrites the label and moves nothing.
    backup.note_which_tree(destination, "Renamed Tree", str(tmp_path / "t"))
    assert "Renamed Tree" in marker.read_text(encoding="utf-8")
    assert marker.parent == Path(destination).parent


def test_a_BACKWARD_CLOCK_cannot_delete_the_copy_just_taken(tmp_path: Path) -> None:
    """⛔ Name order was standing in for creation order. They differ.

    An NTP correction, a restored VM snapshot or a dual-boot clock can stamp a
    copy taken NOW with a name that sorts first. With ``RETAIN`` copies already
    present it lands in the removal set and is deleted **immediately after the
    database write** -- leaving a journal record, written moments earlier and
    already fsynced, pointing at a file that no longer exists.

    ⚠️ **A comment in the caller asserted this could not happen**, on the grounds
    that the newest stamp always sorts last. That is a claim about the clock, not
    about the code. Protecting the copy by NAME removes the dependence entirely
    rather than assuming a better-behaved clock.
    """
    for n in range(1, 6):
        (tmp_path / f"2026-08-2{n}T000000Z-T.sqlite").write_text("older", encoding="utf-8")

    # The clock jumped backwards, so this run's copy sorts FIRST.
    just_taken = tmp_path / "2020-01-01T000000Z-T.sqlite"
    just_taken.write_text("the copy the journal already points at", encoding="utf-8")

    removed = backup.prune(str(tmp_path), keep=3, protect=str(just_taken))

    assert just_taken.exists(), (
        "the backup taken by THIS run was pruned away because a backward clock "
        "made it sort oldest -- the journal record written moments earlier now "
        "points at nothing, which is recoverable-after defeated at the instant "
        "it is needed"
    )
    assert str(just_taken) not in removed
    # ⭐ And retention still does its job on everything else.
    #
    # ⛔ **This assertion said 4 and was wrong.** ``keep`` is 3, so three files
    # is the bound being applied; four was the protected copy landing inside the
    # removal slice, being skipped, and **no replacement being chosen** -- the
    # defect, asserted as though it were the behaviour.
    #
    # ⚠️ The message above it already said *"protecting one copy must not stop
    # the bound applying to the rest"*, which is exactly what 4 means. **The
    # sentence and the number disagreed, and the sentence was the true one.**
    assert len(list(tmp_path.glob("*.sqlite"))) == 3, (
        "protecting one copy must not stop the bound applying to the rest: "
        "keep is 3, so 3 files survive"
    )


def test_a_BACKWARD_CLOCK_does_not_collapse_the_retention_WINDOW(tmp_path: Path) -> None:
    """⛔ Two changes each correct alone, and wrong together.

    Protecting the copy this run took, and selecting the removal slice by name
    order, were added in separate rounds. **Neither change's own tests could see
    the interaction**, and together they produced two distinct defects under a
    clock that had moved backward — an NTP correction, a restored VM snapshot, a
    dual boot:

    * **the count was not honoured.** The protected file landed inside the slice,
      was skipped, and no replacement was chosen — measured as
      ``removed: 0, files after: 21`` with ``RETAIN`` 20;
    * ⛔ **the window collapsed from RETAIN to one.** Each new recovery point
      sorted oldest and was deleted by the very next write, while the stale
      pre-rollback copies survived forever. **A journal record one write old
      already pointed at a deleted file** — which is recoverable-after defeated
      at the moment it is needed.

    ⭐ **This test exercises both changes at once, through the real name builder**,
    because that is the only way the interaction is visible. Reverting *either*
    fix fails it.
    """
    keep = 5
    tree = str(tmp_path / "grampsdb" / "abcd1234")
    root = str(tmp_path / "backups")

    # Five backups taken while the clock ran forward.
    seeded = []
    for day in range(1, keep + 1):
        destination = backup.destination_for(root, "T", f"202608{day:02d}T000000Z", tree_dir=tree)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        Path(destination).write_text("x", encoding="utf-8")
        seeded.append(destination)
    folder = os.path.dirname(seeded[0])

    # ⛔ Now the clock jumps backwards. Every copy below is genuinely the newest
    # recovery point, and every one of them asks for a stamp that sorts first.
    newest = []
    for day in range(1, 4):
        destination = backup.destination_for(root, "T", f"202001{day:02d}T000000Z", tree_dir=tree)
        Path(destination).write_text("the newest recovery point", encoding="utf-8")
        backup.prune(folder, keep=keep, protect=destination)
        newest.append(destination)

        surviving = [n for n in os.listdir(folder) if n.endswith(".sqlite")]
        assert len(surviving) == keep, (
            f"RETAIN is {keep} and the folder holds {len(surviving)}. Protecting a "
            f"file inside the removal slice without choosing a replacement shrinks "
            f"what retention removes."
        )

    # ⭐ And the half that matters more: every recovery point taken since the
    # rollback must still be there. A count that is right while the WRONG files
    # survive is the defect wearing the fix's clothes.
    for path in newest:
        assert Path(path).exists(), (
            f"{os.path.basename(path)} was pruned away by a later write. Under a "
            f"backward clock the newest copies sorted oldest, so the window "
            f"collapsed to one and a journal record one write old pointed at a "
            f"deleted file."
        )


def test_a_long_display_name_cannot_push_the_filename_past_the_component_limit(
    tmp_path: Path,
) -> None:
    """⛔ Every write for an otherwise valid tree was refused, and fail-closed.

    A filesystem component limit is **255 bytes**. A display name long enough
    made ``{stamp}-{unique}-{safe}.sqlite`` exceed it, so creating the copy raised
    and the write path refused — for a tree with nothing wrong with it.

    ⚠️ **The bound is on ENCODED BYTES, and that distinction is the finding.**
    120 accented characters is 153 characters and 273 bytes: inside the limit by
    the character count on Windows, past it by the byte count on Linux. **A bound
    counting the wrong unit is the same defect one layer down.**

    ⭐ What is truncated is decorative. Identity is the digest in the folder name
    and the marker file inside it, so nothing that distinguishes one tree from
    another is lost.
    """
    tree = str(tmp_path / "grampsdb" / "abcd1234")
    root = str(tmp_path / "backups")

    for label, display in (
        ("ascii", "A" * 300),
        ("multibyte", "é" * 120),
        ("mixed", ("naïve-" * 40)),
    ):
        destination = backup.destination_for(root, display, "20260824T000000Z", tree_dir=tree)
        name = os.path.basename(destination)

        assert len(name.encode("utf-8")) <= 255, (
            f"{label}: the filename is {len(name.encode('utf-8'))} BYTES, past the "
            f"component limit — every write for this tree would be refused"
        )

        # ⛔ And it must actually be creatable, not merely short enough on paper.
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        Path(destination).write_text("x", encoding="utf-8")
        assert Path(destination).exists(), f"{label}: could not create the copy"

        # ⚠️ Truncation must not split a character — a name that cannot round-trip
        # through UTF-8 is a name some tool will refuse later.
        assert name == name.encode("utf-8").decode("utf-8"), f"{label}: split a character"

    # ⭐ An ordinary name is untouched. A bound that mangles the common case to
    # survive the rare one has traded the wrong way.
    ordinary = backup.destination_for(root, "RandyReid-Testing", "20260824T000000Z", tree_dir=tree)
    assert "RandyReid-Testing" in os.path.basename(ordinary)

    # ⛔ Two trees whose names share a truncated prefix must still not collide —
    # identity is the digest, and truncating the decorative half must not reach it.
    long_a = backup.destination_for(root, "X" * 300, "20260824T000000Z", tree_dir=tree)
    long_b = backup.destination_for(
        root, "X" * 300, "20260824T000000Z", tree_dir=str(tmp_path / "grampsdb" / "ffff9999")
    )
    assert os.path.dirname(long_a) != os.path.dirname(long_b), (
        "two distinct trees with the same over-long display name share a folder"
    )


def test_verification_is_bounded_by_the_SAME_deadline_as_the_copy(tmp_path: Path) -> None:
    """⛔ The bound now covers the whole pre-write path, not just its first half.

    ⚠️ ``SECONDS_PER_ATTEMPT`` bounded the copy and **nothing bounded
    ``PRAGMA integrity_check``**, which ran afterwards on the same GTK main
    thread with no limit. So the advertised deadline did not describe the
    operation the owner waits through — the third attempt at this bound, each one
    bounding a smaller thing than it claimed.

    ⭐ ``set_progress_handler`` is what allows this without moving verification
    off the pre-write path: a non-zero return interrupts the running statement.

    ⚠️ **The alternative was reordering** — publish, write, then verify and warn.
    Recorded and not taken: it moves corruption detection to *after* the tree has
    changed, telling the owner their backup is unsound at the one moment they can
    no longer decline.
    """
    source = _tree(tmp_path / "source.db", rows=4000)

    # ⛔ A deadline already in the past: verification must refuse rather than run
    # to completion, and it must not raise.
    assert backup.verify(str(source), deadline=time.monotonic() - 1) is False, (
        "verification ignored an expired deadline and ran unbounded"
    )

    # ⭐ And with room, the same call still answers truthfully — a bound that
    # refuses everything would pass the assertion above and be useless.
    assert backup.verify(str(source), deadline=time.monotonic() + 30) is True
    assert backup.verify(str(source)) is True, "an unbounded call must still work"


def test_an_unsound_copy_is_still_refused_BEFORE_publication(tmp_path: Path) -> None:
    """⚠️ Bounding the check must not weaken what it decides.

    The point of verifying before publication is that an unsound copy never wears
    the final name even for an instant. A deadline that let a corrupt copy through
    would have traded the guarantee for the bound.
    """
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)

    assert backup.verify(str(corrupt)) is False
    assert backup.verify(str(corrupt), deadline=time.monotonic() + 30) is False, (
        "a corrupt copy passed verification when a deadline was supplied"
    )


def test_a_LONG_display_name_and_a_BACKWARD_CLOCK_together(tmp_path: Path) -> None:
    """⛔ Both changes to the filename, exercised in one construction.

    Two separate changes reach `` {stamp}-{unique}-{safe}.sqlite `` — the stamp is
    made **monotonic** so retention keeps the newest, and the display portion is
    **bounded in encoded bytes** so an over-long tree name cannot push the
    component past the filesystem limit. They were written in different rounds and
    landed through a conflict resolution.

    ⚠️ **A test covering one of them passes while the other is silently absent.**
    That is exactly how the retention collapse shipped: protecting the current
    copy and selecting by name order were each individually right, each
    individually tested, and wrong together.

    ⭐ So this asserts the properties **at the same time**: a display name well past
    the limit, several writes under a clock that has jumped backwards, and the
    **oldest** removed each time while every recent recovery point survives.
    """
    keep = 4
    tree = str(tmp_path / "grampsdb" / "abcd1234")
    root = str(tmp_path / "backups")
    display = "Ω" * 200  # 200 characters, 400 bytes — past the limit on its own

    seeded = []
    for day in range(1, keep + 1):
        destination = backup.destination_for(
            root, display, f"202608{day:02d}T000000Z", tree_dir=tree
        )
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        Path(destination).write_text("x", encoding="utf-8")
        seeded.append(destination)
    folder = os.path.dirname(seeded[0])

    # ⛔ The bound half: every name this run produced is creatable.
    for path in seeded:
        assert len(os.path.basename(path).encode("utf-8")) <= 255, (
            "the display-portion bound is missing — an over-long tree name pushed "
            "the filename past the component limit"
        )

    # ⛔ The monotonic half: under a backward clock the OLDEST goes, every time.
    taken_since_rollback = []
    for day in range(1, 4):
        destination = backup.destination_for(
            root, display, f"202001{day:02d}T000000Z", tree_dir=tree
        )
        Path(destination).write_text("newest recovery point", encoding="utf-8")
        removed = backup.prune(folder, keep=keep, protect=destination)
        taken_since_rollback.append(destination)

        assert len(os.path.basename(destination).encode("utf-8")) <= 255, (
            "a post-rollback name exceeded the component limit — the bound and the "
            "monotonic stamp do not both apply to the same construction"
        )
        assert len([n for n in os.listdir(folder) if n.endswith(".sqlite")]) == keep, (
            "retention is not holding at RETAIN with both changes in play"
        )
        assert removed, "nothing was removed, so the count is being met by not pruning"
        for gone in removed:
            assert gone not in taken_since_rollback, (
                f"{os.path.basename(gone)[:24]}… was taken after the rollback and was "
                f"pruned anyway — the monotonic stamp is not reaching this filename"
            )

    for path in taken_since_rollback:
        assert Path(path).exists(), (
            "a recovery point taken after the clock moved backwards was deleted by a "
            "later write — the window collapsed, with the byte bound present"
        )
