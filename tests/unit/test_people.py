"""Reading a Gramps XML export: who is in it, and what the record says.

⚠️ **Every document here is assembled at runtime**, for the reason
``tests/fixtures/synthetic`` exists: a committed ``.gramps`` file carries a
``<database ... gramps...>`` line that the PII guard reports outright, and the
only ways to make the build pass again would be to delete the test or to weaken
the guard.

The two privacy questions are tested separately and on purpose. Excluding a
private person from a listing and refusing them as a target are independent
properties -- a handle can arrive from a stale export, from a note somebody
wrote down, or from a caller that never listed at all.
"""

from __future__ import annotations

import gzip
import tracemalloc
from pathlib import Path

from gramps_live_api.core import people
from gramps_live_api.core._specified_containers import SPECIFIED_ATTRIBUTES
from tests.fixtures import synthetic


def export(tmp_path: Path, document: str, *, name: str = "tree.gramps") -> str:
    """``document`` on disk as plain XML, and the path to it."""
    path = tmp_path / name
    path.write_text(document, encoding="utf-8")
    return str(path)


def one_person(**overrides: object) -> str:
    """A document holding exactly one person, with no events."""
    fields: dict[str, object] = {
        "handle": "p0001",
        "gramps_id": "I0044",
        "names": synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
    }
    fields.update(overrides)
    return synthetic.gramps_export_document(people=synthetic.gramps_person(**fields))  # type: ignore[arg-type]


def with_a_birth(date: str, *, role: str | None = "Primary") -> str:
    """One person whose one event is a birth carrying ``date``."""
    return synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
            event_handles=(("e0001", role),),
        ),
        events=synthetic.gramps_event(handle="e0001", event_type="Birth", date=date),
    )


def only(tmp_path: Path, document: str) -> people.Person:
    read = people.read_export(export(tmp_path, document))
    assert len(read) == 1, "the document holds exactly one person"
    return read[0]


# ---------------------------------------------------------------------------
# What a listing carries
# ---------------------------------------------------------------------------


def test_a_person_carries_a_name_a_gramps_id_and_a_handle(tmp_path: Path) -> None:
    person = only(tmp_path, one_person())
    assert person.name == "Elowen Ashenmoor"
    assert person.gramps_id == "I0044"
    assert person.handle == "p0001"


def test_the_handle_loses_exactly_one_leading_underscore(tmp_path: Path) -> None:
    """``importxml`` strips underscores, so the raw attribute is not what a
    reference must name -- and stripping *all* of them would be a different
    answer for a handle that legitimately begins with one."""
    person = only(tmp_path, one_person(handle="_p0001"))
    assert person.handle == "_p0001", "one underscore comes off; the document wrote two"


def test_an_alternate_name_is_not_the_display_name(tmp_path: Path) -> None:
    document = one_person(
        names=synthetic.gramps_name(first="Quorvane", surname="Ashenmoor", alt=True)
        + synthetic.gramps_name(first="Elowen", surname="Ashenmoor")
    )
    assert only(tmp_path, document).name == "Elowen Ashenmoor"


def test_a_person_with_no_primary_name_is_still_listed(tmp_path: Path) -> None:
    """A person nobody named is still a person, and dropping them silently
    would make the listing disagree with the tree."""
    document = one_person(names=synthetic.gramps_name(first="Quorvane", surname="X", alt=True))
    person = only(tmp_path, document)
    assert person.name == ""
    assert person.gramps_id == "I0044"


# ---------------------------------------------------------------------------
# The four date shapes, one test each
# ---------------------------------------------------------------------------


def test_dateval_gives_the_year(tmp_path: Path) -> None:
    person = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856-03-04")))
    assert person.birth_year == 1856
    assert person.birth_display == "1856-03-04"


