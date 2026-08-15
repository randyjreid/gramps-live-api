r"""Derive the frozen container table from the published specifications.

Run this by hand, never in CI. It reads artifacts that were fetched
**separately** and prints ``_specified_containers.py`` on standard output:

    python scripts/derive_specified_containers.py \
        <gramps dtd> <html element index> <svg element index> \
        > src/gramps_live_api/core/_specified_containers.py

⚠️ **CI never fetches anything, and neither does this script.** The network
step is a human one, recorded in the derivation note with each artifact's
digest, so the offline suite can assert the committed table against the
weighting table without ever leaving the machine.

⚠️ **The output is the committed file, byte for byte.** Verification is
re-fetch, compare digest, re-run, and diff -- so nothing here may vary between
runs over the same inputs. In particular this emits **no timestamp**: a fetch
date is a fact about a fetch rather than about a specification, and stamping
one here would make every re-derivation differ from the file it is checking.

Stdlib only, deliberately: a build input this repository cannot audit is worse
than a build step somebody has to run by hand.
"""

from __future__ import annotations

import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# The DTD.
#
# A DTD is not XML and is not parsed by anything in the standard library, but
# the two declarations this reads are regular enough to be read directly, and
# the alternative -- a dependency -- is refused on the standing grounds.
#
# COMMENTS ARE STRIPPED FIRST, and that is not tidiness: this DTD's commentary
# quotes the declarations it is explaining, so a scan of the raw text reads
# documentation as specification.
# ---------------------------------------------------------------------------

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_ELEMENT = re.compile(r"<!ELEMENT\s+(?P<name>\S+)\s+(?P<model>.*?)>", re.DOTALL)
_ATTLIST = re.compile(r"<!ATTLIST\s+(?P<element>\S+)\s+(?P<body>.*?)>", re.DOTALL)

# One attribute definition inside an ATTLIST: a name, a declared type, and the
# default declaration that terminates it. The default is what makes this
# unambiguous -- without it, the next attribute's name is indistinguishable
# from a second type token.
_ATTRIBUTE = re.compile(
    r"(?P<name>[A-Za-z_:][\w.:-]*)\s+"
    r"(?P<type>\([^)]*\)|[A-Z]+)\s+"
    r'(?:\#REQUIRED|\#IMPLIED|\#FIXED\s+"[^"]*"|"[^"]*")',
    re.DOTALL,
)

_ENUMERATION = "enumeration"
"""What an inline enumeration is called once its members stop mattering.

The members are the values a document may write; the *question* this table
answers is what kind of thing the attribute is, and an enumerated attribute is
a fixed vocabulary of the format's own -- bookkeeping, never a payload.
"""


def content_model(declared: str) -> str:
    """Which of the four content models ``declared`` is.

    ⚠️ **This is the derivation rule the audit actually rests on.** "Can this
    container hold prose or an identity field" is a question the DTD answers
    mechanically -- ``(#PCDATA)`` versus ``EMPTY`` versus a child list -- so it
    is read off the specification rather than decided by whoever is reading.
    What the audit still decides is the *category*, per row, with a test.
    """
    squashed = " ".join(declared.split())
    if squashed == "EMPTY":
        return "empty"
    if squashed == "(#PCDATA)":
        return "pcdata"
    if "#PCDATA" in squashed:
        return "mixed"
    return "children"


def elements_of(dtd: str) -> list[tuple[str, str]]:
    """Every declared element with its content model, in declaration order."""
    return [
        (found.group("name").lower(), content_model(found.group("model")))
        for found in _ELEMENT.finditer(dtd)
    ]


def attributes_of(dtd: str) -> list[tuple[str, str, str]]:
    """Every (element, attribute, declared type), in declaration order.

    ⚠️ **An unparsed tail is a failure, not a shortfall.** A declaration this
    cannot read is an attribute silently missing from the table, which is the
    fail-open shape of every enumeration defect this module has had, so it
    stops the derivation instead.
    """
    found: list[tuple[str, str, str]] = []
    for declaration in _ATTLIST.finditer(dtd):
        element = declaration.group("element").lower()
        body = declaration.group("body")
        consumed = 0
        for attribute in _ATTRIBUTE.finditer(body):
            declared = " ".join(attribute.group("type").split())
            found.append(
                (
                    element,
                    attribute.group("name").lower(),
                    _ENUMERATION if declared.startswith("(") else declared,
                )
            )
            consumed = attribute.end()
        remainder = body[consumed:].strip()
        if remainder:
            raise SystemExit(
                f"unread attribute text on <{element}>: {remainder[:60]!r} -- the derivation "
                "would silently omit it"
            )
    return found


# ---------------------------------------------------------------------------
# The two markup element indexes.
#
# These answer ONE question: which of the schema's spellings are also the
# name of an ordinary markup element. A spelling that is cannot earn weight,
# because this repository is full of markup and a document that merely uses it
# is not carrying a person -- see the deliberately-unweighted category.
# ---------------------------------------------------------------------------

_SVG_ENTRY = re.compile(r'class="element-name">.*?<span>([A-Za-z][\w-]*)</span>', re.DOTALL)


