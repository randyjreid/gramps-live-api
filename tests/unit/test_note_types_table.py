"""⛔ The committed note-type table, checked without Gramps and on every run.

⚠️ **This is half of a verification that splits in two, and the half that always
runs.** The two frozen tables this one follows derive from published standards a
human fetched once, and their verification is re-fetch, compare digest, re-run,
diff. This table's source is **a runtime installed on a machine**: it varies per
machine and CI has none at all. So the questions are split -- *is the committed
table internally consistent?*, which needs nothing but the file and is asserted
here, and *does it still match an installation?*, which needs Gramps and is
asserted by ``tests/integration/test_note_types_drift.py``, where it skips.

⛔ **Nothing here writes out a vocabulary.** Every assertion is a relation
between parts of the table, or between the table and the code that reads it. ⚠️ A
literal list of the ten accepted names in this file would be a **second tally**,
which is the counter bug this repository has already paid for: two numbers that
once agreed, drifting apart with nothing to announce it.
"""

from __future__ import annotations

from collections import Counter

from gramps_live_api.core import _note_types, apply, schema
from gramps_live_api.host import document

ACCEPTED_COUNT = 10
"""How many types the owner's ruling accepts. ⚠️ **The RULING's count, not a file's.**

⭐ Confirmed by the owner on 2026-09-04 after the evidence arguing for a wider set
was put to him, so a later reader who wants to widen it is reopening a decision
rather than finishing an open question. It is asserted here because the number is
the visible consequence of the derivation being right, not because the number is
the property: the equality below it is the property.
"""

DECLARED_COUNT = 29
"""How many rows Gramps' two lists hold together, which is ``_DATAMAP``.

⚠️ **This is a count of the SOURCE, and it moves when Gramps moves.** It is not a
guard -- a later release adding a thirtieth row in a shape the parser cannot read
would leave 29 parsed rows and pass this -- and the guard for that is the
derivation refusing an element it cannot read. What this catches is a table
regenerated against something that is not the Gramps this project was built on.
"""


def test_the_table_carries_every_row_of_both_lists_and_nothing_else() -> None:
    """⛔ The two lists PARTITION the table, and neither is empty.

    ⚠️ ``_DATAMAPIGNORE`` is seventeen of the rows and none of the accepted ten,
    so a derivation that lost it would produce a table whose accepted set was
    still exactly right, and whose refusal list had quietly lost seventeen names.
    Criterion 8's test would then be asserting nothing while still passing.
    """
    lists = Counter(declared_in for _a, _v, _k, declared_in in _note_types.NOTE_TYPE_ROWS)

    assert set(lists) == {_note_types.REAL_LIST, _note_types.IGNORED_LIST}, (
        f"a row came from a list this table does not know about: {sorted(lists)}"
    )
    assert lists[_note_types.REAL_LIST] and lists[_note_types.IGNORED_LIST], (
        f"one of the two lists contributed no rows at all: {lists}"
    )
    assert len(_note_types.NOTE_TYPE_ROWS) == DECLARED_COUNT, (
        f"the table holds {len(_note_types.NOTE_TYPE_ROWS)} rows where the Gramps this "
        f"project was built on declares {DECLARED_COUNT}. Re-derive it: "
        "python scripts/derive_note_types.py <installation root>"
    )


def test_no_attribute_name_and_no_integer_appears_twice() -> None:
    """⛔ Either duplicate would make a lookup answer for the wrong row.

    ⚠️ A repeated attribute name is the sharper one: the wire vocabulary is the
    lowercased attribute name, so two rows sharing one would collapse to a single
    wire name whose meaning depends on which row a reader happened to reach.
    """
    attributes = Counter(attribute for attribute, _v, _k, _l in _note_types.NOTE_TYPE_ROWS)
    integers = Counter(value for _a, value, _k, _l in _note_types.NOTE_TYPE_ROWS)

    assert [name for name, count in attributes.items() if count > 1] == []
    assert [value for value, count in integers.items() if count > 1] == []


def test_the_accepted_set_is_the_real_list_LESS_the_two_excluded_rows() -> None:
    """⛔ Computed, so it cannot be a hand-partition of the enum.

    ⚠️ Re-derived here from the rows rather than compared against a written-out
    set. The two are the same statement only while the table is right, which is
    the point: this fails if a row moves between the lists and the accepted set
    does not follow.
    """
    expected = {
        attribute.lower()
        for attribute, _v, _k, declared_in in _note_types.NOTE_TYPE_ROWS
        if declared_in == _note_types.REAL_LIST
        and attribute not in _note_types.EXCLUDED_FROM_ACCEPTED
    }

    assert expected == _note_types.ACCEPTED_NOTE_TYPES
    assert len(_note_types.ACCEPTED_NOTE_TYPES) == ACCEPTED_COUNT, (
        f"the accepted set has {len(_note_types.ACCEPTED_NOTE_TYPES)} members where the "
        f"owner's ruling accepts {ACCEPTED_COUNT}"
    )


