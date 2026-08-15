r"""The derivation script's own properties -- offline, over synthetic declarations.

⚠️ **What is under test here is a VERIFICATION MECHANISM, not a scan.** The
script claims to refuse rather than emit a partial table, and the committed
table is checked by re-fetching the artifacts, re-running it and reading an
empty diff. A declaration it silently misreads therefore costs more than a wrong
row: the fabricated row is visible in that diff and **the omitted one is not.**

⚠️ **No network, and no fetched artifact.** These declarations are assembled
here, so the property is asserted on every run rather than on the days somebody
has the three files to hand. The committed table is checked separately, by hand,
against digests recorded in the derivation note.

The script is not an importable module -- it is a hand-run build step in
``scripts/`` -- so it is loaded by path. That is deliberate: making it importable
would mean a package restructure or a dependency, and it is neither part of the
guard nor allowed to become one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "derive_specified_containers.py"


def _derivation() -> ModuleType:
    """The script, loaded by path under a name that is not ``__main__``.

    Under ``__main__`` the module's own guard would run ``main`` on pytest's
    argument list, which is a confusing way to discover that a script has one.
    """
    specification = importlib.util.spec_from_file_location("_derivation_under_test", _SCRIPT)
    assert specification is not None and specification.loader is not None, (
        f"the derivation script is not loadable from {_SCRIPT}"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


_ELEMENT = "ledger"
_ATTRIBUTE = "marque"
"""Invented names, like every other fixture in this suite.

