"""Who is in the tree, read from a Gramps XML export. Nothing is written here.

Issue #64 is the whole reason this module exists: ``docs/using.md`` told the
owner to find a person's handle by opening the export in a text editor, and on
demo day he did not do it. The export is gzipped XML holding thousands of
people and handles are invisible in the Gramps UI by design, so the documented
step was never a step. This is what does it instead.

⚠️ **The source is the EXPORT, not the open database, and that is a real
trade.** It needs no Gramps process, no ``gi`` and no lock, so every property
below is covered by ordinary unit tests on a runner that has never seen Gramps
-- which is the same boundary ``core.apply`` draws. What it costs is
**staleness**: the export is a snapshot and the copy is live. A handle from an
export made before the copy diverged fails closed at the write (``TargetNotFound``
or ``TargetDisagrees``), and ``cli check`` compares their timestamps so the owner
meets the fact before a refusal does. See ``docs/slice2-mcp.md``.

⚠️ **This is NOT a date model, and it must not become one by accident.** #21 is
out of scope. ``birth_year`` is an integer for sorting and recognising; the raw
shape survives in ``birth_display`` so a range reads as a range instead of being
flattened into a point value the record never asserted -- **and so does what the
record says about that shape**, which is the same property one level down: an
estimated year is not an exact one either. See ``_qualified``.

**Matching is on LOCAL NAME, never on the namespace URI.** The URI carries the
schema version, so matching it would make this reader's answer depend on which
Gramps wrote the file -- the "definition supplied by the surroundings" failure
this project has already paid for four times.
"""

from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

RESULT_CAP = 25
"""How many people one search may return.

A cap rather than a page: every name it returns enters a model's context, and
the ruling that permits that bounds it by the tree's own privacy flag and by
ordinary design. ``Found.matched`` says how many there were, so a caller that
hits the cap is told to narrow rather than left believing it saw everything.
"""

_GZIP_MAGIC = b"\x1f\x8b"

_LEADING_YEAR = re.compile(r"^\s*(\d{4})")
"""A four-digit year at the start of a value, and nothing cleverer.

``dateval``'s ``val`` is ISO-ish (``1856``, ``1856-03``, ``1856-03-04``), so
this reads it exactly. A ``datestr`` carrying prose gives no year, which is the
case ``birth_display`` exists to keep distinguishable from *nothing recorded*.
"""

BIRTH = "Birth"
"""The ``<type>`` text of a birth event, per the Gramps XML schema."""

_CARRIES_DATA = frozenset({"person", "event"})
"""The two elements this reader reads. Everything else is bulk it walks past.

⚠️ **It is what ``_elements`` must not free early**, not merely what
``read_export`` dispatches on. The children of these two are read when the
parent closes, so an element with one of them still open above it has to survive
until it does.
"""

_DATE_VALUE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "dateval": ("val",),
    "daterange": ("start", "stop"),
    "datespan": ("start", "stop"),
    "datestr": ("val",),
}
"""What each date shape carries the date ITSELF in, per shape.

The complement ``_DATE_QUALIFIERS`` is defined against, and the half that makes
the binding test exhaustive: value attributes plus qualifiers is *every*
attribute the schema declares for the shape, so neither table can drift without
that equality failing.
"""

_DATE_QUALIFIERS: dict[str, tuple[str, ...]] = {
    "dateval": ("type", "quality", "cformat", "dualdated", "newyear"),
    "daterange": ("quality", "cformat", "dualdated", "newyear"),
    "datespan": ("quality", "cformat", "dualdated", "newyear"),
    "datestr": (),
}
"""What each date shape says ABOUT its date, in the schema's declaration order.

Read out of ``share/gramps/grampsxml.dtd`` in the installed Gramps 6.0.8, whose
``<!ATTLIST dateval>`` declares ``val`` plus ``type (before|after|about)``,
``quality (estimated|calculated)``, ``cformat``, ``dualdated (0|1)`` and
``newyear``; ``daterange`` and ``datespan`` declare the same four beside
``start`` and ``stop`` **but no ``type``**; and ``<!ATTLIST datestr val CDATA
#REQUIRED>`` declares nothing else at all, so that branch was never lossy.

⚠️ **Composed here and BOUND BY TEST to the frozen table**, which is what
derived means in this repository -- see the note in ``pii_guard`` on why that is
not an import. A qualifier a later schema adds fails
``test_the_qualifier_set_is_the_schemas_minus_what_is_read_as_the_date`` on the
re-derivation rather than being silently dropped from a label that claims to be
lossless.

⚠️ **The ORDER is the schema's, and that is the whole reason there is a table
here rather than a walk over whatever attributes the element carries.**
Attribute order is not significant in XML and ``iterparse`` returns it as
written, so a label built from the document's order would give one date two
labels depending on how the exporter spelled it -- the definition-from-the-
surroundings failure this module's local-name matching already refuses once.
"""

