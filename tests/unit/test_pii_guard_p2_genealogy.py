"""P2 -- no genealogy data the guard has a property for, whatever it is named,
and no content it cannot prove safe.

Extension matching is necessary and not sufficient: the content is sniffed, and
content the guard cannot classify is a finding rather than a pass. The two
halves are not interchangeable -- a format with a property is caught in any
file type, and one without rests on the safe-type gate, which is the residual
this project recorded first.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from gramps_live_api.core._specified_containers import (
    MARKUP_ELEMENT_NAMES,
    SPECIFIED_ELEMENTS,
)
from gramps_live_api.core.pii_guard import (
    _CATEGORY_WEIGHT,
    _DRAWING,
    _GENEALOGY_TEXT_SIGNATURES,
    _GRAMPS_ALL_ELEMENTS,
    _GRAMPS_ATTRIBUTED_ELEMENT,
    _GRAMPS_CATEGORY_OF,
    _GRAMPS_FILLED_ELEMENT,
    _GRAMPS_PROSE_LENGTH,
    _GRAMPS_XML_NAMESPACE,
    _NCNAME_CONTINUE_RANGES,
    _NCNAME_START_RANGES,
    _VOCABULARY,
    _XML_NAME_PREFIX,
    _gedcom_x_identity_score,
    _gramps_identity_score,
    _qualified,
    scan_blob,
    scan_paths,
    scan_text,
)
from tests.fixtures.expectations import rules
from tests.fixtures.synthetic import (
    _level,
    gedcom_document,
    gedcom_walkthrough,
    gedcom_x_biography_and_address,
    gedcom_x_biography_behind_an_escaped_quote,
    gedcom_x_caption_spelled_with_escapes,
    gedcom_x_contact_only,
    gedcom_x_json,
    gedcom_x_name_parts,
    gedcom_x_name_parts_with_qualifiers,
    gedcom_x_note_only,
    gedcom_x_notes_holding,
    gedcom_x_short_note,
    gramps_address_block,
    gramps_attributed_identity,
    gramps_biography_and_address,
    gramps_biography_in_cdata,
    gramps_caption_spelled_with_character_references,
    gramps_contact_url,
    gramps_importer_spec,
    gramps_issue_address_payload,
    gramps_name_block,
    gramps_namespace_fragment,
    gramps_namespace_url,
    gramps_note_biography,
    gramps_note_interrupted_by,
    gramps_notes_holding,
    gramps_person_fragment,
    gramps_prose_holding_only,
    gramps_reference_fragment,
    gramps_short_notes,
    gramps_short_notes_with_attributes,
    gramps_xml_database_element,
    gramps_xml_document,
    inside_a_cdata_section,
    inside_a_comment,
    json_string_spellings,
    labelled_diagram,
    labelled_diagram_holding,
    notes_inside_a_container,
    positioned_notes_outside_a_drawing,
    prose_describing_json_keys_with_escaped_quotes,
    sqlite_bytes,
    unclassifiable_bytes,
    utf16le_gedcom_bytes,
    worded_diagram,
    xml_content_spellings,
    xml_markup_denoting_nothing,
    xml_markup_in_content,
)

# ---------------------------------------------------------------------------
# Probes for the per-row table test below. Assembled, like every fixture here:
# a structural key written whole in this file would be a genuine finding.
# ---------------------------------------------------------------------------

_PROBE_PAYLOAD = "Elowen Ashenmoor, born 2 April 1893 in Thornwick."
"""Long enough to clear the prose floor, so a prose row scores prose weight.

Every other category ignores what it holds, so one payload serves all of them
and the probes stay comparable across rows.
"""

_PROBE_COPIES = (4, 5)
"""Four clears the threshold even at the smallest weight; five is one more."""


_CARRIER_SPELLING = "surname"
_CARRIER_COPIES = 3
"""A fixed score every Gramps probe carries, so the probe never rests on the row.

⚠️ **Without this a row weighing NOTHING cannot be measured, only crashed
into.** The difference method needs two scores; a spelling worth zero produces
no score at all in either probe, so the helper below used to stop at *"does not
clear the threshold even in quantity"* -- which is the right diagnosis when a
category has been lost in compilation, and the wrong one when the table says
zero on purpose. The derivation adds rows that say exactly that: a spelling the
published markup indexes also use is deliberately unweighted.

Three filled identity elements is six against a threshold of four, so every
probe scores whatever the row under test is worth. Being CONSTANT is the whole
mechanism -- it appears identically in the four-copy and five-copy probes, so
it cancels out of the difference and what remains is still the weight of
exactly one element. It cancels for the row that IS the carrier too.

This is the one pre-existing helper the derivation changed, and it is recorded
in CONTRIBUTING as a deliberate edit. It **strengthens** what the tests can
say: a spelling that scores nothing is now reported by name as a disagreement
with its declared weight, rather than raising about a threshold.
"""


def _carrier() -> str:
    """The constant score, assembled like everything else here."""
    return "".join(
        "<" + _CARRIER_SPELLING + ">" + _PROBE_PAYLOAD + "</" + _CARRIER_SPELLING + ">\n"
        for _ in range(_CARRIER_COPIES)
    )


def _gramps_probe(spelling: str, copies: int) -> str:
    return _carrier() + "".join(
        "<" + spelling + ">" + _PROBE_PAYLOAD + "</" + spelling + ">" for _ in range(copies)
    )


_NAMESPACE_PREFIX = "g"
"""One export's alias for the Gramps namespace.

WHICH alias it is says nothing; the property is that it does not matter, and
that is what the tests below assert. It is joined to the spelling at runtime, so
no tracked file spells a filled prefixed identity element -- the rule at the top
of the fixture module, applied to a probe assembled here.
"""

_COMBINING_NAMESPACE_PREFIX = "a" + chr(0x301)
"""A second alias, and the one that says the property is about NCName.

``a`` followed by COMBINING ACUTE ACCENT: a perfectly legal ``NCName``, because
a combining mark is a ``NameChar``. It is not a ``\\w`` character, which is what
the prefix class used to be built from -- so a document consistently using this
alias was missed by every pattern that reads an element name at once, and a
COMPLETE identity document scored nothing at all rather than merely scoring
less.

⚠️ **Assembled with ``chr`` and never pasted.** The tracked file stays plain
ASCII, which is the same rule the character class in the guard follows for the
same reason: this module reads its own repository. Printing it needs
``PYTHONIOENCODING=utf-8`` on a Windows console, which is a property of the
console and not of the property under test.
"""

_NAMESPACE_PREFIXES = (_NAMESPACE_PREFIX, _COMBINING_NAMESPACE_PREFIX)
"""Every alias the equivalence properties below are asserted over.

Aliases go HERE rather than into a test of their own: the claim is that the
alias does not matter, so a new alias must extend every row of every property
at once, exactly as a new vocabulary row does. A one-off example asserts the
example.
"""


def _prefixed(spelling: str, prefix: str = _NAMESPACE_PREFIX) -> str:
    """The same spelling, qualified by a namespace prefix.

    Joined at runtime, so no tracked file spells a filled prefixed identity
    element. Qualifying the SPELLING rather than wrapping the probe is
    deliberate: ``_observed_weight`` reports a probe that scores nothing by the
    spelling it was given, so wrapping the probe makes a prefixed failure and a
    bare one print the same name.
    """
    return prefix + ":" + spelling


def _admits_as_prefix(candidate: str) -> bool:
    """Whether the compiled prefix class accepts ``candidate`` as a whole prefix.

    The fragment is optional, so a candidate it rejects leaves the trailing
    colon unconsumed and the full match fails -- which is the question being
    asked, and it is asked of the fragment the scoring patterns actually carry
    rather than of a copy of the tables.
    """
    return re.fullmatch(_XML_NAME_PREFIX, candidate + ":") is not None


def _in_any_range(code_point: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    """Whether a table names ``code_point`` -- the same test ``_names_an_xml_character`` makes."""
    return any(first <= code_point <= last for first, last in ranges)


def _gramps_attributed_probe(spelling: str, copies: int) -> str:
    """``copies`` elements of one spelling carrying an attribute and no content.

    The attributed pass is the SECOND site the shared alternation feeds, and it
    is a separate loop -- so a prefix could be taught to one pass and not the
    other, which is this module's oldest defect wearing a new spelling. Scored
    by the same difference method as the filled probe, so it needs no knowledge
    of what the pass charges.
    """
    return _carrier() + "".join(
        "<" + spelling + ' val="' + _PROBE_PAYLOAD + '"/>' for _ in range(copies)
    )


_DRAWING_PREFIX = "svg"
"""The alias a drawing conventionally binds its own namespace to.

Deliberately the harder spelling: ``<svg:svg>`` puts the element's own name in
the prefix position, so a pattern that reads the prefix as if it were the tag
matches the opening and then cannot find its closing tag.
"""

_DRAWING_PREFIXES = (_DRAWING_PREFIX, _COMBINING_NAMESPACE_PREFIX)
"""Every alias the drawing properties below are asserted over.

⚠️ **``svg`` stays FIRST and stays present.** The constant above argues it is
deliberately the harder spelling, and that argument has to survive a second
alias being added beside it rather than being displaced by one. The second is
here for the reason it is in ``_NAMESPACE_PREFIXES``: this site failed under a
combining mark too, and it is the site that fails CLOSED.
"""

_NOT_THE_SVG_NAMESPACE = "urn" + ":" + "example" + ":" + "quarterly-rollup"
"""A namespace that is not SVG, for an alias shaped exactly like SVG's.