def test_the_two_excluded_rows_are_CARRIED_and_not_accepted() -> None:
    """⛔ They leave the accepted set without leaving the table.

    ⚠️ ``custom`` and ``unknown`` are two of the nineteen names a lookup written
    slightly wrong would let through, so criterion 8's test names them -- and it
    can only name them because they are here to name. Dropping them from the
    table would leave the two rows most likely to be mishandled untested.
    """
    for excluded in _note_types.EXCLUDED_FROM_ACCEPTED:
        assert any(row[0] == excluded for row in _note_types.NOTE_TYPE_ROWS), (
            f"{excluded} is excluded from the accepted set and is not in the table, so "
            "nothing can assert that it is refused"
        )
        assert excluded.lower() not in _note_types.ACCEPTED_NOTE_TYPES


def test_the_DEFAULT_type_is_one_of_the_accepted_ones() -> None:
    """⛔ A default outside the accepted set is unwritable through its own route.

    ⚠️ The document route defaults an omitted ``type`` to ``transcript``, so a
    narrowing that dropped it would leave every existing untyped graph asking for
    a type the same route refuses. That it survives the narrowing had to be
    checked rather than assumed.
    """
    assert document.DEFAULT_NOTE_TYPE in _note_types.ACCEPTED_NOTE_TYPES


def test_every_wire_name_recovers_its_attribute_name_by_UPPER_CASING() -> None:
    """⛔ The writer resolves ``getattr`` from the upper-cased wire name.

    ⚠️ The wire name is defined as the attribute name lowercased, and the reverse
    only holds while every attribute name is upper case. It is today, for all
    twenty-nine. **A row whose attribute carried a lower-case letter would make
    the writer's ``getattr`` miss a type the package had already accepted** --
    after the owner approved the document, which is the one moment this route
    exists to make safe. Asserted here rather than assumed there.
    """
    broken = [
        attribute
        for attribute, _v, _k, _l in _note_types.NOTE_TYPE_ROWS
        if attribute.lower().upper() != attribute
    ]

    assert broken == [], (
        f"these attribute names are not recovered by upper-casing their wire name, so "
        f"the writer's getattr would look for something Gramps does not declare: {broken}"
    )


def test_the_provenance_names_two_files_and_a_version_read_from_one_of_them() -> None:
    """⚠️ **Two files, two digests**, and the version is not in the rows file.

    A generator given only ``notetype.py`` cannot derive the version it claims to
    record, so it would have to carry a typed literal -- and a table regenerated
    against a newer Gramps would keep the old version while staying
    byte-reproducible and passing every row check on this page.
    """
    labels = [label for label, _digest in _note_types.SOURCE_DIGESTS]

    assert len(labels) == 2 and len(set(labels)) == 2, (
        f"the table does not record one digest per source file: {labels}"
    )
    for label, digest in _note_types.SOURCE_DIGESTS:
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef"), (
            f"{label} carries something that is not a SHA-256: {digest!r}"
        )

    assert _note_types.GRAMPS_VERSION_TUPLE and all(
        isinstance(part, int) for part in _note_types.GRAMPS_VERSION_TUPLE
    ), f"the recorded version is not a tuple of integers: {_note_types.GRAMPS_VERSION_TUPLE}"


# ---------------------------------------------------------------------------
# ⛔ The readers use the TABLE, never a copy of it
# ---------------------------------------------------------------------------


def test_the_schema_vocabulary_IS_the_table_and_not_a_copy() -> None:
    """⛔ Identity, not equality, and the difference is the whole point.

    ⚠️ Two equal sets are one edit away from being two different sets, and this
    repository's most-recorded defect class is two mechanisms for one property
    drifting apart. ``schema.NOTE_TYPES`` is what ``validate`` reads and what the
    note tool's description interpolates; the document route's vocabulary is what
    a graph is refused against. **Neither may be a second listing.**
    """
    assert schema.NOTE_TYPES is _note_types.ACCEPTED_NOTE_TYPES
    assert document.NOTE_TYPES is _note_types.ACCEPTED_NOTE_TYPES


def test_the_gramps_spelling_of_every_accepted_type_comes_from_the_table() -> None:
    """⛔ ``NOTE_TYPE_ATTRIBUTES`` stops being a hand-written map.

    ⚠️ It was two entries typed out beside a two-member frozenset, asserted total
    over that frozenset by a test. At ten members a hand-written map is a second
    tally; derived from the rows, the attribute name is **the table's own**
    rather than a guess about capitalisation, and the totality that test asserted
    is a property of the derivation rather than of somebody's diligence.
    """
    assert set(apply.NOTE_TYPE_ATTRIBUTES) == set(_note_types.ACCEPTED_NOTE_TYPES)

    by_wire_name = {
        attribute.lower(): attribute for attribute, _v, _k, _l in _note_types.NOTE_TYPE_ROWS
    }
    for wire_name, spelling in apply.NOTE_TYPE_ATTRIBUTES.items():
        assert spelling == by_wire_name[wire_name], (
            f"{wire_name!r} is spelled {spelling!r} where the table declares "
            f"{by_wire_name[wire_name]!r}"
        )
