"""P2 -- no genealogy data the guard has a property for, whatever it is named,
and no content it cannot prove safe.

Extension matching is necessary and not sufficient: the content is sniffed, and
content the guard cannot classify is a finding rather than a pass. The two
halves are not interchangeable -- a format with a property is caught in any
file type, and one without rests on the safe-type gate, which is the residual
this project recorded first.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from gramps_live_api.core.pii_guard import (
    _CATEGORY_WEIGHT,
    _VOCABULARY,
    _gedcom_x_identity_score,
    _gramps_identity_score,
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
    gedcom_x_json,
    gedcom_x_name_parts,
    gedcom_x_name_parts_with_qualifiers,
    gedcom_x_note_only,
    gedcom_x_short_note,
    gramps_address_block,
    gramps_attributed_identity,
    gramps_biography_and_address,
    gramps_biography_in_cdata,
    gramps_contact_url,
    gramps_importer_spec,
    gramps_name_block,
    gramps_namespace_fragment,
    gramps_namespace_url,
    gramps_note_biography,
    gramps_person_fragment,
    gramps_reference_fragment,
    gramps_short_notes,
    gramps_xml_document,
    labelled_diagram,
    sqlite_bytes,
    unclassifiable_bytes,
    utf16le_gedcom_bytes,
    worded_diagram,
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


def _gramps_probe(spelling: str, copies: int) -> str:
    return "".join(
        "<" + spelling + ">" + _PROBE_PAYLOAD + "</" + spelling + ">" for _ in range(copies)
    )


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
    """What one filled key or element of ``spelling`` is actually worth."""
    low, high = (scorer(probe(spelling, copies)) for copies in _PROBE_COPIES)
    assert low is not None and high is not None, (
        f"{spelling!r} does not clear the threshold even in quantity, so the compiled "
        "scorer scores it at nothing -- the category is lost, not mis-weighted"
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


def test_a_worded_chart_label_is_not_a_biography() -> None:
    """The false positive that returns if the floor is lowered instead.

    Positioned text carrying coordinates is a label; a bare text element is a
    note body. Lowering the floor to admit short notes admits these as well,
    which is measured in the table beside the constant.
    """
    assert scan_text(worded_diagram(), source="docs/chart.md") == [], (
        "a chart with worded labels is a chart"
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