Assembled rather than written, like every other value in these fixtures. What
it names does not matter and that is the point: **nothing in this module reads
it.** A prefix is matched by shape and never resolved, so the alias ``svg``
bound here is indistinguishable from the alias ``svg`` bound to the drawing
namespace -- which is why an exemption may not rest on it.
"""


def _alternatives_of(fragment: str) -> list[str]:
    """The spellings ``_qualified`` emitted, in the order it emitted them.

    Reads the helper's own output rather than a pattern that embeds it, so a
    change to the helper's shape fails this loudly instead of quietly returning
    something else.
    """
    return fragment.rsplit("(?:", 1)[1].rstrip(")").split("|")


def _gedcom_x_probe(spelling: str, copies: int) -> str:
    """A GEDCOM X document holding ``copies`` filled keys of one spelling.

    The structural key opens the corroboration gate for the categories that
    need one. It is taken from the table rather than written, and it scores
    identically in both probes, so it cancels out of the difference.
    """
    gate = next(
        (shared + json_only)[0]
        for category, shared, _, json_only in _VOCABULARY
        if category == "structure"
    )
    keys = ",".join('"' + spelling + '":"' + _PROBE_PAYLOAD + '"' for _ in range(copies))
    return '{"' + gate + '":[{' + keys + "}]}"


def _observed_weight(
    scorer: Callable[[str], tuple[int, int] | None],
    probe: Callable[[str, int], str],
    spelling: str,
) -> int:
    """What one filled key or element of ``spelling`` is actually worth.

    Zero is a MEASUREMENT here, not a crash: the Gramps probes carry a constant
    score of their own, so a deliberately-unweighted row measures 0 and is
    reported by its caller against the weight it declares. See ``_carrier``.
    """
    low, high = (scorer(probe(spelling, copies)) for copies in _PROBE_COPIES)
    assert low is not None and high is not None, (
        f"{spelling!r} produced no score in a probe that carries one of its own, so the probe "
        "itself is broken rather than the row being unweighted"
    )
    return int(high[0]) - int(low[0])


def test_gedcom_content_is_a_finding() -> None:
    findings = scan_text(gedcom_document(), source="anything.txt")
    assert rules(findings) == ["P2"], f"expected a P2 finding, got {findings}"


def test_gramps_xml_content_is_a_finding() -> None:
    findings = scan_text(gramps_xml_document(), source="anything.txt")
    assert rules(findings) == ["P2"], f"expected a P2 finding, got {findings}"


def test_a_gedcom_indented_in_a_code_block_is_a_finding() -> None:
    """The threat this property exists for, in the form it will actually arrive.

    Pasting a sample into a design note is what an import spec does, and a
    four-space indent is how Markdown renders one. The document is a safe file
    type, so the signatures are the only thing standing there.
    """
    indented = "".join(f"    {line}\n" for line in gedcom_document().splitlines())

    findings = scan_text(indented, source="notes.md")

    assert rules(findings) == ["P2"], (
        f"verbatim GEDCOM does not stop being GEDCOM when it is indented, got {findings}"
    )


def test_a_gedcom_quoted_in_markdown_is_a_finding() -> None:
    """The other spelling of the same paste: a quoted reply rather than a block."""
    quoted = "".join(f"> {line}\n" for line in gedcom_document().splitlines())

    findings = scan_text(quoted, source="notes.md")

    assert rules(findings) == ["P2"], f"a quoted GEDCOM is still a GEDCOM, got {findings}"


def test_a_record_fragment_with_no_level_zero_line_is_a_finding() -> None:
    """The argument that no prefix class can ever answer.

    Round 7 fixed the anchoring by enumerating which characters may precede a
    level-0 record. A paste that contains no level-0 record at all is invisible
    to any such class, however wide -- the axis is wrong, not the width.
    """
    fragment = "1 NAME Quorvane /Ashenmoor/\n2 SURN Ashenmoor\n1 SEX F\n"

    findings = scan_text(fragment, source="notes.md")

    assert rules(findings) == ["P2"], (
        f"records are records without a header above them, got {findings}"
    )


def test_genealogy_records_are_found_under_any_decoration() -> None:
    """Every form the reviewer committed as a markdown file and got clean.

    Measured over this repository before choosing: the prefix-free variant --
    matching the record shape anywhere in a line -- has no false positives here
    but cannot see a diff line, because the marker abuts the digit with no
    space. Stripping decoration first is what catches all of these.
    """
    document = gedcom_document()
    decorations = {
        "diff fence, added": "+",
        "diff fence, removed": "-",
        "markdown bullet": "- ",
        "table row": "| ",
        "blockquoted diff": "> +",
        "indented code block": "    ",
        "tabbed": "\t",
    }

    missed = [
        name
        for name, prefix in decorations.items()
        if not scan_text(
            "".join(f"{prefix}{line}\n" for line in document.splitlines()), source="notes.md"
        )
    ]
    numbered = "".join(
        f"{number}. {line}\n" for number, line in enumerate(document.splitlines(), 1)
    )
    if not scan_text(numbered, source="notes.md"):
        missed.append("numbered list")

    assert missed == [], f"these spellings of a committed export are not caught: {missed}"


def test_an_annotated_walkthrough_is_a_finding() -> None:
    """A whole identity, one record at a time, with prose between each.

    Adjacency was the wrong axis. The document an importer design note actually
    is does not paste an export in one block: it explains a record, then shows
    the next. Name, sex, birth date, birthplace and occupation went through
    untouched.

    Note the records are level-1 only. A walkthrough that includes the level-0
    header is caught by the header signature, which is what made the first
    attempt at this test pass for the wrong reason.
    """
    findings = scan_text(gedcom_walkthrough(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"a family tree with paragraphs between the records is a family tree, got {findings}"
    )


def test_a_gramps_person_fragment_is_a_finding() -> None:
    """This project's own format, at round-1 strength until now.

    A fragment carrying a full name, gender and birth date matched nothing: the
    element signature wants the database element, and the namespace fallback
    wanted an XML prolog at the very start of the file. Three rounds went into
    hardening GEDCOM, which was already covered, while the native format was
    not.
    """
    findings = scan_text(gramps_person_fragment(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"a person, their gender and their date of birth, got {findings}"
    )


def test_the_gramps_namespace_is_a_finding_wherever_it_sits() -> None:
    """The other half of the same finding: an anchor, not a property.

    The namespace fallback required a prolog at the start of the file, so a
    fragment escaped for the sole reason of not being first in its document.
    """
    findings = scan_text(gramps_namespace_fragment(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"the namespace names the format wherever it appears, got {findings}"
    )


def test_a_bare_name_block_is_a_finding() -> None:
    """Three elements and a complete person.

    The count was calibrated on how many elements a full export contains, which
    is a fair basis for measuring density and the wrong basis for deciding
    which elements carry a person. Five structural tags are nobody in
    particular; a name and a surname are somebody.
    """
    findings = scan_text(gramps_name_block(), source="notes.md")

    assert rules(findings) == ["P2"], f"a given name and a surname is a person, got {findings}"


def test_a_note_carrying_a_biography_is_a_finding() -> None:
    """Two elements holding a whole life.

    A prose container is the one element that can carry anything, so counting
    it the same as a structural tag is the defect rather than the threshold.
    """
    findings = scan_text(gramps_note_biography(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"birth, marriage, trade and death in free text, got {findings}"
    )


def test_an_importer_spec_is_not_a_finding() -> None:
    """The document this repository is about to start writing.

    Element names in backticks, a mapping table, the namespace in prose. Every
    mention is unfilled, and that is the distinction the property turns on: a
    document *about* a format mentions its elements, a document *containing*
    one has them filled. Without that distinction this scores 18.
    """
    findings = scan_text(gramps_importer_spec(), source="docs/importing.md")

    assert findings == [], f"a specification is not an export, got {findings}"


def test_short_labels_in_a_diagram_are_not_a_biography() -> None:
    """A prose container is worth four when it holds prose, and nothing otherwise.

    Found by a surviving mutant and then by measuring one sample larger: two
    axis labels score two, four score four, and four is the threshold. A prose
    weight with no floor under it turns any diagram with labels into a family
    tree.
    """
    findings = scan_text(labelled_diagram(), source="docs/chart.md")

    assert findings == [], f"axis labels are not a life story, got {findings}"


def test_records_that_only_reference_each_other_are_a_finding() -> None:
    """An export is not only filled elements; it is also the links between them.

    A handle or an hlink is export syntax -- nothing writes one in prose -- so
    an element carrying a quoted attribute counts even with no content of its
    own. Nothing asserted that until a mutant removed it and nothing failed.
    """
    findings = scan_text(gramps_reference_fragment(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"the shape of an export is data about who is in it, got {findings}"
    )


def test_naming_the_format_is_not_carrying_it() -> None:
    """The namespace corroborates a count; on its own it is a word.

    Making it a verdict looked free -- the tip stayed clean, because the
    constant is composed from parts -- and it fired 43 times across the
    published range, on this guard's own source and every historical copy of
    it. A guard that detects a string contains that string.
    """
    prose = (
        "# Import notes\n\nExports identify themselves with the namespace "
        + gramps_namespace_url()
        + ",\nwhich is how the importer will recognise one. No tree is stored here.\n"
    )

    findings = scan_text(prose, source="notes.md")

    assert findings == [], f"a document about the format is not a document in it, got {findings}"


def test_the_density_property_does_not_report_this_repository() -> None:
    """The cost of the property, measured on the artefact it has to live with.

    One tracked file matched when this was measured, and its matching lines
    were literal GEDCOM records inside the fixture module -- which its own
    documented rule says to assemble at runtime rather than write as literals.
    Correcting a fixture that breaks its own rule is not weakening the guard.
    """
    repository_root = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    reported = []
    for name in tracked:
        try:
            content = (repository_root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if scan_text(content, source=name):
            reported.append(name)

    assert reported == [], f"the guard reports its own repository: {reported}"


def test_a_single_indented_header_is_still_a_finding() -> None:
    """What the prefix tolerance is still for, once counting took over.

    Found by a surviving mutant: re-pinning the signatures to column zero
    stopped failing anything, because every document the other tests use has
    enough records for the count to catch it anyway. A file with one or two
    records has not, and the single-line signatures are the only thing standing
    there -- so the tolerance does real work and nothing was asserting it.
    """
    lone_header = "# Notes\n\n    " + _level(0, "HEAD") + "\n"

    findings = scan_text(lone_header, source="notes.md")

    assert rules(findings) == ["P2"], (
        f"one record is below the count, and indenting it must not hide it, got {findings}"
    )


def test_every_genealogy_signature_anchors_the_same_way() -> None:
    """The defect underneath both: one tuple, two anchorings.

    Two signatures were pinned to column zero while the third tolerated
    leading whitespace, so which spelling of the same paste got caught
    depended on which format it was in.
    """
    prefixes = ("", "    ", "> ", "\t")
    documents = {"GEDCOM": gedcom_document(), "Gramps XML": gramps_xml_document()}

    missed = [
        f"{name} with prefix {prefix!r}"
        for name, document in documents.items()
        for prefix in prefixes
        if not scan_text(
            "".join(f"{prefix}{line}\n" for line in document.splitlines()), source="notes.md"
        )
    ]

    assert missed == [], f"these spellings of committed genealogy data are not caught: {missed}"


def test_gedcom_finding_reports_source_and_line() -> None:
    text = "Some harmless preamble.\n" + gedcom_document()

    findings = scan_text(text, source="notes.txt")

    assert findings, "expected a P2 finding"
    assert findings[0].source == "notes.txt"
    assert findings[0].line == 2, f"expected line 2, got line {findings[0].line}"


def test_gedcom_renamed_as_text_is_still_caught(tmp_path: Path) -> None:
    disguised = tmp_path / "notes.txt"
    disguised.write_text(gedcom_document(), encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"a GEDCOM renamed .txt must still be a P2 finding, got {findings}"
    )
    assert findings[0].source == "notes.txt"


def test_sqlite_database_is_caught_by_file_magic(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_bytes(sqlite_bytes())

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], f"expected a P2 finding, got {findings}"


def test_unclassifiable_content_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "mystery.bin").write_bytes(unclassifiable_bytes())

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"content the guard cannot classify must be a P2 finding, got {findings}"
    )


def test_genealogy_extension_alone_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "family.ged").write_text("nothing suspicious in here\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"a genealogy extension is sufficient on its own, got {findings}"
    )


def test_ordinary_text_is_not_a_finding(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text(
        "# Title\n\n0 HEADQUARTERS moved in 1991.\nA level 0 outline follows.\n",
        encoding="utf-8",
    )
    (tmp_path / "module.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    assert scan_paths([tmp_path]) == [], "ordinary text must not be a P2 finding"


def test_empty_file_is_not_a_finding(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_bytes(b"")

    assert scan_paths([tmp_path]) == [], "an empty file must not be a P2 finding"


# ---------------------------------------------------------------------------
# Root cause B -- UTF-8 decodability is not proof of safety.
#
# The guard classifies content as *known-safe* and treats everything else as a
# finding. Growing the list of known-bad signatures is the losing side of this
# race; there will always be one more genealogy format.
# ---------------------------------------------------------------------------


def test_alternate_encoded_genealogy_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_bytes(utf16le_gedcom_bytes())

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"UTF-16LE decodes as UTF-8 but is not text; it must not pass, got {findings}"
    )


def test_binary_masquerading_as_decodable_text_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_bytes(b"\x00\x01\x02")

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"control bytes decode cleanly as UTF-8 and are not text, got {findings}"
    )


def test_an_unrecognised_genealogy_format_is_a_finding_under_a_safe_type() -> None:
    """The guarantee, tested where it was actually false.

    This payload has been in the suite since round 1 as a text file, and a text
    file is not a safe type -- so the type gate refused it and content
    detection was never exercised. The same bytes in a Markdown, Python or YAML
    file came back clean, which are the three commonest types here.
    """
    document = gedcom_x_json().encode()

    missed = [name for name in ("tree.md", "tree.py", "tree.yml") if not scan_blob(document, name)]

    assert missed == [], f"a genealogy format is one whatever the file is called; missed {missed}"


def test_a_name_expressed_as_parts_is_a_finding() -> None:
    """GEDCOM X carries a name as parts, and the parts were not recognised.

    Each part is an object with a type URI and a value, so the identity keys
    the property already scores never appear. Two parts are a given name and a
    surname -- the same person the Gramps side is caught by at the same score.
    """
    findings = scan_blob(gedcom_x_name_parts().encode(), "tree.md")

    assert rules(findings) == ["P2"], f"a name in parts is still a name, got {findings}"


def test_a_name_in_parts_is_a_finding_when_the_parts_carry_qualifiers() -> None:
    """The pairing was right; the way it stayed inside one object was not.

    A name part is an object carrying a type beside a value, and the matcher
    kept itself inside one object by refusing to cross a brace. A qualifier --
    ordinary GEDCOM X, saying which part is primary -- nests an object inside
    the part, so the part stopped being a part the moment it acquired one.
    Given name and surname both escaped, on a valid document, leaving three
    structural keys and a score below the bar.

    This is NOT the recorded single-name-part ceiling: there are two parts
    here, which is the case that has always scored four.
    """
    findings = scan_text(gedcom_x_name_parts_with_qualifiers(), source="tree.md")

    assert rules(findings) == ["P2"], (
        f"a name part does not stop being one when it is qualified, got {findings}"
    )


def test_nesting_cannot_smuggle_a_pairing_that_is_not_in_one_object() -> None:
    """The other direction, and the reason the pairing must survive the fix.

    Eliding a nested object must not merge it into its parent: a type in a
    child and a value in the parent are not a name part, and a fix that
    flattened the document would report every schema with a nested type.
    """
    split = '{"val' + 'ue":"on","child":{"ty' + 'pe":"string"}}'

    assert scan_text(split, source="settings.md") == [], (
        "a type in a child object is not paired with a value in its parent"
    )


def test_a_populated_address_is_a_finding() -> None:
    """Where somebody lives, which the element weighting simply did not list.

    Not a threshold problem and not a partial application of the score: the
    address children were absent from the vocabulary altogether, so a complete
    address block scored zero.
    """
    findings = scan_text(gramps_address_block(), source="notes.md")

    assert rules(findings) == ["P2"], f"an address locates a person, got {findings}"


def test_the_address_payload_issue_four_was_filed_with_is_a_finding() -> None:
    """⚠️ **GREEN ON ARRIVAL, and that is the result rather than a failure of TDD.**

    Issue #4 item 1 reported this exact payload scoring **1** -- only the dated
    element was recognised, so street, city, postal and phone, which are pure
    identity, scored nothing and a complete personal address passed. The audit
    that item belongs to re-measures every item before fixing any of them,
    because the issue predates several fix rounds and a fix applied twice is
    its own defect.

    Re-measured on this head: **9** against a threshold of 4 -- eight from the
    four filled address children and one from the attributed dated element.
    The address row reached the vocabulary in the round that ended the
    per-format split, which closed this item without naming it.

    So this test is not the red that demanded code. It is the measurement that
    says no code is owed, committed because an unasserted claim that something
    is already fixed is exactly how a closed item comes back.
    """
    findings = scan_text(gramps_issue_address_payload(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"the payload this item was filed with is still not caught, got {findings}"
    )


def test_json_prose_is_weighed_as_prose_and_not_as_an_address() -> None:
    """The compiled table disagreeing with itself.

    Compilation collapsed prose, address and contact into one pattern and
    charged them all the address weight, so a whole life in one note scored
    three where the table says five -- and passed, in a safe-typed file, while
    the identical prose as XML was caught. That is the per-format divergence
    the shared table was built to end, reappearing inside the thing that ended
    it.
    """
    findings = scan_text(gedcom_x_note_only(), source="tree.md")

    assert rules(findings) == ["P2"], f"a life in a note is a life, got {findings}"


def test_a_short_json_note_is_not_a_biography() -> None:
    """The half of the F5 fix that stops it manufacturing a false positive.

    Raising the weight to four without carrying the RULES across reports a
    two-character caption under a note key as a family tree. The floor is not
    a property of the XML spelling; it is a property of prose, and it was
    stated in only one of the two formats -- the same partial application one
    level down from the weight.

    There is no positioned-label branch here, and there cannot be: a JSON key
    carries no attributes. The floor is the whole discriminator on this side.
    """
    assert scan_text(gedcom_x_short_note(), source="tree.md") == [], (
        "a caption in a note key is a caption"
    )


_WEIGHTS_BEFORE_THE_DERIVATION = {
    "surname": 2,
    "name": 2,
    "first": 2,
    "ptitle": 2,
    "pname": 2,
    "street": 2,
    "city": 2,
    "county": 2,
    "state": 2,
    "postal": 2,
    "country": 2,
    "phone": 2,
    "url": 2,
    "email": 2,
    "text": 4,
    "note": 4,
    "person": 1,
    "family": 1,
    "gender": 1,
    "birth": 1,
    "death": 1,
    "dateval": 1,
    "placeobj": 1,
    "address": 1,
    "citation": 1,
    "eventref": 1,
    "childref": 1,
    "noteref": 1,
    "attribute": 1,
}
"""Every Gramps spelling the vocabulary held, and its weight, before #4's audit.