PRIMARY_ROLE = "Primary"
"""The ``role`` on an ``<eventref>`` that makes the event the person's own.

The untranslated string from ``EventRoleType._DATAMAP``, which is what
``xml_str`` writes and what ``set_from_xml_str`` matches -- exactly, so this
matches it exactly too.
"""


class PeopleError(Exception):
    """The export cannot be read, or a question about it cannot be answered."""


class ExportUnreadable(PeopleError):
    """The file is not a Gramps XML export this reader can parse."""


class SearchTermRequired(PeopleError):
    """A listing was asked for with no term to narrow it.

    ⚠️ **Deliberate, and it is a privacy control rather than an ergonomic one.**
    Every name returned goes into a model's context by design (see the residual
    in ``docs/slice2-mcp.md``); *list everyone* would put the whole tree there in
    one call, which is a different act from looking somebody up.
    """


@dataclass(frozen=True, slots=True)
class Person:
    """One person as the export records them, with nothing inferred.

    ``handle`` has had its one leading underscore removed, because
    ``plugins/importer/importxml.py`` reads the attribute as
    ``attrs["handle"].replace("_", "")`` -- so the raw attribute is not what the
    database holds and not what a reference may name.
    """

    gramps_id: str
    handle: str
    name: str
    birth_year: int | None
    birth_display: str
    """The record's own date, and what the record said about it. May be empty.

    The lossless half of the pair: the shape the export used, plus every
    qualifier the schema declares for that shape, as ``1856 [quality=Estimated]``
    -- see ``_qualified``. ``birth_year`` beside it is the approximation, and
    empty here means no date element at all rather than none this reader liked.
    """

    private: bool
    other_birth_events: int = 0
    """How many further birth events **of their own** they carry beyond the one shown.

    Counted rather than hidden: a person with two birth events has a record
    somebody should look at, and a reader that silently picked one would be the
    only thing that knew.

    ⚠️ **It counts what ``_own`` selected, not everything referenced.** A birth
    somebody merely witnessed is not a birth event they carry, and counting it
    here would report the record as doubtful on the strength of somebody else's
    event.
    """


@dataclass(frozen=True, slots=True)
class Found:
    """What a search returned, and how much it did not return.

    ⚠️ **``matched`` counts what the caller was ALLOWED to see.** A private
    person is not in ``people`` and is not in ``matched`` either -- reporting
    *42 matched, 25 shown* over a set that included people it will never show
    would leak the existence of the excluded ones by arithmetic.
    """

    people: tuple[Person, ...]
    matched: int


@dataclass
class _Raw:
    """A person element as read, before event references are resolved."""

    gramps_id: str = ""
    handle: str = ""
    name: str = ""
    private: bool = False
    event_refs: list[tuple[str, str | None]] = field(default_factory=list)
    """``(handle, role)``, where ``None`` is a role the document did not state.

    ⚠️ **``None`` and ``""`` are different documents and Gramps reads them
    differently**, so the absent case is carried as absent rather than
    flattened into an empty string. See ``_own``.
    """


def local_name(tag: object) -> str:
    """The element name with any namespace removed.

    ``{http://gramps-project.org/xml/1.7.2/}person`` is ``person``, and so is
    the same element out of a file written by any other Gramps. The version
    lives in that URI, which is exactly why it is discarded here.
    """
    return str(tag).rpartition("}")[2]


