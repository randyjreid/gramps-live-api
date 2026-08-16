"""The record that makes a write reversible by hand, and what it costs to fail.

⚠️ **The pre-record is not logging.** It is the only artefact that lets the
owner undo this write himself, so a write with no record is exactly what the
rail exists to prevent -- which is why a record that cannot be written aborts
before the transaction opens rather than being noted and carried past.

The two failures are asymmetric on purpose, and the asymmetry is the whole
design:

* **before** the commit, a record that cannot be written aborts everything;
* **after** the commit, a record that cannot be written does NOT roll anything
  back. The commit stands, the handles are printed, and the exit is non-zero.
  The operator can reconstruct a record; they cannot reconstruct a handle they
  were never told.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gramps_live_api.core import apply, schema
from tests.fixtures.trees import MOMENT, blessed

APPROVED = "add a research note to person I0044: “Ashenmoor deed”"

OPERATION = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
    note_type="research",
    text="Ashenmoor deed",
)


def write(copy: apply.WritableCopy, *, moment: datetime = MOMENT) -> str:
    return apply.write_undo_record(
        copy,
        OPERATION,
        approved_preview=APPROVED,
        written_utc=moment,
        gramps_version="6.0.8",
    )


def test_the_record_lands_inside_the_tree_directory(tmp_path: Path) -> None:
    # Inside, for the same reason the sentinel is: it needs no second
    # configuration key, and it travels with the copy it describes.
    copy = blessed(tmp_path / "tree")

    stem = write(copy)

    assert Path(stem).parent == Path(copy.tree_dir) / apply.UNDO_DIRECTORY
    assert Path(stem).is_file()


def test_the_record_holds_what_a_hand_undo_needs(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")

    recorded = json.loads(Path(write(copy)).read_text(encoding="utf-8"))

    assert recorded["operation"] == schema.to_dict(OPERATION)
    assert recorded["approved_preview"] == APPROVED, (
        "the sentence the owner said yes to is what binds the approval to the "
        "write; a record without it says what was done and not what was agreed"
    )
    assert recorded["tree"] == copy.tree_dir
    assert recorded["written_utc"] == MOMENT.isoformat()
    assert recorded["gramps_version"] == "6.0.8"
    assert recorded["tool_version"]


def test_the_stem_separates_two_operations_written_in_one_second(tmp_path: Path) -> None:
    # A timestamp alone collides at one-second resolution, and a collision
    # aborts (below) -- so a second operation in the same second would be
    # refused for a reason that has nothing to do with it.
    copy = blessed(tmp_path / "tree")
    other = schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        note_type="todo",
        text="Quorvane deed",
    )

    stem = write(copy)
    second = apply.write_undo_record(
        copy, other, approved_preview=APPROVED, written_utc=MOMENT, gramps_version="6.0.8"
    )

    assert stem != second


def test_a_record_that_already_exists_aborts_rather_than_clobbers(tmp_path: Path) -> None:
    # Mode "x". Clobbering would destroy the only record of an earlier write,
    # which is a worse outcome than refusing this one.
    copy = blessed(tmp_path / "tree")
    write(copy)

    with pytest.raises(apply.UndoRecordRefused):
        write(copy)


def test_an_undo_directory_that_is_not_a_directory_aborts(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    (Path(copy.tree_dir) / apply.UNDO_DIRECTORY).write_text("", encoding="utf-8")

    with pytest.raises(apply.UndoRecordRefused):
        write(copy)


def test_the_record_is_forced_to_disk_before_anything_else_happens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A written record must not mean a record sitting in a buffer.

    A buffered record and a committed database change is the one ordering this
    whole mechanism exists to make impossible, and it is invisible until the
    machine loses power. So the call is asserted rather than assumed.
    """
    copy = blessed(tmp_path / "tree")
    synced: list[int] = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd) or real(fd))

    write(copy)

    assert synced, (
        "the undo record was flushed but never fsync'd, so a power loss can "
        "leave the database change on disk and the record that reverses it not"
    )


def test_the_result_record_lands_beside_the_pre_record(tmp_path: Path) -> None:
    # The handles cannot exist before the write, and they are what a hand-undo
    # actually needs -- so they are a second file rather than a rewrite of the
    # first, which would mean opening the only record for writing again.
    copy = blessed(tmp_path / "tree")
    stem = write(copy)

    written = apply.write_result_record(
        stem,
        apply.NoteWritten(
            note_handle="f00d1e5f00d1e5", note_gramps_id="N0021", person_handle="a1b2c3d4e5f607"
        ),
        written_utc=MOMENT,
    )

    recorded = json.loads(Path(written).read_text(encoding="utf-8"))
    assert recorded["note_handle"] == "f00d1e5f00d1e5"
    assert recorded["note_gramps_id"] == "N0021"
    assert recorded["person_handle"] == "a1b2c3d4e5f607"
    assert Path(written).parent == Path(stem).parent
    assert Path(written) != Path(stem)


def test_the_moment_is_read_in_utc(tmp_path: Path) -> None:
    # A local timestamp on a record whose whole job is to say when something
    # happened is a record that says it twice, differently, twice a year.
    moment = apply.utc_now()

    assert moment.tzinfo is timezone.utc
