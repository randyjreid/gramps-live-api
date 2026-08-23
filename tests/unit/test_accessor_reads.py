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
    private: bool = False

    def get_privacy(self) -> bool:
        return self.private

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

    def get_note_list(self) -> list[Any]:
        return []

    def get_parent_family_handle_list(self) -> list[Any]:
        return []

    def get_family_handle_list(self) -> list[Any]:
        return []

    def get_handle(self) -> str:
        # A handle no fixture's ref list uses, so tests that are not about
        # membership privacy behave exactly as they did before the gate.
        return "handle_of_" + self.gramps_id


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


@dataclass
class FakeDate:
    year: int = 1867

    def is_empty(self) -> bool:
        return False

    def get_year(self) -> int:
        return self.year


@dataclass
class FakeEvent:
    private: bool = False

    def get_privacy(self) -> bool:
        return self.private

    def get_date_object(self) -> FakeDate:
        return FakeDate()


class TreeWithABirth:
    def __init__(self, private_birth: bool) -> None:
        self._event = FakeEvent(private=private_birth)
        self.person = person("I0500", "Anna", "Public")
        self.person.get_birth_ref = lambda: type("Ref", (), {"ref": "h1"})()  # type: ignore[method-assign]

    def get_person_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return self.person if gramps_id == "I0500" else None

    def get_event_from_handle(self, handle: str) -> FakeEvent:
        return self._event

    def iter_people(self):  # noqa: ANN201
        return iter([self.person])


def test_a_private_birth_event_costs_the_date_and_not_the_name() -> None:
    """⛔ Hiding a private date must not disable the identity check.

    ``document.preview`` shows this tree-read name so the owner can notice he is
    attaching to the WRONG person. Letting the gate's ``None`` raise into the
    broad handler replaced the whole display with "(could not read its name)" —
    a privacy fix silently switching off a safety check on the write path.

    ⚠️ **Driven through ``resolve_nodes``, which is the APPROVAL path.** An
    earlier version of this test called ``find_people`` — that renders through
    ``_person_display``, while the dialog renders through the separate
    ``_display_of``. **Reverting the fix would have left this test green**, which
    is a regression test asserting the wrong function: the same
    passes-for-an-unrelated-reason defect the privacy guard itself exists to
    prevent.
    """
    for private, expect_year in ((False, True), (True, False)):
        tree = TreeWithABirth(private_birth=private)
        accessor.bind(FakeDbState(db=tree))
        try:
            resolution = accessor.resolve_nodes({"people": [{"id": "p1", "gramps_id": "I0500"}]})
            shown = resolution.nodes[0].display
        finally:
            accessor.forget()

        assert "Public, Anna" in shown, (
            f"the person's NAME must survive a private birth event; got {shown!r}"
        )
        assert ("1867" in shown) is expect_year, (
            f"private={private} should {'show' if expect_year else 'hide'} the year; got {shown!r}"
        )


# --------------------------------------------------------------------------
# Round 1 findings. Each of these is a named input that produced a named wrong
# output on the previous head.
# --------------------------------------------------------------------------


class FamilyWithAPrivateChild:
    """One public family: two public children and one private one."""

    def __init__(self) -> None:
        self.father = person("I0100", "Bertram", "Public")
        self.mother = person("I0101", "Clemency", "Public")
        self.kids = [
            person("I0102", "Dorcas", "Public"),
            person("I0103", "Ephraim", "Public"),
            person("I0104", "Hidden", "Public", private=True),
        ]
        # The children point back at the family, as Gramps' own records do.
        for kid in self.kids:
            kid.get_parent_family_handle_list = lambda: ["h_fam"]  # type: ignore[method-assign]
        for parent in (self.father, self.mother):
            parent.get_family_handle_list = lambda: ["h_fam"]  # type: ignore[method-assign]
        self._by_handle = {
            "h_f": self.father,
            "h_m": self.mother,
            "h_k0": self.kids[0],
            "h_k1": self.kids[1],
            "h_k2": self.kids[2],
        }
        self.family = FakeFamily(
            gramps_id="F0100",
            father="h_f",
            mother="h_m",
            children=["h_k0", "h_k1", "h_k2"],
        )

    def get_person_from_handle(self, handle: str):  # noqa: ANN201
        return self._by_handle.get(handle)

    def get_family_from_handle(self, handle: str):  # noqa: ANN201
        return self.family

    def get_family_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return self.family if gramps_id == "F0100" else None

    def get_person_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        everyone = [self.father, self.mother, *self.kids]
        return next((p for p in everyone if p.gramps_id == gramps_id), None)

    def iter_people(self):  # noqa: ANN201
        return iter([self.father, self.mother, *self.kids])


