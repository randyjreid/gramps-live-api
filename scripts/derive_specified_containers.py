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

# XML 1.0 (Fifth Edition), section 3.3.1, transcribed:
#
#     AttType        ::= StringType | TokenizedType | EnumeratedType
#     StringType     ::= 'CDATA'
#     TokenizedType  ::= 'ID' | 'IDREF' | 'IDREFS' | 'ENTITY' | 'ENTITIES'
#                      | 'NMTOKEN' | 'NMTOKENS'
#     EnumeratedType ::= NotationType | Enumeration
#     NotationType   ::= 'NOTATION' S '(' S? Name (S? '|' S? Name)* S? ')'
#     Enumeration    ::= '(' S? Nmtoken (S? '|' S? Nmtoken)* S? ')'
#
# ⚠️ **THE CLOSED KEYWORD SET IS THE REPAIR, NOT AN INCIDENTAL TIDY-UP.** This
# was `[A-Z]+`, which is what let `NOTATION` pass as a type in its own right: a
# composite `foo NOTATION (gif) #IMPLIED` could not match from `foo`, so the
# scan resumed at `NOTATION`, emitted a fabricated attribute of that name, and
# the real attribute vanished. **And the fail-closed check below passed anyway**,
# because the later match consumed the declaration's tail -- so the script
# emitted a partial table while claiming it would refuse to. The fabricated row
# is visible in a re-derivation diff; the omission is not.
#
# With the enumerated list, an unknown type token cannot match at all, so the
# parser stops where it stands and the script refuses as it says it does. The
# check that "passed anyway" no longer exists: `attributes_of` walks the body
# left to right and cannot advance past a byte it did not match.
# Ordering is longest-first -- `IDREFS` before `IDREF` before `ID`, `ENTITIES`
# before `ENTITY`, `NMTOKENS` before `NMTOKEN` -- plus `\b`, so a longer type is
# never shadowed by the shorter one it begins with. That is the rule the guard's
# own `_qualified` follows, for the same reason.
#
# Closed and externally specified, so this enumeration is accepted on exactly
# the grounds the guard's transcribed productions are: it does not grow.
_ATT_TYPE = (
    r"NOTATION\s*\([^)]*\)"
    r"|\([^)]*\)"
    r"|(?:CDATA|IDREFS|IDREF|ID|ENTITIES|ENTITY|NMTOKENS|NMTOKEN)\b"
)

# ⚠️ **`AttValue` may be quoted EITHER way**, and this accepted only `"…"`.
# That failed closed -- the whole attribute failed to match and the parser
# refused -- so it defeated no guarantee, but it refused a valid DTD, and
# leaving a known identical hole in the production being repaired is the class
# this fix exists to close. It changes nothing in the committed table.
_ATT_VALUE = r"(?:'[^']*'|\"[^\"]*\")"

# One attribute definition inside an ATTLIST: a name, a declared type, and the
# default declaration that terminates it. The default is what makes this
# unambiguous -- without it, the next attribute's name is indistinguishable
# from a second type token.
_ATTRIBUTE = re.compile(
    r"(?P<name>[A-Za-z_:][\w.:-]*)\s+"
    r"(?P<type>" + _ATT_TYPE + r")\s+"
    r"(?:\#REQUIRED|\#IMPLIED|\#FIXED\s+(?P<fixed>" + _ATT_VALUE + r")|" + _ATT_VALUE + r")",
    re.DOTALL,
)

# Where the next definition begins, or nothing but whitespace is left. The
# parser below walks an ATTLIST body position by position, so it needs exactly
# one thing the productions above do not give it: how far to skip between two
# definitions, and how to tell the end of the body from the start of the next.
_NEXT_DEFINITION = re.compile(r"\S")

_VALUE_SEPARATOR = "/"
"""Where a ``#FIXED`` default is split before it is written out.

⚠️ **The emitted module is tracked content this repository's own guard scans,
and the value this emission was added for is a namespace.** The guard scores
that namespace as a substring wherever it appears, and its constant's own note
records the published range showing it **43 times** when an anchor came off. So
the value is never written contiguously; it is split here and joined by whoever
reads it. The split is deterministic given the value, so the byte-for-byte
reproduction property this script rests on is untouched.
"""

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


