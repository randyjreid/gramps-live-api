"""Making a created path durable, and saying honestly which of three happened.

⛔ **This is the guard R4's guarantee rests on at the filesystem level.** A backup
whose directory entry never reached the disk is a backup that a power loss can
take while keeping the change it was meant to undo.

⚠️ **Windows cannot fsync a directory at all**, so the answer here is genuinely
three-valued. Collapsing it to a boolean made the guarantee unverifiable on the
only platform this runs on -- and the caller then had to ignore the signal to
function at all, which is the same as not having one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gramps_live_api.host import paths


def test_only_the_levels_THIS_RUN_created_are_flushed(tmp_path: Path) -> None:
    """⛔ The bound is *what this run created*, not a fixed number of levels.

    ⚠️ An earlier version walked **eight** levels toward the root, which is an
    enumeration wearing a bound's clothes and is wrong in both directions at
    once. Too far: it fsynced the tree directory, ``grampsdb``, the home
    directory and ``/`` -- none of them created here -- so one quirky ancestor on
    an NFS or FUSE mount returned FAILED and **refused every approved write**.
    Not far enough: a ninth created level was never flushed while SYNCED was
    reported, which is the same lie pointing the other way.
    """
    deep = tmp_path / "a" / "b" / "c" / "d" / "e"
    levels = paths.create_directory(str(deep))

    assert deep.is_dir(), "the directory must actually be created"
    # the five new levels, plus the pre-existing parent whose entry gained "a"
    assert len(levels) == 6, f"expected the created path and its parent, got {levels}"
    assert str(deep.resolve()) in [str(Path(x).resolve()) for x in levels]
    assert str(tmp_path.resolve()) in [str(Path(x).resolve()) for x in levels], (
        "the first PRE-EXISTING ancestor gained the topmost new level, so its own "
        "entry needs flushing too -- an unflushed parent loses the whole created "
        "path exactly as an unflushed leaf loses the file"
    )
    for level in levels:
        assert str(tmp_path.resolve()) in str(Path(level).resolve()), (
            f"{level} is above the created path and was never created by this run"
        )


def test_an_existing_directory_flushes_only_itself(tmp_path: Path) -> None:
    """⛔ Nothing was created, so nothing above it changed.

    Its entry in its parent is already durable; flushing the parent again would
    be work done to satisfy a rule rather than a property.
    """
    existing = tmp_path / "already"
    existing.mkdir()

    levels = paths.create_directory(str(existing))

    assert len(levels) == 1, f"only the directory itself, got {levels}"
    assert Path(levels[0]).resolve() == existing.resolve()


def test_a_flushable_directory_is_reported_honestly(tmp_path: Path) -> None:
    """Whatever this platform does, it must be one of the three and not FAILED."""
    levels = paths.create_directory(str(tmp_path / "fresh"))
    verdict = paths.durable_directory(levels)

    assert verdict in {paths.SYNCED, paths.UNSUPPORTED, paths.FAILED}
    assert verdict != paths.FAILED, (
        "an ordinary temp directory reported a genuine flush FAILURE, which "
        "would refuse every write on this machine"
    )
    if os.name == "nt":
        assert verdict == paths.UNSUPPORTED, (
            "Windows cannot open a directory as a descriptor, so the honest "
            "answer is 'this platform cannot', never 'it worked'"
        )


@pytest.mark.skipif(os.name == "nt", reason="the split only bites where the open is supported")
def test_a_REAL_failure_is_not_dressed_as_a_platform_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The class-3 instance found inside the code written to fix class 3.

    ``_flush_one`` reported **every** ``OSError`` from opening the directory as
    ``UNSUPPORTED`` -- so the label meant *the open did not work* rather than
    *this platform cannot do this*. On POSIX the open is always supported, so
    ``EMFILE``, ``EACCES`` and ``ENOENT`` are genuine failures, and calling them
    a platform limit walked them straight past the guard that refuses a write
    when the entry cannot be made durable.
    """
    real_open = os.open

    def refuses(path: object, *args: object, **kwargs: object) -> int:
        if str(path).endswith("target"):
            raise OSError(24, "Too many open files")
        return real_open(path, *args, **kwargs)  # type: ignore[arg-type]

    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(os, "open", refuses)

    assert paths.durable_directory([str(target)]) == paths.FAILED, (
        "fd exhaustion was reported as a platform limit, so the write proceeded "
        "past the very guard that exists to refuse it"
    )


@pytest.mark.skipif(os.name == "nt", reason="Windows has no POSIX modes; ACLs govern access")
def test_everything_this_code_creates_with_tree_data_is_OWNER_ONLY(tmp_path: Path) -> None:
    """⛔ A backup is the whole tree, privacy-filtered records included.

    ⚠️ Under the common ``022`` umask a directory is created ``0755`` and SQLite
    creates its destination ``0644``. On any shared POSIX machine that means
    **another local account can walk into the backup folder and read exactly the
    records the API refuses to show** — the protection the rest of this project
    exists to provide, undone by a default nobody chose.

    ⭐ Stated as a rule rather than a patch: *anything this code creates that
    holds tree data is owner-only.* The backup copy, the journal record, and the
    directories created to hold them.
    """
    created = tmp_path / "state" / "backups" / "abc123"
    levels = paths.create_directory(str(created))

    for level in levels:
        if Path(level).resolve() == tmp_path.resolve():
            continue  # pre-existing; its permissions are the owner's choice
        mode = os.stat(level).st_mode & 0o777
        assert mode == 0o700, (
            f"{level} is {oct(mode)} — another local account can traverse into "
            f"the backups and read the whole tree"
        )

    copy = created / "20260824T000000Z-x.sqlite"
    paths.create_file_owner_only(str(copy))
    mode = os.stat(copy).st_mode & 0o777
    assert mode == 0o600, (
        f"the backup file is {oct(mode)} — it contains every record the privacy "
        f"filtering hides, readable by any local account"
    )


def test_narrowing_never_touches_a_directory_this_run_did_not_create(tmp_path: Path) -> None:
    """⛔ The same list that bounds the flush bounds the permission change.

    Narrowing a directory the owner already had would change permissions they
    chose, on a path this code merely passed through.
    """
    outer = tmp_path / "theirs"
    outer.mkdir()
    before = os.stat(outer).st_mode & 0o777

    paths.create_directory(str(outer / "ours"))

    assert (os.stat(outer).st_mode & 0o777) == before, (
        "a pre-existing directory had its permissions changed"
    )