def test_daterange_gives_the_start_year_and_still_reads_as_a_range(tmp_path: Path) -> None:
    person = only(tmp_path, with_a_birth(synthetic.gramps_daterange("1856", "1860")))
    assert person.birth_year == 1856
    assert person.birth_display == "between 1856 and 1860", "a range must not read as a point"


def test_datespan_gives_the_start_year_and_still_reads_as_a_span(tmp_path: Path) -> None:
    person = only(tmp_path, with_a_birth(synthetic.gramps_datespan("1856", "1860")))
    assert person.birth_year == 1856
    assert person.birth_display == "from 1856 to 1860"


def test_datestr_is_carried_verbatim(tmp_path: Path) -> None:
    person = only(tmp_path, with_a_birth(synthetic.gramps_datestr("in the year of the flood")))
    assert person.birth_display == "in the year of the flood"


def test_a_recorded_date_with_no_parseable_year_is_not_an_absent_one(tmp_path: Path) -> None:
    """The distinction criterion 2 asks for: ``birth_year`` is ``None`` in both
    cases, and ``birth_display`` is what tells them apart."""
    unparseable = only(tmp_path, with_a_birth(synthetic.gramps_datestr("about the flood")))
    absent = only(tmp_path, with_a_birth(""))
    assert unparseable.birth_year is None and absent.birth_year is None
    assert unparseable.birth_display == "about the flood"
    assert absent.birth_display == "", "nothing recorded renders as nothing, not as a guess"


def test_a_person_with_no_birth_event_at_all_has_no_birth(tmp_path: Path) -> None:
    person = only(tmp_path, one_person())
    assert person.birth_year is None
    assert person.birth_display == ""


# ---------------------------------------------------------------------------
# The qualifiers the record puts ON a date shape
#
# ``birth_display`` is the lossless half of the pair, so a qualifier dropped
# from it is the record asserting one thing and the label saying another. The
# set is not written here: it is the schema's, minus what this reader already
# reads as the date, and the binding test at the end of this block is what makes
# that true rather than claimed.
# ---------------------------------------------------------------------------


def test_an_estimated_date_does_not_read_as_an_exact_one(tmp_path: Path) -> None:
    """The finding. Two different records must not produce one label.

    The value is carried as the record spelled it, capital and all: normalising
    it would be the reader deciding what ``Estimated`` means, which is the date
    model #21 is for.
    """
    estimated = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856", quality="Estimated")))
    exact = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856")))
    assert estimated.birth_display == "1856 [quality=Estimated]"
    assert exact.birth_display == "1856"
    assert estimated.birth_year == exact.birth_year == 1856, "the sortable half does not move"


def test_a_date_the_record_calls_approximate_does_not_read_as_a_point(tmp_path: Path) -> None:
    """``type`` is the other half of the same defect: ``before 1856`` is not
    ``1856``, and only ``dateval`` declares the attribute."""
    person = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856", type="before")))
    assert person.birth_display == "1856 [type=before]"
    assert person.birth_year == 1856


def test_the_qualifiers_read_in_the_schemas_order_not_the_documents(tmp_path: Path) -> None:
    """⚠️ **The order is the SCHEMA's.** Attribute order in a document is not
    significant in XML and ``iterparse`` hands it back as written, so a label
    built in document order would give two spellings of one date two labels --
    the "definition supplied by the surroundings" failure this reader's own
    local-name matching exists to avoid. Written here scrambled on purpose.
    """
    person = only(
        tmp_path,
        with_a_birth(
            synthetic.gramps_dateval(
                "1712",
                newyear="Mar25",
                quality="calculated",
                dualdated="1",
                cformat="Julian",
                type="about",
            )
        ),
    )
    assert person.birth_display == (
        "1712 [type=about, quality=calculated, cformat=Julian, dualdated=1, newyear=Mar25]"
    )
    assert person.birth_year == 1712