class _HtmlElementIndex(HTMLParser):
    """The first cell of every BODY row of the index's element table.

    ⚠️ **Body rows only, and the header row is why.** The table's own column
    headings are words -- ``description``, ``children``, ``attributes`` -- and
    ``description`` is a real element of the schema being derived. Reading the
    heading row would zero a genuine container on the strength of a table
    label, which is a fail-open produced entirely inside the derivation.

    ⚠️ **The index omits closing cell tags**, so a cell ends where the next one
    begins rather than at an end tag that never arrives. Waiting for
    ``</th>`` reads no names at all.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: list[str] = []
        self._in_body = False
        self._in_cell = False
        self._buffer = ""

    def _flush(self) -> None:
        if not self._in_cell:
            return
        self._in_cell = False
        for piece in self._buffer.split(","):
            candidate = piece.strip().lower()
            if re.fullmatch(r"[a-z][a-z0-9-]*", candidate):
                self.names.append(candidate)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tbody":
            self._in_body = True
        if tag in ("td", "th", "tr"):
            self._flush()
        if tag == "th" and self._in_body:
            self._in_cell = True
            self._buffer = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("tr", "table"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buffer += data


def html_element_names(index: str) -> set[str]:
    """The element names the HTML index lists."""
    opening = index.find("<caption>List of elements</caption>")
    if opening < 0:
        raise SystemExit("the HTML index does not contain its element table")
    parser = _HtmlElementIndex()
    parser.feed(index[opening : index.find("</table>", opening)])
    if not parser.names:
        raise SystemExit("the HTML element table yielded no names")
    return set(parser.names)


def svg_element_names(index: str) -> set[str]:
    """The element names the SVG index lists."""
    names = {found.group(1).lower() for found in _SVG_ENTRY.finditer(index)}
    if not names:
        raise SystemExit("the SVG element index yielded no names")
    return names


# ---------------------------------------------------------------------------
# Emitting the module.
# ---------------------------------------------------------------------------

_HEADER = '''"""The container vocabulary the published specifications declare.

⚠️ **MACHINE-GENERATED. DO NOT HAND-EDIT.** Regenerate it with
``scripts/derive_specified_containers.py`` over artifacts matching the digests
below, and see the derivation note in ``docs`` for where each one comes from.

This module is DATA, not behaviour: nothing in the guard imports it, and the
scan does not change if it is deleted. It is the **checklist** -- the frozen
enumeration issue #4's exit condition is stated against -- while the weighting
lives in the guard's own vocabulary table. A test binds the two, which is what
makes "every row has a weight and a test" finite and checkable rather than a
promise about an unbounded format.

⚠️ **No fetch date is recorded here.** Verification is re-fetch, compare
digest, re-run, and diff against this file; a timestamp would make every such
run differ from the file it is checking. Dates belong to the note.
"""

from __future__ import annotations
'''


def quoted(value: str) -> str:
    """A string literal the formatter will leave alone."""
    return '"' + value + '"'


def emit(
    digests: list[tuple[str, str]],
    elements: list[tuple[str, str]],
    attributes: list[tuple[str, str, str]],
    markup: set[str],
) -> str:
    """The whole generated module, formatted as the repository formats code."""
    lines = [_HEADER]

    lines.append("SOURCE_DIGESTS: tuple[tuple[str, str], ...] = (")
    for name, digest in digests:
        lines.append(f"    ({quoted(name)}, {quoted(digest)}),")
    lines.append(')\n"""Each source artifact and the SHA-256 it was read from."""\n')

    lines.append("SPECIFIED_ELEMENTS: tuple[tuple[str, str], ...] = (")
    for name, model in elements:
        lines.append(f"    ({quoted(name)}, {quoted(model)}),")
    lines.append(')\n"""Every declared element, with the content model the schema gives it."""\n')

    lines.append("SPECIFIED_ATTRIBUTES: tuple[tuple[str, str, str], ...] = (")
    for element, attribute, declared in attributes:
        lines.append(f"    ({quoted(element)}, {quoted(attribute)}, {quoted(declared)}),")
    lines.append(')\n"""Every (element, attribute, declared type) the schema declares."""\n')

    lines.append("MARKUP_ELEMENT_NAMES: frozenset[str] = frozenset(")
    lines.append("    (")
    for name in sorted(markup):
        lines.append(f"        {quoted(name)},")
    lines.append("    )")
    lines.append(")")
    lines.append('"""Every element name the two published markup indexes list."""')
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit(
            "usage: derive_specified_containers.py <gramps dtd> <html index> <svg index>"
        )
    paths = [Path(argument) for argument in argv]
    raw = [path.read_bytes() for path in paths]
    labels = ("gramps-xml-dtd", "html-element-index", "svg-element-index")
    digests = [
        (label, hashlib.sha256(content).hexdigest())
        for label, content in zip(labels, raw, strict=True)
    ]
    dtd, html, svg = (content.decode("utf-8", "replace") for content in raw)
    bare = _COMMENT.sub(" ", dtd)

    sys.stdout.write(
        emit(
            digests,
            elements_of(bare),
            attributes_of(bare),
            html_element_names(html) | svg_element_names(svg),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