def read_export(path: str) -> tuple[Person, ...]:
    """Every person in the export at ``path``, private ones included.

    ⚠️ **Private people ARE returned, and the filtering happens above.** The two
    enforcement points ruling 1 sets are different questions -- a listing must
    not show them, and a target must be refused *by name* rather than reported
    as absent -- and a reader that dropped them here could only answer the
    second one wrongly.

    One streaming pass with ``iterparse``, because a real tree is megabytes, and
    two collections resolved afterwards, because nothing guarantees ``<events>``
    comes after ``<people>``.
    """
    people: list[_Raw] = []
    births: dict[str, tuple[int | None, str]] = {}
    try:
        with _opened(path) as stream:
            for element in _elements(stream):
                name = local_name(element.tag)
                if name == "person":
                    people.append(_person(element))
                elif name == "event":
                    _birth(element, births)
    except ET.ParseError as failure:
        raise ExportUnreadable(f"{path}: this is not readable as XML -- {failure}") from failure
    except (EOFError, zlib.error) as failure:
        # ⚠️ **Neither of these is an ``OSError``, and that is the whole of the
        # defect.** A gzip stream that ends early raises ``EOFError``; damage
        # inside the compressed data raises ``zlib.error``. Both escaped the two
        # handlers around them, so the caller got a raw internal exception where
        # the designed refusal should have been -- and this one travels: the MCP
        # tools relay what they are given, so a decompressor's message about bit
        # lengths reaches a person as noise with no remedy in it.
        #
        # A failed CHECKSUM is not in this pair on purpose: ``gzip`` raises
        # ``BadGzipFile`` for that and ``BadGzipFile`` subclasses ``OSError``,
        # so it was already caught below. Three ways for a file to be damaged,
        # one message, and the tests name all three so they stay one state.
        raise ExportUnreadable(
            f"{path}: this export is truncated or corrupt and cannot be read -- {failure}. "
            "Export the tree again"
        ) from failure
    except OSError as failure:
        raise ExportUnreadable(f"{path}: {failure.strerror or failure}") from failure
    return tuple(_resolved(raw, births) for raw in people)


def search(people: Sequence[Person], term: str, *, cap: int = RESULT_CAP) -> Found:
    """The people whose name contains ``term``, minus the private ones.

    ``str.casefold`` rather than ``str.lower``: lowering leaves the sharp s
    alone, so a caller typing ``weissvane`` on an ASCII keyboard misses a name
    spelled with one. Folding is what "the same name written differently" means
    for matching, and lowering is what it means for display.
    """
    wanted = term.strip()
    if not wanted:
        raise SearchTermRequired(
            "a search term is required -- name part of the person you are looking for"
        )
    folded = wanted.casefold()
    matches = [
        person for person in people if not person.private and folded in person.name.casefold()
    ]
    return Found(people=tuple(matches[:cap]), matched=len(matches))


def find(people: Iterable[Person], gramps_id: str) -> Person | None:
    """The person with that Gramps ID, **private or not**, or ``None``.

    The Gramps ID resolves, matching ``core.apply``'s ruling on which half of a
    reference is authoritative: it is what a person supplied and what the
    preview showed them.
    """
    return next((person for person in people if person.gramps_id == gramps_id), None)


# ---------------------------------------------------------------------------
# Reading one element
# ---------------------------------------------------------------------------


def _opened(path: str) -> io.BufferedIOBase:
    """The export as a byte stream, decompressed if it is compressed.

    ⚠️ **Sniffed, not decided by the extension.** Gramps writes gzipped XML
    under ``.gramps``, and it also writes plain XML under the same extension
    when the box is unticked. Reading the first two bytes answers the question
    the name only guesses at -- and issue #64's first bullet is that nobody told
    the owner it was compressed at all.
    """
    with open(path, "rb") as probe:
        compressed = probe.read(len(_GZIP_MAGIC)) == _GZIP_MAGIC
    return gzip.open(path, "rb") if compressed else open(path, "rb")  # noqa: SIM115


def _elements(stream: io.BufferedIOBase) -> Iterator[ET.Element]:
    """Every element, as it closes, **and freed once the caller has read it**.

    Streaming, because a real tree is megabytes -- and the freeing is what makes
    that word true rather than aspirational. Two separate things have to happen
    and only one of them is ``clear``:

    - **``element.clear()`` empties an element of its children**, and it used to
      run for ``person`` and ``event`` alone. Every other element fell through
      an ``else: continue``, so a real export's ``<notes>``, ``<families>``,
      ``<citations>`` and ``<sources>`` -- which this reader looks at none of --
      were built and kept for the length of the file.
    - **``iterparse`` leaves a finished element in its parent's child list.**
      Clearing it empties the shell and does not unlink it, so ``<people>`` goes
      on accumulating one emptied ``<person>`` per person in the tree. Removing
      it from its parent is what actually drops it.

    ⚠️ **The freeing happens AFTER the ``yield``, which is the whole reason this
    is a generator.** Control returns here only when the caller asks for the next
    element, so by then it has finished with this one. Doing it before would hand
    back an emptied element.

    ⚠️ **An element inside a ``person`` or an ``event`` is NOT freed at its own
    end.** Those close first -- ``<first>`` before ``<name>`` before ``<person>``
    -- and ``_person`` reads them when the person closes, so freeing them on the
    way past would hand the caller an empty husk. ``open_data`` counts how many
    of the two are still open; while it is non-zero this yields and frees
    nothing, and the ancestor's own ``clear`` takes the whole subtree at once.

    The removal is O(1) in practice rather than a scan: each child is unlinked
    as it closes, so a parent never holds more than the one.
    """
    ancestors: list[ET.Element] = []
    open_data = 0
    for event, element in ET.iterparse(stream, events=("start", "end")):
        carries_data = local_name(element.tag) in _CARRIES_DATA
        if event == "start":
            ancestors.append(element)
            open_data += carries_data
            continue
        ancestors.pop()
        open_data -= carries_data
        yield element
        if open_data:
            continue
        element.clear()
        if ancestors:
            # ⚠️ ``Element.remove`` compares by IDENTITY, per its own
            # documentation -- so this unlinks this element and not a sibling
            # that happens to carry the same tag and the same (now empty)
            # contents. Emptying it first would otherwise make them all alike.
            ancestors[-1].remove(element)


