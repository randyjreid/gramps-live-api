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
flattened into a point value the record never asserted.

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

PRIMARY_ROLE = "Primary"
"""The ``role`` on an ``<eventref>`` that makes the event the person's own."""


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
    private: bool
    other_birth_events: int = 0
    """How many further birth events this person carries beyond the one shown.

    Counted rather than hidden: a person with two birth events has a record
    somebody should look at, and a reader that silently picked one would be the
    only thing that knew.
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
    event_refs: list[tuple[str, str]] = field(default_factory=list)


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
                else:
                    continue
                element.clear()
    except ET.ParseError as failure:
        raise ExportUnreadable(f"{path}: this is not readable as XML -- {failure}") from failure
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
    """Every element, as it closes. Streaming, because a real tree is megabytes."""
    for _, element in ET.iterparse(stream, events=("end",)):
        yield element


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
            raw.event_refs.append((_handle(child.get("hlink", "")), child.get("role", "")))
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
    """
    for child in event:
        name = local_name(child.tag)
        if name == "dateval":
            value = child.get("val", "")
            return _year(value), value
        if name == "daterange":
            return _spanning(child, "between {start} and {stop}")
        if name == "datespan":
            return _spanning(child, "from {start} to {stop}")
        if name == "datestr":
            value = child.get("val", "")
            return _year(value), value
    return None, ""


def _spanning(element: ET.Element, wording: str) -> tuple[int | None, str]:
    """A two-ended date, labelled as one. The START is what gives the year."""
    start = element.get("start", "")
    stop = element.get("stop", "")
    if not start and not stop:
        return None, ""
    if not stop:
        return _year(start), start
    return _year(start), wording.format(start=start, stop=stop)


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


def _resolved(raw: _Raw, births: dict[str, tuple[int | None, str]]) -> Person:
    """One person with their birth event looked up, after the whole file is read."""
    referenced = [(handle, role) for handle, role in raw.event_refs if handle in births]
    primary = [handle for handle, role in referenced if role == PRIMARY_ROLE]
    chosen = primary or [handle for handle, _ in referenced]
    year, display = births[chosen[0]] if chosen else (None, "")
    return Person(
        gramps_id=raw.gramps_id,
        handle=raw.handle,
        name=raw.name,
        birth_year=year,
        birth_display=display,
        private=raw.private,
        other_birth_events=max(len(referenced) - 1, 0),
    )
