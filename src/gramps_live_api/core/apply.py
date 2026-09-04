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
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Protocol

from gramps_live_api import __version__
from gramps_live_api.core import _note_types
from gramps_live_api.core.schema import (
    AddNote,
    ObjectRef,
    Operation,
    to_dict,
    type_name_of,
    validate,
)

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


class UnsupportedOperation(ApplyError):
    """An operation type this slice does not write. Named, not silently skipped."""


class UnsupportedTarget(ApplyError):
    """A target object type this slice does not write.

    ``AddNote.target`` may name any of the nine primary types. This slice
    implements ``person`` and refuses the other eight, because a dispatch table
    across nine get-and-commit pairs is the generalisation the brief says to
    resist and the demo is about a person.
    """


class NotWellFormed(ApplyError):
    """``validate`` rejects this operation, so nothing is written.

    The front end validates before it previews. This is the same judge again at
    the write boundary, because the operation crosses a process boundary in
    between, and a boundary is where a claim stops being checked.
    """


class ApprovalMismatch(ApplyError):
    """The sentence that was approved is not the sentence this operation renders.

    ⚠️ **The whole review model in one check.** The preview happens in the front
    end and the write happens inside Gramps, so the approved sentence arrives as
    a string beside the operation. Recording it proves what was shown; comparing
    it proves the two were about the same operation.
    """


class TargetNotFound(ApplyError):
    """The tree holds no object with that Gramps ID.

    ``RuleId.TARGET_DOES_NOT_EXIST``, declared PHASE_3 in ``schema`` and
    undecidable there, met for the first time now that there is a database.
    """


class TargetDisagrees(ApplyError):
    """The reference's two halves name two different objects.

    Which half is authoritative is decided here: the **Gramps ID** is what a
    person supplied and what the preview showed them, so it is what resolves.
    The handle is machine identity, and if it names something else then the
    sentence that was approved and the object that would be written are not the
    same thing.
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
    digest = approval_digest(operation)[:_STEM_DIGEST_LENGTH]
    compact = written_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"{compact}-{digest}"


def approval_digest(operation: Operation) -> str:
    """A LOSSLESS fingerprint of exactly what would be written.

    ⚠️ **The approval used to be compared as a rendered sentence, and a sentence
    is lossy.** ``preview`` elides free text at 60 characters, so two operations
    sharing a 59-character prefix rendered identically and the comparison passed
    between them -- while the transaction wrote the whole of whichever it held.
    Everything past the limit was outside the approval entirely.

    A digest over the canonical serialisation has no such horizon: every field,
    at full length, in an order that does not depend on dictionary iteration.
    ``sort_keys`` is what makes it reproducible across processes, which is the
    only reason it can be compared across one.

    ⚠️ **Not a security boundary against a hostile front end**, and must not be
    read as one. Both sides derive from the same read of the same file, so this
    asserts that the operation reaching the write is the operation that was
    approved -- not that the operation is trustworthy. What makes the human's
    approval meaningful is ``schema.full_display`` showing them all of it.
    """
    payload = json.dumps(to_dict(operation), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


# ---------------------------------------------------------------------------
# The tree, as this module needs to see it
#
# ⚠️ **Four questions, and the Gramps object model is behind all four.** The
# adapter that answers them lives in ``gramps_plugin/`` and is the only code in
# this project that imports ``gramps``. Keeping the protocol this narrow is
# what lets `mypy src` run without Gramps stubs and lets the ordering above be
# tested on a runner that has never seen Gramps -- and it is also the honest
# boundary, because everything on the far side of it is what CI cannot reach.
# ---------------------------------------------------------------------------

TARGET_OBJECT_TYPE = "person"
"""The one object type this slice attaches a note to. See ``UnsupportedTarget``."""

OPERATION_TYPE = "add_note"
"""The one operation this slice writes. See ``UnsupportedOperation``."""

NOTE_TYPE_ATTRIBUTES: Mapping[str, str] = MappingProxyType(
    {
        attribute.lower(): attribute
        for attribute, _value, _key, _declared_in in _note_types.NOTE_TYPE_ROWS
        if attribute.lower() in _note_types.ACCEPTED_NOTE_TYPES
    }
)
"""``schema.NOTE_TYPES`` in the spelling ``gramps.gen.lib.NoteType`` uses.

