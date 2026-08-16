"""Nothing is written to a tree that has not been blessed by hand.

⚠️ **This is the rail the whole slice rests on, and it is STRUCTURAL rather
than a check somebody remembers to call.** ``apply_operation`` demands a
``WritableCopy``, and the only way to hold one is to have passed the check
below. There is deliberately no flag, no configuration key and no argument that
reaches it -- the copy path is not an input to the decision, it is derived from
the directory the token was authorised over and cross-checked against the
database Gramps has already opened.

The sentinel lives **inside** the tree directory, beside ``name.txt``. A
sentinel placed beside the tree directory would sit in the folder that holds
every tree, and would bless the live one -- the exact inverse of the rail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gramps_live_api.core import apply


def bless(directory: Path) -> Path:
    """A directory shaped like a Gramps tree the owner has blessed by hand."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / apply.NAME_FILE).write_text("Invented Copy\n", encoding="utf-8")
    (directory / apply.SENTINEL_NAME).write_text("", encoding="utf-8")
    return directory


def test_a_blessed_directory_authorises(tmp_path: Path) -> None:
    copy = apply.authorise(str(bless(tmp_path / "tree")))

    assert isinstance(copy, apply.WritableCopy)
    assert Path(copy.tree_dir) == (tmp_path / "tree").resolve()


def test_a_tree_without_the_sentinel_is_refused(tmp_path: Path) -> None:
    # The ordinary case, and the one the owner watches happen: a real tree is
    # a directory carrying name.txt and nothing else of ours.
    unblessed = tmp_path / "tree"
    unblessed.mkdir()
    (unblessed / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")

    with pytest.raises(apply.UnblessedTree) as refusal:
        apply.authorise(str(unblessed))

    assert apply.SENTINEL_NAME in str(refusal.value), (
        "a refusal has to name the file that is missing, or the owner cannot "
        f"act on it; got {refusal.value}"
    )


def test_a_directory_that_is_not_a_tree_is_refused(tmp_path: Path) -> None:
    # The sentinel alone blesses nothing. Without name.txt this is not a tree,
    # and a token over it would be a token over an arbitrary directory.
    stray = tmp_path / "not-a-tree"
    stray.mkdir()
    (stray / apply.SENTINEL_NAME).write_text("", encoding="utf-8")

    with pytest.raises(apply.UnblessedTree) as refusal:
        apply.authorise(str(stray))

    assert apply.NAME_FILE in str(refusal.value)


def test_a_directory_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(apply.UnblessedTree):
        apply.authorise(str(tmp_path / "nowhere"))


def test_a_sentinel_that_is_a_directory_blesses_nothing(tmp_path: Path) -> None:
    # ``exists`` would be satisfied by a directory of that name, and a rail
    # satisfied by making a folder is not a rail.
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")
    (tree / apply.SENTINEL_NAME).mkdir()

    with pytest.raises(apply.UnblessedTree):
        apply.authorise(str(tree))


def test_the_token_cannot_be_built_around_the_check(tmp_path: Path) -> None:
    """The constructor IS the check, so there is no second way to hold one.

    ⚠️ **A checking function beside a plain dataclass is not this property.**
    It would leave ``WritableCopy(path)`` sitting there as an unchecked
    constructor, and the rail would then be "everybody calls ``authorise``"
    -- a convention, which is what this slice is trying not to rely on.
    """
    unblessed = tmp_path / "tree"
    unblessed.mkdir()
    (unblessed / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")

    with pytest.raises(apply.UnblessedTree):
        apply.WritableCopy(str(unblessed))


def test_the_token_carries_the_resolved_path(tmp_path: Path) -> None:
    # Every later comparison is against this value, so it is resolved once,
    # here, rather than at each site that compares it.
    bless(tmp_path / "tree")

    copy = apply.authorise(str(tmp_path / "tree" / "." / ".." / "tree"))

    assert Path(copy.tree_dir) == (tmp_path / "tree").resolve()
    assert copy.tree_dir == str(Path(copy.tree_dir).resolve())