def _person(element: ET.Element) -> _Raw:
    raw = _Raw(
        gramps_id=element.get("id", ""),
        handle=_handle(element.get("handle", "")),
        private=_private(element.get("priv")),
    )
    for child in element:
        name = local_name(child.tag)
        if name == "name" and not raw.name and child.get("alt") != "1":
            raw.name = _name(child)
        elif name == "eventref":
            raw.event_refs.append((_handle(child.get("hlink", "")), child.get("role")))
    return raw


def _birth(element: ET.Element, births: dict[str, tuple[int | None, str]]) -> None:
    """Record ``element`` under its handle if it is a birth. Others are skipped."""
    kind = next((child for child in element if local_name(child.tag) == "type"), None)
    if kind is None or (kind.text or "").strip() != BIRTH:
        return
    births[_handle(element.get("handle", ""))] = _date(element)


def _date(event: ET.Element) -> tuple[int | None, str]:
    """The event's date as a year for sorting and a label for reading.

    ⚠️ **Four shapes, and the label is not a rendering of a parsed date.** It
    carries what the record said, so a range stays a range. Turning any of these
    into one comparable value is #21, which is out of scope, and a label that
    quietly did it would be the date model arriving by accident.

    ⚠️ **What the record says ABOUT the date is part of what it said.** An
    ``<dateval val="1856" quality="Estimated"/>`` labelled ``1856`` presents an
    estimate as a fact -- in the one listing whose job is telling people apart
    -- so every qualifier the shape declares is appended by ``_qualified``.
    ``birth_year`` is untouched by any of it: the sortable half was always an
    approximation and this is the half that is not.
    """
    for child in event:
        name = local_name(child.tag)
        if name == "dateval":
            value = child.get("val", "")
            return _year(value), _qualified(child, value)
        if name == "daterange":
            return _spanning(child, "between {start} and {stop}")
        if name == "datespan":
            return _spanning(child, "from {start} to {stop}")
        if name == "datestr":
            value = child.get("val", "")
            return _year(value), _qualified(child, value)
    return None, ""


def _spanning(element: ET.Element, wording: str) -> tuple[int | None, str]:
    """A two-ended date, labelled as one. The START is what gives the year.

    All three exits go through ``_qualified``, including the one-ended and the
    valueless ones. Fixing only the branch a finding names is how the adjacent
    branch keeps the same defect.
    """
    start = element.get("start", "")
    stop = element.get("stop", "")
    if not start and not stop:
        return None, _qualified(element, "")
    if not stop:
        return _year(start), _qualified(element, start)
    return _year(start), _qualified(element, wording.format(start=start, stop=stop))


def _qualified(element: ET.Element, label: str) -> str:
    """``label`` with every qualifier the record put on ``element``, verbatim.

    **Read as ``1856 [quality=Estimated]``, and deliberately not as prose.** The
    label is for somebody skimming a short list to recognise a person before
    attaching a note to them, so the only hard requirement is that ``1856`` and
    an estimated ``1856`` are not one string. Beyond that the bracket form is
    chosen over Gramps' own wording for two reasons:

    - **It cannot be mistaken for a rendered date.** ``about 1856`` reads as
      this module having understood the date; ``1856 [type=about]`` reads as it
      quoting the record, which is all it did. That difference is exactly the
      accident ``_date``'s warning is about.
    - **It needs no vocabulary.** ``quality`` and ``type`` have enumerated
      English values, but ``cformat``, ``dualdated`` and ``newyear`` do not, and
      a prose scheme would need this module to translate each of them -- and to
      invent a word order the record never stated. Naming the field says what
      the record said and nothing more.

    ⚠️ **An unrecognised attribute is NOT appended, and an empty label still
    takes the suffix.** The first keeps a hand-written ``type`` on a range out
    of the label, because the schema declares none there; the second keeps a
    date element that carries a qualifier and no value distinguishable from the
    record that carries no date element at all, which is the distinction the
    empty label exists to make.
    """
    stated = [
        f"{name}={value}"
        for name in _DATE_QUALIFIERS.get(local_name(element.tag), ())
        if (value := element.get(name)) is not None
    ]
    if not stated:
        return label
    suffix = "[" + ", ".join(stated) + "]"
    return f"{label} {suffix}" if label else suffix


