"""⛔ Two ways a caller could not IDENTIFY an event, and both caused duplicates.

The whole point of letting a document name an event by ``gramps_id`` is that
citing an event stops meaning creating a second copy of it. That only works if
the caller can (a) **find** the event and (b) **tell it apart** from its
neighbours. Round 2 of the review found both halves broken:

* ⚠️ ``list_events`` walked only ``get_event_ref_list()``. Gramps keeps Birth and
  Death in **their own slots**, so the two most common events in any tree had no
  discoverable id -- a caller looked, found nothing, omitted the id, and created
  the duplicate the feature exists to prevent.
* ⚠️ The approval dialog rendered an event without its **place**. Two Residence
  events in one census year are then the same string, and the owner cannot see a
  citation landing on the wrong one.

⛔ Both are about the OWNER's ability to check, which is the only real gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from gramps_live_api.host import accessor


@dataclass
class Ref:
    ref: str
    private: bool = False

    def get_privacy(self) -> bool:
        return self.private


@dataclass
class Date:
    year: int = 1880

    def is_empty(self) -> bool:
        return False

    def get_year(self) -> int:
        return self.year

    def __str__(self) -> str:
        return str(self.year)


@dataclass
class Name:
    value: str

    def get_value(self) -> str:
        return self.value


@dataclass
class Place:
    value: str
    private: bool = False

    def get_privacy(self) -> bool:
        return self.private

    def get_name(self) -> Name:
        return Name(self.value)

    def get_title(self) -> str:
        return self.value


@dataclass
class Event:
    gramps_id: str
    kind: str
    place_handle: str = ""
    private: bool = False
    description: str = ""

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_type(self) -> str:
        return self.kind

    def get_date_object(self) -> Date:
        return Date()

    def get_place_handle(self) -> str:
        return self.place_handle

    def get_description(self) -> str:
        return self.description


@dataclass
class Person:
    gramps_id: str = "I0700"
    birth: Any = None
    death: Any = None
    others: list[Any] = field(default_factory=list)

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return False

    def get_birth_ref(self) -> Any:
        return self.birth

    def get_death_ref(self) -> Any:
        return self.death

    def get_event_ref_list(self) -> list[Any]:
        return list(self.others)


class Tree:
    def __init__(self, person: Person, events: dict[str, Event], places: dict[str, Place]) -> None:
        self.person = person
        self.events = events
        self.places = places

    def is_open(self) -> bool:
        return True

    def get_person_from_gramps_id(self, gramps_id: str) -> Person | None:
        return self.person if gramps_id == self.person.gramps_id else None

    def get_event_from_handle(self, handle: str) -> Event | None:
        return self.events.get(handle)

    def get_place_from_handle(self, handle: str) -> Place | None:
        return self.places.get(handle)


class State:
    def __init__(self, db: Any) -> None:
        self.db = db


@pytest.fixture
def unbind() -> Any:
    yield
    accessor.forget()


def bind(person: Person, events: dict[str, Event], places: dict[str, Place] | None = None) -> None:
    accessor.bind(State(Tree(person, events, places or {})))


# ---------------------------------------------------------------------------
# (a) the dedicated slots
# ---------------------------------------------------------------------------


def test_a_birth_and_a_death_are_LISTED_even_though_gramps_keeps_them_apart(
    unbind: None,
) -> None:
    """⛔ The defect exactly: neither was returned, so neither could be cited."""
    bind(
        Person(birth=Ref("hb"), death=Ref("hd"), others=[Ref("hr")]),
        {
            "hb": Event("E0001", "Birth"),
            "hd": Event("E0002", "Death"),
            "hr": Event("E0003", "Residence"),
        },
    )

    ids = [match.gramps_id for match in accessor.list_events("I0700").matches]

    assert "E0001" in ids, "the BIRTH has no discoverable id, so citing it duplicates it"
    assert "E0002" in ids, "the DEATH has no discoverable id, so citing it duplicates it"
    assert "E0003" in ids, "the ordinary event regressed"


def test_an_event_in_BOTH_places_is_listed_ONCE(unbind: None) -> None:
    """⚠️ Gramps may keep a birth in the slot AND in the list.

    ⭐ Without the dedup a person would read as having two births, which is a new
    way to make the owner doubt the dialog -- the opposite of the fix's purpose.
    """
    shared = Ref("hb")
    bind(Person(birth=shared, others=[Ref("hb")]), {"hb": Event("E0001", "Birth")})

    ids = [match.gramps_id for match in accessor.list_events("I0700").matches]

    assert ids.count("E0001") == 1, f"the birth was listed twice: {ids}"


def test_a_PRIVATE_birth_reference_is_still_gated_in_its_slot(unbind: None) -> None:
    """⛔ The negative control, and the one that matters.

    ⚠️ A new traversal is a new way to bypass the privacy gate, and this one was
    caught by the container ratchet during the build -- the first version read the
    handle off an ungated reference. **A test that only proved births appear would
    pass against the leaking version too.**
    """
    bind(
        Person(birth=Ref("hb", private=True), death=Ref("hd")),
        {"hb": Event("E0001", "Birth"), "hd": Event("E0002", "Death")},
    )

    ids = [match.gramps_id for match in accessor.list_events("I0700").matches]

    assert "E0001" not in ids, "a PRIVATE birth reference reached the wire"
    assert "E0002" in ids, "the gate refused everything, so the test above proves nothing"


# ---------------------------------------------------------------------------
# (b) telling two of them apart
# ---------------------------------------------------------------------------


def test_the_dialog_shows_the_PLACE_so_two_same_year_events_differ(unbind: None) -> None:
    """⛔ Without the place these two render identically, and the owner cannot check."""
    places = {"pa": Place("Amherst County, Invented"), "pb": Place("Bedford County, Invented")}
    bind(Person(), {}, places)

    first = accessor._display_of(
        accessor._DBSTATE.db, "event", Event("E0010", "Residence", place_handle="pa")
    )
    second = accessor._display_of(
        accessor._DBSTATE.db, "event", Event("E0011", "Residence", place_handle="pb")
    )

    assert first != second, f"two different events render identically: {first!r}"
    assert "Amherst" in first and "Bedford" in second

    # ⛔ The separator is not the description's. ``_event_display`` ends a
    # described event with ``-- <description>``; a place appended the same way
    # would give one string with two identical separators, which is harder to
    # read than the ambiguity it was meant to resolve.
    described = accessor._display_of(
        accessor._DBSTATE.db,
        "event",
        Event("E0012", "Census", place_handle="pa", description="household of 4"),
    )
    assert described.count(" -- ") == 1, f"two separators of the same shape: {described!r}"
    assert described.endswith("at Amherst County, Invented"), described


def test_a_PRIVATE_place_is_not_named_in_the_dialog(unbind: None) -> None:
    """⚠️ The dialog is a wire too. A private place must not be shown to reach it."""
    bind(Person(), {}, {"pa": Place("Hidden County, Invented", private=True)})

    shown = accessor._display_of(
        accessor._DBSTATE.db, "event", Event("E0010", "Residence", place_handle="pa")
    )

    assert "Hidden" not in shown, f"a PRIVATE place was named in the dialog: {shown!r}"
    assert "Residence" in shown, "the event stopped rendering at all"
