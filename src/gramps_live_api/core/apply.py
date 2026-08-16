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

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from gramps_live_api import __version__
from gramps_live_api.core.schema import Operation, to_dict

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


class UndoRecordRefused(ApplyError):
    """The record that would make this write reversible could not be written.

    Raised **before** the transaction opens, and it aborts the whole operation.
    A write nobody can reverse by hand is the outcome this rail exists to
    prevent, so the record is a precondition rather than a courtesy.
    """


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


# ---------------------------------------------------------------------------
# The undo record
#
# Inside the tree directory, for the reasons the sentinel is: it is derived
# from the one path the tool was given, it needs no second configuration key,
# it travels with the copy, and the blessing that authorised writing there at
# all covers it.
# ---------------------------------------------------------------------------

UNDO_DIRECTORY = ".gramps-live-api-undo"
"""Where the pair of records per apply lands, inside the tree directory."""

RECORD_FORMAT = 1
"""The record layout's own version, so a later reader can tell which it has."""

_STEM_DIGEST_LENGTH = 8
_RESULT_SUFFIX = ".result.json"


@dataclass(frozen=True, slots=True)
class NoteWritten:
    """What a completed write produced, and what a hand-undo needs to reverse it.

    None of it can exist before the write: Gramps mints the note's handle and
    its Gramps ID inside the transaction. That is why the result is a second
    record rather than a field of the first.
    """

    note_handle: str
    note_gramps_id: str
    person_handle: str


def utc_now() -> datetime:
    """The moment, in UTC. A local timestamp says it differently twice a year."""
    return datetime.now(timezone.utc)


def record_stem(operation: Operation, written_utc: datetime) -> str:
    """The basename both records of one apply share.

    The timestamp alone collides at one-second resolution, and a collision
    ABORTS -- so a second operation written in the same second would be refused
    for a reason that has nothing to do with it. The digest separates them.

    ⚠️ **Two IDENTICAL operations in the same second still collide, and the
    abort is correct there.** The record cannot distinguish them either, so
    writing the second one would produce two records nobody can tell apart over
    a tree that now holds two notes.
    """
    payload = json.dumps(to_dict(operation), sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_STEM_DIGEST_LENGTH]
    compact = written_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"{compact}-{digest}"


def write_undo_record(
    copy: WritableCopy,
    operation: Operation,
    *,
    approved_preview: str,
    written_utc: datetime,
    gramps_version: str,
) -> str:
    """Write the pre-record, force it to disk, and return the path it landed at.

    ⚠️ **Opened with mode ``"x"``.** A stem collision aborts rather than
    clobbers: overwriting would destroy the only record of an earlier write,
    which is worse than refusing this one.

    ⚠️ **``os.fsync`` before returning, and the caller opens no transaction
    until this has returned.** Otherwise "the record was written" can mean "the
    record is in a buffer" while the database change reaches the disk -- which
    is the one ordering this mechanism exists to make impossible, and it is
    invisible until the machine loses power.

    **What is NOT forced is the directory entry**, which has no portable
    spelling -- a directory cannot be ``fsync``'d on Windows. Recorded rather
    than carved around: the residual is a record whose bytes are durable and
    whose name may not be, on a crash in the same instant.
    """
    stem = os.path.join(copy.tree_dir, UNDO_DIRECTORY, record_stem(operation, written_utc))
    record = {
        "record": RECORD_FORMAT,
        "written_utc": written_utc.isoformat(),
        "tree": copy.tree_dir,
        "operation": to_dict(operation),
        "approved_preview": approved_preview,
        "gramps_version": gramps_version,
        "tool_version": __version__,
    }
    return _durably(f"{stem}.json", record)


def write_result_record(stem: str, written: NoteWritten, *, written_utc: datetime) -> str:
    """Write the result record beside ``stem``, and return the path it landed at.

    A second file rather than a rewrite of the first, so completing a record
    never means opening the only record of the write for writing again.
    """
    record = {
        "record": RECORD_FORMAT,
        "written_utc": written_utc.isoformat(),
        "note_handle": written.note_handle,
        "note_gramps_id": written.note_gramps_id,
        "person_handle": written.person_handle,
    }
    return _durably(_result_path(stem), record)


def _result_path(stem: str) -> str:
    root, _, _ = stem.rpartition(".json")
    return f"{root}{_RESULT_SUFFIX}"


def _durably(path: str, record: dict[str, object]) -> str:
    """Create ``path`` exclusively, write ``record``, and force it to disk."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as failure:
        raise UndoRecordRefused(f"{path}: {failure.strerror or failure}") from failure
    return path
