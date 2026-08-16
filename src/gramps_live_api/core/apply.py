"""Writing one agreed operation into a Gramps tree the owner has blessed.

⚠️ **This module imports no Gramps and no ``gi``, and it must not start.** The
Gramps object model is reached through ``Tree``, a protocol the plugin shim
implements out in ``gramps_plugin/`` -- which is the one place in this project
permitted to import ``gramps`` (``CONTRIBUTING.md``, the second recorded
exception). Two things fall out of that and both are the point: ``mypy src``
needs no Gramps stubs, and the ORDERING this module is really about -- authorise,
record, then write -- is exercised by ordinary unit tests on a fake tree, on a
runner that has never heard of Gramps.

**What that does NOT buy is coverage of the write.** A fake tree proves this
module drives a tree correctly; it proves nothing about ``DbTxn``, about the
plugin being registered, or about the note being there afterwards. Those are
observable only on a machine with Gramps and a blessed copy, and the demo is
what observes them. Green CI is not evidence this slice works.

The rail, stated once:

* ``WritableCopy`` is the only key to ``apply_operation``, and its constructor
  IS the check -- ``os.path.realpath`` first, then ``name.txt`` and the sentinel
  must both be files. There is no flag and no configuration key that reaches it.
* ``apply_operation`` re-derives the path from ``Tree.save_path()`` -- the
  database Gramps has already opened -- and refuses if it disagrees with the
  token. So a wrong ``-O`` argument cannot produce a write; it produces a
  refusal naming the path.
* The undo record is written and ``fsync``'d **before** the transaction opens,
  and a record that cannot be written aborts the whole thing. A write with no
  record is precisely what this rail exists to prevent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

SENTINEL_NAME = ".gramps-live-api-copy"
"""The file the owner creates by hand, INSIDE the tree directory.

⚠️ **Inside, not beside, and the reason is the rail itself.** Trees the owner
can open by name live as sibling directories under one parent, so a sentinel
placed beside a tree directory sits in that parent and blesses every tree in it
-- including the live one. Inside the tree directory it is per-tree and cannot
be confused.
"""

NAME_FILE = "name.txt"
"""What makes a directory a Gramps family tree, per ``gramps.cli.clidbman``.

Required as well as the sentinel: the sentinel says *this copy may be written*,
and this says *the thing being written is a tree*. A token over an arbitrary
directory carrying only a sentinel would be a token over an arbitrary directory.
"""


class ApplyError(Exception):
    """Something about this write is refused. Nothing has been written."""


class UnblessedTree(ApplyError):
    """The directory is not a copy the owner has blessed for writing."""


@dataclass(frozen=True, slots=True)
class WritableCopy:
    """Proof that a directory is a hand-blessed copy, and the only key to a write.

    ⚠️ **The constructor performs the check, rather than a function beside a
    plain dataclass doing it.** A checking helper next to an unchecked
    constructor leaves ``WritableCopy(anything)`` sitting there, and the rail
    degrades to "everybody remembers to call ``authorise``" -- a convention,
    which is what this slice exists not to rely on.

    ``os.path.realpath`` runs FIRST, so a junction or a symlink cannot point a
    blessed name at the live tree: what is checked and what is carried are the
    resolved path, and every later comparison is against that one value.
    """

    tree_dir: str

    def __post_init__(self) -> None:
        resolved = os.path.realpath(self.tree_dir)
        for required, why in (
            (NAME_FILE, "this is not a Gramps family tree directory"),
            (SENTINEL_NAME, "this tree has not been blessed for writing"),
        ):
            if not os.path.isfile(os.path.join(resolved, required)):
                raise UnblessedTree(f"{resolved}: {why} -- {required} is not there")
        object.__setattr__(self, "tree_dir", resolved)


def authorise(tree_dir: str) -> WritableCopy:
    """The blessed-copy token for ``tree_dir``, or refuse and write nothing.

    A named function for the one construction, so a call site reads as the
    permission check it is. It adds nothing to ``WritableCopy`` and cannot: the
    check is in the constructor, deliberately.
    """
    return WritableCopy(tree_dir)