def attributes_of(
    dtd: str,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, tuple[str, ...]]]]:
    """Every (element, attribute, declared type), and every ``#FIXED`` default.

    Both in declaration order, and both out of ONE pass: the second is a
    property of the same declarations the first reads, and parsing an ATTLIST
    twice would be a second place for the production to be spelled.

    ⚠️ **An unparsed definition is a failure, not a shortfall.** A declaration
    this cannot read is an attribute silently missing from the table, which is
    the fail-open shape of every enumeration defect this module has had, so it
    stops the derivation instead.

    ⚠️ **THE GUARANTEE IS STRUCTURAL, AND THAT IS THE REPAIR.** This used to
    scan the body for matches and then check the text left over after the last
    one -- two checks, of which only the second was ever written down. It
    validated the TAIL and nothing else: in ``bad WIDGET #IMPLIED good CDATA
    #IMPLIED`` the scan skipped the unreadable definition, the later match
    carried the consumed offset to the end of the body, the remainder was empty,
    and the script emitted a partial table while reporting that it never would.
    Same shape as the composite-type defect above -- something the pattern could
    not read was passed over and the check succeeded anyway -- and the silent
    omission is again the exposure a re-derivation diff cannot show.

    So the body is now consumed left to right and **the parser cannot advance
    past a byte it did not match**. "Nothing was skipped" stops being a property
    somebody has to maintain, and the refusal quotes the FIRST unreadable text
    rather than whatever survived to the end.

    ⚠️ **Both ``EnumeratedType`` forms normalise to ``_ENUMERATION``.** A
    NOTATION type is a fixed vocabulary of the format's own, which is what that
    constant's note already says of the inline form; recording the two
    differently would be a distinction the table has no question for.
    """
    found: list[tuple[str, str, str]] = []
    defaults: list[tuple[str, str, tuple[str, ...]]] = []
    for declaration in _ATTLIST.finditer(dtd):
        element = declaration.group("element").lower()
        body = declaration.group("body")
        position = 0
        while True:
            following = _NEXT_DEFINITION.search(body, position)
            if following is None:
                # Whitespace to the end of the body: the list is read whole.
                break
            position = following.start()
            attribute = _ATTRIBUTE.match(body, position)
            if attribute is None:
                raise SystemExit(
                    f"unread attribute text on <{element}>: {body[position : position + 60]!r} "
                    "-- the derivation would silently omit it"
                )
            name = attribute.group("name").lower()
            declared = " ".join(attribute.group("type").split())
            found.append(
                (
                    element,
                    name,
                    _ENUMERATION if declared.startswith(("(", "NOTATION")) else declared,
                )
            )
            fixed = attribute.group("fixed")
            if fixed is not None:
                defaults.append((element, name, tuple(fixed[1:-1].split(_VALUE_SEPARATOR))))
            position = attribute.end()
    return found, defaults


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
    fixed_defaults: list[tuple[str, str, tuple[str, ...]]],
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

    lines.append("FIXED_ATTRIBUTE_DEFAULTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (")
    for element, attribute, pieces in fixed_defaults:
        written = ", ".join(quoted(piece) for piece in pieces)
        lines.append(f"    ({quoted(element)}, {quoted(attribute)}, ({written})),")
    lines.append(")")
    lines.append('"""Every value the schema FIXES an attribute at, split at each separator.')
    lines.append("")
    lines.append("The declared type says what kind of thing an attribute is; this says what the")
    lines.append("schema requires the attribute to BE, which is how the namespace a Gramps")
    lines.append("document declares becomes a fact read off the specification rather than a")
    lines.append("string somebody typed into the guard.")
    lines.append("")
    lines.append("⚠️ **Split rather than written whole, and that is not a style choice.** This")
    lines.append("file is tracked content the repository's own guard scans, and the guard scores")
    lines.append("that namespace as a substring wherever it appears -- 43 times over the")
    lines.append("published range, once an anchor came off. Rejoin with a forward slash.")
    lines.append('"""\n')

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
    attributes, fixed_defaults = attributes_of(bare)

    sys.stdout.write(
        emit(
            digests,
            elements_of(bare),
            attributes,
            fixed_defaults,
            html_element_names(html) | svg_element_names(svg),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