@dataclass
class FakeChildRef:
    ref: str


@dataclass
class FakeFamily:
    gramps_id: str
    father: str | None = None
    mother: str | None = None
    children: list[str] = field(default_factory=list)
    private: bool = False

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_father_handle(self) -> str | None:
        return self.father

    def get_mother_handle(self) -> str | None:
        return self.mother

    def get_child_ref_list(self) -> list[FakeChildRef]:
        return [FakeChildRef(ref=handle) for handle in self.children]

    def get_handle(self) -> str:
        return "h_fam"


def test_a_private_child_is_not_in_the_family_count() -> None:
    """⛔ The leak by arithmetic, arriving through a display string.

    A PUBLIC family with a private child reported ``[3 children]`` while only two
    were public -- which announces that a hidden family member exists, to a
    caller that is never allowed to see them. The parents were gated; the count
    was not.
    """
    tree = FamilyWithAPrivateChild()
    accessor.bind(FakeDbState(db=tree))
    try:
        found = accessor.find_families("I0102")
        shown = found.matches[0].display
    finally:
        accessor.forget()

    assert "[2 children]" in shown, (
        f"the private child was counted -- a hidden record revealed by arithmetic: {shown!r}"
    )
    assert "3" not in shown
    assert "Hidden" not in shown


def test_an_attached_family_is_recognisable_in_the_dialog() -> None:
    """⛔ Without a family branch the dialog said "(could not read its name)".

    The owner cannot notice he is attaching to the WRONG household if the
    household has no name, and noticing is the only check there is.
    """
    tree = FamilyWithAPrivateChild()
    accessor.bind(FakeDbState(db=tree))
    try:
        resolution = accessor.resolve_nodes(
            dict(
                people=[dict(id="p1", given="Wilhelmina", surname="Newcomer")],
                families=[dict(id="f1", gramps_id="F0100", children=["p1"])],
            )
        )
        shown = next(n.display for n in resolution.nodes if n.gramps_id == "F0100")
    finally:
        accessor.forget()

    assert "could not read" not in shown, f"the family is unrecognisable: {shown!r}"
    assert "Public, Bertram" in shown and "Public, Clemency" in shown


def test_an_unsupported_note_kind_is_refused_not_retargeted(bound_tree: None) -> None:
    """⛔ A misspelt kind used to become a PERSON lookup silently.

    ``kind="sorce"`` answered about whatever person carried that id, or reported
    no notes at all -- and *no notes* is a result a caller acts on.
    """
    with pytest.raises(reads.UnknownKind) as refusal:
        accessor.list_notes("I0041", kind="sorce")
    assert "sorce" in str(refusal.value)

    # ⚠️ And the supported kinds still work rather than being refused too.
    assert accessor.list_notes("I0041", kind="person").matches == ()