def test_a_range_and_a_span_carry_their_qualifiers_too(tmp_path: Path) -> None:
    """The identical defect in the adjacent branch: ``_spanning`` dropped these
    for exactly the reason ``_date`` dropped ``quality``."""
    ranged = only(
        tmp_path, with_a_birth(synthetic.gramps_daterange("1850", "1860", quality="estimated"))
    )
    spanned = only(
        tmp_path, with_a_birth(synthetic.gramps_datespan("1850", "1860", cformat="Julian"))
    )
    assert ranged.birth_display == "between 1850 and 1860 [quality=estimated]"
    assert spanned.birth_display == "from 1850 to 1860 [cformat=Julian]"
    assert ranged.birth_year == spanned.birth_year == 1850


def test_a_one_ended_range_keeps_its_qualifiers(tmp_path: Path) -> None:
    """The branch where ``_spanning`` returns the start alone is a third place
    the suffix has to reach, and it is the one a shape-by-shape fix misses."""
    person = only(
        tmp_path, with_a_birth(synthetic.gramps_daterange("1850", "", quality="estimated"))
    )
    assert person.birth_display == "1850 [quality=estimated]"


def test_a_daterange_has_no_type_because_the_schema_declares_none(tmp_path: Path) -> None:
    """⚠️ **Not every attribute present is a qualifier.** ``type`` is declared on
    ``dateval`` and on nothing else here, so a hand-written one on a range is not
    part of the record's date and is not promoted into the label by symmetry.
    """
    person = only(tmp_path, with_a_birth(synthetic.gramps_daterange("1850", "1860", type="before")))
    assert person.birth_display == "between 1850 and 1860"


def test_a_datestr_carries_no_qualifiers_because_the_schema_declares_none(tmp_path: Path) -> None:
    """``datestr`` is declared ``val CDATA #REQUIRED`` and nothing else, so the
    branch that was already lossless stays byte-for-byte what it was."""
    person = only(
        tmp_path,
        with_a_birth(synthetic.gramps_datestr("in the year of the flood", quality="estimated")),
    )
    assert person.birth_display == "in the year of the flood"


def test_a_qualifier_on_a_valueless_date_is_still_not_dropped(tmp_path: Path) -> None:
    """A date element with no value is not *nothing recorded*, and the empty
    label is reserved for the record that carries no date element at all."""
    valueless = only(tmp_path, with_a_birth(synthetic.gramps_dateval("", quality="estimated")))
    absent = only(tmp_path, with_a_birth(""))
    assert valueless.birth_year is None and absent.birth_year is None
    assert valueless.birth_display == "[quality=estimated]"
    assert absent.birth_display == "", "nothing recorded still renders as nothing"


def test_the_qualifier_set_is_the_schemas_minus_what_is_read_as_the_date() -> None:
    """⚠️ **This is what makes the two tables in ``people`` derived rather than
    remembered.** They are composed constants bound by test to the frozen,
    digest-pinned table -- which is what "derived" means here, per the note in
    ``pii_guard``: *nothing is maintained by hand without a test that would
    fail*, not *imported at runtime*.

    The equality is a concatenation, so it is exhaustive in both directions: a
    qualifier a later schema adds is missing from the left, and one invented
    here is missing from the right.
    """
    for shape, values in people._DATE_VALUE_ATTRIBUTES.items():
        declared = tuple(name for element, name, _ in SPECIFIED_ATTRIBUTES if element == shape)
        assert declared, f"{shape} is not an element the frozen table declares"
        assert values + people._DATE_QUALIFIERS[shape] == declared, shape
    assert people._DATE_QUALIFIERS["datestr"] == (), "the schema declares datestr only its value"
    assert people._DATE_QUALIFIERS["dateval"], "and it declares dateval five qualifiers"


# ---------------------------------------------------------------------------
# Resolving the reference
# ---------------------------------------------------------------------------


def test_an_event_after_the_people_still_resolves(tmp_path: Path) -> None:
    """``gramps_export_document`` writes ``<events>`` last on purpose. A reader
    that resolves a reference as it meets it passes on Gramps' own ordering and
    fails here."""
    assert only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856"))).birth_year == 1856