⚠️ **This is not a duplicate of the vocabulary; it is a FROZEN SNAPSHOT of a
different moment, and the difference is the point.** The audit that derives the
container list from the published schema has one invariant standing over it:
*no row already in the vocabulary is gated or zero-weighted by this work.* That
is a claim about the past, so it needs a record of the past to be checked
against -- otherwise "nothing was retracted" is only ever a promise in a commit
message, and the quiet way to make a widening's measurement look good is to
zero an existing catch.

Three spellings here are **not** in the published schema at all -- ``birth``,
``death`` and ``email``. They stay exactly as they are for the same reason: the
derivation adds rows, and a row it cannot account for is not thereby wrong.
"""


def test_no_spelling_the_vocabulary_already_had_changes_what_it_scores() -> None:
    """⭐ **Invariant 1 of the derivation, asserted rather than promised.**

    The audit widens the vocabulary from what reviewers happened to name to
    what the published schema declares, and the affordability problem it runs
    into -- schema spellings that are also ordinary markup element names -- is
    answered by a deliberately-unweighted category. That answer is safe only
    while the zero is a condition on rows the audit ADDS. Applied to a row the
    guard already catches, the very same mechanism is a retraction: ``<text>``
    is an SVG element name too, and zeroing it would drop the note-carrying-a-
    biography catch entirely while every number in the measurement improved.

    So the snapshot is the control. Scored through the compiled scorer rather
    than read out of the table, because the claim is about what the guard
    DOES.
    """
    retracted = []

    for spelling, expected in sorted(_WEIGHTS_BEFORE_THE_DERIVATION.items()):
        observed = _observed_weight(_gramps_identity_score, _gramps_probe, spelling)
        if observed != expected:
            retracted.append(f"<{spelling}>: was {expected}, now {observed}")

    assert retracted == [], (
        "this audit adds rows and retracts none, and these spellings scored less than they did "
        f"before it: {retracted}"
    )


def test_no_spelling_is_claimed_by_two_categories() -> None:
    """A spelling in two rows takes the LAST one silently, and nothing says so.

    Written because it happened while the schema's rows were being placed:
    ``header`` was put in the structural row and again in the unweighted one,
    and the category lookup -- a comprehension over the table in order -- simply
    took the second. The per-row test caught it, but only because the two
    weights differ. **Two rows of the same weight would disagree about what an
    element MEANS and no test would see it**, and meaning is what this table
    exists to record.
    """
    seen: dict[str, str] = {}
    doubled = []

    for category, shared, xml_only, _ in _VOCABULARY:
        for spelling in shared + xml_only:
            if spelling in seen:
                doubled.append(f"<{spelling}>: {seen[spelling]} and {category}")
            seen[spelling] = category

    assert doubled == [], (
        f"these spellings are claimed by two categories, and the later one wins silently: {doubled}"
    )


def test_every_container_the_published_schema_declares_has_a_weight() -> None:
    """⭐ **The exit condition of issue #4, mechanically.**

    The issue was filed with five items, grew to six, and its original exit
    condition -- *every place in either format where a container can hold prose
    or an identity field* -- is universally quantified over a format with no
    way to say when it has been satisfied. It was re-specified: the container
    list is DERIVED from the published specification and frozen as a committed
    table, and the audit closes when every row of that table has a weight and a
    test.

    This is that sentence as an assertion. The frozen table is the checklist,
    the vocabulary is the weighting, and a row present in one and absent from
    the other is precisely the partial application the issue exists to end.
    ``test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row``
    supplies the other half -- that the weight the table declares is the weight
    the compiled scorer charges -- so between them ~100 rows are covered
    without ~100 hand-written tests, and a row added to the schema by a later
    version extends both without either being edited.
    """
    unweighted = [
        f"<{spelling}> ({model})"
        for spelling, model in SPECIFIED_ELEMENTS
        if spelling not in _GRAMPS_CATEGORY_OF
    ]

    assert unweighted == [], (
        f"{len(unweighted)} containers the published schema declares carry no weight, so the "
        f"vocabulary is still what reviewers happened to name: {unweighted}"
    )


def test_a_spelling_the_published_markup_indexes_also_use_earns_no_weight() -> None:
    """⭐ **What makes the widening affordable, and it is the whole risk.**

    The schema declares ``title``, ``style``, ``code``, ``map``, ``object``,
    ``source`` and ``header``. **Those are HTML and SVG element names**, and
    this repository is full of markup. Weighted at even the smallest weight,
    four filled ones reach the threshold and an ordinary markup snippet is
    reported -- so the rows that close the audit are also the rows that could
    make the guard something contributors route around.

    The answer is a deliberately-unweighted category, and it is accepted on
    exactly the ground ``FILESYSTEM_ROOTS`` and the drawing exemption are:
    the collision is read off two published element indexes, which are closed
    and externally specified rather than a list somebody maintains.

    **The rejected alternative is recorded so it is not re-proposed:** a
    document-level structural gate -- score these spellings only once the file
    has proved it is Gramps. It is the more precise answer and it is a second
    document-level condition on the XML scorer, and the failure mode of the one
    taken is stated instead: a real export earns nothing from its ``<title>``
    elements, which costs nothing, because such an export is caught many times
    over by spellings that collide with nothing.

    ⚠️ **The two exceptions are not exceptions to the rule; they are Invariant
    1.** ``text`` and ``address`` were weighted before this audit, and the
    twin test above is what keeps them that way.
    """
    earning = []

    for spelling, _ in SPECIFIED_ELEMENTS:
        if spelling not in MARKUP_ELEMENT_NAMES:
            continue
        if spelling in _WEIGHTS_BEFORE_THE_DERIVATION:
            continue
        observed = _observed_weight(_gramps_identity_score, _gramps_probe, spelling)
        if observed != 0:
            earning.append(f"<{spelling}>: {observed}")

    assert earning == [], (
        "these spellings are ordinary markup element names, so a document using them is not "
        f"evidence of anything, and they score: {earning}"
    )


def test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row() -> None:
    """⭐ **Every row of the table, both formats, against the weight it declares.**

    The other tests here check the rows somebody thought to check. This one
    checks the rows, full stop -- so a category cannot be lost in compilation
    and go unnoticed because the weight it was wrongly given happened to be
    right. That is not hypothetical: prose was charged the address weight, and
    CONTACT was charged it in the same expression and scores correctly *by
    coincidence*, because contact and address both weigh two. Change either
    number and a second silent defect appears with no test to see it.

    Measured by DIFFERENCE, four copies against five, so the constant a probe
    needs to clear the threshold cancels and what remains is the weight of
    exactly one filled key or element. A spelling that scores nothing fails
    the threshold instead and is reported by name.
    """
    disagreements = []

    for category, shared, xml_only, json_only in _VOCABULARY:
        expected = _CATEGORY_WEIGHT[category]
        for spelling in shared + xml_only:
            observed = _observed_weight(_gramps_identity_score, _gramps_probe, spelling)
            if observed != expected:
                disagreements.append(f"Gramps <{spelling}> is {category}: {observed} != {expected}")
        for spelling in shared + json_only:
            observed = _observed_weight(_gedcom_x_identity_score, _gedcom_x_probe, spelling)
            if observed != expected:
                disagreements.append(
                    f"GEDCOM X {spelling!r} is {category}: {observed} != {expected}"
                )

    assert disagreements == [], (
        "the compiled scorers disagree with the vocabulary table they are compiled from: "
        f"{disagreements}"
    )


def test_a_namespace_prefix_does_not_change_what_a_filled_row_scores() -> None:
    """⭐ **Every row of the table, prefixed against unprefixed.**

    A namespace prefix is a document's private alias for a namespace, so a
    prefixed export is the same export and has to score the same. It did not:
    with a prefix declared the compiled matcher saw NO element at all, in any
    category -- including the four already weighted correctly -- because the
    alternation held bare spellings and a qualified tag does not begin with one.
    The gap is LEXICAL rather than semantic, which is why it takes every
    category with it at once.

    Derived from the table rather than exampled, in the same shape as the test
    above, so adding a row extends this property without this test being
    edited. Asserted as AGREEMENT between the two spellings rather than against
    the weight table, because the claim is that the prefix does not matter --
    which stays true, and stays checked, when a weight changes.

    Every row is crossed with every ALIAS in ``_NAMESPACE_PREFIXES`` for the
    same reason: an alias legal under ``NCName`` but outside ``\\w`` -- a
    combining mark -- was missed here at every row at once, and adding it as a
    one-off example would have asserted the example rather than the property.
    """
    disagreements = []

    for _, shared, xml_only, _ in _VOCABULARY:
        for spelling in shared + xml_only:
            bare = _observed_weight(_gramps_identity_score, _gramps_probe, spelling)
            for prefix in _NAMESPACE_PREFIXES:
                prefixed = _observed_weight(
                    _gramps_identity_score, _gramps_probe, _prefixed(spelling, prefix)
                )
                if bare != prefixed:
                    disagreements.append(
                        f"<{ascii(prefix)}:{spelling}>: {bare} bare, {prefixed} prefixed"
                    )

    assert disagreements == [], (
        "a namespace prefix changes what these rows score, so one export in two spellings "
        f"gets two verdicts: {disagreements}"
    )


def test_a_namespace_prefix_does_not_change_what_an_attributed_row_scores() -> None:
    """The same property over the OTHER pass the alternation feeds.

    Two loops read one alternation, and teaching the prefix to the pattern only
    one of them uses is precisely the partial application this vocabulary exists
    to make impossible. An export is not only its filled elements; it is also
    the links between them, and under a prefix those scored nothing either.
    """
    disagreements = []

    for _, shared, xml_only, _ in _VOCABULARY:
        for spelling in shared + xml_only:
            bare = _observed_weight(_gramps_identity_score, _gramps_attributed_probe, spelling)
            for prefix in _NAMESPACE_PREFIXES:
                prefixed = _observed_weight(
                    _gramps_identity_score, _gramps_attributed_probe, _prefixed(spelling, prefix)
                )
                if bare != prefixed:
                    disagreements.append(
                        f"<{ascii(prefix)}:{spelling} val=...>: {bare} bare, {prefixed} prefixed"
                    )

    assert disagreements == [], (
        f"a namespace prefix changes what these rows score in the attributed pass: {disagreements}"
    )


def test_a_prefixed_database_element_names_the_format_the_same_way() -> None:
    """The third site: the signature by which a Gramps export is recognised at all.

    A document declaring the namespace on a prefixed database element was not
    recognised as the format, and the namespace fallback does not stand in for
    it -- two points is below the threshold, so the document was clean.

    Asserted as agreement between the two spellings, with the unprefixed control
    checked first so that "neither of them is caught" cannot satisfy it, and over
    every alias for the reason the two derived tests above are.
    """
    bare = scan_text(gramps_xml_database_element(), source="notes.md")
    assert rules(bare) == ["P2"], f"the control is not caught, so this proves nothing: {bare}"

    disagreements = []
    for prefix in _NAMESPACE_PREFIXES:
        prefixed = scan_text(gramps_xml_database_element(prefix=prefix), source="notes.md")
        if [finding.message for finding in prefixed] != [finding.message for finding in bare]:
            disagreements.append(f"{ascii(prefix)}: {[finding.message for finding in prefixed]}")

    assert disagreements == [], (
        "a prefixed export is the same export, and the finding must name the signature that "
        f"caught it: bare says {[finding.message for finding in bare]}, these aliases say "
        f"{disagreements}"
    )


def test_a_prefixed_document_still_declares_the_namespace_it_belongs_to() -> None:
    """The site that needed no change, checked rather than assumed.

    A prefix moves the declaration from ``xmlns`` to ``xmlns:g``; the URI it
    binds is untouched, and the URI is what the fallback reads. Green on
    arrival, deliberately: "no change needed here" is a claim like any other,
    and an unasserted claim in a commit message is how the drawing exemption --
    since deleted as a site, for reading a prefix it could not resolve -- came
    to be found in planning rather than in the code.
    """
    missing = [
        ascii(prefix)
        for prefix in _NAMESPACE_PREFIXES
        if _GRAMPS_XML_NAMESPACE not in gramps_xml_database_element(prefix=prefix)
    ]

    assert missing == [], (
        f"the namespace fallback reads a URI, and a prefixed document still declares it: {missing}"
    )


def test_every_pattern_that_scores_an_element_is_built_from_the_one_alternation() -> None:
    """⭐ **One construction site, and EXACTLY which patterns use it.**

    Three compiled patterns score a Gramps element, and under a namespace
    prefix all three failed by letting data out. A fourth site hand-rolling its
    own alternation fails the same way, and nothing behavioural sees it until
    somebody writes the document, so the site set is what gets asserted.

    ⚠️ **The exclusion is asserted too, and it is not symmetry.** ``_DRAWING``
    was built from this alternation and the fourth site was deleted: matching
    more elements means more FINDINGS when scoring and more SUPPRESSION when
    exempting, so the same mechanism that is conservative in the three patterns
    above is fail-open in an exemption. Wiring it back in is the obvious way to
    "finish the job", it looks like consistency, and it re-opens a P1 -- so it
    fails here rather than being caught by a comment.
    """
    signature = dict(_GENEALOGY_TEXT_SIGNATURES)["Gramps XML database element"]
    sites = {
        "_GRAMPS_FILLED_ELEMENT": (_GRAMPS_FILLED_ELEMENT.pattern, _GRAMPS_ALL_ELEMENTS),
        "_GRAMPS_ATTRIBUTED_ELEMENT": (_GRAMPS_ATTRIBUTED_ELEMENT.pattern, _GRAMPS_ALL_ELEMENTS),
        "Gramps XML database element": (signature.pattern, ("database",)),
    }

    hand_rolled = [
        name for name, (pattern, names) in sites.items() if _qualified(*names) not in pattern
    ]

    assert hand_rolled == [], (
        "these patterns do not read the shared alternation, so a namespace prefix means "
        f"something different to each of them: {hand_rolled}"
    )
    assert _qualified("svg") not in _DRAWING.pattern, (
        "the drawing exemption reads the shared alternation again, so a container whose "
        "alias this module never resolves suppresses every short element inside it"
    )


def test_the_alternation_never_lets_a_shorter_spelling_shadow_a_longer_one() -> None:
    """Longest first, asserted structurally because nothing behavioural can see it.

    No two spellings in the table collide today, so a shorter alternative
    shadowing a longer one is a defect no document can currently exhibit -- and
    the table is about to be derived from a published schema, which is where
    collisions come from. The trailing word boundary makes the engine backtrack
    into the longer alternative anyway; the point is that the patterns must not
    DEPEND on that.
    """
    lengths = [len(name) for name in _alternatives_of(_qualified(*_GRAMPS_ALL_ELEMENTS))]

    assert lengths == sorted(lengths, reverse=True), (
        f"the alternation is not ordered longest-first: {lengths}"
    )
    assert _alternatives_of(_qualified("name", "namemaps"))[0] == "namemaps", (
        "a spelling that begins with another must be offered before it, or reaching it "
        "depends on the engine backtracking"
    )


def test_the_prefix_class_is_the_ncname_production_it_transcribes() -> None:
    """⭐ **Every boundary of both tables, inside and just outside, both positions.**

    The class used to be built from ``\\w``, which is a Python word class and
    not an XML production. It missed combining marks -- legal ``NameChar``s --
    so a document using a legal alias was invisible at every site that reads an
    element name at once.
    The repair is to transcribe the production, and a transcription is checked
    the only way one can be without an unbounded sweep: at the edges.

    Both directions, because a transcription can be wrong either way. A missing
    boundary fails OPEN, the way ``\\w`` did. A boundary that reaches one code
    point too far is how a raw ``-`` or ``^`` inside a character class turns a
    range into something else -- which is exactly what the escaping in
    ``_character_class`` exists to prevent, and this is what would see it.

    The just-outside probes carry the colon check for free: ``0x39`` is the end
    of the digits, so ``0x3A`` is probed, and ``0x3A`` is ``:``.
    """
    wrong = []
    positions = (
        ("as the first character", _NCNAME_START_RANGES, ""),
        ("after the first character", _NCNAME_CONTINUE_RANGES, "a"),
    )

    for where, ranges, lead in positions:
        for first, last in ranges:
            for code_point in (first, last):
                if not _admits_as_prefix(lead + chr(code_point)):
                    wrong.append(f"U+{code_point:04X} is in the table and rejected {where}")
            for code_point in (first - 1, last + 1):
                outside_unicode = code_point < 0 or code_point > 0x10FFFF
                surrogate = 0xD800 <= code_point <= 0xDFFF
                if outside_unicode or surrogate or _in_any_range(code_point, ranges):
                    continue
                if _admits_as_prefix(lead + chr(code_point)):
                    wrong.append(f"U+{code_point:04X} is outside the table and accepted {where}")

    assert wrong == [], (
        "the compiled prefix class is not the NCName production the tables transcribe, so a "
        f"legal alias is missed or an illegal one is read as markup: {wrong}"
    )


def test_a_namespace_prefix_may_not_begin_with_a_character_that_may_only_continue_one() -> None:
    """The two tables are not one table, and collapsing them is a fail-open.

    ``NCNameStartChar`` and ``NCNameChar`` differ by exactly the characters a
    name may carry but not open with: a combining mark, a digit, ``-`` and
    ``.``. Building one class and using it in both positions would pass every
    assertion in the test above -- both tables would still be transcribed -- and
    would read ``<-9:name>`` as an element. So the DIFFERENCE is asserted, not
    just the membership.
    """
    wrong = []

    for first, last in _NCNAME_CONTINUE_RANGES:
        if _in_any_range(first, _NCNAME_START_RANGES):
            continue
        for code_point in (first, last):
            if _admits_as_prefix(chr(code_point)):
                wrong.append(f"U+{code_point:04X} may not BEGIN a prefix and is accepted there")
            if not _admits_as_prefix("a" + chr(code_point)):
                wrong.append(f"U+{code_point:04X} may continue a prefix and is rejected there")

    assert wrong == [], (
        "the start class and the continue class are not distinguished as the production "
        f"distinguishes them: {wrong}"
    )


def test_the_prefix_class_cannot_match_markup() -> None:
    """The bound the constant's own note states, asserted rather than restated.

    A prefix class is read at every ``<`` in the document, so what it CANNOT
    match is the thing keeping an optional prelude from swallowing markup. The
    note beside ``_XML_NAME_PREFIX`` has always claimed this bound; widening the
    class from a word class to a specification's ranges is the change that could
    quietly cost it, so it stops being a claim here.
    """
    admitted = [
        ascii(candidate)
        for character in ":<>/=\"' \t\r\n"
        for candidate in (character, "a" + character)
        if _admits_as_prefix(candidate)
    ]

    assert admitted == [], (
        f"the prefix class matches markup, so the prelude can swallow a tag: {admitted}"
    )


def test_a_prefixed_drawing_is_not_a_drawing() -> None:
    """The site that was withdrawn, asserted rather than left to the comment.

    ``_DRAWING`` reads the UNPREFIXED spelling and nothing else. A prefix is
    matched by SHAPE everywhere in this module, never resolved, and that is
    conservative for the three scorers -- matching more elements means more
    findings -- and fail-open here, because matching more containers means more
    SUPPRESSION. The exemption is withdrawn from a container it cannot prove is
    a drawing rather than granted on an unresolved alias.
    """
    matched = [
        ascii(prefix)
        for prefix in _DRAWING_PREFIXES
        if _DRAWING.search(worded_diagram(prefix=prefix)) is not None
    ]

    assert matched == [], (
        "a drawing is a drawing by its unprefixed spelling; an alias this module never "
        f"resolves does not buy an exemption: {matched}"
    )


def test_labels_in_a_prefixed_drawing_are_reported() -> None:
    """The behavioural half, and the wanted direction is DISAGREEMENT.

    The bare chart is exempt and the prefixed one is reported: the same chart,
    reported because its container cannot be proved to be a drawing. That is a
    false positive and it is the direction this module's posture requires --
    refuse what cannot be proved safe. The cost is recorded in CONTRIBUTING's
    residual table, with issue #33's rendering boundary named as where a real
    "is this a drawing" answer belongs.

    The bare arm is asserted here rather than assumed: it is the exemption that
    actually earns its keep, and it is the thing a careless revert breaks.
    """
    bare = rules(scan_text(worded_diagram(), source="docs/chart.md"))
    reported = {
        ascii(prefix): rules(scan_text(worded_diagram(prefix=prefix), source="docs/chart.md"))
        for prefix in _DRAWING_PREFIXES
    }

    assert bare == [] and all(found == ["P2"] for found in reported.values()), (
        "an unresolved alias does not buy an exemption, and an ordinary drawing keeps one: "
        f"bare says {bare}, prefixed says {reported}"
    )


def test_a_container_whose_prefix_is_bound_elsewhere_is_not_a_drawing() -> None:
    """⭐ **The reproduction the fourth site was deleted for.**

    A prefix bound to a namespace that is not SVG still had the SHAPE of a
    drawing, so the container matched, the exemption applied, and every short
    text element inside it was suppressed. A whole identity -- a name, a date of
    birth and a place -- went from a finding to nothing by being wrapped in a
    tag whose alias this module never resolves. Prefix-shape matching is
    conservative for the three scorers and fail-open for an exemption, and this
    is what fail-open looked like.

    **Three assertions, and the two on the ends are what keep the middle one
    honest.** Without the unwrapped premise a scoring change makes this vacuous
    -- the notes would stop being a finding and the test would still pass.
    Without the unprefixed control, a revert that went further than the fourth
    site would break the exemption that actually earns its keep and nothing
    here would say so. Same payload in all three, so the container is the only
    variable.
    """
    unwrapped = rules(scan_text(gramps_short_notes(), source="notes.md"))
    exempt = rules(scan_text(notes_inside_a_container(), source="notes.md"))
    reported = {
        ascii(prefix): rules(
            scan_text(
                notes_inside_a_container(prefix=prefix, namespace=_NOT_THE_SVG_NAMESPACE),
                source="notes.md",
            )
        )
        for prefix in _DRAWING_PREFIXES
    }

    assert unwrapped == ["P2"], (
        f"the premise: three short notes are a whole identity on their own, got {unwrapped}"
    )
    assert exempt == [], f"an ordinary drawing still exempts its labels, and must: got {exempt}"
    assert all(found == ["P2"] for found in reported.values()), (
        "an alias bound to something that is not SVG is a drawing by shape alone, and an "
        f"exemption may not rest on a shape this module never resolves: {reported}"
    )


def test_one_life_is_judged_the_same_in_both_formats() -> None:
    """The root defect: a vocabulary living in two places lets one of them lag.

    The commit that added GEDCOM X name-parts and Gramps addresses together
    carried neither across, so the identical biography and address is caught as
    XML and passes as JSON. Asserted as agreement rather than as two verdicts,
    because agreement is the property.
    """
    as_json = rules(scan_text(gedcom_x_biography_and_address(), source="tree.md"))
    as_xml = rules(scan_text(gramps_biography_and_address(), source="tree.md"))

    assert as_json == as_xml == ["P2"], (
        f"one life, two spellings, two verdicts: JSON says {as_json}, XML says {as_xml}"
    )


def test_an_address_alone_is_a_finding_in_the_json_format_too() -> None:
    """The shared table proved, from the side that used to lag.

    Emptying the address row must fail tests in BOTH formats. The XML case has
    had one since the row was added; without this one the row could be emptied
    on the JSON side and only half the suite would notice -- which is exactly
    how the vocabulary came to differ between formats in the first place.
    """
    address_only = (
        '{"pers' + 'ons":[{"addres' + 'ses":[{"str' + 'eet":"14 Milllane",'
        '"ci' + 'ty":"Thornwick"}]}]}'
    )

    findings = scan_text(address_only, source="tree.md")

    assert rules(findings) == ["P2"], f"where somebody lives, in either spelling, got {findings}"


def test_cdata_delimiters_are_not_content() -> None:
    """The wrapper must not inflate a short note into prose.

    Unwrapping matters in both directions: it stops a wrapped biography reading
    as markup, and it stops the twenty-odd characters of delimiter turning a
    short note into a life story. Without it this scores prose weight and is
    reported, which is the false-positive half of the same fix.
    """
    short = "<note><text><![" + "CDATA[Elowen Ashen]" + "]></text></note>"

    assert scan_text(short, source="notes.md") == [], (
        "a dozen characters of name wrapped in a dozen of syntax is still a dozen of name"
    )


def test_identity_carried_in_an_attribute_is_weighed_as_identity() -> None:
    """The principle ran on one of the two passes.

    The attributed pass never looked at the tag, so an attributed surname
    scored the structural weight rather than the identity weight -- one, not
    zero. A place name element is in no list at all and scored zero even
    carrying a full place.
    """
    findings = scan_text(gramps_attributed_identity(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"a surname is a surname whether it is content or an attribute, got {findings}"
    )


def test_a_biography_in_cdata_is_still_a_biography() -> None:
    """CDATA is ordinary XML for prose containing markup or an ampersand.

    Which is what a biography contains. The content pattern read the opening
    delimiter as markup, so wrapping the same prose dropped it below the bar.
    """
    findings = scan_text(gramps_biography_in_cdata(), source="notes.md")

    assert rules(findings) == ["P2"], f"a wrapper is not a disguise, got {findings}"


def test_markup_inside_a_prose_element_does_not_end_the_element() -> None:
    """Every kind of markup XML lets sit between an element's tags.

    A filled prose element carrying a whole identity scored NOTHING once an
    XML comment sat inside it: the content alternation admitted a CDATA
    section and refused anything else beginning with an angle bracket, so the
    pattern could not reach its own closing tag. CDATA had been taught as a
    special case; the other members of the same production had not, which is
    this module's recurring defect rather than a new one.

    Asserted as AGREEMENT with the uninterrupted spelling, over the whole
    table. "The commented one is caught" is satisfied by a special case for
    comments -- the same shape as the defect.
    """
    control = _gramps_identity_score(gramps_note_interrupted_by())
    assert control is not None, "the premise: uninterrupted, this element carries a life"

    disagreed = [
        f"{spelling}: {_gramps_identity_score(gramps_note_interrupted_by(markup))}"
        for spelling, markup in xml_markup_in_content("transcribed from the register").items()
        if _gramps_identity_score(gramps_note_interrupted_by(markup)) != control
    ]

    assert disagreed == [], (
        f"markup between two runs of character data changed the verdict: {disagreed}"
    )


def test_a_comment_holding_the_closing_tag_does_not_end_the_element() -> None:
    """A comment's text is not markup, and the element ends where XML ends it.

    The pattern reads the closing tag literally, so a comment quoting one used
    to be the end of the element -- or, before an interruption was admitted at
    all, the reason there was no element. Reading the comment as a node is what
    makes the real closing tag the real closing tag.
    """
    quoting = inside_a_comment("the closing " + "</te" + "xt>" + " goes here")
    findings = scan_text(gramps_note_interrupted_by(quoting), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"a closing tag inside a comment is text, not the end of the element, got {findings}"
    )


def test_a_comment_cannot_shorten_the_prose_it_sits_in() -> None:
    """The measurement errs long, and markup must not be a way around that.

    Measured over the RAW content, a reference written inside a comment would
    collapse where XML reads nothing, shortening the value and dropping the
    element below the floor. That is the one direction this measurement must
    not err in, and it is the pair of defects the last round fixed for CDATA.
    """
    references = inside_a_comment(" " + "&amp;" * 10 + " ")
    findings = scan_text(gramps_note_interrupted_by(references), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"a comment shortened the character data around it, got {findings}"
    )


def test_a_prose_element_holding_only_markup_is_worth_a_short_note() -> None:
    """The recorded decision, asserted in both directions.

    A comment contains no character data, so the measured quantity excludes it
    by definition. What that concedes is exactly what a bare short note
    concedes and nothing more: one scores identity weight and escapes, two
    reach the threshold and are caught. The ceiling is the one already recorded
    in the acceptance document, not a new one -- and asserting only the second
    half would pass on a rule that measured the comment's own text.
    """
    identity = "Elowen Ashenmoor, born 2 April 1893 in Thornwick"

    for spelling, markup in xml_markup_denoting_nothing(identity).items():
        one = scan_text(gramps_prose_holding_only(markup), source="notes.md")
        two = scan_text(gramps_prose_holding_only(markup, copies=2), source="notes.md")

        assert one == [], f"{spelling} alone is worth a short note, got {one}"
        assert rules(two) == ["P2"], f"two of {spelling} reach the threshold, got {two}"


def test_a_label_in_a_drawing_stays_a_label_when_it_carries_a_comment() -> None:
    """The false positive the same cause produced, in the other direction.

    With the element invisible to the filled pass, the attributed pass picked
    it up instead and charged it prose weight -- and that pass has no drawing
    exemption, so an ordinary chart label with a developer's comment beside it
    was reported. One cause, both directions, one fix.

    Markup denoting nothing only. A CDATA section beside the label would be
    thirty-odd characters of real text in it, and an element holding that much
    text is prose by the floor -- correctly, and at head as well as here.
    """
    for spelling, markup in xml_markup_denoting_nothing(
        "computed from the quarterly rollup"
    ).items():
        findings = scan_text(labelled_diagram_holding(markup), source="chart.md")

        assert findings == [], f"a label inside its drawing is a label, {spelling}: {findings}"


def test_three_short_notes_are_a_whole_identity() -> None:
    """A name, a date of birth and a place, each too short to clear the floor.

    The floor exists because chart labels reached the threshold, and it was
    calibrated only from that side. A bare text element is not a positioned
    label, and that is the discriminator -- see the measurement recorded beside
    the constant.
    """
    findings = scan_text(gramps_short_notes(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"three facts about one person are that person, got {findings}"
    )


def test_a_contact_address_is_identity() -> None:
    """A live e-mail identifies somebody at least as directly as a home path.

    The pairing is chosen so the CONTACT is what decides the verdict. Paired
    with the attributed-identity fixture this would pass either way -- that
    fixture is caught on its own, so the e-mail could score nothing and the
    assertion would never notice. A lone surname scores 2 and is clean; the
    e-mail is the second fact that takes it to the threshold, so emptying the
    contact category fails here rather than passing quietly.
    """
    surname = "<surna" + "me>Ashen</surna" + "me>"

    assert scan_text(surname, source="notes.md") == [], (
        "the premise of this test: one name-fact alone is below the bar"
    )

    findings = scan_text(gramps_contact_url() + surname, source="notes.md")

    assert rules(findings) == ["P2"], f"a way to reach a person names them, got {findings}"


def test_an_ordinary_attribute_does_not_turn_a_note_into_a_chart_label() -> None:
    """The exemption asked the wrong question, so any answer let data out.

    The discriminator is meant to separate a positioned drawing label from a
    note body, and it accepted ANY attribute as proof of the first. Adding
    ``xml:space``, which says how to treat whitespace and nothing about
    position, returned an exact name-date-place payload clean.

    Both obvious repairs are enumerations and both fail. Listing positioning
    attributes fails open on the next one nobody listed; listing
    non-positioning attributes is the same list pointed backwards and fails by
    admitting whatever is new. So the question changes instead: what makes a
    label a label is the DRAWING it sits in, which is a thing the document
    says outright.
    """
    findings = scan_text(gramps_short_notes_with_attributes(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"three facts about one person do not stop being that person, got {findings}"
    )


def test_coordinates_outside_a_drawing_buy_no_exemption() -> None:
    """The price of the container axis, asserted rather than left to be found.

    This is the trade and it is deliberate: the old question failed OPEN, and
    data escaped; the new one fails CLOSED, and a chart fragment pasted without
    its drawing is reported. The module refuses what it cannot prove safe, so
    of the two directions this is the one that matches it -- and a `text`
    element holding somebody's name is arguably a finding whatever coordinates
    it wears.
    """
    findings = scan_text(positioned_notes_outside_a_drawing(), source="notes.md")

    assert rules(findings) == ["P2"], (
        f"there is no drawing here, so there are no drawing labels, got {findings}"
    )


def test_a_contact_address_is_identity_in_the_json_format_too() -> None:
    """The contact row, proved from the side nothing was watching.

    Found by the mutation matrix, not by reading: emptying the contact row
    failed exactly one test, and that test is Gramps XML. The row could have
    been emptied on the JSON side and only half the suite would have noticed
    -- which is precisely how the vocabulary came to differ between formats in
    the first place, and why the address row already has this counterpart.

    It is the same row whose weight is correct *by coincidence*, contact and
    address both weighing two. Unwatched and accidentally right is not a
    combination to leave standing.
    """
    findings = scan_text(gedcom_x_contact_only(), source="tree.md")

    assert rules(findings) == ["P2"], (
        f"a way to reach a person names them in either spelling, got {findings}"
    )


def test_a_worded_chart_label_is_not_a_biography() -> None:
    """The false positive that returns if the floor is lowered instead.

    Positioned text carrying coordinates is a label; a bare text element is a
    note body. Lowering the floor to admit short notes admits these as well,
    which is measured in the table beside the constant.
    """
    assert scan_text(worded_diagram(), source="docs/chart.md") == [], (
        "a chart with worded labels is a chart"
    )


# ---------------------------------------------------------------------------
# Serialized spelling versus logical value.
#
# The fifth and sixth findings of one class: a rule reasoning about text as it
# is WRITTEN when the thing it means to judge is what that text SAYS. Both
# directions, both formats, and they are one defect rather than four.
# ---------------------------------------------------------------------------


def test_a_biography_behind_an_escaped_quote_is_still_a_biography() -> None:
    """The fail-open half. A capture that stops at the first quote it sees.

    A JSON string ends at its first UNESCAPED quote, and an escaped one is
    ordinary writing -- somebody quoting the register entry they transcribed.
    Reading the escaped quote as the end measures a whole life as two
    characters, which is below the floor, so the exact payload the prose
    weighting exists to reject scores identity weight and passes.
    """
    findings = scan_text(gedcom_x_biography_behind_an_escaped_quote(), source="tree.md")

    assert rules(findings) == ["P2"], (
        f"a quotation mark inside a life does not end the life, got {findings}"
    )


def test_a_caption_spelled_with_escapes_is_still_a_caption() -> None:
    """The false-positive half, in JSON, asserted as AGREEMENT between spellings.

    Twenty-four characters of serialization for a four-character caption. The
    floor is meant to separate a caption from a biography, and it cannot do
    that while it measures how the caption is written.
    """
    escaped = rules(scan_text(gedcom_x_caption_spelled_with_escapes(), source="tree.md"))
    literal = rules(scan_text('{"person' + 's":[],"no' + 'te":"<<<<"}', source="tree.md"))

    assert escaped == literal == [], (
        f"one caption, two spellings, two verdicts: escaped says {escaped}, literal says {literal}"
    )


def test_a_caption_spelled_with_character_references_is_still_a_caption() -> None:
    """⬅ The sixth instance, and the reason this fix is not a JSON fix.

    The floor measuring the logical value is a property of the RULE, not of
    JSON. Stated in one format and not the other it is the same partial
    application that has cost this module four rounds -- so the XML side, whose
    character references are serialization exactly as JSON escapes are, is
    carried across in the same change.

    ⚠️ **This docstring used to record "false positive only -- there is no XML
    counterpart of the fail-open above", and that was wrong.** The reasoning
    held for the reference itself, which is indeed always longer than what it
    denotes, and it did not hold for the measurement built on it: collapsing a
    reference in a place XML does not read one, or for a character XML forbids,
    shortens the value and loses the finding. Both arrived in the next round.
    See the two tests at the end of this block, which is where the counterpart
    that supposedly did not exist is now asserted from both sides.
    """
    referenced = rules(
        scan_text(gramps_caption_spelled_with_character_references(), source="notes.md")
    )
    literal = rules(scan_text("<te" + "xt>&&&&</te" + "xt>", source="notes.md"))

    assert referenced == literal == [], (
        f"one caption, two spellings, two verdicts: referenced says {referenced}, "
        f"literal says {literal}"
    )


_SPELLING_CHARACTERS = (
    ("a quote", '"'),
    ("an angle bracket", "<"),
    ("a separator", "/"),
    ("an ampersand", "&"),
    ("a plain letter", "a"),
)
"""One character per row, chosen for how differently the two formats spell it.

