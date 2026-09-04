r"""The note-type derivation's own properties -- offline, over synthetic classes.

⚠️ **What is under test here is a VERIFICATION MECHANISM, not a guard.** The
script claims to refuse rather than emit a partial table, and a row it silently
drops is exactly what a re-derivation diff cannot show. That failure is not
hypothetical for this table: a first pass over ``notetype.py`` with a regexp for
``(NAME, _("Label"), "Key")`` returned **27 rows and looked complete**, having
skipped ``TODO`` and ``LINK`` -- which are written with the two-argument
translation call -- and ``todo`` is one of the two types the whole note flow
exists to write.

⚠️ **The fixtures here are written for the test, and are not a copy of Gramps'
vocabulary.** Names like ``BADGER`` and ``KETTLE`` appear nowhere in any Gramps
release. A fixture that reproduced the real rows would be a second tally of the
committed table, which is the counter bug this repository has already paid for.

⚠️ **No Gramps, and no installation.** These class bodies are assembled here, so
the properties are asserted on every run rather than on a machine that happens to
have Gramps on it. The committed table's agreement with a real installation is
the separate, skipping test in ``tests/integration``.

The script is not an importable module -- it is a hand-run build step in
``scripts/`` -- so it is loaded by path, exactly as the two existing derivation
tests load theirs.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "derive_note_types.py"

_SOURCE = "an-invented-artifact"
"""What the refusals below name. Never a path, and never a real file name."""


def _derivation() -> ModuleType:
    """The script, loaded by path under a name that is not ``__main__``.

    Under ``__main__`` the module's own guard would run ``main`` on pytest's
    argument list, which is a confusing way to discover that a script has one.
    """
    specification = importlib.util.spec_from_file_location("_note_type_derivation", _SCRIPT)
    assert specification is not None and specification.loader is not None, (
        f"the derivation script is not loadable from {_SCRIPT}"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _class_body(*, constants: str, real: str, ignored: str) -> str:
    """A synthetic ``NoteType`` carrying exactly the pieces a caller supplies.

    The surrounding module apes the real file's shape -- a translation function
    bound at module level, a class with a docstring, the two lists concatenated
    into a third -- because the parser reads a class body and not a fragment.
    """
    return (
        "_ = lambda *arguments: arguments[0]\n"
        "\n"
        "\n"
        "class NoteType:\n"
        '    """An invented class that is not any Gramps release."""\n'
        "\n"
        f"{constants}"
        "\n"
        "    _DATAMAPREAL = [\n"
        f"{real}"
        "    ]\n"
        "\n"
        "    _DATAMAPIGNORE = [\n"
        f"{ignored}"
        "    ]\n"
        "\n"
        "    _DATAMAP = _DATAMAPREAL + _DATAMAPIGNORE\n"
    )


_CONSTANTS = "    BADGER = -1\n    KETTLE = 4\n    LANTERN = 7  # a trailing remark\n"
"""Three invented constants. ⚠️ **The negative and the commented one are the
point**: ``UNKNOWN = -1`` is a unary minus rather than an integer literal, and
``SOURCE_TEXT = 21  # ...`` is the shape that has already broken a parser which
looked correct."""

_ONE_ARGUMENT = '        (BADGER, _("Badger"), "Badger"),\n'
_TWO_ARGUMENT = '        (KETTLE, _("Kettle", "notetype"), "Kettle Key"),\n'
_IGNORED_ROW = '        (LANTERN, _("Lantern"), "Lantern Key"),\n'


def _whole(real: str = _ONE_ARGUMENT + _TWO_ARGUMENT, ignored: str = _IGNORED_ROW) -> str:
    return _class_body(constants=_CONSTANTS, real=real, ignored=ignored)


# ---------------------------------------------------------------------------
# The rows, and the two translation-call shapes that have already been missed
# ---------------------------------------------------------------------------


def test_both_translation_call_shapes_are_read_and_neither_is_dropped() -> None:
    """⛔ The near-miss this whole derivation exists because of.

    ⚠️ ``TODO`` and ``LINK`` are written ``_("To Do", "notetype")`` -- the
    two-argument call, used where a word needs a disambiguating context -- and a
    pattern written for the one-argument form skipped both **while the output
    still looked like a full enumeration**. ``todo`` is one of the two types the
    note flow exists to write, so the silent result of trusting that pass would
    have been a table missing the type this work is for.

    ⭐ Both shapes are asserted in one test, because what makes them a hazard is
    that they sit side by side in one list and only one of them is obvious.
    """
    derivation = _derivation()

    rows = derivation.rows_of(_whole(), _SOURCE)

    assert rows == [
        ("BADGER", -1, "Badger", derivation.REAL_LIST),
        ("KETTLE", 4, "Kettle Key", derivation.REAL_LIST),
        ("LANTERN", 7, "Lantern Key", derivation.IGNORED_LIST),
    ], f"a translation-call shape was dropped or misread: {rows}"


def test_the_two_lists_are_read_in_order_and_each_row_says_which_it_came_from() -> None:
    """⛔ Which list a row came from is what the accepted set is computed FROM.

    ⚠️ A table that carried the rows and not their provenance would make the
    accepted set a hand-partition of the enum, which is the thing the ruling
    asked this derivation to avoid. It is also the field that makes widening the
    set later a one-line change to the derivation rather than a re-derivation.

    Order is asserted rather than membership: the committed table is compared
    byte for byte against a re-run, so anything that varies between two runs over
    one input breaks the verification story.
    """
    derivation = _derivation()

    rows = derivation.rows_of(_whole(real=_TWO_ARGUMENT + _ONE_ARGUMENT), _SOURCE)

    assert [row[0] for row in rows] == ["KETTLE", "BADGER", "LANTERN"], (
        f"the rows are not in declaration order, with the real list first: {rows}"
    )
    assert [row[3] for row in rows] == [
        derivation.REAL_LIST,
        derivation.REAL_LIST,
        derivation.IGNORED_LIST,
    ]


def test_a_constant_written_with_a_trailing_comment_is_still_read() -> None:
    """⚠️ ``SOURCE_TEXT = 21  # this is used for verbatim source text``.

    Half of the real class's interesting constants carry one, and a parser that
    read the assignment as text rather than as syntax has already tripped on it.
    """
    derivation = _derivation()

    rows = derivation.rows_of(_whole(real=_ONE_ARGUMENT, ignored=_IGNORED_ROW), _SOURCE)

    assert ("LANTERN", 7, "Lantern Key", derivation.IGNORED_LIST) in rows, (
        f"the constant carrying a trailing comment was not resolved: {rows}"
    )


def test_a_negative_constant_is_read_as_a_negative_number() -> None:
    """⚠️ ``UNKNOWN = -1`` is a unary minus applied to a literal, not a literal.

    It is also one of the two rows the accepted set is computed by REMOVING, so
    a derivation that could not read it would have to exclude it by name, which
    is the hand-partition the ruling refuses.
    """
    derivation = _derivation()

    rows = derivation.rows_of(_whole(), _SOURCE)

    assert rows[0][1] == -1, f"a negative constant did not survive the derivation: {rows[0]}"


# ---------------------------------------------------------------------------
# Fail closed. ⛔ The property without which the whole scheme is decorative.
# ---------------------------------------------------------------------------


_UNREADABLE = (
    '        (BADGER, "Badger", "Badger"),\n',
    '        (BADGER, _("Badger")),\n',
    '        (99, _("Badger"), "Badger"),\n',
    '        (NOBODY_DECLARED_THIS, _("Badger"), "Badger"),\n',
    '        (BADGER, _("Badger"), 17),\n',
    '        "a bare string where a row belongs",\n',
    '        (BADGER, _(*translations), "Badger"),\n',
)
"""Element shapes the derivation must REFUSE rather than skip.

