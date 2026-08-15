r"""The derivation script's own properties -- offline, over synthetic lines.

⚠️ **What is under test here is a VERIFICATION MECHANISM, not a guard.** The
script claims to refuse rather than emit a partial table, and the committed
table is checked by re-fetching the two artifacts, re-running it and reading an
empty diff. A line it silently misreads therefore costs more than a wrong row:
the fabricated row is visible in that diff and **the omitted one is not.** That
is the failure this module has already been bitten by, which is why the source
files it reads are the ones stating every range explicitly rather than the
primary file that expresses two whole categories as ``First``/``Last`` row
pairs.

⚠️ **No network, and no fetched artifact.** These lines are assembled here, so
the property is asserted on every run rather than on the days somebody has the
two files to hand. The committed table is checked separately, by hand, against
the digests recorded in the derivation note.

The script is not an importable module -- it is a hand-run build step in
``scripts/`` -- so it is loaded by path, exactly as C1's derivation test loads
its own. Making it importable would mean a package restructure, and it is
neither part of the guard nor allowed to become one.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "derive_unrenderable.py"

_VERSION = "9.9.9"
"""An invented Unicode version. No published standard carries it."""

_SOURCE = "an-invented-artifact"
"""What the refusals below name. Never a path, and never a real file name."""


def _derivation() -> ModuleType:
    """The script, loaded by path under a name that is not ``__main__``.

    Under ``__main__`` the module's own guard would run ``main`` on pytest's
    argument list, which is a confusing way to discover that a script has one.
    """
    specification = importlib.util.spec_from_file_location("_unrenderable_derivation", _SCRIPT)
    assert specification is not None and specification.loader is not None, (
        f"the derivation script is not loadable from {_SCRIPT}"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _document(*lines: str, version: str = _VERSION) -> str:
    """One artifact: the header line the UCD files carry, then ``lines``."""
    return "\n".join((f"# InventedProperties-{version}.txt", *lines)) + "\n"


def _row(first: int, last: int | None = None, *fields: str) -> str:
    """One data line in the shape both artifacts write, with a trailing comment.

    The comment is always present in the published files and is always ignored,
    so writing the fixtures without one would leave the commonest shape untested.
    """
    range_text = f"{first:04X}" if last is None else f"{first:04X}..{last:04X}"
    return f"{range_text}          ; {'; '.join(fields)} # an invented annotation"


_MADE_UP = "Invented_Property_Nobody_Publishes"
"""A property name the script wants nothing to do with, so its rows are read and dropped."""


def test_a_line_the_parser_cannot_read_stops_the_derivation() -> None:
    """The fail-closed guarantee, asserted NON-VACUOUSLY.

    ⚠️ **This is what stops the repair being a pattern that matches
    everything.** A row shape widened to whatever appears in that position would
    pass every other test here and destroy the guarantee outright: the script
    would emit a plausible-looking row for an unreadable line instead of
    refusing, and a range silently dropped is exactly what a re-derivation diff
    cannot show.
    """
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.rows(_document("0041 the wrong shape entirely"), _SOURCE)

    assert "would silently omit" in str(refusal.value), (
        f"an unreadable line stops the derivation and says why: {refusal.value}"
    )
    assert _SOURCE in str(refusal.value), (
        f"a refusal that does not name the artifact is one nobody can act on: {refusal.value}"
    )


def test_an_unreadable_line_anywhere_in_a_file_stops_the_derivation() -> None:
    """Quantified over POSITION, so no position is special.

    ⚠️ A check placed after the scan is correct exactly when the unreadable text
    is the LAST thing in the file -- which is the one position a reviewer's
    hand-written reproduction tends to use. Start, middle and end each get
    asserted, and **the refusal must quote the first unreadable line** rather
    than whatever survived to the end, because that is the line somebody has to
    go and look at.
    """
    derivation = _derivation()
    unreadable = "0041 the wrong shape entirely"
    readable = (_row(0x0042, None, "Cf"), _row(0x0043, 0x0044, "Cf"))
    passed = []

    for position in range(len(readable) + 1):
        lines = list(readable)
        lines.insert(position, unreadable)
        try:
            read = derivation.rows(_document(*lines), _SOURCE)
        except SystemExit as refusal:
            if unreadable not in str(refusal):
                passed.append(f"{position}: refused without quoting it -- {refusal}")
        else:
            passed.append(f"{position}: {read}")

    assert passed == [], (
        f"an unreadable line stops the derivation wherever it sits, and these were passed "
        f"over: {passed}"
    )


def test_every_readable_line_is_read_whole_and_in_order() -> None:
    """The non-vacuity partner, and neither can be satisfied by weakening the other.

    A pattern that quietly matches everything passes the test above and fails
    this one; a parser that refuses everything passes that one and fails this.
    The two together are what say the derivation reads a whole artifact and
    refuses the rest, rather than doing either one of those things well.

    Order is asserted, not just membership: the label precedence between the two
    sources is defined over the order rows arrive in, so a parser that returned
    a set would make the emitted table depend on nothing in particular.
    """
    derivation = _derivation()
    written = [(0x0042, 0x0042), (0x0043, 0x0044), (0x1F000, 0x1F00F)]
    misread = []

    for count in (2, 3):
        chosen = written[:count]
        read = derivation.rows(
            _document(*(_row(first, last, _MADE_UP) for first, last in chosen)), _SOURCE
        )
        expected = [(first, last, (_MADE_UP,)) for first, last in chosen]
        if read != expected:
            misread.append(f"{chosen} -> {read}")

    assert misread == [], f"a list of readable lines is read whole and in order: {misread}"


def test_a_single_code_point_and_a_range_are_both_read() -> None:
    # Both spellings occur throughout both artifacts, and a parser that read
    # only the range form would drop every single-code-point row -- which is
    # most of the format characters, silently.
    derivation = _derivation()

    read = derivation.rows(_document(_row(0x0042, None, _MADE_UP)), _SOURCE)

    assert read == [(0x0042, 0x0042, (_MADE_UP,))], (
        f"a single code point is the range that starts and ends at it: {read}"
    )


def test_a_row_carrying_an_enumerated_value_is_read_as_its_own_row() -> None:
    # ⚠️ The shape that would otherwise stop the derivation on a correct
    # artifact. DerivedCoreProperties.txt states enumerated properties as
    # `<range> ; <property>; <value>`, so a parser accepting exactly one field
    # after the range refuses a published file -- fail-closed, and useless.
    # The fields are read as they are written and the selection happens later.
    derivation = _derivation()

    read = derivation.rows(_document(_row(0x0042, None, _MADE_UP, "Linker")), _SOURCE)

    assert read == [(0x0042, 0x0042, (_MADE_UP, "Linker"))], (
        f"a property with an enumerated value is one row of two fields: {read}"
    )


def test_a_comment_or_a_blank_line_is_skipped_without_being_read() -> None:
    # Both artifacts are mostly commentary, and the `@missing` annotations the
    # format defines are comments too. Skipping them is not the same as reading
    # them: a row list that held them would carry them into the table.
    derivation = _derivation()

    read = derivation.rows(
        _document("", "# a remark", "   ", "# @missing: 0000..10FFFF; Invented; None", ""), _SOURCE
    )

    assert read == [], f"comments and blank lines are not rows: {read}"


def test_the_declared_version_is_read_from_the_artifact_itself() -> None:
    # The whole reason these two files are the sources rather than the primary
    # one: each states its own version, so the provenance note records what the
    # artifact says instead of what its URL implied.
    derivation = _derivation()

    assert derivation.declared_version(_document(), _SOURCE) == _VERSION


def test_an_artifact_declaring_no_version_stops_the_derivation() -> None:
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.declared_version("# no version anywhere\n", _SOURCE)

    assert _SOURCE in str(refusal.value), (
        f"a refusal that does not name the artifact is one nobody can act on: {refusal.value}"
    )


def test_two_artifacts_declaring_different_versions_stop_the_derivation() -> None:
    # ⚠️ Two files from different releases produce a table that is a fact about
    # neither. It is a plausible mistake -- one refetched, one not -- and it
    # leaves no trace in the output, so it is refused rather than reported.
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.agreed_version(
            [(_SOURCE, _document()), ("another-invented-artifact", _document(version="8.8.8"))]
        )

    assert _VERSION in str(refusal.value) and "8.8.8" in str(refusal.value), (
        f"the refusal names both declared versions: {refusal.value}"
    )


def test_the_general_category_wins_where_the_two_sources_overlap() -> None:
    # The documented precedence, asserted rather than left to dictionary order.
    # A code point that is both `Cf` and default-ignorable -- most of them are --
    # is labelled with its category, because that is the more specific published
    # fact and a refusal message reads better for naming it.
    derivation = _derivation()
    category = derivation.UNRENDERABLE_CATEGORIES[1]

    labels = derivation.labelled(
        derivation.rows(_document(_row(0x0042, None, category)), _SOURCE),
        derivation.rows(_document(_row(0x0042, None, derivation.DEFAULT_IGNORABLE)), _SOURCE),
    )

    assert labels == {0x0042: category}, (
        f"the general category is the label where a code point has both: {labels}"
    )


def test_a_default_ignorable_code_point_with_no_wanted_category_keeps_its_property() -> None:
    # The other half of the same rule, and round 4's finding in miniature: a
    # code point that is default-ignorable and NOT in the Other group is in the
    # class, labelled by the property that put it there.
    derivation = _derivation()

    labels = derivation.labelled(
        [], derivation.rows(_document(_row(0x0042, None, derivation.DEFAULT_IGNORABLE)), _SOURCE)
    )

    assert labels == {0x0042: derivation.DEFAULT_IGNORABLE}, (
        f"a default-ignorable code point outside the Other group is in the class: {labels}"
    )


def test_a_category_the_class_does_not_want_is_not_in_the_table() -> None:
    # ⚠️ Unassigned is where this matters. `Cn` is stated explicitly in the
    # general-category artifact -- it is not absent from it -- so what keeps it
    # out of the table is that the wanted set does not name it. There is no
    # `!= "Cn"` clause anywhere to get wrong, and no readable category reaches
    # the table either.
    derivation = _derivation()

    labels = derivation.labelled(
        derivation.rows(_document(_row(0x0042, None, "Cn"), _row(0x0043, None, "Lo")), _SOURCE), []
    )

    assert labels == {}, f"only the wanted categories reach the table: {labels}"


def test_adjacent_code_points_sharing_a_label_become_one_run() -> None:
    derivation = _derivation()

    assert derivation.runs({0x41: "Cf", 0x42: "Cf", 0x43: "Cf"}) == [(0x41, 0x43, "Cf")]


def test_adjacent_code_points_with_different_labels_stay_apart() -> None:
    # The coalesce must not merge across labels: the label is what the refusal
    # message names, so a run that swallowed its neighbour would name the wrong
    # published fact.
    derivation = _derivation()

    assert derivation.runs({0x41: "Cf", 0x42: "Cc"}) == [(0x41, 0x41, "Cf"), (0x42, 0x42, "Cc")]


def test_a_gap_between_two_code_points_breaks_a_run() -> None:
    derivation = _derivation()

    assert derivation.runs({0x41: "Cf", 0x43: "Cf"}) == [(0x41, 0x41, "Cf"), (0x43, 0x43, "Cf")]


def test_emitting_twice_over_the_same_input_is_byte_identical() -> None:
    # ⚠️ The property the whole verification story rests on. Verification is
    # re-fetch, compare digest, re-run, and read an empty diff -- so anything
    # that varies between two runs over the same inputs makes that check report
    # a difference that is not one. A timestamp is the obvious way to break it,
    # which is why the script emits none.
    derivation = _derivation()
    digests = [(_SOURCE, "0" * 64)]
    ranges = [(0x41, 0x43, "Cf")]

    assert derivation.emit(digests, _VERSION, ranges) == derivation.emit(digests, _VERSION, ranges)


def test_the_emitted_module_carries_no_date() -> None:
    # A fetch date is a fact about a fetch rather than about a standard, and
    # stamping one here would make every re-derivation differ from the file it
    # is checking. Dates belong to the note.
    derivation = _derivation()

    emitted = derivation.emit([(_SOURCE, "0" * 64)], _VERSION, [(0x41, 0x43, "Cf")])

    assert re.search(r"\d{4}-\d{2}-\d{2}", emitted) is None, (
        f"the emitted module carries a date: {emitted}"
    )