A quote cannot be written bare inside a JSON string and an angle bracket cannot
be written bare as XML content, so for those the escaped forms are the WHOLE
set -- they still have to agree with each other, which is the property stated
without needing a literal to compare against.
"""

_BELOW_THE_FLOOR, _ABOVE_THE_FLOOR = 4, 24


def test_prose_is_measured_on_the_logical_value_whatever_its_spelling() -> None:
    """⭐ **One value, every legal spelling, both formats, one score.**

    The two findings above are one defect seen from two sides, so this asserts
    the property underneath them rather than the two instances: a serialization
    is not its value, and the floor judges the value. Every spelling of one
    string is a different LENGTH -- up to six characters of source for one
    character of meaning -- so a floor reading the source disagrees with itself
    across this table, in whichever direction the spelling happens to run.

    Both sides of the floor are driven, and the two must DIFFER. Without that
    second half a scorer that returned a constant would satisfy the first half
    perfectly, and the floor could be deleted with this test still green.

    Asserted on the scorers rather than on ``scan_text`` so the property is
    isolated from P1 -- a table of separators and quotes is exactly the shape
    the path rules read, and a test that fails for the other property's reason
    is not telling anyone what broke.
    """
    disagreements = []

    for described, character in _SPELLING_CHARACTERS:
        for format_name, spellings_of, document_holding, scorer in (
            ("GEDCOM X", json_string_spellings, gedcom_x_notes_holding, _gedcom_x_identity_score),
            ("Gramps XML", xml_content_spellings, gramps_notes_holding, _gramps_identity_score),
        ):
            scored: dict[int, dict[str, int | None]] = {}
            for length in (_BELOW_THE_FLOOR, _ABOVE_THE_FLOOR):
                scored[length] = {}
                for spelling, body in spellings_of(character * length).items():
                    result = scorer(document_holding(body))
                    scored[length][spelling] = None if result is None else result[0]

                observed = set(scored[length].values())
                if len(observed) != 1:
                    disagreements.append(
                        f"{format_name} {described} x{length}: one value, "
                        f"{len(observed)} verdicts -- {scored[length]}"
                    )

            below = set(scored[_BELOW_THE_FLOOR].values())
            above = set(scored[_ABOVE_THE_FLOOR].values())
            if below == above:
                disagreements.append(
                    f"{format_name} {described}: the floor did not move between "
                    f"{_BELOW_THE_FLOOR} and {_ABOVE_THE_FLOOR} characters -- {below}; "
                    "the spellings agree because nothing is being measured"
                )

    assert disagreements == [], (
        "the prose floor is reading the serialization rather than the value it denotes: "
        f"{disagreements}"
    )


def test_measuring_a_value_never_decodes_it_into_the_document() -> None:
    """The guardrail on the fix, which matters as much as the fix.

    Decoding for LENGTH is safe only while the decoded text stays a number. The
    moment it is handed back as a string, an escape can manufacture the
    structure ``_STRUCTURE_CHARACTERS`` exists to refuse -- and the JSON and XML
    spellings of that hazard are the same hazard.

    Both halves of the accepted residual are asserted here, from inside a value
    that IS now measured: the escaped drive path stays uncaught, and prose
    naming four member names stays clean rather than decoding into four
    apparent structural keys.
    """
    backslash = chr(92)
    escaped_path = (
        "C" + backslash + "u003a" + backslash + "u005c" + "Users" + backslash + "u005c" + "elowen"
    )

    inside_a_measured_value = scan_text(
        gedcom_x_notes_holding(escaped_path, copies=1), source="notes.md"
    )

    assert "P1" not in rules(inside_a_measured_value), (
        "measuring a value must not decode it into a path the document does not "
        f"contain, got {inside_a_measured_value}"
    )
    assert (
        scan_text(prose_describing_json_keys_with_escaped_quotes(), source="docs/notes.md") == []
    ), "measuring a value must not manufacture the structure the source lacks"


def test_an_unterminated_json_string_is_not_measured() -> None:
    """⚠️ The ACCEPTED residual of this fix, recorded as a test rather than prose.

    Reading a string literal correctly means finding its true end, and a
    document whose only closing quote is an escaped one has no true end. It
    scores nothing where it previously scored a filled key -- but that previous
    match was itself the defect: it captured two characters of a truncated
    payload because it stopped at the wrong quote.

    A genuinely truncated document -- no closing quote at all -- matched under
    neither spelling, so what is lost is narrow. The obvious repair is a
    fallback to the old pattern, and it is refused for the reason two paths are
    always refused here: two matchers with two ideas of where a string ends is
    how the vocabulary came to differ between formats in the first place.
    """
    unterminated = '{"no' + 'tes":[{"te' + 'xt":"' + _PROBE_PAYLOAD + chr(92) + '"}]}'

    assert _gedcom_x_identity_score(unterminated) is None, (
        "recorded residual: a string with no unescaped end is not measured; "
        "if this now scores, the residual table needs the row removed"
    )


_INERT = "a"
"""A character no rule below reads: not a reference, not markup, not whitespace.

