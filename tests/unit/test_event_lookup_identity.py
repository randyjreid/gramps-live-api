"""⛔ Telling one event from another, and one claim that turned out to be false.

Letting a document name an event by ``gramps_id`` only stops meaning *duplicate
it* if the caller can find the event **and** tell it apart from its neighbours.

⚠️ A review round reported two ways that failed. **Only one of them was real.**

* **Real** -- the approval dialog rendered an event without its *place*, so two
  Residence events in one census year were the same string and the owner could
  not see a citation landing on the wrong one.
* **False** -- that ``list_events`` missed births and deaths because Gramps keeps
  them in slots outside ``get_event_ref_list()``. It does not: ``get_birth_ref``
  returns ``event_ref_list[birth_ref_index]``, an index into that same list.

⛔ **The false one was fixed before it was checked, and a negative control passed
on the fix**, because the fixture's fake ``Person`` returned the slots separately
from its ref list and so encoded the premise the test was meant to prove. **A
control demonstrates that the code satisfies the fixture.** Where the fixture is
the thing in doubt, it demonstrates nothing -- which is why the fake below now
models Gramps' actual arrangement, and why the first test asserts the arrangement
rather than the fix.
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
    """⛔ ``str(date)`` and ``get_year()`` must DIFFER here, or nothing is proved.

    ⚠️ A first version returned the year from both, so a mutation truncating the
    display to the year changed no output and the negative control stayed silent
    -- a fixture that cannot express the defect cannot test the fix.
    """

    year: int = 1880
    month: int = 6
    day: int = 1

    def is_empty(self) -> bool:
        return False

    def get_year(self) -> int:
        return self.year

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d}"


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
    when: Date = field(default_factory=Date)

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_type(self) -> str:
        return self.kind

    def get_date_object(self) -> Date:
        return self.when

    def get_place_handle(self) -> str:
        return self.place_handle

    def get_description(self) -> str:
        return self.description


@dataclass
class Person:
    """⛔ Modelled on Gramps' own arrangement, which is the thing in doubt here.

    ``event_refs`` is the whole list. ``birth_index`` and ``death_index`` are
    INDEXES into it, exactly as ``Person.birth_ref_index`` is -- so a birth is
    always reachable through ``get_event_ref_list()``. An earlier version of this
    fake held the slots in separate fields, which made a false claim about Gramps
    testable and therefore made a wrong fix look proven.
    """

    gramps_id: str = "I0700"
    event_refs: list[Any] = field(default_factory=list)
    birth_index: int = -1
    death_index: int = -1

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return False

    def _slot(self, index: int) -> Any:
        return self.event_refs[index] if 0 <= index < len(self.event_refs) else None

    def get_birth_ref(self) -> Any:
        return self._slot(self.birth_index)

    def get_death_ref(self) -> Any:
        return self._slot(self.death_index)

    def get_event_ref_list(self) -> list[Any]:
        return list(self.event_refs)


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
# (a) the claim that was false
# ---------------------------------------------------------------------------


def test_a_birth_is_reachable_through_the_REF_LIST_because_the_slot_is_an_index(
    unbind: None,
) -> None:
    """⛔ The disproof, kept as a test so the wrong fix is not made twice.

    ⚠️ A review round reported that ``list_events`` missed births and deaths, and
    a traversal of ``get_birth_ref()``/``get_death_ref()`` was written and gated
    and tested before the premise was checked. **The premise is false.** Gramps'
    ``Person.get_birth_ref`` is ``event_ref_list[birth_ref_index]``
    (``gen/lib/person.py:814``), and ``set_birth_ref`` appends to that list when
    the ref is not already in it.

    ⭐ Confirmed against the live tree as well as here: a person's birth comes
    back from ``list_events`` with no slot traversal in the code at all.
    """
    birth, residence = Ref("hb"), Ref("hr")
    bind(
        Person(event_refs=[birth, residence], birth_index=0),
        {"hb": Event("E0001", "Birth"), "hr": Event("E0003", "Residence")},
    )

    ids = [match.gramps_id for match in accessor.list_events("I0700").matches]

    # The slot and the list are the SAME object -- that is the whole point.
    person = accessor._DBSTATE.db.person
    assert person.get_birth_ref() is person.get_event_ref_list()[0]
    assert ids == ["E0001", "E0003"], (
        f"the birth is not reachable through the ref list after all: {ids}"
    )
    assert ids.count("E0001") == 1, "the birth was listed twice"


def test_a_PRIVATE_event_reference_is_still_gated(unbind: None) -> None:
    """⚠️ The gate this loop has always carried, asserted so the revert kept it."""
    bind(
        Person(event_refs=[Ref("hb", private=True), Ref("hd")], birth_index=0),
        {"hb": Event("E0001", "Birth"), "hd": Event("E0002", "Death")},
    )

    ids = [match.gramps_id for match in accessor.list_events("I0700").matches]

    assert "E0001" not in ids, "a PRIVATE event reference reached the wire"
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

    # ⛔ **The preview's order, because both strings land in the same dialog.**
    # ``document._event_line`` renders ``type date at PLACE -- description``; a
    # resolved event rendering ``-- description at PLACE`` would be the
    # preview/writer disagreement class inside one approval screen.
    assert described == ("Census 1880-06-01 at Amherst County, Invented -- household of 4"), (
        described
    )


def test_a_PRIVATE_place_is_not_named_in_the_dialog(unbind: None) -> None:
    """⚠️ The dialog is a wire too. A private place must not be shown to reach it."""
    bind(Person(), {}, {"pa": Place("Hidden County, Invented", private=True)})

    shown = accessor._display_of(
        accessor._DBSTATE.db, "event", Event("E0010", "Residence", place_handle="pa")
    )

    assert "Hidden" not in shown, f"a PRIVATE place was named in the dialog: {shown!r}"
    assert "Residence" in shown, "the event stopped rendering at all"


def test_two_events_in_ONE_year_are_told_apart_by_the_FULL_date(unbind: None) -> None:
    """⛔ Same type, same year, same place, same description -- different days.

    ⚠️ ``list_events`` hands the caller ``str(date)``, so the caller picks between
    two ids it can see are different. The approval line rendered only the YEAR, so
    the two ids produced the SAME string and the owner had nothing to check
    against. **The identity mechanism failed exactly where two candidates exist**,
    which is the only case it is for.
    """
    bind(Person(), {}, {"pa": Place("Amherst County, Invented")})
    db = accessor._DBSTATE.db

    spring = accessor._display_of(
        db, "event", Event("E0020", "Residence", place_handle="pa", when=Date(1880, 4, 2))
    )
    autumn = accessor._display_of(
        db, "event", Event("E0021", "Residence", place_handle="pa", when=Date(1880, 10, 9))
    )

    assert spring != autumn, f"two events months apart render identically: {spring!r}"
    assert "1880-04-02" in spring and "1880-10-09" in autumn


def test_the_LOOKUP_and_the_DIALOG_render_an_event_IDENTICALLY(unbind: None) -> None:
    """⛔ The bound, not a fourth fix.

    This branch produced three instances of one class: the lookup and the
    approval dialog described the same event differently, first missing the
    **place**, then losing the **date's precision**, then omitting the
    **description**. Each was a real way for the caller to choose an id it could
    see was distinct and hand the owner a line that was not.

    ⚠️ Fixing the third instance is not the fix. **Two renderers kept in step is
    the defect**; they now share one, and this asserts the sharing rather than
    the three symptoms -- so a field added to either arrives in both or fails
    here.

    ⭐ It matters because these two strings are the whole identity check: the
    caller picks from the lookup, the owner approves from the dialog, and a
    citation on the wrong event is invisible unless those two agree.
    """
    place = Place("Amherst County, Invented")
    events = {
        "h1": Event(
            "E0030",
            "Occupation",
            place_handle="pa",
            description="wheelwright",
            when=Date(1880, 6, 1),
        ),
        "h2": Event(
            "E0031",
            "Occupation",
            place_handle="pa",
            description="farm labourer",
            when=Date(1880, 6, 1),
        ),
    }
    bind(Person(event_refs=[Ref("h1"), Ref("h2")]), events, {"pa": place})
    db = accessor._DBSTATE.db

    found = accessor.list_events("I0700")
    from_lookup = {match.gramps_id: match.display for match in found.matches}
    from_dialog = {
        event.gramps_id: accessor._display_of(db, "event", event) for event in events.values()
    }

    assert from_lookup == from_dialog, (
        "the caller and the owner are shown different descriptions of the same "
        f"events:\n  lookup: {from_lookup}\n  dialog: {from_dialog}"
    )

    # ⛔ And the two must actually be DISTINGUISHABLE -- an agreement that
    # renders both events identically would satisfy the assertion above and
    # defeat its entire purpose.
    assert len(set(from_lookup.values())) == 2, (
        f"two events differing only by description render alike: {from_lookup}"
    )
    assert "wheelwright" in from_lookup["E0030"]
    assert "farm labourer" in from_lookup["E0031"]