def test_every_advertised_kind_list_matches_the_lookup() -> None:
    """⛔ ONE pin for every ``*_KINDS`` constant, not one per constant.

    ``NOTE_KINDS`` had a pin. ``CITED_KINDS`` was then written **without** one and
    immediately drifted: it advertised ``event`` and ``citation`` while
    ``_by_gramps_id`` had no branch for either, so ``list_citations(kind="event")``
    returned a **successful empty result** -- and a caller reading *no citations*
    adds the duplicate the tool exists to prevent. **A false negative is worse
    than an error, because only one of them is visible.**

    ⚠️ **The lesson did not transfer because the pin was written for ONE
    constant.** This one discovers them, so a third list cannot repeat it.

    ⚠️ **And it asserts two one-way relations rather than equality.** The previous
    pin required ``NOTE_KINDS`` to EQUAL the lookup's branches, so widening the
    lookup for citations broke a test about notes. The honest relations are:
    everything advertised is supported (here), and everything supported is
    advertised by something (below).
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(accessor._by_gramps_id)))
    spelled = {
        node.comparators[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "kind"
        and isinstance(node.comparators[0], ast.Constant)
        and isinstance(node.comparators[0].value, str)
    }
    assert spelled, "found no kind branches -- has _by_gramps_id been reshaped?"

    advertised = {
        name: set(getattr(accessor, name))
        for name in dir(accessor)
        if name.endswith("_KINDS") and name != "ORPHAN_KINDS"
    }
    assert advertised, "no *_KINDS constants found -- has the naming changed?"

    for name, kinds in sorted(advertised.items()):
        unsupported = sorted(kinds - spelled)
        assert unsupported == [], (
            f"{name} advertises kinds _by_gramps_id cannot look up, so a caller "
            f"naming one gets a successful EMPTY answer: {unsupported}"
        )

    every = set().union(*(set(getattr(accessor, n)) for n in dir(accessor) if n.endswith("_KINDS")))
    unreachable = sorted(spelled - every)
    assert unreachable == [], (
        "_by_gramps_id can look these up and no route offers them, so the "
        f"branches are unreachable: {unreachable}"
    )


@dataclass
class FakeRef:
    """A Gramps reference: a handle, plus a privacy flag of its own."""

    ref: str
    private: bool = False
    relation: str = ""

    def get_privacy(self) -> bool:
        return self.private

    def get_relation(self) -> str:
        return self.relation


class TreeJoinedByPrivateReferences:
    """Everything public. Every JOIN between them marked private."""

    def __init__(self) -> None:
        self.subject = person("I0200", "Frederick", "Openly")
        self.associate = person("I0201", "Godwin", "Openly")
        self.child = person("I0202", "Perpetua", "Openly")
        self.event = FakeEvent(private=False)
        self.family = FakeFamily(gramps_id="F0200", father="h_s", children=["h_c"])
        self.family.get_child_ref_list = lambda: [FakeChildRef2("h_c", private=True)]  # type: ignore[method-assign]
        self.family.get_event_ref_list = lambda: [FakeRef("h_e", private=True)]  # type: ignore[method-assign]
        self.subject.get_person_ref_list = lambda: [  # type: ignore[method-assign]
            FakeRef("h_a", private=True, relation="Godfather")
        ]
        self.subject.get_family_handle_list = lambda: ["h_fam"]  # type: ignore[method-assign]
        self._people = {"h_s": self.subject, "h_a": self.associate, "h_c": self.child}

    def get_person_from_handle(self, handle: str):  # noqa: ANN201
        return self._people.get(handle)

    def get_event_from_handle(self, handle: str):  # noqa: ANN201
        return self.event

    def get_family_from_handle(self, handle: str):  # noqa: ANN201
        return self.family

    def get_family_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return self.family if gramps_id == "F0200" else None

    def get_person_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return next((p for p in self._people.values() if p.gramps_id == gramps_id), None)

    def iter_people(self):  # noqa: ANN201
        return iter(self._people.values())


@dataclass
class FakeChildRef2:
    ref: str
    private: bool = False

    def get_privacy(self) -> bool:
        return self.private


def _joined_tree():
    tree = TreeJoinedByPrivateReferences()
    accessor.bind(FakeDbState(db=tree))
    return tree


def test_a_private_personref_association_is_not_returned() -> None:
    """⛔ Both people public, the ASSOCIATION private.

    The relationship is the private fact. Returning the associate's id, the
    relationship text and their name because both endpoints are public publishes
    exactly what the flag on the join was set to hide.
    """
    _joined_tree()
    try:
        found = accessor.list_associations("I0200")
    finally:
        accessor.forget()

    assert found.matches == (), f"a private association reached the wire: {found.matches}"
    assert found.matched == 0, "and it was counted, which leaks it by arithmetic"


def test_a_private_eventref_on_a_family_is_not_returned() -> None:
    """⛔ Public family, public event, PRIVATE join."""
    _joined_tree()
    try:
        found = accessor.list_family_events("F0200")
    finally:
        accessor.forget()

    assert found.matches == (), f"an event joined by a private reference leaked: {found.matches}"


def test_a_private_childref_is_not_counted_in_the_family() -> None:
    """⛔ The child is public; the family MEMBERSHIP is private.

    Distinct from the private-child case fixed in round 1 -- there the person
    was private, here the relationship is.
    """
    _joined_tree()
    try:
        found = accessor.find_families("I0200")
        shown = found.matches[0].display
    finally:
        accessor.forget()

    assert "children" not in shown, f"a child joined by a private reference was counted: {shown!r}"


# --------------------------------------------------------------------------
# Round 4. The membership is private while both ends are public -- and the
# backlink carries no reference, so the round 2 bound cannot see it.
# --------------------------------------------------------------------------


class TreeWithAPrivateMembership:
    """A public child, a public family, and a PRIVATE ChildRef joining them."""

    def __init__(self) -> None:
        self.child = person("I0300", "Rowena", "Openly")
        self.father = person("I0301", "Aurelius", "Openly")
        self.child.get_handle = lambda: "h_child"  # type: ignore[method-assign]
        self.child.get_parent_family_handle_list = lambda: ["h_fam"]  # type: ignore[method-assign]
        self.child.get_family_handle_list = lambda: []  # type: ignore[method-assign]
        self.family = FakeFamily(gramps_id="F0300", father="h_dad")
        self.family.get_child_ref_list = lambda: [FakeChildRef2("h_child", private=True)]  # type: ignore[method-assign]
        self._people = {"h_child": self.child, "h_dad": self.father}

    def get_person_from_handle(self, handle: str):  # noqa: ANN201
        return self._people.get(handle)

    def get_family_from_handle(self, handle: str):  # noqa: ANN201
        return self.family

    def get_person_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return next((p for p in self._people.values() if p.gramps_id == gramps_id), None)

    def get_family_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return self.family if gramps_id == "F0300" else None

    def iter_people(self):  # noqa: ANN201
        return iter(self._people.values())


def test_a_privately_joined_child_does_not_reveal_the_household() -> None:
    """⛔ Walking from the CHILD reached the family through a bare handle.

    ``get_parent_family_handle_list()`` returns handles, not references, so the
    private ``ChildRef`` sits on the family's side with nothing on the person's
    side pointing at it. The family came back public, with its public parents,
    publishing the single fact the flag was set on: **that this child belongs to
    this household.**

    ⚠️ This is the mirror of the round 2 count fix, and the round 2 *bound* does
    not cover it — that test governs how a ``.ref`` is followed, and there is no
    ``.ref`` on this path.
    """
    accessor.bind(FakeDbState(db=TreeWithAPrivateMembership()))
    try:
        found = accessor.find_families("I0300")
    finally:
        accessor.forget()

    assert found.matches == (), f"a private parent-child membership was published: {found.matches}"
    assert found.matched == 0, "and counted, which leaks it by arithmetic"


def test_a_public_membership_is_still_returned() -> None:
    """⚠️ The gate must not simply hide every family reached from a child."""
    tree = TreeWithAPrivateMembership()
    tree.family.get_child_ref_list = lambda: [FakeChildRef2("h_child", private=False)]  # type: ignore[method-assign]
    accessor.bind(FakeDbState(db=tree))
    try:
        found = accessor.find_families("I0300")
    finally:
        accessor.forget()

    assert len(found.matches) == 1, "a public membership was hidden -- the gate over-reaches"
    assert found.matches[0].gramps_id == "F0300"


# --------------------------------------------------------------------------
# Round 5: the person is public and the NAME is not.
# --------------------------------------------------------------------------


def _person_with_a_private_alternate() -> FakePerson:
    """Public person, public primary name, PRIVATE alternate spelling."""
    subject = FakePerson(
        gramps_id="I0400",
        primary=FakeName(first="Cornelia", surnames=[FakeSurname("Ostrander")]),
        alternates=[FakeName(first="Cornelia", surnames=[FakeSurname("Vandermeer")], private=True)],
    )
    return subject


def test_a_private_alternate_spelling_is_not_searchable() -> None:
    """⛔ The oracle. The name never reached the wire and was still leaked.

    Searching the private spelling returned the person under their PUBLIC name,
    so nothing on the wire looked wrong — and the caller had just confirmed that
    a person is associated with a name marked private.
    """
    accessor.bind(FakeDbState(db=FakeTree([_person_with_a_private_alternate()])))
    try:
        hidden = accessor.find_people("Vandermeer")
        public = accessor.find_people("Ostrander")
    finally:
        accessor.forget()

    assert hidden.matches == (), (
        "a private alternate name is searchable -- the route is an oracle for it"
    )
    assert hidden.matched == 0, "and counted, which leaks it by arithmetic"
    assert len(public.matches) == 1, "the PUBLIC spelling must still find them"


def test_a_private_primary_name_is_withheld_not_rendered() -> None:
    """⛔ Public person, private primary name."""
    subject = FakePerson(
        gramps_id="I0401",
        primary=FakeName(first="Ignatius", surnames=[FakeSurname("Thorncastle")], private=True),
    )
    accessor.bind(FakeDbState(db=FakeTree([subject])))
    try:
        resolution = accessor.resolve_nodes(dict(people=[dict(id="p1", gramps_id="I0401")]))
        shown = resolution.nodes[0].display
    finally:
        accessor.forget()

    assert "Thorncastle" not in shown and "Ignatius" not in shown, (
        f"a private name was rendered in the approval dialog: {shown!r}"
    )
    assert shown == accessor.WITHHELD, (
        "the owner must be told the name is withheld rather than shown nothing -- "
        f"he cannot confirm the identity, so he cancels; got {shown!r}"
    )


# --------------------------------------------------------------------------
# The three read tools. Two are use-derived; C0012 is the trigger.
# --------------------------------------------------------------------------


@dataclass
class FakeCitation:
    gramps_id: str
    page: str = ""
    source: str | None = None
    private: bool = False
    handle: str = "h_cit"

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_page(self) -> str:
        return self.page

    def get_reference_handle(self) -> str | None:
        return self.source

    def get_handle(self) -> str:
        return self.handle


@dataclass
class FakeSource:
    gramps_id: str
    title: str = ""
    private: bool = False
    handle: str = "h_src"

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_title(self) -> str:
        return self.title

    def get_handle(self) -> str:
        return self.handle


class TreeWithCitations:
    """One cited person, one UNCITED citation -- the C0012 shape."""

    def __init__(self) -> None:
        self.source = FakeSource("S0001", "Marriage register, 1946")
        self.attached = FakeCitation("C0001", "p. 44", source="h_src")
        self.orphan = FakeCitation("C0012", "p. 91", source="h_src")
        self.private_cit = FakeCitation("C0099", "p. 1", source="h_src", private=True)
        self.orphan.handle = "h_orphan"
        self.private_cit.handle = "h_private"
        self.subject = person("I0600", "Wendell", "Ashgrove")
        self.subject.get_citation_list = lambda: ["h_cit"]  # type: ignore[method-assign]
        self._cits = {
            "h_cit": self.attached,
            "h_orphan": self.orphan,
            "h_private": self.private_cit,
        }
        self.backlinks = {"h_cit": [("Person", "h_p")]}

    def get_person_from_gramps_id(self, gramps_id: str):  # noqa: ANN201
        return self.subject if gramps_id == "I0600" else None

    def get_citation_from_handle(self, handle: str):  # noqa: ANN201
        return self._cits.get(handle)

    def get_source_from_handle(self, handle: str):  # noqa: ANN201
        return self.source

    def iter_citations(self):  # noqa: ANN201
        return iter(self._cits.values())

    def iter_sources(self):  # noqa: ANN201
        return iter([self.source])

    def iter_notes(self):  # noqa: ANN201
        return iter([])

    def iter_places(self):  # noqa: ANN201
        return iter([])

    def iter_repositories(self):  # noqa: ANN201
        return iter([])

    def find_backlink_handles(self, handle: str):  # noqa: ANN201
        return iter(self.backlinks.get(handle, []))

    def iter_people(self):  # noqa: ANN201
        return iter([self.subject])


def test_a_cited_record_reports_its_citation_and_source() -> None:
    """⭐ The question no tool could ask: *is this record cited, and by what?*"""
    accessor.bind(FakeDbState(db=TreeWithCitations()))
    try:
        found = accessor.list_citations("I0600", kind="person")
    finally:
        accessor.forget()

    assert len(found.matches) == 1
    assert found.matches[0].gramps_id == "C0001"
    assert "Marriage register" in found.matches[0].display, (
        "the citation without its source is half an answer -- the owner needs to "
        f"know WHAT cites it: {found.matches[0].display!r}"
    )


def test_the_c0012_shape_is_found_as_an_orphan() -> None:
    """⭐ A citation attached to nothing.

    It existed, it was correct, and it pointed at nothing -- so it did no work,
    and it was found only by reading an export by hand.
    """
    accessor.bind(FakeDbState(db=TreeWithCitations()))
    try:
        found = accessor.find_orphans("citation")
    finally:
        accessor.forget()

    ids = {match.gramps_id for match in found.matches}
    assert "C0012" in ids, f"the orphan was not found: {ids}"
    assert "C0001" not in ids, "a citation that IS attached was reported as an orphan"


def test_a_private_record_is_never_reported_as_an_orphan() -> None:
    """⛔ P2 holds here too: not in the results, not in the count."""
    accessor.bind(FakeDbState(db=TreeWithCitations()))
    try:
        found = accessor.find_orphans("citation")
    finally:
        accessor.forget()

    assert "C0099" not in {m.gramps_id for m in found.matches}
    assert found.matched == len(found.matches), "the leak by arithmetic"


def test_a_failed_backlink_lookup_never_reports_an_orphan() -> None:
    """⛔ *Nothing points at this* must never mean *the question failed*.

    The owner acts on an orphan report by deleting. Reporting a record as
    unreferenced because the lookup raised would send him deleting one that is
    in use -- the worst possible direction for this tool to fail in.
    """
    tree = TreeWithCitations()

    def explode(handle: str):  # noqa: ANN202
        raise RuntimeError("the reference table is unavailable")

    tree.find_backlink_handles = explode  # type: ignore[method-assign]
    accessor.bind(FakeDbState(db=tree))
    try:
        found = accessor.find_orphans("citation")
    finally:
        accessor.forget()

    assert found.matches == (), (
        "a backlink lookup that FAILED was reported as 'referenced by nothing'"
    )


def test_orphan_and_citation_kinds_are_refused_when_unknown() -> None:
    accessor.bind(FakeDbState(db=TreeWithCitations()))
    try:
        with pytest.raises(reads.UnknownKind):
            accessor.find_orphans("peple")
        with pytest.raises(reads.UnknownKind):
            accessor.list_citations("I0600", kind="sorce")
        with pytest.raises(reads.SearchTermRequired):
            accessor.find_orphans("")
    finally:
        accessor.forget()


class TreeThatCounts:
    def __init__(self) -> None:
        self._n = {
            "people": 2934,
            "families": 1586,
            "events": 10931,
            "places": 2256,
            "sources": 14,
            "citations": 17,
            "notes": 66,
            "repositories": 6,
            "media": 12,
        }

    def is_open(self) -> bool:
        return True

    def __getattr__(self, name: str):  # noqa: ANN204
        if name.startswith("get_number_of_"):
            key = name[len("get_number_of_") :]
            return lambda: self._n[key]
        raise AttributeError(name)


def test_the_tree_totals_answer_a_question_no_search_could() -> None:
    """⚠️ ``find_people`` requires a term, so there was no way to ask how big the tree is."""
    accessor.bind(FakeDbState(db=TreeThatCounts()))
    try:
        totals = accessor.tree_totals()
    finally:
        accessor.forget()

    assert totals["people"] == 2934
    assert totals["events"] == 10931
    assert set(totals) == {
        "people",
        "families",
        "events",
        "places",
        "sources",
        "citations",
        "notes",
        "repositories",
        "media",
    }


# --------------------------------------------------------------------------
# changed_since -- and the swallow that made its first version answer nothing.
# --------------------------------------------------------------------------


@dataclass
class FakeChanged:
    gramps_id: str
    change: int = 0
    private: bool = False
    expose_getter: bool = True

    def get_gramps_id(self) -> str:
        return self.gramps_id

    def get_privacy(self) -> bool:
        return self.private

    def get_title(self) -> str:
        return "a record"

    def __getattr__(self, name: str):  # noqa: ANN204
        if name == "get_change":
            if not object.__getattribute__(self, "expose_getter"):
                raise AttributeError(name)
            return lambda: object.__getattribute__(self, "change")
        raise AttributeError(name)


class TreeThatChanges:
    def __init__(self, records: list[FakeChanged]) -> None:
        self._records = records

    def iter_sources(self):  # noqa: ANN201
        return iter(self._records)

    def iter_people(self):  # noqa: ANN201
        return iter([])

    def iter_families(self):  # noqa: ANN201
        return iter([])

    def iter_events(self):  # noqa: ANN201
        return iter([])

    def iter_places(self):  # noqa: ANN201
        return iter([])

    def iter_citations(self):  # noqa: ANN201
        return iter([])

    def iter_notes(self):  # noqa: ANN201
        return iter([])


def test_records_changed_after_the_cutoff_are_returned() -> None:
    old = FakeChanged("S0001", change=1_500_000_000)
    recent = FakeChanged("S0002", change=1_787_483_523)
    accessor.bind(FakeDbState(db=TreeThatChanges([old, recent])))
    try:
        found = accessor.changed_since("2026-08-01", kind="sources")
    finally:
        accessor.forget()

    assert [m.gramps_id for m in found.matches] == ["S0002"]
    assert "changed" in found.matches[0].display


def test_a_private_record_is_never_reported_as_changed() -> None:
    """⛔ P2 holds here too: not in the results, not in the count."""
    accessor.bind(
        FakeDbState(
            db=TreeThatChanges(
                [
                    FakeChanged("S0002", change=1_787_483_523),
                    FakeChanged("S0099", change=1_787_483_523, private=True),
                ]
            )
        )
    )
    try:
        found = accessor.changed_since("2026-08-01", kind="sources")
    finally:
        accessor.forget()

    assert "S0099" not in {m.gramps_id for m in found.matches}
    assert found.matched == len(found.matches), "the leak by arithmetic"


def test_a_tree_whose_stamps_cannot_be_read_REFUSES_rather_than_reporting_none() -> None:
    """⛔ The defect the first version shipped past, and it is the whole lesson.

    It wrapped the read in ``except AttributeError: continue``, so using the
    wrong accessor skipped every record and the route answered an empty result --
    **the full walk's cost and none of its answer.** Measured live: 275 ms over
    2,935 people, ``shown=0``, on a tree that had changed that morning.

    ⚠️ *Nothing changed* is exactly the answer a caller acts on, so a silent
    wrong one is worse than an error.
    """
    accessor.bind(
        FakeDbState(
            db=TreeThatChanges(
                # ⚠️ Neither path yields a usable number: no getter, and the
                # attribute holds something that is not a timestamp. That models
                # the real failure -- an accessor whose answer cannot be used --
                # rather than merely a missing method, which the fallback handles.
                [
                    FakeChanged("S0001", change="not-a-timestamp", expose_getter=False)  # type: ignore[arg-type]
                    for _ in range(3)
                ]
            )
        )
    )
    try:
        with pytest.raises(reads.ReadRefused) as refusal:
            accessor.changed_since("2020-01-01", kind="sources")
    finally:
        accessor.forget()

    assert "change stamp" in str(refusal.value)
    assert "Refusing rather than reporting none" in str(refusal.value)


def test_an_unreadable_date_is_refused() -> None:
    accessor.bind(FakeDbState(db=TreeThatChanges([])))
    try:
        with pytest.raises(reads.SearchTermRequired):
            accessor.changed_since("last Tuesday", kind="sources")
        with pytest.raises(reads.SearchTermRequired):
            accessor.changed_since("")
        with pytest.raises(reads.UnknownKind):
            accessor.changed_since("2020-01-01", kind="peoples")
    finally:
        accessor.forget()


def test_a_private_record_cannot_change_the_shape_of_the_answer() -> None:
    """⛔ A private record must not reach the stamp read at all.

    Counting it as unreadable let it turn an empty 200 into a refusal -- so its
    existence was detectable through **control flow**: absent from the results
    and the counts, and leaking through the shape of the response instead.
    """
    accessor.bind(
        FakeDbState(
            db=TreeThatChanges(
                [
                    FakeChanged("S0099", change="unreadable", private=True, expose_getter=False),  # type: ignore[arg-type]
                    FakeChanged("S0001", change=1_500_000_000),
                ]
            )
        )
    )
    try:
        found = accessor.changed_since("2026-08-01", kind="sources")
    finally:
        accessor.forget()

    assert found.matches == ()
    assert found.matched == 0


def test_nothing_changed_is_an_answer_not_a_refusal() -> None:
    """⚠️ A partially readable collection whose readable records are all older
    than the cutoff was refused for giving exactly the right answer."""
    accessor.bind(
        FakeDbState(
            db=TreeThatChanges(
                [
                    FakeChanged("S0001", change=1_500_000_000),
                    FakeChanged("S0002", change="unreadable", expose_getter=False),  # type: ignore[arg-type]
                ]
            )
        )
    )
    try:
        found = accessor.changed_since("2026-08-01", kind="sources")
    finally:
        accessor.forget()

    assert found.matches == (), "nothing changed since the cutoff"
    assert found.matched == 0


def test_the_iso_date_times_the_tool_advertises_are_accepted() -> None:
    """⛔ The documented input was rejected by the code that documents it.

    ``changed_since`` says *an ISO date or date-time*, and three hand-written
    ``strptime`` formats are not ISO -- so ``2026-08-01T12:00:00Z``, an offset,
    and fractional seconds all came back as 400.
    """
    import datetime

    naive = accessor._as_epoch("2026-08-01T12:00:00")
    assert naive == int(datetime.datetime(2026, 8, 1, 12, 0, 0).timestamp()), (
        "a naive input must stay LOCAL -- Gramps writes change from time.time()"
    )

    utc = accessor._as_epoch("2026-08-01T12:00:00Z")
    offset = accessor._as_epoch("2026-08-01T14:00:00+02:00")
    assert utc is not None and offset is not None
    assert utc == offset, "the same instant expressed two ways gave two answers"

    assert accessor._as_epoch("2026-08-01T12:00:00.123456") is not None
    assert accessor._as_epoch("2026-08-01") is not None
    assert accessor._as_epoch("2026/08/01") is not None
    assert accessor._as_epoch("last Tuesday") is None


def test_a_change_stamp_of_zero_is_a_stamp_not_an_absence() -> None:
    """⛔ Truthiness said the opposite of the docstring directly above it.

    A stamp of 0 is the Unix epoch -- a real value. Treating it as unreadable
    meant a collection whose public records all carried 0 produced a **refusal**
    instead of the correct empty result.
    """
    assert accessor._change_stamp(FakeChanged("S0001", change=0)) == 0
    assert accessor._change_stamp(FakeChanged("S0002", change=1_787_483_523)) == 1_787_483_523
    assert (
        accessor._change_stamp(FakeChanged("S0003", change="nonsense", expose_getter=False)) is None
    )  # type: ignore[arg-type]


def test_a_fractional_cutoff_does_not_reach_backwards() -> None:
    """⛔ ``int()`` moved a fractional cutoff to the START of its second.

    Gramps stamps whole seconds, so a record changed at ``12:00:00`` was reported
    for a cutoff of ``12:00:00.5`` -- earlier than the instant asked for, which
    is not *at or after*.
    """
    whole = accessor._as_epoch("2026-08-01T12:00:00")
    fractional = accessor._as_epoch("2026-08-01T12:00:00.5")

    assert whole is not None and fractional is not None
    assert fractional == whole + 1, (
        "a fractional cutoff must not include the second it falls inside"
    )
    # ⚠️ And the ordinary whole-second case is untouched.
    assert accessor._as_epoch("2026-08-01T12:00:00") == whole
