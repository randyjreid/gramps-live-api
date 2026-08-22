"""The five live reads, against a fake tree — the §3 substance without Gramps.

⭐ **The case this exists for is a real one from the owner's tree.** A person
whose PRIMARY surname is spelled with an umlaut carries the ``ue`` spelling only
in her **alternate names**. A search on the ``ue`` spelling therefore missed her,
and missing her is one step from entering a duplicate mother.

⚠️ **Everything here is invented.** The shape is taken from the real record; the
names are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from gramps_live_api.host import accessor, reads


@dataclass
class FakeSurname:
    value: str = ""

    def get_surname(self) -> str:
        return self.value


@dataclass
class FakeName:
    first: str = ""
    surnames: list[FakeSurname] = field(default_factory=list)

    def get_first_name(self) -> str:
        return self.first

    def get_surname(self) -> str:
        return self.surnames[0].value if self.surnames else ""

    def get_surname_list(self) -> list[FakeSurname]:
        return list(self.surnames)


@dataclass
class FakePerson:
    gramps_id: str
    primary: FakeName
    alternates: list[FakeName] = field(default_factory=list)
    private: bool = False

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_primary_name(self) -> FakeName:
        return self.primary

    def get_alternate_names(self) -> list[FakeName]:
        return list(self.alternates)

    def get_privacy(self) -> bool:
        return self.private

    def get_birth_ref(self) -> Any:
        return None

    def get_event_ref_list(self) -> list[Any]:
        return []


def person(gramps_id: str, first: str, surname: str, **kw: Any) -> FakePerson:
    alt = kw.pop("alternate", None)
    alternates = []
    if alt is not None:
        alternates.append(FakeName(first=alt[0], surnames=[FakeSurname(alt[1])]))
    return FakePerson(
        gramps_id=gramps_id,
        primary=FakeName(first=first, surnames=[FakeSurname(surname)]),
        alternates=alternates,
        **kw,
    )


class FakeTree:
    def __init__(self, people: list[FakePerson]) -> None:
        self._people = people

    def iter_people(self):  # noqa: ANN201 -- duck-typed like Gramps' own
        return iter(self._people)

    def get_person_from_gramps_id(self, gramps_id: str) -> FakePerson | None:
        return next((p for p in self._people if p.gramps_id == gramps_id), None)


@dataclass
class FakeDbState:
    db: Any


UMLAUT = "Künkele"


@pytest.fixture
def bound_tree():
    """A tree carrying the four spellings the owner's copy actually holds."""
    people = [
        person("I0000", "Anna", UMLAUT),
        person("I0041", "Caroline", UMLAUT, alternate=("Caroline", "Kuenkele")),
        person("I0137", "Jakob", "Kuenkele"),
        person("I0274", "Maria", "Kunkele"),
        person("I0900", "Hidden", "Kuenkele", private=True),
    ]
    accessor.bind(FakeDbState(db=FakeTree(people)))
    yield
    accessor.forget()


def test_the_alternate_name_spelling_is_found(bound_tree: None) -> None:
    """⭐ The duplicate-mother case. A primary-only search misses I0041."""
    found = accessor.find_people("Kuenkele")
    ids = {match.gramps_id for match in found.matches}

    assert "I0041" in ids, (
        "the person whose PRIMARY name uses the umlaut and who carries the 'ue' "
        "spelling as an ALTERNATE name was missed -- this is the defect"
    )
    assert "I0137" in ids, "the person whose primary name is the 'ue' spelling"


def test_folding_finds_the_accented_spelling(bound_tree: None) -> None:
    """Unicode normalisation: an unaccented search finds the accented name."""
    ids = {m.gramps_id for m in accessor.find_people("Kunkele").matches}
    assert {"I0000", "I0041", "I0274"} <= ids


def test_a_private_person_is_never_returned_and_never_counted(bound_tree: None) -> None:
    """⛔ A2, through the accessor rather than through ``reads.bound`` alone."""
    found = accessor.find_people("Kuenkele")

    assert "I0900" not in {m.gramps_id for m in found.matches}
    assert found.matched == len(found.matches), (
        "matched counted somebody who will never be shown -- the leak by arithmetic"
    )


def test_a_listing_without_a_term_is_refused(bound_tree: None) -> None:
    with pytest.raises(reads.SearchTermRequired):
        accessor.find_people("")


def test_listing_events_of_a_private_person_is_refused_by_name(bound_tree: None) -> None:
    """⛔ Ruling 1's second enforcement point, on a direct target."""
    with pytest.raises(reads.TargetIsPrivate) as refusal:
        accessor.list_events("I0900")
    assert "private" in str(refusal.value)

    # ⚠️ And absent is a DIFFERENT answer, not the same silence.
    assert accessor.list_events("I9999").matches == ()