Each is a plausible neighbour of a real row: no translation call, a short tuple,
an inline integer where a declared constant belongs, a name the class never
declares, a non-string key, something that is not a tuple at all, and a
translation call whose arguments are not literals. ⛔ **A parser that skipped any
of these would emit a table short by exactly the rows nobody thought about**, and
every check downstream would still pass, because the committed rows and the
parsed rows would have dropped the same row.
"""


@pytest.mark.parametrize("element", _UNREADABLE)
def test_an_element_the_parser_cannot_read_stops_the_derivation(element: str) -> None:
    """⛔ The fail-closed guarantee, asserted NON-VACUOUSLY.

    ⚠️ **This is what stops the repair being a pattern that matches everything.**
    A row shape widened to whatever appears in that position would pass every
    other test in this file and destroy the guarantee outright: the script would
    emit a plausible-looking row for an unreadable element instead of refusing.

    ⚠️ **And a fixed expected count is not the guard either.** A later
    ``notetype.py`` that adds a thirtieth row in an unrecognised shape leaves 29
    parsed rows and passes any ``== 29``. The guard is that every element of both
    lists was UNDERSTOOD.
    """
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.rows_of(_whole(real=_ONE_ARGUMENT + element), _SOURCE)

    assert "would silently omit" in str(refusal.value), (
        f"an unreadable element stops the derivation and says why: {refusal.value}"
    )
    assert _SOURCE in str(refusal.value), (
        f"a refusal that does not name the artifact is one nobody can act on: {refusal.value}"
    )


def test_the_refusal_quotes_the_LINE_the_unreadable_element_sits_on() -> None:
    """⛔ A refusal naming no line is a refusal somebody has to go hunting behind.

    ⚠️ And it must quote the FIRST unreadable element rather than whatever
    survived to the end of the list: a check placed after the scan is correct
    exactly when the bad element is the last one, which is the position a
    hand-written reproduction tends to use.
    """
    derivation = _derivation()
    unreadable = '        (BADGER, "Badger", "Badger"),\n'
    second = '        (KETTLE, _("Kettle"), 17),\n'

    with pytest.raises(SystemExit) as refusal:
        derivation.rows_of(_whole(real=unreadable + second), _SOURCE)

    message = str(refusal.value)
    assert unreadable.strip() in message, f"the refusal does not quote the element: {message}"
    assert second.strip() not in message, (
        f"the refusal quotes a later element as well as the first one: {message}"
    )
    assert re.search(r"line \d+", message), f"the refusal names no line number: {message}"


@pytest.mark.parametrize("position", (0, 1, 2))
def test_an_unreadable_element_ANYWHERE_in_a_list_stops_the_derivation(position: int) -> None:
    """Quantified over POSITION, so no position is special."""
    derivation = _derivation()
    unreadable = '        (BADGER, "Badger", "Badger"),\n'
    readable = [_ONE_ARGUMENT, _TWO_ARGUMENT]
    readable.insert(position, unreadable)

    with pytest.raises(SystemExit):
        derivation.rows_of(_whole(real="".join(readable)), _SOURCE)


def test_a_missing_list_stops_the_derivation_rather_than_yielding_a_short_table() -> None:
    """⛔ A renamed list is the upgrade that empties half the table in silence.

    ⚠️ ``_DATAMAPIGNORE`` is 17 of the 29 rows and none of the accepted 10, so a
    derivation that treated its absence as *no ignored rows* would produce a
    table whose accepted set was still right and whose refusal list had lost
    seventeen names -- and criterion 8's test would then be asserting nothing.
    """
    derivation = _derivation()
    without = _class_body(constants=_CONSTANTS, real=_ONE_ARGUMENT, ignored=_IGNORED_ROW).replace(
        "_DATAMAPIGNORE = [", "_DATAMAPRENAMED = ["
    )

    with pytest.raises(SystemExit) as refusal:
        derivation.rows_of(without, _SOURCE)

    assert derivation.IGNORED_LIST in str(refusal.value), (
        f"the refusal does not name the list it could not find: {refusal.value}"
    )


def test_a_file_declaring_no_NoteType_at_all_stops_the_derivation() -> None:
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.rows_of("class SomethingElse:\n    pass\n", _SOURCE)

    assert derivation.CLASS_NAME in str(refusal.value) and _SOURCE in str(refusal.value)


# ---------------------------------------------------------------------------
# The version, which lives in a DIFFERENT file
# ---------------------------------------------------------------------------


_VERSION_FILE = (
    "DEV_VERSION = False\n"
    "VERSION_TUPLE = (9, 8, 7)\n"
    'VERSION_QUALIFIER = ""\n'
    'VERSION = ".".join(map(str, VERSION_TUPLE)) + VERSION_QUALIFIER\n'
)
"""An ordinary ``version.py``, whose ``VERSION`` is COMPUTED rather than typed.

