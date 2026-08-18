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
from pathlib import Path

from gramps_live_api.core import people
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
