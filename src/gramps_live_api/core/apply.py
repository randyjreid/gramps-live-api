"""The blessing that makes a Gramps tree writable.

⚠️ **This module imports no Gramps and no ``gi``, and it must not start.** The
Gramps object model is reached only out in ``gramps_plugin/``, which is the one
place in this project permitted to import ``gramps`` (``CONTRIBUTING.md``, the
recorded exception). What falls out of that is the point: ``mypy src`` needs no
Gramps stubs, and the check below is exercised by ordinary unit tests on a
runner that has never heard of Gramps.

⛔ **The write path that used to live here is gone with R9.** ``apply_operation``,
``verify_operation``, the ``Tree`` protocol, the approval digest, the undo
record pair and ``NOTE_TYPE_ATTRIBUTES`` all served the note flow, which is
retired; the document route writes inside Gramps through
``gramps_plugin/gramps_live_api_writer.py`` and journals through
``host/document.py``. **One thing did not go with it**, and it is load bearing
somewhere else:

* ``WritableCopy`` and ``authorise`` -- the blessing. ``host.accessor`` and the
  MCP server both hold a token before they touch a copy, and its constructor IS
  the check. There is no flag and no configuration key that reaches it.

⚠️ **``NOTE_TYPE_ATTRIBUTES`` went on a re-read of R9's first carve out, and an
earlier revision of this docstring said it stayed.** The carve out keeps the note
type TABLE, which is ``core/_note_types.py``; the map here was the note flow's
Gramps-spelling lookup and its only runtime reader was the retired apply route.
The document route reads ``core._note_types.ACCEPTED_NOTE_TYPES`` directly and
the writer carries its own inlined copy, bound to the table by test.

**What the blessing does NOT buy is coverage of a write.** It proves a directory
is a copy the owner blessed by hand; it proves nothing about ``DbTxn`` or about
anything being in the tree afterwards. Those are observable only on a machine
with Gramps, which is what ``tests/integration/test_round_trip.py`` is for.
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