Neither is a Gramps container spelling, so nothing here can pass or fail for a
reason belonging to the guard's vocabulary rather than to this parser.
"""


def _attlist(*definitions: str) -> str:
    """One ``<!ATTLIST>`` declaration holding ``definitions``, assembled."""
    return "<!ATTLIST " + _ELEMENT + " " + " ".join(definitions) + ">"


def _definition(name: str, declared: str, default: str = "#IMPLIED") -> str:
    """One attribute definition: a name, a declared type, a default declaration."""
    return name + " " + declared + " " + default


# XML 1.0 (Fifth Edition) section 3.3.1, transcribed:
#
#     AttType        ::= StringType | TokenizedType | EnumeratedType
#     StringType     ::= 'CDATA'
#     TokenizedType  ::= 'ID' | 'IDREF' | 'IDREFS' | 'ENTITY' | 'ENTITIES'
#                      | 'NMTOKEN' | 'NMTOKENS'
#     EnumeratedType ::= NotationType | Enumeration
#     NotationType   ::= 'NOTATION' S '(' S? Name (S? '|' S? Name)* S? ')'
#     Enumeration    ::= '(' S? Nmtoken (S? '|' S? Nmtoken)* S? ')'
#
# Closed and externally specified, so this enumeration is accepted on exactly
# the grounds the guard's own transcribed productions are: it does not grow.
_EVERY_ATTRIBUTE_TYPE = (
    "CDATA",
    "ID",
    "IDREF",
    "IDREFS",
    "ENTITY",
    "ENTITIES",
    "NMTOKEN",
    "NMTOKENS",
    "(one|two)",
    "NOTATION (gif|png)",
)

_ENUMERATED_FORMS = frozenset({"(one|two)", "NOTATION (gif|png)"})
"""The two ``EnumeratedType`` alternatives, which normalise to one name."""


def test_a_composite_attribute_type_is_read_as_one_attribute() -> None:
    """⭐ **The reproduction: a composite type read as a second attribute.**

    ``NOTATION (gif) #IMPLIED`` is one attribute type in two tokens. The pattern
    could not match from the attribute's name, resumed at ``NOTATION``, and
    emitted a fabricated attribute of that name -- while the real one vanished.

    ⚠️ **And the fail-closed check passed anyway**, which is the actual defect:
    the later match consumed the declaration's tail, so the remainder was empty
    and the script emitted a partial table while claiming it never would.
    """
    derivation = _derivation()

    rows, _ = derivation.attributes_of(_attlist(_definition(_ATTRIBUTE, "NOTATION (gif)")))

    assert rows == [(_ELEMENT, _ATTRIBUTE, derivation._ENUMERATION)], (
        "a NOTATION type belongs to the attribute that declares it, and the table names a "
        f"fabricated attribute instead: {rows}"
    )


def test_a_declaration_the_parser_cannot_read_stops_the_derivation() -> None:
    """The fail-closed guarantee, asserted NON-VACUOUSLY.

    ⚠️ **This is what stops the repair being a pattern that matches
    everything.** Widening the type to whatever appears in that position would
    pass the test above and destroy the guarantee outright -- the script would
    then emit a row for anything, and an unreadable declaration would be a
    plausible-looking row rather than a refusal.

    The closed keyword set is what makes both true at once: an unknown type
    token cannot match, so the remainder check sees the tail it was written for.
    """
    derivation = _derivation()

    with pytest.raises(SystemExit) as refusal:
        derivation.attributes_of(_attlist(_definition(_ATTRIBUTE, "WIDGET")))

    assert "would silently omit" in str(refusal.value), (
        f"an unreadable declaration stops the derivation and says why: {refusal.value}"
    )


def test_every_attribute_type_the_specification_permits_is_read() -> None:
    """Derived over ``AttType`` rather than over the types this DTD happens to use.

    The committed table is unaffected by any of this -- the pinned schema
    declares no composite type -- so a test naming only the reproduction would
    be satisfied by a repair that handles ``NOTATION`` and nothing else. The
    production is closed, so quantify over it.
    """
    derivation = _derivation()
    misread = []

    for declared in _EVERY_ATTRIBUTE_TYPE:
        rows, _ = derivation.attributes_of(_attlist(_definition(_ATTRIBUTE, declared)))
        expected = derivation._ENUMERATION if declared in _ENUMERATED_FORMS else declared
        if rows != [(_ELEMENT, _ATTRIBUTE, expected)]:
            misread.append(f"{declared!r} -> {rows}")

    assert misread == [], (
        f"every alternative of the AttType production is one attribute, and these were not: "
        f"{misread}"
    )


def test_a_longer_type_is_never_shadowed_by_the_shorter_one_it_begins_with() -> None:
    """``IDREFS`` past ``IDREF`` past ``ID``, and the same for the other two families.

    The rule ``_qualified`` follows in the guard, for the reason it follows it:
    an alternation ordered shortest-first matches the prefix and leaves the tail
    unread, which here means the type is wrong AND the remainder check fires on
    text that was perfectly legal. Asserted as the type coming back whole.
    """
    derivation = _derivation()
    shadowed = []

    for declared in ("IDREFS", "IDREF", "ENTITIES", "NMTOKENS"):
        rows, _ = derivation.attributes_of(_attlist(_definition(_ATTRIBUTE, declared)))
        if rows != [(_ELEMENT, _ATTRIBUTE, declared)]:
            shadowed.append(f"{declared!r} -> {rows}")

    assert shadowed == [], f"a longer type was read as a shorter one it begins with: {shadowed}"


def test_a_single_quoted_default_is_read_like_a_double_quoted_one() -> None:
    """``AttValue`` may be quoted either way, and only one spelling was accepted.

    Today this fails CLOSED -- the whole attribute fails to match and the
    remainder check refuses -- so it defeats no guarantee. It refuses a valid
    DTD, though, and leaving a known identical hole in the very production being
    repaired is the class this fix exists to close.
    """
    derivation = _derivation()
    refused = []

    for default in ("'plain'", '"plain"', "#FIXED 'plain'", '#FIXED "plain"'):
        rows, _ = derivation.attributes_of(_attlist(_definition(_ATTRIBUTE, "CDATA", default)))
        if rows != [(_ELEMENT, _ATTRIBUTE, "CDATA")]:
            refused.append(f"{default!r} -> {rows}")

    assert refused == [], f"a valid DefaultDecl was refused for the quote it used: {refused}"


def test_a_fixed_default_is_recorded_with_its_value() -> None:
    """The additive emission the marker gate binds its namespace to.

    The derived table records an attribute's declared TYPE and not its default,
    so the namespace the schema fixes had nothing in the frozen table to be
    bound to. It does now.
    """
    derivation = _derivation()
    value = "http:" + "//example.invalid" + "/ledger/1.0/"

    _, defaults = derivation.attributes_of(
        _attlist(_definition(_ATTRIBUTE, "CDATA", '#FIXED "' + value + '"'))
    )

    assert [(element, name, "/".join(pieces)) for element, name, pieces in defaults] == [
        (_ELEMENT, _ATTRIBUTE, value)
    ], f"a #FIXED default is the value the schema fixes, reassembled: {defaults}"


def test_a_fixed_default_never_reaches_the_emitted_module_as_one_literal() -> None:
    """⭐ **Why the value is emitted in PIECES, and it is not a style choice.**

    The emitted module is a tracked ``.py`` file that this repository's own
    guard scans. The value being added here is a namespace, and the guard scores
    that namespace as a substring wherever it appears -- ``_GRAMPS_XML_NAMESPACE``
    records the published range showing exactly that **43 times** when an anchor
    came off. This emission puts such a value into a tracked file for the first
    time, so it is split at its own separator and joined back by whoever reads
    it.

    Asserted on the EMITTED TEXT rather than on the pieces, because the pieces
    being plural says nothing about what the file ends up spelling.
    """
    derivation = _derivation()
    value = "http:" + "//example.invalid" + "/ledger/1.0/"
    declaration = _attlist(_definition(_ATTRIBUTE, "CDATA", '#FIXED "' + value + '"'))
    rows, defaults = derivation.attributes_of(declaration)

    emitted = derivation.emit([], derivation.elements_of(""), rows, defaults, set())

    assert value not in emitted, (
        "the generated module is tracked content this repository scans, so a fixed value never "
        "appears in it contiguously"
    )
    assert all(piece in emitted for piece in defaults[0][2]), (
        f"and the pieces it is split into are all there: {defaults}"
    )