⚠️ ``(9, 8, 7)`` is not any Gramps release. A fixture carrying the installed
version would be a second tally of the committed table's provenance field.
"""


def test_the_version_tuple_is_read_and_a_computed_VERSION_is_not_a_packaging_string() -> None:
    """⚠️ ``VERSION_TUPLE`` is what Gramps IS. ``VERSION`` is what built it.

    An ordinary source install computes ``VERSION`` from the tuple, so there is
    no packaging string to record and recording the computed expression would be
    provenance in name only.
    """
    derivation = _derivation()

    assert derivation.version_of(_VERSION_FILE, _SOURCE) == ((9, 8, 7), "")


def test_a_second_assignment_overwriting_VERSION_is_recorded_BESIDE_the_tuple() -> None:
    """⛔ The all-in-one build appends its own ``VERSION`` at the end of the file.

    ⚠️ So ``VERSION`` says what the installer called the build and
    ``VERSION_TUPLE`` says what Gramps is. Recording ``VERSION`` as the version
    would make the table claim a provenance that is a fact about an installer,
    and the two are not recoverable from each other.
    """
    derivation = _derivation()
    appended = _VERSION_FILE + "\nVERSION = 'INVENTED64-9.8.7--3'\n"

    assert derivation.version_of(appended, _SOURCE) == ((9, 8, 7), "INVENTED64-9.8.7--3")


def test_a_version_file_with_no_VERSION_TUPLE_stops_the_derivation() -> None:
    """⛔ Rather than falling back to a literal, which is the failure this guards.

    ⚠️ **A provenance field that looks derived and is actually typed is worse
    than no field**, because the next reader trusts it: a table regenerated
    against a newer Gramps would keep the old version while staying
    byte-reproducible and passing every row check on this page.
    """
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.version_of("DEV_VERSION = False\n", _SOURCE)

    assert "VERSION_TUPLE" in str(refusal.value) and _SOURCE in str(refusal.value)


def test_a_VERSION_TUPLE_that_is_not_a_tuple_of_integers_stops_the_derivation() -> None:
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.version_of('VERSION_TUPLE = "9.8.7"\n', _SOURCE)

    assert "VERSION_TUPLE" in str(refusal.value)


# ---------------------------------------------------------------------------
# What is emitted
# ---------------------------------------------------------------------------


def _emitted(derivation: ModuleType) -> str:
    return derivation.emit(
        [("an-invented-artifact", "0" * 64), ("another-invented-artifact", "1" * 64)],
        (9, 8, 7),
        "INVENTED64-9.8.7--3",
        [
            ("BADGER", -1, "Badger", derivation.REAL_LIST),
            ("KETTLE", 4, "Kettle Key", derivation.REAL_LIST),
            ("LANTERN", 7, "Lantern Key", derivation.IGNORED_LIST),
        ],
    )


def test_emitting_twice_over_the_same_input_is_byte_identical() -> None:
    """⚠️ The property the whole verification story rests on.

    Verification is re-run against the same installation and read an empty diff,
    so anything that varies between two runs over one input makes that check
    report a difference that is not one.
    """
    derivation = _derivation()

    assert _emitted(derivation) == _emitted(derivation)


def test_the_emitted_module_carries_no_date() -> None:
    """A derivation date is a fact about a run rather than about the runtime."""
    derivation = _derivation()

    assert re.search(r"\d{4}-\d{2}-\d{2}", _emitted(derivation)) is None, (
        f"the emitted module carries a date: {_emitted(derivation)}"
    )


def test_the_emitted_module_COMPUTES_its_accepted_set_rather_than_listing_it() -> None:
    """⛔ So the accepted set cannot drift from the rows beside it.

    ⚠️ Asserted by executing the emitted text: a module that listed the accepted
    names would still produce the right set today, and would stop agreeing with
    its own rows the first time one moved between the two lists. Here the rows
    are edited and the set is required to follow.
    """
    derivation = _derivation()
    namespace: dict[str, object] = {}
    exec(compile(_emitted(derivation), "<emitted>", "exec"), namespace)  # noqa: S102

    assert namespace["ACCEPTED_NOTE_TYPES"] == frozenset({"badger", "kettle"}), (
        "the emitted module's accepted set is not the real list lowercased"
    )

    moved = _emitted(derivation).replace(
        f'("KETTLE", 4, "Kettle Key", "{derivation.REAL_LIST}")',
        f'("KETTLE", 4, "Kettle Key", "{derivation.IGNORED_LIST}")',
    )
    assert moved != _emitted(derivation), (
        "the row could not be found to move, so this test would pass without exercising anything"
    )
    followed: dict[str, object] = {}
    exec(compile(moved, "<emitted>", "exec"), followed)  # noqa: S102

    assert followed["ACCEPTED_NOTE_TYPES"] == frozenset({"badger"}), (
        "a row moved to the ignored list did not leave the accepted set, so the "
        "set is a listing rather than a computation over the rows"
    )


def test_the_excluded_names_leave_the_accepted_set_without_leaving_the_TABLE() -> None:
    """⛔ ``CUSTOM`` and ``UNKNOWN`` are carried and not accepted, deliberately.

    They are two of the nineteen names a lookup written slightly wrong would let
    through, and criterion 8's test names them. A table that dropped them would
    leave that test asserting nothing about the two rows most likely to be
    mishandled.
    """
    derivation = _derivation()
    emitted = derivation.emit(
        [("an-invented-artifact", "0" * 64)],
        (9, 8, 7),
        "",
        [
            ("CUSTOM", 0, "Custom", derivation.REAL_LIST),
            ("UNKNOWN", -1, "Unknown", derivation.REAL_LIST),
            ("BADGER", 1, "Badger", derivation.REAL_LIST),
        ],
    )
    namespace: dict[str, object] = {}
    exec(compile(emitted, "<emitted>", "exec"), namespace)  # noqa: S102

    assert namespace["ACCEPTED_NOTE_TYPES"] == frozenset({"badger"})
    assert [row[0] for row in namespace["NOTE_TYPE_ROWS"]] == [  # type: ignore[union-attr]
        "CUSTOM",
        "UNKNOWN",
        "BADGER",
    ], "an excluded row left the table instead of merely leaving the accepted set"