def test_an_event_that_is_not_a_birth_is_not_a_birth(tmp_path: Path) -> None:
    document = synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
            event_handles=(("e0001", "Primary"),),
        ),
        events=synthetic.gramps_event(
            handle="e0001", event_type="Baptism", date=synthetic.gramps_dateval("1856")
        ),
    )
    assert only(tmp_path, document).birth_year is None


def test_a_primary_role_is_preferred_over_another_role(tmp_path: Path) -> None:
    document = synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
            event_handles=(("e0001", "Family"), ("e0002", "Primary")),
        ),
        events=synthetic.gramps_event(
            handle="e0001", event_type="Birth", date=synthetic.gramps_dateval("1801")
        )
        + synthetic.gramps_event(
            handle="e0002", event_type="Birth", date=synthetic.gramps_dateval("1856")
        ),
    )
    person = only(tmp_path, document)
    assert person.birth_year == 1856, "the Primary role decides, not document order"


def two_births(first: tuple[str, str | None], second: tuple[str, str | None]) -> str:
    """One person referencing two birth events, ``(role, year)`` each."""
    (first_role, first_year), (second_role, second_year) = first, second
    return synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
            event_handles=(("e0001", first_role), ("e0002", second_role)),
        ),
        events=synthetic.gramps_event(
            handle="e0001", event_type="Birth", date=synthetic.gramps_dateval(str(first_year))
        )
        + synthetic.gramps_event(
            handle="e0002", event_type="Birth", date=synthetic.gramps_dateval(str(second_year))
        ),
    )


def test_a_birth_a_person_merely_witnessed_is_not_their_own(tmp_path: Path) -> None:
    """C1-3, and it is a defect in what ``list_people`` is for.

    A witness at a birth carries a perfectly valid ``eventref`` to it. The
    fallback took any referenced birth when no Primary one existed, so the
    witness was listed with **the baby's** birth year -- and this listing exists
    so a person can be identified before a note is attached to them.
    """
    person = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856"), role="Witness"))

    assert person.birth_year is None, "a witness does not acquire the baby's birth year"
    assert person.birth_display == ""
    assert person.other_birth_events == 0, "an event they witnessed is not one they carry"


def test_a_role_the_export_does_not_state_is_the_person_s_own(tmp_path: Path) -> None:
    """The open question, answered from Gramps rather than from memory.

    ``grampsxml.dtd`` declares ``role CDATA #IMPLIED``, and ``importxml.py``
    reads it as ``if "role" in attrs: self.eventref.role.set_from_xml_str(...)``
    -- so an absent role leaves the ``EventRoleType()`` the ``EventRef`` was
    constructed with, whose ``_DEFAULT`` is ``PRIMARY``. Absent means Primary in
    Gramps' own reader, and this one says the same thing.
    """
    person = only(tmp_path, two_births(("Witness", 1801), (None, 1856)))

    assert person.birth_year == 1856, "an eventref with no role at all is the person's own"
    assert person.other_birth_events == 0, "and the witnessed one is not counted as theirs"


def test_a_role_stated_as_empty_is_a_custom_role_and_not_their_own(tmp_path: Path) -> None:
    """The other half of the same reading, and it is not the same case.

    ``set_from_xml_str("")`` finds no match in ``_E2IMAP`` and falls to the else
    branch, which sets ``_CUSTOM`` with an empty name. So ``role=""`` is a
    custom role Gramps did not write -- its exporter emits the attribute only
    ``if role:`` -- and it is not Primary. Reading it as Primary because the
    string happens to be empty would be this project's own "the definition came
    from the surroundings" failure, one more time.
    """
    person = only(tmp_path, with_a_birth(synthetic.gramps_dateval("1856"), role=""))

    assert person.birth_year is None, "an empty role is a custom role, not an absent one"


