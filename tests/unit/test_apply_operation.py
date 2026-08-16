"""The one write, and everything it refuses before it opens a transaction.

⚠️ **What this file covers is the ORDERING and the REFUSALS, on a tree that is
not Gramps.** It cannot cover ``DbTxn``, the plugin registration, or the note
being there when the copy is next opened -- those need a machine with Gramps and
a blessed copy, and the demo is what observes them. Green here is not evidence
this slice works.

The order is the subject: agree with the open database, refuse what this slice
does not do, resolve the target, **write the record**, and only then open the
transaction. Each step before the record leaves nothing behind; the record is
the first thing that touches the copy at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gramps_live_api.core import apply, schema
from tests.fixtures.trees import MOMENT, FakeTree, blessed

OPERATION = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
    note_type="research",
    text="Ashenmoor deed",
)


def run(copy: apply.WritableCopy, tree: FakeTree, operation: schema.Operation = OPERATION):
    return apply.apply_operation(
        operation,
        copy,
        tree,
        approved_preview=schema.preview(operation),
        approved_digest=apply.approval_digest(operation),
        gramps_version="6.0.8",
        written_utc=MOMENT,
    )


def test_a_note_reaches_the_person_the_preview_named(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")

    applied = run(copy, tree)

    assert tree.written == [("a1b2c3d4e5f607", "RESEARCH", "Ashenmoor deed")], (
        "the write has to reach the person the sentence named, with the note "
        f"type mapped to what Gramps calls it; got {tree.written}"
    )
    assert applied.written.note_gramps_id == "N0021"
    assert applied.written.person_handle == "a1b2c3d4e5f607"


def test_the_record_is_on_disk_before_the_transaction_opens(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")

    applied = run(copy, tree)

    assert tree.records_when_the_transaction_opened == [Path(applied.record).name], (
        "the transaction opened over a copy carrying no undo record, so a crash "
        "at that moment leaves a change nobody can reverse by hand; saw "
        f"{tree.records_when_the_transaction_opened}"
    )


def test_the_result_record_lands_after_the_commit(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")

    applied = run(copy, tree)

    assert applied.record_error is None
    assert applied.result_record is not None
    recorded = json.loads(Path(applied.result_record).read_text(encoding="utf-8"))
    assert recorded["note_handle"] == applied.written.note_handle


def test_a_record_that_cannot_be_written_aborts_before_the_transaction(tmp_path: Path) -> None:
    # The whole reason the record comes first: if it cannot be written, nothing
    # is written at all. Not a warning, not a best effort.
    copy = blessed(tmp_path / "tree")
    (Path(copy.tree_dir) / apply.UNDO_DIRECTORY).write_text("", encoding="utf-8")
    tree = FakeTree(tmp_path / "tree")

    with pytest.raises(apply.UndoRecordRefused):
        run(copy, tree)

    assert "transaction opened" not in tree.events, (
        f"a transaction was opened after the record was refused; saw {tree.events}"
    )
    assert tree.written == []


def test_a_result_record_that_fails_does_not_roll_back_the_commit(tmp_path: Path) -> None:
    """The commit stands, and the handles are reported anyway.

    ⚠️ **The tempting repair is to roll the write back, and it is wrong.** The
    change is committed; discarding it silently is a second write nobody
    approved. The operator can reconstruct a record. They cannot reconstruct a
    handle they were never told.
    """
    copy = blessed(tmp_path / "tree")
    undo = Path(copy.tree_dir) / apply.UNDO_DIRECTORY
    undo.mkdir()
    (undo / f"{apply.record_stem(OPERATION, MOMENT)}.result.json").write_text("", encoding="utf-8")
    tree = FakeTree(tmp_path / "tree")

    applied = run(copy, tree)

    assert applied.written.note_handle == "f00d1e5f00d1e5", (
        "the handles are the one thing that cannot be reconstructed, so they "
        "are reported even when the record of them could not be written"
    )
    assert applied.record_error is not None
    assert applied.result_record is None
    assert tree.written


def test_a_token_for_one_tree_cannot_write_to_another(tmp_path: Path) -> None:
    """The load-bearing half of the rail: the path comes from the OPEN database.

    A token is proof about a directory. It is not proof about the database
    Gramps happens to be holding, and the two are different questions -- so a
    wrong ``-O`` argument produces a refusal naming the path, never a write.
    """
    copy = blessed(tmp_path / "blessed")
    elsewhere = tmp_path / "live"
    elsewhere.mkdir()
    tree = FakeTree(elsewhere)

    with pytest.raises(apply.UnblessedTree) as refusal:
        run(copy, tree)

    assert tree.written == []
    assert "transaction opened" not in tree.events
    assert str(elsewhere.resolve()) in str(refusal.value)


def test_a_target_that_is_not_a_person_is_refused_by_name(tmp_path: Path) -> None:
    # The narrowing this slice took on purpose: nine object types would be a
    # dispatch table across nine get-and-commit pairs, and the demo is about a
    # person. The refusal says which slice, so it reads as a boundary rather
    # than as a defect.
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")
    family = schema.AddNote(
        target=schema.ObjectRef(object_type="family", handle="7fd3a9c15e0842", gramps_id="F0007"),
        note_type="research",
        text="Ashenmoor deed",
    )

    with pytest.raises(apply.UnsupportedTarget) as refusal:
        run(copy, tree, family)

    assert "family" in str(refusal.value)
    assert tree.records_on_disk() == []


def test_an_operation_this_slice_does_not_write_is_refused(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")
    citation = schema.AddCitation(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        citation=schema.ObjectRef(
            object_type="citation", handle="e41b8c07a25fd3", gramps_id="C0042"
        ),
    )

    with pytest.raises(apply.UnsupportedOperation):
        run(copy, tree, citation)

    assert tree.records_on_disk() == []


def test_a_target_the_tree_does_not_hold_is_refused(tmp_path: Path) -> None:
    # PHASE_3's TARGET_DOES_NOT_EXIST, met for the first time: the rule the
    # schema declares and deliberately cannot decide. Nothing is recorded,
    # because nothing happened.
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree", people={})

    with pytest.raises(apply.TargetNotFound) as refusal:
        run(copy, tree)

    assert "I0044" in str(refusal.value)
    assert tree.records_on_disk() == []


def test_a_reference_whose_two_halves_disagree_is_refused(tmp_path: Path) -> None:
    """Which half of a reference is authoritative, decided at the boundary.

    The Gramps ID is what the human supplied and what the preview showed, so it
    is what resolves. The handle is machine identity, and if it names a
    different object then the sentence that was approved and the object that
    would be written are not the same thing -- which is the one disagreement
    this project exists to make impossible.
    """
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree", people={"I0044": "0000000000dead"})

    with pytest.raises(apply.TargetDisagrees):
        run(copy, tree)

    assert tree.records_on_disk() == []


def test_an_approval_for_a_different_operation_is_refused(tmp_path: Path) -> None:
    """The binding between what was agreed and what is written, made checkable.

    The front end previews in one process and the write happens in another, so
    the approval arrives beside the operation. The sentence is recorded, proving
    what was shown; the DIGEST is compared, proving they were about the same
    operation.
    """
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")
    other = schema.AddNote(
        target=OPERATION.target, note_type="research", text="an entirely different note"
    )

    with pytest.raises(apply.ApprovalMismatch):
        apply.apply_operation(
            OPERATION,
            copy,
            tree,
            approved_preview=schema.preview(other),
            approved_digest=apply.approval_digest(other),
            gramps_version="6.0.8",
            written_utc=MOMENT,
        )

    assert tree.written == []
    assert tree.records_on_disk() == []


def test_an_approval_whose_sentence_matches_but_whose_text_differs_is_refused(
    tmp_path: Path,
) -> None:
    """The defect this rework exists for, pinned as a negative control.

    ⚠️ **These two notes render to the SAME sentence.** ``preview`` elides free
    text at 60 characters, so two operations sharing a 59-character prefix are
    indistinguishable to a comparison over sentences -- and the transaction
    writes the whole of whichever it holds. The approval therefore covered the
    prefix and nothing after it.

    Comparing digests instead has no such horizon. Remove the digest check and
    restore the sentence comparison, and this test passes a fabricated note
    through an approval given for a different one.
    """
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")
    shared = "Marriage recorded in the parish register, second volume, page "
    approved = schema.AddNote(
        target=OPERATION.target,
        note_type="research",
        text=shared + "141. Confirmed against the original.",
    )
    written = schema.AddNote(
        target=OPERATION.target,
        note_type="research",
        text=shared + "141. FABRICATED: inheritance passes to the other line.",
    )
    assert schema.preview(approved) == schema.preview(written), (
        "this test is meaningless unless the two sentences really are identical"
    )
    assert approved.text != written.text

    with pytest.raises(apply.ApprovalMismatch):
        apply.apply_operation(
            written,
            copy,
            tree,
            approved_preview=schema.preview(approved),
            approved_digest=apply.approval_digest(approved),
            gramps_version="6.0.8",
            written_utc=MOMENT,
        )

    assert tree.written == []
    assert tree.records_on_disk() == []


def test_an_operation_that_is_not_well_formed_never_reaches_the_tree(tmp_path: Path) -> None:
    # The front end validates before it previews. This is the same judge, at
    # the write boundary, because the operation crosses a process boundary in
    # between and a boundary is where a claim stops being checked.
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree")
    unregistered = schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
        note_type="musing",
        text="Ashenmoor deed",
    )

    with pytest.raises(apply.NotWellFormed):
        run(copy, tree, unregistered)

    assert tree.records_on_disk() == []


def test_every_note_type_the_schema_allows_has_a_gramps_spelling() -> None:
    """The mapping is total, or an operation ``validate`` passes cannot be written.

    ⚠️ **Asserted over ``schema.NOTE_TYPES`` rather than written out**, so a
    third note type fails here instead of failing at a terminal in front of the
    owner with a ``KeyError``.
    """
    missing = sorted(schema.NOTE_TYPES - set(apply.NOTE_TYPE_ATTRIBUTES))

    assert missing == [], (
        f"validate accepts these note types and the write cannot spell them: {missing}"
    )


def test_the_read_back_compares_the_text_and_the_backlink(tmp_path: Path) -> None:
    # Two questions, and the second is the one an XML round trip cannot ask:
    # the note existing is not the note being ON the person.
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree", text_read_back="Ashenmoor deed", attached=True)

    verified = apply.verify_operation(
        OPERATION, copy, tree, note_handle="f00d1e5f00d1e5", person_handle="a1b2c3d4e5f607"
    )

    assert verified.text_matches and verified.attached


def test_a_note_that_is_not_on_the_person_fails_the_read_back(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    tree = FakeTree(tmp_path / "tree", text_read_back="Ashenmoor deed", attached=False)

    verified = apply.verify_operation(
        OPERATION, copy, tree, note_handle="f00d1e5f00d1e5", person_handle="a1b2c3d4e5f607"
    )

    assert verified.text_matches
    assert not verified.attached, (
        "a note that exists and is attached to nothing is not what was agreed, "
        "and reporting it as verified is the failure this second read exists for"
    )


def test_the_read_back_refuses_a_tree_the_token_does_not_cover(tmp_path: Path) -> None:
    # Read-only, and still gated: it is a second process opening a database,
    # and the question of WHICH database is the same question.
    copy = blessed(tmp_path / "blessed")
    elsewhere = tmp_path / "live"
    elsewhere.mkdir()
    tree = FakeTree(elsewhere)

    with pytest.raises(apply.UnblessedTree):
        apply.verify_operation(
            OPERATION, copy, tree, note_handle="f00d1e5f00d1e5", person_handle="a1b2c3d4e5f607"
        )