def _year(value: str) -> int | None:
    """The four-digit year a value opens with, or nothing.

    Nothing is the honest answer for free text, and it is why ``birth_display``
    is carried beside this: *no year* and *nothing recorded* have to stay
    distinguishable, and only one of them has a label.
    """
    found = _LEADING_YEAR.match(value)
    return int(found.group(1)) if found else None


def _name(element: ET.Element) -> str:
    """A primary name, as a person would write it: given names then surname."""
    parts = []
    for child in element:
        if local_name(child.tag) in {"first", "surname"}:
            text = (child.text or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def _handle(raw: str) -> str:
    """The handle the database holds: the attribute, less ONE leading underscore.

    ⚠️ **One, not all of them.** ``importxml`` strips every underscore, and
    copying that here would silently rewrite a handle that legitimately begins
    with one -- a value the caller then hands to ``validate``'s reference check,
    which would refuse it with no clue why.
    """
    return raw[1:] if raw.startswith("_") else raw


def _private(flag: str | None) -> bool:
    """Whether ``priv`` marks this record private. **Unstated is not private.**

    Gramps' own default, which ruling 1 says to take rather than guess at.

    ⚠️ **A value the schema does not declare IS private.** The DTD declares
    ``priv`` as ``(0|1) #IMPLIED``, so anything else is not a document Gramps
    wrote, and a privacy flag is the wrong place to read an unknown value
    generously. Absent means absent; present and unrecognised means refuse.
    """
    return flag is not None and flag != "0"


def _own(role: str | None) -> bool:
    """Whether an ``eventref`` carrying ``role`` makes the event the person's OWN.

    ⚠️ **A role Gramps names is taken at its word, and only ``Primary`` is the
    person's own.** A witness at a birth carries a valid ``eventref`` to it, and
    a fallback that took any referenced birth gave the witness the baby's birth
    year -- in the one listing whose purpose is telling people apart.

    ⚠️ **An ABSENT role is Primary. That is Gramps' reading, not a guess**, and
    it was read out of the installed copy rather than remembered:

    - ``share/gramps/grampsxml.dtd`` declares ``role CDATA #IMPLIED``, so the
      attribute may legitimately be missing;
    - ``plugins/importer/importxml.py`` does ``if "role" in attrs:
      self.eventref.role.set_from_xml_str(attrs["role"])``, so an absent role
      leaves the ``EventRoleType()`` that ``EventRef.__init__`` constructed;
    - ``gen/lib/grampstype.py`` sets that to ``_DEFAULT``, and
      ``EventRoleType._DEFAULT`` is ``PRIMARY``.

    ⚠️ **An EMPTY role is not an absent one**, which is why the parser keeps the
    two apart instead of reading ``get("role", "")``. ``set_from_xml_str("")``
    finds nothing in ``_E2IMAP`` and falls to the else branch: ``_CUSTOM`` with
    an empty name. So ``role=""`` is a custom role, not Primary -- and no Gramps
    export contains one, because ``exportxml.py`` writes the attribute only
    ``if role:``. Nothing is lost by reading a hand-written ``role=""`` the way
    Gramps reads it, and reading it as Primary because the string is empty would
    be a definition taken from the shape of our own parsing.
    """
    return role is None or role == PRIMARY_ROLE


def _resolved(raw: _Raw, births: dict[str, tuple[int | None, str]]) -> Person:
    """One person with their birth event looked up, after the whole file is read."""
    chosen = [handle for handle, role in raw.event_refs if handle in births and _own(role)]
    year, display = births[chosen[0]] if chosen else (None, "")
    return Person(
        gramps_id=raw.gramps_id,
        handle=raw.handle,
        name=raw.name,
        birth_year=year,
        birth_display=display,
        private=raw.private,
        other_birth_events=max(len(chosen) - 1, 0),
    )