def test_a_second_birth_event_is_counted_rather_than_hidden(tmp_path: Path) -> None:
    document = synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
            event_handles=(("e0001", "Primary"), ("e0002", "Primary")),
        ),
        events=synthetic.gramps_event(
            handle="e0001", event_type="Birth", date=synthetic.gramps_dateval("1856")
        )
        + synthetic.gramps_event(
            handle="e0002", event_type="Birth", date=synthetic.gramps_dateval("1857")
        ),
    )
    person = only(tmp_path, document)
    assert person.birth_year == 1856, "the first in document order"
    assert person.other_birth_events == 1, "and the others are counted, not dropped"


# ---------------------------------------------------------------------------
# The two things that must not decide the answer
# ---------------------------------------------------------------------------


def test_a_different_schema_version_reads_the_same(tmp_path: Path) -> None:
    """The namespace URI carries the schema version. Matching on it would make
    the answer depend on which Gramps wrote the export."""
    document = synthetic.gramps_export_document(
        people=synthetic.gramps_person(
            handle="p0001",
            gramps_id="I0044",
            names=synthetic.gramps_name(first="Elowen", surname="Ashenmoor"),
        ),
        version="1.99.9",
    )
    assert only(tmp_path, document).name == "Elowen Ashenmoor"


def test_a_gzipped_export_reads_the_same_as_a_plain_one(tmp_path: Path) -> None:
    """What Gramps actually writes. ``docs/using.md`` told the owner to open it
    in a text editor, which is issue #64's first bullet."""
    document = one_person()
    path = tmp_path / "tree.gramps"
    path.write_bytes(gzip.compress(document.encode("utf-8")))
    compressed = people.read_export(str(path))
    plain = people.read_export(export(tmp_path, document, name="plain.gramps"))
    assert compressed == plain


