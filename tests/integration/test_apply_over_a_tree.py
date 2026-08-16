"""A link cannot point a blessed name at a tree that was never blessed.

⚠️ **This is why ``os.path.realpath`` runs FIRST in ``WritableCopy``**, and it
needs a real link on a real filesystem to assert -- a unit test on ``tmp_path``
cannot make one without a process on Windows.

No skip and no platform branch in the assertion: a **junction** on Windows and a
**symlink** elsewhere are both created without special privilege, and both are
resolved by ``realpath``. (A Windows *symlink* is not: it needs a privilege this
machine does not grant, which is why the junction is used there.)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gramps_live_api.core import apply
from tests.fixtures.trees import blessed


def linked(name: Path, target: Path) -> None:
    """``name`` becomes another way to say ``target``, on either platform."""
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(name), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    os.symlink(target, name, target_is_directory=True)


def test_a_link_wearing_a_blessed_name_over_an_unblessed_tree_is_refused(tmp_path: Path) -> None:
    """The attack the realpath is for: a blessed NAME over the live tree.

    Without resolving first, the check would look at whatever the link is
    called and the write would land in whatever it points at -- which is the
    one thing this rail exists to prevent, dressed as a directory listing.
    """
    live = tmp_path / "live"
    live.mkdir()
    (live / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")
    disguise = tmp_path / "blessed-copy"
    linked(disguise, live)

    with pytest.raises(apply.UnblessedTree) as refusal:
        apply.authorise(str(disguise))

    assert apply.SENTINEL_NAME in str(refusal.value)


def test_a_link_to_a_blessed_copy_authorises_the_copy_it_resolves_to(tmp_path: Path) -> None:
    # The other direction, and it is the one that proves the token cannot be
    # laundered through a name: reaching a blessed copy by another route
    # produces a token carrying the RESOLVED path, which is what every later
    # comparison -- including the one against the open database -- uses.
    real = blessed(tmp_path / "copy")
    another_way = tmp_path / "also-the-copy"
    linked(another_way, Path(real.tree_dir))

    copy = apply.authorise(str(another_way))

    assert copy.tree_dir == real.tree_dir, (
        "a token reached through a link carries the link's own name, so a later "
        f"comparison against the open database would disagree with itself; got {copy.tree_dir}"
    )