⚠️ **Attribute NAMES rather than the integers behind them.** Gramps publishes
``NoteType.RESEARCH`` and ``NoteType.TODO`` as class attributes; their numeric
values are an implementation detail this repository has no business pinning, and
a renumbering would silently file every note under the wrong type. Looked up
with ``getattr`` in the shim, so a rename fails loudly there instead.

⛔ **DERIVED from the frozen table, and it used to be two entries typed here.**
Two was tractable to maintain by hand and ten is not, so the map now reads the
same rows the accepted set is computed from. ⭐ **Keyed off the accepted set
rather than recomputing the exclusion**, so there is one place that decides which
types are accepted and this is not a second one.

⚠️ **The spelling is the TABLE'S attribute name, not ``name.upper()``.** Those
agree for all twenty-nine rows today and a test asserts they still do, but a map
built by upper-casing would be asserting its own arithmetic rather than reading
what Gramps declares.

⚠️ **The old totality test is gone and this is where it went.** It asserted
``NOTE_TYPES - set(NOTE_TYPE_ATTRIBUTES)`` was empty, which cannot fail once both
sides come from one table: a test that cannot fail watches nothing. What the
totality actually rests on now is that every accepted attribute name exists on
the INSTALLED ``NoteType``, which needs Gramps and is asserted where Gramps is.
"""


@dataclass(frozen=True, slots=True)
class NoteIdentity:
    """What Gramps minted for a note inside the transaction."""

    handle: str
    gramps_id: str


@dataclass(frozen=True, slots=True)
class NoteSighting:
    """What a note looks like when read back in a fresh process."""

    text: str
    attached: bool


class Tree(Protocol):
    """The Gramps database, reduced to what one ``add_note`` needs."""

    def save_path(self) -> str:
        """Where the OPEN database lives. The rail reads this, never an argument."""

    def person_handle_of(self, gramps_id: str) -> str | None:
        """The handle of the person with that Gramps ID, or ``None``."""

    def transaction(self, message: str) -> AbstractContextManager[object]:
        """Gramps' own transaction, so undo and referential integrity are Gramps'."""

    def add_note_to_person(
        self, *, person_handle: str, note_type: str, text: str, transaction: object
    ) -> NoteIdentity:
        """Create the note and attach it, inside ``transaction``."""

    def note_on_person(self, *, note_handle: str, person_handle: str) -> NoteSighting:
        """Read the note back and say whether the person still carries it."""


@dataclass(frozen=True, slots=True)
class Applied:
    """What one completed write produced, including how its record went."""

    written: NoteWritten
    record: str
    result_record: str | None
    record_error: str | None
    """Set when the commit succeeded and its record did not. See ``apply_operation``."""


@dataclass(frozen=True, slots=True)
class Verified:
    """What a fresh process saw when it went looking for the note."""

    text_matches: bool
    attached: bool
    text: str


def apply_operation(
    operation: Operation,
    copy: WritableCopy,
    tree: Tree,
    *,
    approved_preview: str,
    approved_digest: str,
    gramps_version: str,
    written_utc: datetime | None = None,
) -> Applied:
    """Write ``operation`` into ``copy``, in the one order that is safe.

    The order is the design, and every step before the record leaves nothing
    behind:

    1. the token and the OPEN database must name the same tree;
    2. the operation must be one this slice writes, and well-formed;
    3. the approved DIGEST must be this operation's digest;
    4. the target must resolve, by Gramps ID, to exactly the handle it carries;
    5. **the undo record is written and forced to disk**;
    6. only then does the transaction open.

    ⚠️ **A ``WritableCopy`` is required and is still not sufficient.** It is
    proof about a directory; step 1 is what makes it proof about the database
    Gramps is actually holding. A wrong ``-O`` argument therefore produces a
    refusal naming the path rather than a write.

    ⚠️ **A result record that fails AFTER the commit does not roll anything
    back.** The change is committed, and discarding it silently would be a
    second write nobody approved. The handles come back with ``record_error``
    set; the caller prints them and exits non-zero. An operator can reconstruct
    a record and cannot reconstruct a handle they were never told.

    ⚠️ **``approved_preview`` no longer gates anything and is still REQUIRED.**
    Step 3 moved to the digest because a sentence is elided and a digest is not,
    and a reader meeting a parameter that no check consults will reasonably take
    the narrowing as licence to delete it. It is not: it carries **the exact
    sentence the operator was shown**, into the undo record, which is the only
    place that fact survives the process. The digest proves what was written;
    the sentence is what a human can read afterwards and recognise. They answer
    different questions and the record needs both.
    """
    moment = utc_now() if written_utc is None else written_utc
    _agrees(copy, tree)
    note, target = _writable(operation)
    # ⚠️ The DIGEST, not the sentence. A sentence is elided at 60 characters, so
    # comparing sentences let two operations sharing a 59-character prefix pass
    # for each other while the transaction wrote the whole of whichever it held.
    # The digest covers every field at full length.
    if approved_digest != approval_digest(note):
        raise ApprovalMismatch(
            "the approved operation is not this operation, so the "
            "approval and the write are not about the same thing"
        )
    person_handle = _resolved(target, tree)

    record = write_undo_record(
        copy,
        note,
        approved_preview=approved_preview,
        written_utc=moment,
        gramps_version=gramps_version,
    )

    with tree.transaction(f"gramps-live-api: {OPERATION_TYPE}") as transaction:
        identity = tree.add_note_to_person(
            person_handle=person_handle,
            note_type=NOTE_TYPE_ATTRIBUTES[note.note_type],
            text=note.text,
            transaction=transaction,
        )

    written = NoteWritten(
        note_handle=identity.handle,
        note_gramps_id=identity.gramps_id,
        person_handle=person_handle,
    )
    try:
        result_record = write_result_record(record, written, written_utc=moment)
    except UndoRecordRefused as failure:
        return Applied(
            written=written, record=record, result_record=None, record_error=str(failure)
        )
    return Applied(written=written, record=record, result_record=result_record, record_error=None)


def verify_operation(
    operation: Operation,
    copy: WritableCopy,
    tree: Tree,
    *,
    note_handle: str,
    person_handle: str,
) -> Verified:
    """Read the note back and say whether it is what was agreed.

    ⚠️ **Run in a SECOND, FRESH process, which is what makes it evidence.** The
    assertion then crosses the database file rather than a live object graph --
    the difference between "we wrote it" and "it is there".

    Two questions, and the second is the one an export-and-import round trip
    cannot ask: the note existing is not the note being *on* the person.
    """
    _agrees(copy, tree)
    note, _ = _writable(operation)
    sighting = tree.note_on_person(note_handle=note_handle, person_handle=person_handle)
    return Verified(
        text_matches=sighting.text == note.text,
        attached=sighting.attached,
        text=sighting.text,
    )


def _agrees(copy: WritableCopy, tree: Tree) -> None:
    """Refuse unless the token and the open database name the same tree."""
    open_tree = os.path.realpath(tree.save_path())
    if open_tree != copy.tree_dir:
        raise UnblessedTree(
            f"{open_tree}: the open database is not the copy this token authorises "
            f"({copy.tree_dir}), so nothing is written"
        )


def _writable(operation: Operation) -> tuple[AddNote, ObjectRef]:
    """``operation`` as the one thing this slice writes, or refuse by name.

    Returns the target alongside it rather than leaving the caller to re-read a
    field this has already proved is there -- an ``Optional`` that has been
    checked and then re-checked is two claims about one value.
    """
    type_name = type_name_of(operation)
    if type_name != OPERATION_TYPE or not isinstance(operation, AddNote):
        raise UnsupportedOperation(f"{type_name}: this slice writes {OPERATION_TYPE} only")
    if not validate(operation).well_formed:
        raise NotWellFormed("this operation is not well-formed, so nothing is written")
    target = operation.target
    if target is None or target.object_type != TARGET_OBJECT_TYPE:
        named = "nothing" if target is None else target.object_type
        raise UnsupportedTarget(
            f"{named}: this slice attaches a note to a {TARGET_OBJECT_TYPE} only"
        )
    return operation, target


def _resolved(target: ObjectRef, tree: Tree) -> str:
    """The handle of the person ``target`` names, or refuse and write nothing."""
    found = tree.person_handle_of(target.gramps_id)
    if found is None:
        raise TargetNotFound(
            f"{target.gramps_id}: this tree holds no {TARGET_OBJECT_TYPE} with that Gramps ID"
        )
    if target.handle != found:
        raise TargetDisagrees(
            f"{target.gramps_id}: the reference's handle names a different object, so "
            "the sentence that was approved and the object that would be written "
            "are not the same thing"
        )
    return found