def half_an_export(tmp_path: Path, name: str) -> str:
    """A gzip stream that stops in the middle, the way a copy interrupted does."""
    whole = gzip.compress(one_person().encode("utf-8"))
    path = tmp_path / name
    path.write_bytes(whole[: len(whole) // 2])
    return str(path)


def test_a_truncated_export_is_refused_as_unreadable_not_as_a_traceback(
    tmp_path: Path,
) -> None:
    """L1. **The agent relays whatever it gets**, so this reaches a person.

    A gzip stream that ends early raises ``EOFError``, which is neither
    ``ET.ParseError`` nor ``OSError`` -- so it went past both handlers and the
    caller received a raw internal exception in place of the designed *retake
    the export* message. The type is the whole point: ``ExportUnreadable`` is
    what says what to do about it.
    """
    try:
        people.read_export(half_an_export(tmp_path, "truncated.gramps"))
    except people.ExportUnreadable as refusal:
        assert "export" in str(refusal).lower(), "the remedy is named, not just the condition"
    else:  # pragma: no cover - the assertion is the failure
        raise AssertionError("a truncated export must be refused, not parsed")


def test_a_corrupt_export_is_refused_as_unreadable_too(tmp_path: Path) -> None:
    """The other half of L1: damage inside the compressed stream raises
    ``zlib.error``, which is not an ``OSError`` either.

    ⚠️ **A CRC failure was already covered and this is not it.** ``gzip`` raises
    ``BadGzipFile`` for that, and ``BadGzipFile`` IS an ``OSError`` -- so the
    checksum case reached the designed message all along while the two below did
    not. Asserting all three is what keeps them from being read as one state.
    """
    whole = bytearray(gzip.compress(one_person().encode("utf-8")))
    for index in range(40, 60):
        whole[index] ^= 0xFF
    path = tmp_path / "corrupt.gramps"
    path.write_bytes(bytes(whole))

    try:
        people.read_export(str(path))
    except people.ExportUnreadable as refusal:
        assert str(refusal).strip()
    else:  # pragma: no cover - the assertion is the failure
        raise AssertionError("a corrupt export must be refused, not parsed")


def test_a_failed_checksum_was_already_refused_and_still_is(tmp_path: Path) -> None:
    """The control for the test above: ``BadGzipFile`` subclasses ``OSError``."""
    whole = gzip.compress(one_person().encode("utf-8"))
    path = tmp_path / "bad-crc.gramps"
    path.write_bytes(whole[:-8] + bytes(8))

    try:
        people.read_export(str(path))
    except people.ExportUnreadable as refusal:
        assert "CRC" in str(refusal)
    else:  # pragma: no cover - the assertion is the failure
        raise AssertionError("a failed checksum must be refused, not parsed")


# ---------------------------------------------------------------------------
# priv="1" -- ruling 1
# ---------------------------------------------------------------------------


def test_an_unstated_privacy_flag_is_not_private(tmp_path: Path) -> None:
    """Gramps' own default, and the ruling says take it rather than guess."""
    assert only(tmp_path, one_person()).private is False


def test_priv_zero_is_not_private(tmp_path: Path) -> None:
    assert only(tmp_path, one_person(private="0")).private is False


def test_priv_one_is_private(tmp_path: Path) -> None:
    assert only(tmp_path, one_person(private="1")).private is True


def test_a_privacy_value_the_schema_does_not_declare_is_private(tmp_path: Path) -> None:
    """The DTD declares ``priv`` as ``(0|1)``. Anything else is not a document
    Gramps wrote, and a privacy flag is the wrong place to guess generously."""
    assert only(tmp_path, one_person(private="yes")).private is True


# ---------------------------------------------------------------------------
# Searching, and what a search may return
# ---------------------------------------------------------------------------


def cast(count: int, *, private_from: int = 10**6) -> str:
    return "".join(
        synthetic.gramps_person(
            handle=f"p{index:04d}",
            gramps_id=f"I{index:04d}",
            names=synthetic.gramps_name(first=f"Elowen{index}", surname="Ashenmoor"),
            private="1" if index >= private_from else "",
        )
        for index in range(count)
    )


def test_a_search_matches_a_substring_of_the_name(tmp_path: Path) -> None:
    read = people.read_export(export(tmp_path, synthetic.gramps_export_document(people=cast(3))))
    assert [person.gramps_id for person in people.search(read, "elowen1").people] == ["I0001"]


def test_a_search_folds_case_rather_than_lowering_it(tmp_path: Path) -> None:
    """``str.lower()`` leaves the sharp s alone; ``casefold`` maps it to ``ss``,
    which is what a caller typing an ASCII keyboard will send."""
    document = one_person(names=synthetic.gramps_name(first="Elowen", surname="Weißvane"))
    read = people.read_export(export(tmp_path, document))
    assert people.search(read, "weissvane").people, "casefold, not lower"


def test_a_search_caps_its_results_and_says_how_many_matched(tmp_path: Path) -> None:
    document = synthetic.gramps_export_document(people=cast(people.RESULT_CAP + 5))
    read = people.read_export(export(tmp_path, document))
    found = people.search(read, "ashenmoor")
    assert len(found.people) == people.RESULT_CAP
    assert found.matched == people.RESULT_CAP + 5, "the caller is told the cap bit"


def test_a_search_excludes_a_private_person(tmp_path: Path) -> None:
    """Ruling 1, enforcement point one."""
    document = synthetic.gramps_export_document(people=cast(3, private_from=2))
    read = people.read_export(export(tmp_path, document))
    found = people.search(read, "ashenmoor")
    assert [person.gramps_id for person in found.people] == ["I0000", "I0001"]
    assert found.matched == 2, "a private person is not counted either"


def test_an_empty_search_term_is_refused(tmp_path: Path) -> None:
    """Requiring a term is what keeps ``list everyone`` from being a call."""
    read = people.read_export(export(tmp_path, one_person()))
    try:
        people.search(read, "   ")
    except people.SearchTermRequired as refusal:
        assert "search term" in str(refusal)
    else:  # pragma: no cover - the assertion is the failure
        raise AssertionError("an empty term must be refused, not answered with everybody")


# ---------------------------------------------------------------------------
# ⭐ The streaming claim, MEASURED rather than asserted
# ---------------------------------------------------------------------------


def bulky(tmp_path: Path, *, notes: int, name: str) -> Path:
    """An export whose bulk is the collection ``read_export`` walks past.

    Twenty people either way, so the *result* is a fixed size and everything the
    measurement below sees moving is what the parse held on to rather than what
    it returned. Built at runtime, never committed: a real tree is megabytes,
    and a megabyte fixture in the repository would be one.
    """
    padding = "Ashenmoor deed, volume two, page one hundred and forty-one. " * 4
    path = tmp_path / name
    path.write_text(
        synthetic.gramps_export_document(
            people=cast(20),
            events="".join(
                synthetic.gramps_event(
                    handle=f"e{index:04d}",
                    event_type="Birth",
                    date=synthetic.gramps_dateval("1856-03-04"),
                )
                for index in range(20)
            ),
            notes="".join(
                synthetic.gramps_export_note(handle=f"n{index:06d}", text=padding)
                for index in range(notes)
            ),
        ),
        encoding="utf-8",
    )
    return path


def peak_bytes(path: str) -> int:
    """What ``read_export`` had allocated at its high-water mark."""
    tracemalloc.start()
    try:
        read = people.read_export(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(read) == 20, "a parse that read nobody would measure nothing"
    return peak


def test_the_parse_streams_rather_than_holding_the_whole_export(tmp_path: Path) -> None:
    """⚠️ **``read_export``'s docstring says *one streaming pass with iterparse,
    because a real tree is megabytes*, and the owner's tree IS that case.**

    Two things had to be true for that sentence and neither was. ``element.clear()``
    ran only for ``person`` and ``event`` -- every other element took the
    ``else: continue`` and was never cleared, so a real export's ``<notes>``,
    ``<families>``, ``<citations>`` and ``<sources>`` accumulated whole. And
    clearing alone would not have been enough anyway: ``iterparse`` leaves each
    finished element in its parent's child list, so the emptied shells stay
    reachable from the root for the length of the file.

    **Measured, not argued.** The same twenty people are read out of two
    documents differing only in bulk the reader never looks at. A parse that
    streams shows a high-water mark that barely moves; a parse that accumulates
    shows one that tracks the file. The threshold is a quarter of the growth --
    far above the noise of a flat parse and far below the measured behaviour of
    an accumulating one, which grew by about two and a half times the bytes.
    """
    small = bulky(tmp_path, notes=200, name="small.gramps")
    large = bulky(tmp_path, notes=4000, name="large.gramps")
    people.read_export(str(small))  # warm whatever a first parse allocates once

    grew = large.stat().st_size - small.stat().st_size
    held = peak_bytes(str(large)) - peak_bytes(str(small))

    assert held < grew / 4, (
        f"the file grew {grew} bytes and the parse's high-water mark grew {held} -- "
        "which is a parse holding the export, not streaming it"
    )


# ---------------------------------------------------------------------------
# find -- the target path, which never goes through a search
# ---------------------------------------------------------------------------


def test_find_returns_a_private_person_so_the_caller_can_refuse_them(tmp_path: Path) -> None:
    """Ruling 1, enforcement point two, and the reason the two are separate.

    If ``find`` hid a private person the target path could only report *no such
    person*, and the caller could not tell the two apart -- which the ruling
    says plainly it must be able to do.
    """
    read = people.read_export(export(tmp_path, one_person(private="1")))
    found = people.find(read, "I0044")
    assert found is not None and found.private is True


def test_find_says_nothing_about_a_gramps_id_the_export_does_not_hold(tmp_path: Path) -> None:
    read = people.read_export(export(tmp_path, one_person()))
    assert people.find(read, "I9999") is None