The controls are built from it so that a control's LENGTH is the only thing
distinguishing it, which is what lets both tests below compare verdicts instead
of asserting weights nobody can rederive.
"""


def test_content_xml_treats_literally_is_measured_literally() -> None:
    """⬅ The measurement decoded what XML does not: the wrong PLACE.

    A CDATA section is the one construct whose content XML reads as itself, and
    the wrapper was stripped before the length was taken -- so a reference
    written inside one, where it denotes the five or six characters it is
    spelled with, was counted as the single character it would name outside.
    Every such reference shortened the value, and shortening is the direction
    that loses the finding rather than the direction that reports one.

    Stated as the property and not as the instance: a section holding N
    characters is worth what N characters are worth. The controls carry the
    same COUNT of inert characters, so nothing here asserts a weight -- a
    disagreement means the section was measured as something other than its own
    source, whichever way it went.

    Both sides of the floor are driven, and they must differ. Without that a
    scorer ignoring content entirely would satisfy the agreement half perfectly.
    """
    disagreements = []
    observed = set()

    for described, character in _SPELLING_CHARACTERS:
        for copies in (1, _BELOW_THE_FLOOR):
            for spelling, body in xml_content_spellings(character * copies).items():
                literal = _gramps_identity_score(gramps_notes_holding(inside_a_cdata_section(body)))
                same_length = _gramps_identity_score(gramps_notes_holding(_INERT * len(body)))
                observed.add(None if same_length is None else same_length[0])
                if literal != same_length:
                    disagreements.append(
                        f"{described} x{copies} {spelling}: {len(body)} characters of source "
                        f"scored {literal} inside a section and {same_length} outside one"
                    )

    assert disagreements == [], (
        "a CDATA section is being decoded before it is measured, so content XML "
        f"takes literally was counted as what it would mean elsewhere: {disagreements}"
    )
    assert len(observed) > 1, (
        f"every control reached the same verdict {observed}; the floor is not being "
        "driven from both sides, so the agreement above proves nothing"
    )


_XML_CHARACTER_BOUNDARIES = (
    # Both sides of every edge of the XML 1.0 Char production, transcribed from
    # the specification rather than derived from the implementation -- a table
    # that recomputed the rule would agree with a wrong rule.
    #
    #   Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD]
    #                                            | [#x10000-#x10FFFF]
    ("the control below tab", 0x8, False),
    ("tab", 0x9, True),
    ("line feed", 0xA, True),
    ("the control between line feed and carriage return", 0xB, False),
    ("carriage return", 0xD, True),
    ("the last control below space", 0x1F, False),
    ("space, opening the main range", 0x20, True),
    ("the last character below the surrogates", 0xD7FF, True),
    ("the first surrogate", 0xD800, False),
    ("the last surrogate", 0xDFFF, False),
    ("the first character above the surrogates", 0xE000, True),
    ("the last character below the noncharacters", 0xFFFD, True),
    ("the first noncharacter", 0xFFFE, False),
    ("the second noncharacter", 0xFFFF, False),
    ("the first supplementary character", 0x10000, True),
    ("the largest code point", 0x10FFFF, True),
    ("one past the largest code point", 0x110000, False),
)
"""Every edge of the production, from both sides, with what XML says of each.

⚠️ **The plane-one noncharacters are absent deliberately.** XML 1.0 permits
``U+1FFFE`` and its kin -- the production excludes only the two in the basic
plane -- so a row asserting otherwise would be asserting Unicode's opinion in
the place XML's is what matters.
"""


def test_a_reference_names_a_character_or_it_names_nothing() -> None:
    """⬅ The measurement decoded what XML does not: the wrong CHARACTER.

    The same defect as above seen from its other side. The check tested one
    edge of the production -- is this above the largest code point -- and every
    other edge fell through it, so NUL, a control, a surrogate and a
    noncharacter each collapsed to one character apiece. XML forbids all four
    outright: they name nothing, and counting nothing as one character shortens
    the value.

    ⚠️ **The function's docstring already stated the contract this violates**:
    *only a reference that provably denotes exactly one character is collapsed
    to one*. A stated rule that nothing asserted is its own defect class, and
    the reason this is a test and not a comment.

    Every probe is exactly the floor in SOURCE characters, so the two controls
    are the whole assertion: a reference XML permits collapses and lands with
    the shorter control, and one it forbids stays put and lands with the longer
    one. No weight is written down, and a rule that always collapsed or never
    collapsed fails half the table either way.
    """
    stays = _gramps_identity_score(gramps_notes_holding(_INERT * _GRAMPS_PROSE_LENGTH))
    collapses = _gramps_identity_score(gramps_notes_holding(_INERT * (_GRAMPS_PROSE_LENGTH - 1)))
    assert stays != collapses, "the premise of this test: the floor separates these two controls"

    disagreements = []

    for described, code_point, permitted in _XML_CHARACTER_BOUNDARIES:
        for spelling, reference in (
            ("decimal", "&#" + str(code_point) + ";"),
            ("hex", "&#x" + format(code_point, "x") + ";"),
        ):
            body = _INERT * (_GRAMPS_PROSE_LENGTH - len(reference)) + reference
            measured = _gramps_identity_score(gramps_notes_holding(body))
            expected = collapses if permitted else stays
            if measured != expected:
                disagreements.append(
                    f"U+{code_point:04X} ({described}) as a {spelling} reference: XML "
                    f"{'permits' if permitted else 'forbids'} it, so it should have "
                    f"scored {expected} and scored {measured}"
                )

    assert disagreements == [], (
        "a numeric reference is being collapsed on the strength of naming a code "
        f"point rather than a character XML permits: {disagreements}"
    )


def test_configuration_json_is_not_genealogy_without_the_format(tmp_path: Path) -> None:
    """The corroboration gate, which is load-bearing rather than decorative.

    The JSON spellings of prose and address are ordinary words. Counting them
    without a GEDCOM X marker present in the file reports any configuration
    that has a text key -- a button caption, say -- and that is the difference
    between this vocabulary and a rule nobody could keep.
    """
    ordinary = '{"text":"Click here to continue","city":"the city field label"}\n'

    assert scan_text(ordinary, source="settings.md") == [], (
        "these keys are only genealogy in a document that says it is genealogy"
    )


def test_ordinary_configuration_is_not_a_name_in_parts() -> None:
    """The discriminator, asserted rather than assumed.

    A bare value key is everywhere in configuration and schemas. It is the
    PAIRING of a type with a value inside one object that is the name-part
    shape, and that pairing is what must not be simplified away.
    """
    ordinary = (
        '{"value":"on","options":[{"value":"off"},{"value":"auto"}]}\n'
        '{"properties":{"value":{"type":"string"}}}\n'
    )

    assert scan_text(ordinary, source="settings.md") == [], (
        "matching a value key alone would report every configuration file here"
    )


def test_a_specification_about_that_format_is_not_a_finding() -> None:
    """The other direction, as ever: naming the keys is not carrying them."""
    spec = (
        "# Importing GEDCOM X\n\nEach record has a `persons` array; every entry carries `names`,\n"
        "each of which has `nameForms`, and a form has a `fullText` string.\n"
    )

    assert scan_text(spec, source="docs/importing.md") == [], "a specification is not an export"


def test_an_unrecognised_genealogy_format_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text(gedcom_x_json(), encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], (
        f"a genealogy format the guard cannot name must still not pass, got {findings}"
    )


def test_an_unprovable_file_type_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "settings.cfg").write_text("harmless = 1\n", encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert rules(findings) == ["P2"], f"an unknown file type is not provably safe, got {findings}"


def test_the_unprovable_type_finding_says_how_to_allow_the_type(tmp_path: Path) -> None:
    (tmp_path / "settings.cfg").write_text("harmless = 1\n", encoding="utf-8")

    message = scan_paths([tmp_path])[0].message

    assert "SAFE_EXTENSIONS" in message, (
        "a contributor who cannot see how to add a type files a bug instead of "
        f"a one-line change; got {message!r}"
    )


def test_every_file_type_the_repository_uses_is_provably_safe(tmp_path: Path) -> None:
    for name in ("module.py", "notes.md", "pyproject.toml", "ci.yml", "LICENSE", ".gitignore"):
        (tmp_path / name).write_text("harmless\n", encoding="utf-8")

    assert scan_paths([tmp_path]) == [], "the types this repository already uses must pass"
