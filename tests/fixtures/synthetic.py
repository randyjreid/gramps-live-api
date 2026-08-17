"""Builders for strings that *look like* the things the PII guard rejects.

Nothing in this module is a literal absolute path or genealogy record. Every
such value is assembled at runtime from harmless parts, because
the guard runs over this whole checkout in CI: a committed literal would be a
genuine finding, and suppressing it would mean weakening the guard to let the
tests pass.

All names used here are invented. See ``tests/fixtures/__init__``.
"""

from __future__ import annotations

import itertools
import json

_BACKSLASH = chr(92)
_SLASH = "/"


def _level(number: int, rest: str) -> str:
    """One GEDCOM record, assembled rather than written.

    The rule at the top of this module applies to every line of an export, not
    only the level-0 ones. Half of them used to be literals, which made this
    the one file in the repository the density property reported -- correctly:
    three consecutive records are three consecutive records wherever they sit,
    and a fixture that breaks its own rule is the thing to fix.
    """
    return f"{number} {rest}"


def windows_path(*parts: str, drive: str = "C") -> str:
    """A drive-letter absolute path: drive, colon, then parts joined by backslashes."""
    return drive + ":" + _BACKSLASH + _BACKSLASH.join(parts)


def windows_path_forward_slashes(*parts: str, drive: str = "D") -> str:
    """A drive-letter absolute path written with forward slashes."""
    return drive + ":" + _SLASH + _SLASH.join(parts)


def unc_path(host: str, *parts: str) -> str:
    """A UNC absolute path: two backslashes, the host, then the parts."""
    return (_BACKSLASH * 2) + host + _BACKSLASH + _BACKSLASH.join(parts)


def posix_path(*parts: str) -> str:
    """A leading-slash absolute path: a slash, then parts joined by slashes."""
    return _SLASH + _SLASH.join(parts)


def gedcom_document() -> str:
    """A minimal but structurally real GEDCOM file, invented names only."""
    lines = [
        _level(0, "HEAD"),
        _level(1, "SOUR ExampleKit"),
        _level(1, "GEDC"),
        _level(2, "VERS 5.5.1"),
        _level(0, "@I1@ INDI"),
        _level(1, "NAME Quorvane"),
        _level(2, "SURN Ashenmoor"),
        _level(1, "SEX F"),
        _level(0, "TRLR"),
    ]
    return "\n".join(lines) + "\n"


def gedcom_walkthrough() -> str:
    """An importer design note: one record, then prose explaining it.

    The document this repository will actually produce. Not an export pasted in
    a block -- records interleaved with paragraphs, which is why counting them
    across the file rather than consecutively is what catches it.
    """
    records = [
        _level(1, "NAME Quorvane " + _SLASH + "Ashenmoor" + _SLASH),
        _level(2, "GIVN Quorvane"),
        _level(2, "SURN Ashenmoor"),
        _level(1, "SEX F"),
        _level(1, "BIRT"),
        _level(2, "DATE 2 APR 1893"),
        _level(2, "PLAC Thornwick, Ashenmoor Vale"),
        _level(1, "OCCU Wheelwright"),
    ]
    prose = "The line above gives the name; the slashes delimit the surname.\n\n"
    return "# Importing a tree\n\n" + "".join(f"{record}\n\n{prose}" for record in records)


def _element(name: str, *, attributes: str = "", body: str = "", empty: bool = False) -> str:
    """One XML element, assembled rather than written.

    Same rule as the GEDCOM records above, for the same reason: this project's
    native format is Gramps XML, and a literal person element in a tracked file
    is a genuine finding once the guard counts them.
    """
    opening = "<" + name + (f" {attributes}" if attributes else "")
    if empty:
        return opening + "/>"
    return opening + ">" + body + "</" + name + ">"


def gramps_person_fragment() -> str:
    """A person, their gender and their date of birth. No prolog, no database element."""
    name = _element(
        "name",
        attributes='type="Birth Name"',
        body=_element("first", body="Quorvane") + _element("surname", body="Ashenmoor"),
    )
    birth = _element("birth", body=_element("dateval", attributes='val="1893-04-02"', empty=True))
    inner = "\n  ".join((_element("gender", body="F"), name, birth))
    return _element("person", attributes='handle="_h1" id="I0001"', body="\n  " + inner + "\n")


GRAMPS_XML_VERSION = "1.7.2"
"""What Gramps 6.0 reads and writes, per ``plugins/lib/libgrampsxml.py``."""

SEED_PERSON_HANDLE = "slice1person"
SEED_PERSON_GRAMPS_ID = "I0001"
"""The one person in ``importable_tree_document``, by both of its names.

⚠️ **The handle here has NO leading underscore, and the document below writes
one.** ``plugins/importer/importxml.py`` reads the attribute as
``attrs["handle"].replace("_", "")``, so the value in the database is the
stripped one -- which is what an operation has to name, and what cost a probe
run to find out.
"""


def importable_tree_document() -> str:
    """A whole Gramps XML document holding one invented person.

    Assembled from parts for the reason the whole module is: a literal person
    element in a tracked file is a genuine finding here. This one is a complete
    document rather than a fragment because Gramps has to be able to *import*
    it -- it is how the round-trip test gets a real tree without any real tree.

    ⚠️ **Imported into an EMPTY tree, which is what preserves the handles.**
    ``importxml.py`` sets ``replace_import_handle = db.get_number_of_people() >
    0``, so a fresh tree keeps what the document says and a populated one
    renames everything. The test needs the first behaviour, and the owner's
    export-then-import-as-a-new-tree copy gets it for the same reason.
    """
    namespace = "http:" + "//gramps-project" + ".org/xml/" + GRAMPS_XML_VERSION + _SLASH
    person = _element(
        "person",
        attributes=f'handle="_{SEED_PERSON_HANDLE}" id="{SEED_PERSON_GRAMPS_ID}"',
        body=_element("gender", body="F")
        + _element(
            "name",
            attributes='type="Birth Name"',
            body=_element("first", body="Quorvane") + _element("surname", body="Ashenmoor"),
        ),
    )
    header = _element(
        "header",
        body=_element("created", attributes='date="2026-08-16" version="6.0.8"', empty=True)
        + _element("researcher"),
    )
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _element(
        "database",
        attributes=f'xmlns="{namespace}"',
        body=header + _element("people", body=person),
    )


def gramps_name_block() -> str:
    """A name and nothing else: three elements and a complete person."""
    return _element(
        "name",
        body=_element("first", body="Quorvane") + _element("surname", body="Ashenmoor"),
    )


def gramps_note_biography() -> str:
    """A note carrying a life in prose. Two elements and a whole person."""
    return _element(
        "note",
        attributes='handle="_n1"',
        body=_element(
            "text",
            body=(
                "Quorvane Ashenmoor, born 2 April 1893 in Thornwick, married twice, "
                "wheelwright by trade, died 17 November 1961."
            ),
        ),
    )


def gedcom_x_name_parts() -> str:
    """A name expressed as GEDCOM X parts: each carries a type URI and a value.

    Keys assembled, like every other builder here.
    """
    type_key, value_key = "ty" + "pe", "val" + "ue"
    parts = [
        {type_key: "http://gedcomx.org/Given", value_key: "Quorvane"},
        {type_key: "http://gedcomx.org/Surname", value_key: "Ashenmoor"},
    ]
    return json.dumps({"na" + "meForms": [{"pa" + "rts": parts}]}, separators=(",", ":")) + "\n"


def gedcom_x_name_parts_with_qualifiers() -> str:
    """The same name in parts, each part carrying a qualifier.

    A qualifier says which part is primary and is entirely ordinary GEDCOM X.
    It nests an object inside the part, which is all it takes to defeat a
    matcher that keeps itself inside one object by refusing to cross a brace.

    Nested under the full document shape the reviewer used, so the structural
    keys are present and the part pairing is the only thing deciding the
    verdict. Keys assembled, like every builder here.
    """
    type_key, value_key = "ty" + "pe", "val" + "ue"
    qualifiers = "qualifi" + "ers"
    parts = [
        {
            type_key: "http://gedcomx.org/Given",
            value_key: "Quorvane",
            qualifiers: [{"name": "http://gedcomx.org/Primary"}],
        },
        {
            type_key: "http://gedcomx.org/Surname",
            value_key: "Ashenmoor",
            qualifiers: [{"name": "http://gedcomx.org/Primary"}],
        },
    ]
    document = {
        "person" + "s": [
            {"name" + "s": [{"name" + "Forms": [{"pa" + "rts": parts}]}]},
        ]
    }
    return json.dumps(document, separators=(",", ":")) + "\n"


_BIOGRAPHY = "Elowen Ashenmoor, born 2 April 1893 in Thornwick, wheelwright, died 1961."

_A_WHOLE_IDENTITY = ("Elowen Ashenmoor", "2 April 1893", "Thornwick")
"""A name, a date of birth and a place: too short to be prose, a person together.

⚠️ **Extracted from ``gramps_short_notes``, which now reads it, rather than
copied beside it.** Two builders spelling the same identity is how one of them
comes to be edited alone -- and a test that derives a figure from ``len(...)``
here would silently disagree with a payload that had grown a fourth fact.
"""


def gedcom_x_biography_and_address() -> str:
    """The same life the Gramps fixture carries, in the other format.

    One payload, two spellings: this is what a vocabulary living in two places
    lets through. Keys assembled, like every builder here.
    """
    document = {
        "person" + "s": [
            {
                "no" + "tes": [{"te" + "xt": _BIOGRAPHY}],
                "addres" + "ses": [{"str" + "eet": "14 Milllane", "ci" + "ty": "Thornwick"}],
            }
        ]
    }
    return json.dumps(document, separators=(",", ":")) + "\n"


def gedcom_x_note_only() -> str:
    """A whole life in one GEDCOM X note, and nothing else.

    The payload the XML side has always caught as prose. Two keys: one
    structural, one prose.
    """
    return json.dumps({"no" + "tes": [{"te" + "xt": _BIOGRAPHY}]}, separators=(",", ":")) + "\n"


def gedcom_x_short_note() -> str:
    """A note too short to be prose, in the format's own container.

    The false-positive side of weighing JSON prose as prose. A caption under a
    note key is a caption; the length floor is what says so, and the XML side
    has had one since the floor was measured.
    """
    return json.dumps({"no" + "tes": [{"te" + "xt": "OK"}]}, separators=(",", ":")) + "\n"


def gedcom_x_contact_only() -> str:
    """Two ways to reach a person, in the JSON spellings, and nothing else.

    Deliberately carries no name, no address and no prose: the CONTACT row is
    the only thing that can take this over the threshold, so emptying that row
    fails here rather than passing quietly. The XML side has had such a test
    since the row was added; this is its counterpart.
    """
    document = {
        "person" + "s": [
            {
                "u" + "rl": "mailto:elowen.ashenmoor@example.invalid",
                "email" + "s": "elowen.ashenmoor@example.invalid",
            }
        ]
    }
    return json.dumps(document, separators=(",", ":")) + "\n"


def gramps_biography_and_address() -> str:
    """The same life as Gramps XML, which has always been caught."""
    return _element(
        "person",
        attributes='handle="_h1"',
        body=_element("note", body=_element("text", body=_BIOGRAPHY))
        + _element(
            "address",
            body=_element("street", body="14 Milllane") + _element("city", body="Thornwick"),
        ),
    )


def gramps_biography_in_cdata() -> str:
    """A biography wrapped in CDATA, which is ordinary XML for prose with markup."""
    wrapped = "<![" + "CDATA[" + _BIOGRAPHY + " Married twice & mother of three.]" + "]>"
    return _element("note", attributes='handle="_n1"', body=_element("text", body=wrapped))


def gramps_short_notes() -> str:
    """Three short notes: a name, a date of birth, a place. A whole identity."""
    return "".join(
        _element("note", body=_element("text", body=value)) for value in _A_WHOLE_IDENTITY
    )


def gramps_short_notes_with_attributes() -> str:
    """The same three short notes, wearing an ordinary XML attribute.

    ``xml:space`` says how to treat whitespace and nothing whatever about
    position. Any attribute at all used to be read as evidence of a positioned
    chart label, so adding this to an exact name-date-place payload returned
    it clean.
    """
    return "".join(
        _element("note", body=_element("text", attributes='xml:space="preserve"', body=value))
        for value in ("Elowen Ashenmoor", "2 April 1893", "Thornwick")
    )


def positioned_notes_outside_a_drawing() -> str:
    """Short notes carrying coordinates, with no drawing around them.

    The cost of judging by container instead of by attribute, made visible.
    Nothing here is a chart -- there is no drawing -- so the coordinates buy
    no exemption and a name, a date and a place are reported.
    """
    return "".join(
        _element("note", body=_element("text", attributes=f'x="0" y="{offset}"', body=value))
        for offset, value in ((0, "Elowen Ashenmoor"), (9, "2 April 1893"), (18, "Thornwick"))
    )


def gramps_contact_url() -> str:
    """A live e-mail address, which identifies a person as directly as a home path."""
    return _element(
        "url", attributes='href="mailto:elowen.ashenmoor@example.invalid" type="E-mail"', empty=True
    )


def gramps_attributed_identity() -> str:
    """Identity carried in attributes: a surname, and a place name in no list at all."""
    return _element("surname", attributes='val="Ashenmoor"', empty=True) + _element(
        "pname", attributes='value="Quorvane, Aldershire"', empty=True
    )


def worded_diagram(*, prefix: str = "") -> str:
    """A chart whose labels are words rather than numbers.

    The shape that returns if the prose floor is lowered instead of the
    positioned-text discriminator being used.

    ``prefix`` spells the drawing and its labels as a namespace-prefixed
    document -- ``<svg:svg>`` holding ``<svg:text>``. That is the same lexical
    blindness the element patterns had, pointing the other way: the labels are
    visible to the scorer and their container is not, so a chart is reported.
    Both tags take the prefix, because a document that qualifies one qualifies
    the other.
    """
    qualifier = prefix + ":" if prefix else ""
    labels = "".join(
        _element(qualifier + "text", attributes=f'x="0" y="{offset}"', body=value)
        for offset, value in ((9, "Temperature"), (18, "Pressure over time"))
    )
    return _element(qualifier + "svg", body=labels)


def positioned_label(*, body: str | None = None, offset: int = 9, prefix: str = "") -> str:
    """One positioned label, in the three spellings that differ by what it holds.

    ``body=None`` is the self-closing spelling and ``body=""`` the paired-empty
    one. **Those two are what the filled pass cannot see**: its content
    alternative needs at least one character, so neither reaches a closing tag
    and neither is ever claimed as filled. Anything else -- a space, a number, a
    word -- is content, and the filled pass claims it.

    That is the whole distinction this builder exists to hold as a parameter
    rather than as three fixtures: the two no-content spellings must be shown to
    agree with each other, and to differ from a whitespace-only one, on the same
    element in the same container.
    """
    qualifier = prefix + ":" if prefix else ""
    attributes = f'x="0" y="{offset}"'
    if body is None:
        return _element(qualifier + "text", attributes=attributes, empty=True)
    return _element(qualifier + "text", attributes=attributes, body=body)


def drawing_holding(body: str, *, prefix: str = "") -> str:
    """A drawing around whatever it is given: the container as a variable.

    The neighbouring drawing builders each carry a fixed payload and a property
    of their own, so none of them can be asked what a *different* payload does
    inside the same container. This one takes the payload, which is what lets a
    property be asserted over the label spellings above rather than over a
    chart somebody wrote.
    """
    qualifier = prefix + ":" if prefix else ""
    return _element(qualifier + "svg", body=body)


def attributed_wrapper_holding(
    *, facts: tuple[str, ...] = _A_WHOLE_IDENTITY, spelling: str = "note", copies: int = 1
) -> str:
    """``copies`` prose wrappers, each carrying an attribute and enclosing ``facts``.

    ⚠️ **The shape whose content the filled pass cannot READ.** The wrapper's
    own content begins with a nested start tag, and the filled pattern's content
    alternative admits neither ``<`` nor any markup node that ends where an
    element does -- so the pattern cannot reach the wrapper's closing tag and
    the filled pass never claims it. The attributed pass does, and it measures
    no content at all.

    The children are ordinary short prose and are claimed by the filled pass, so
    what a drawing around this suppresses is **them** and not the wrapper.

    ``spelling`` names the WRAPPER only; the children stay one spelling, so a
    property asserted across the prose rows varies the element under test and
    nothing else.
    """
    return "".join(
        _element(
            spelling,
            attributes='handle="_n1"',
            body="".join(_element("text", body=fact) for fact in facts),
        )
        for _ in range(copies)
    )


def notes_inside_a_container(*, prefix: str = "", namespace: str = "") -> str:
    """Three short notes inside a drawing container, bare or namespace-prefixed.

    The payload is ``gramps_short_notes`` -- a name, a date of birth and a
    place, each too short to clear the prose floor and a finding together. It
    is the SAME payload in both spellings, so the only variable is the
    container.

    With no ``prefix`` this is the exemption that earns its keep: an ordinary
    drawing, whose short text elements are labels. With one, the container is a
    drawing by SHAPE alone -- ``namespace`` binds that alias to something that
    is not SVG, and nothing here resolves it. Matching by shape is conservative
    for a scorer and fail-open for an exemption, so the exemption is withdrawn
    rather than granted on an unresolved alias and the notes are reported.

    The binding is assembled by the caller, like every other value here: a
    namespace written whole in a tracked file is a value in a tracked file.
    """
    qualifier = prefix + ":" if prefix else ""
    binding = "xmlns:" + prefix + '="' + namespace + '"' if prefix else ""
    return _element(qualifier + "svg", attributes=binding, body=gramps_short_notes())


def gramps_address_block() -> str:
    """Where a person lives: a populated Gramps address record."""
    return _element(
        "address",
        attributes='handle="_a1"',
        body="".join(
            (
                _element("street", body="14 Milllane"),
                _element("city", body="Thornwick"),
                _element("postal", body="ZZ1 1ZZ"),
            )
        ),
    )


def gramps_issue_address_payload() -> str:
    """The address payload issue #4 item 1 was filed with, assembled.

    Kept apart from ``gramps_address_block`` deliberately: that one is the
    property's own fixture and may be rewritten with it, while this is a
    RE-MEASUREMENT of a specific reported input and has to stay the input that
    was reported. It carries the dated element the issue wrote and one more
    address child than the block does.
    """
    return _element(
        "address",
        body="".join(
            (
                _element("dateval", attributes='val="1893-04-02"', empty=True),
                _element("street", body="12 Zephyrglass Lane"),
                _element("city", body="Thornwick"),
                _element("postal", body="ZX1"),
                _element("phone", body="555-0100"),
            )
        ),
    )


def genealogy_record_as_a_filename() -> str:
    """A committed NAME that is itself a genealogy record.

    Assembled like every record here. The characters are all legal in a Git
    tree entry, which is the point: a name is published exactly as its file's
    contents are, and an export dumped one-record-per-file names its files
    after the records.
    """
    return _level(0, "@I1@ INDI") + ".md"


def gramps_reference_fragment() -> str:
    """An export's links: elements with handles and no content of their own.

    A handle is export syntax -- nothing writes one in prose -- so this is
    genealogy data even though not one element is filled.
    """
    return "".join(
        (
            _element("person", attributes='handle="_h1"', empty=True),
            _element("eventref", attributes='hlink="_e1"', empty=True),
            _element("childref", attributes='hlink="_c1"', empty=True),
            _element("noteref", attributes='hlink="_n1"', empty=True),
        )
    )


def labelled_diagram() -> str:
    """Four short labels in a chart: the shape a prose weight with no floor eats."""
    labels = "".join(
        _element("text", attributes=f'x="{offset}" y="12"', body=value)
        for offset, value in ((0, "0.5"), (9, "1.0"), (18, "1.5"), (27, "2.0"))
    )
    return _element("svg", body=labels)


def gramps_importer_spec() -> str:
    """A design note *about* the format: mentions, a mapping table, the namespace.

    The document an importer spec actually is, and the one the guard must not
    report. Every element name here is a mention -- backticked, unfilled, with
    no content of its own -- which is the whole distinction the property rests
    on.
    """
    mentions = (
        ("person", "one row per individual"),
        ("name", "display name, assembled from the parts below"),
        ("surname", "family name"),
        ("first", "given name"),
        ("gender", "mapped to our sex enumeration"),
        ("birth", "a vital event with a date and a place"),
        ("note", "free text, imported verbatim"),
        ("text", "the body of a note"),
    )
    rows = "\n".join(f"| `<{tag}>` | {meaning} |" for tag, meaning in mentions)
    return (
        "# Importing a Gramps export\n\n"
        f"Exports identify themselves with the namespace {gramps_namespace_url()}, which is\n"
        "how the importer recognises one.\n\n"
        "| element | maps to |\n| --- | --- |\n"
        f"{rows}\n\n"
        "Nested `<dateval>` and `<placeobj>` elements are parsed recursively. No tree is\n"
        "stored in this repository.\n"
    )


def gramps_namespace_url() -> str:
    """The namespace on its own -- what a document *about* the format contains."""
    # Split inside it, for the reason given below.
    return "http:" + "//gramps-project" + ".org/xml/1.7.1/"


def gramps_namespace_fragment() -> str:
    """A fragment carrying the namespace but not first in its document."""
    # Split inside the namespace, not merely before it: the guard now
    # recognises that string wherever it appears, so a contiguous copy here
    # is a genuine finding in a tracked file.
    namespace = "http:" + "//gramps-project" + ".org/xml/1.7.1/"
    inner = _element("person", body=_element("name", body=_element("first", body="Quorvane")))
    return (
        "# Import notes\n\nWe get documents shaped like this:\n\n"
        + _element("something", attributes=f'xmlns="{namespace}"', body="\n  " + inner + "\n")
        + "\n"
    )


def gramps_xml_document() -> str:
    """A minimal Gramps XML export, invented names only."""
    # Split inside the namespace, not merely before it: the guard now
    # recognises that string wherever it appears, so a contiguous copy here
    # is a genuine finding in a tracked file.
    namespace = "http:" + "//gramps-project" + ".org/xml/1.7.1/"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<database xmlns="{namespace}">',
        "  <people>",
        "    " + _element("person", attributes='handle="_h1" id="I0001"', body=""),
        "      " + gramps_name_block(),
        "    </person>",
        "  </people>",
        "</database>",
    ]
    return "\n".join(lines) + "\n"


def gramps_xml_database_element(*, prefix: str = "") -> str:
    """The line by which the format names itself: a database element and the namespace.

    ``prefix`` spells it as a namespace-prefixed document -- what an export
    written by a tool that binds the namespace to an alias looks like, and the
    spelling the signature was blind to. Assembled prefix and all, for the
    reason at the top of this module: the unprefixed form of this line is a
    genuine finding in a tracked file.
    """
    # Split inside the namespace, not merely before it, exactly as the builders
    # above split it and for the same reason.
    namespace = "http:" + "//gramps-project" + ".org/xml/1.7.1/"
    qualifier = prefix + ":" if prefix else ""
    declaration = "xmlns:" + prefix if prefix else "xmlns"
    return _element(qualifier + "database", attributes=f'{declaration}="{namespace}"')


def names_the_gramps_format() -> str:
    """The declared namespace, IN a declaration: the marker, and nothing else with it.

    A spelling the schema derivation ADDED scores only in a text that names the
    format. This is the cheapest such text, and it is deliberately the *only*
    marker these fixtures carry.

    ⚠️ **This used to return the namespace on its own, and that stopped being a
    marker.** The gate reads the schema-fixed value as the VALUE of an ``xmlns``
    attribute in a start tag, because a document that merely *mentions* the
    namespace has not declared it -- a prose sentence naming it beside four
    generic ``<type>`` elements scored 6 and was reported. See the marker block
    in ``pii_guard`` for why the gate is anchored. Left returning the bare URL,
    every probe built on this would measure a CLOSED gate and every test using
    one would go red for the right reason and the wrong cause.

    ⚠️ **Deliberately NOT the document element.** ``<database … gramps…>`` is a
    genealogy TEXT SIGNATURE, and a signature short-circuits ``_sniff_genealogy``
    before any scorer runs -- so a fixture marked that way would report for a
    reason that has nothing to do with the gate, and a test using it could not
    tell an open gate from a closed one. ``catalogue`` is a name the published
    schema does not declare, so the wrapper carries no weight of its own and
    leaves the scorer the thing being measured.

    Composed inside itself, like every other spelling of it here: the guard
    recognises that string wherever it appears, so a contiguous copy in a
    tracked file is a genuine finding.
    """
    return _element("catalogue", attributes='xmlns="' + gramps_namespace_url() + '"')


def a_prose_mention_of_the_namespace() -> str:
    """A sentence naming the namespace, with no markup anywhere around it.

    What a document *about* the format contains, and what the gate must not
    read as the format declaring itself. Distinct from
    ``gramps_importer_spec`` on purpose: that one is a whole design note, and
    this is the one sentence, so a repair that rests on anything else in the
    note fails here.
    """
    return (
        "# Import notes\n\nExports identify themselves with the namespace "
        + gramps_namespace_url()
        + ",\nwhich is how the importer recognises one.\n"
    )


def generic_xml_names_beside_a_prose_mention() -> str:
    """The reproduction: that sentence, then four filled ``<type>`` elements.

    A mention is not a declaration, so the four generic names after it are as
    ordinary as they are in the bare reproduction. Written as the sentence plus
    the existing builder rather than as a new document, so the only thing this
    adds to that reproduction is the mention.
    """
    return a_prose_mention_of_the_namespace() + "\n" + gramps_generic_xml_names()


def gramps_generic_xml_names() -> str:
    """Four filled ``<type>`` elements in a document about unrelated XML.

    The reproduction the marker gate was built for. ``type`` is a schema
    spelling AND an ordinary XML name, so it is in neither published markup
    index and the deliberately-unweighted category never sees it -- four filled
    ones reached the threshold in any document that happened to show a type.
    """
    values = ("string", "integer", "boolean", "date")
    return "\n".join(_element("type", body=value) for value in values) + "\n"


def generic_xml_names_under_an_unrelated_namespace(*, namespace: str) -> str:
    """The reproduction: an unrelated format's namespace on the schema's document element.

    ``<database xmlns="...">`` wrapping the four filled ``<type>`` elements
    above. A document that declares a namespace which is **not** the Gramps one
    has named a different format, so the four generic names inside it are as
    ordinary as they are in the bare reproduction.

    The namespace is passed in rather than written here, exactly as
    ``notes_inside_a_container`` takes one: what it names does not matter, only
    that it is not the value the schema fixes.
    """
    return _element(
        "database",
        attributes='xmlns="' + namespace + '"',
        body="\n" + gramps_generic_xml_names(),
    )


def generic_xml_names_under_an_unrelated_doctype(*, identifier: str) -> str:
    """The same reproduction, spelled as a doctype naming an unrelated identifier.

    A doctype's ``Name`` is the document element, so a document declaring one
    named ``database`` is not thereby a Gramps document: the identifier beside
    it is what says which format, and this one names another.

    ⚠️ **``<!DOCTYPE`` is assembled**, like every other marker-shaped string in
    this module: written whole beside four filled containers it would be a
    marker in a tracked file rather than a fixture.
    """
    opening = "<!DOC" + "TYPE database SYSTEM " + '"' + identifier + '">'
    return opening + "\n" + gramps_generic_xml_names()


def unrelated_xml_document() -> str:
    """A build manifest: a file, its status, a description and a type.

    The second reproduction, and the one that shows the problem is not about
    ``<type>`` in particular. Not one of these four spellings is a Gramps word;
    every one of them is a row the schema derivation added.
    """
    fields = (
        ("file", "quarterly-rollup.csv"),
        ("status", "complete"),
        ("description", "regenerated nightly from the ledger export"),
        ("type", "scheduled"),
    )
    return "\n".join(_element(name, body=value) for name, value in fields) + "\n"


def gramps_researcher_block() -> str:
    """The researcher block: a name and a home address, invented.

    ⭐ **This is the accepted COST of the gate, not a false positive.** Every
    spelling in it -- ``resname``, ``rescity``, ``respostal`` -- is a row the
    derivation added, so quoted without its marker it is no longer caught. The
    number is measured and recorded in CONTRIBUTING rather than argued.
    """
    return _element(
        "researcher",
        body=(
            _element("resname", body="Elowen Ashenmoor")
            + _element("rescity", body="Thornwick")
            + _element("respostal", body="ZX1")
        ),
    )


def gramps_events_block() -> str:
    """Two events, each with a type and a description.

    The second half of the residual, and it takes TWO events: one event is two
    filled structural elements and scores 2, which is below the threshold and so
    was never a finding to lose. Assembled from the count rather than written
    twice, so the reason the count is two stays visible.
    """
    event = _element(
        "event",
        body=_element("type", body="Birth") + _element("description", body="parish register"),
    )
    return _element("events", body=event * 2)


def utf16le_gedcom_bytes() -> bytes:
    """A GEDCOM saved as BOM-less UTF-16LE.

    Every byte of this is accepted by the UTF-8 decoder -- the interleaved NULs
    decode to U+0000 -- so decodability proves nothing. It is also why none of
    the line-anchored GEDCOM signatures match it.
    """
    return gedcom_document().encode("utf-16-le")


def gedcom_x_json() -> str:
    """A GEDCOM X document: a real, current genealogy format, carried in JSON.

    It matches no GEDCOM or Gramps XML signature, which is the point: the guard
    cannot recognise every genealogy format that exists, so it must not treat
    "I did not recognise it" as "it is safe".

    Assembled, like every other builder here. It was a literal until the guard
    gained a property for this format, at which point this module reported
    itself -- the fifth time the assemble-at-runtime rule has been enforced by
    the guard rather than remembered by anybody.
    """
    # The KEYS are assembled too, not merely the structure. Serialising a
    # literal dict would leave every key-and-value pair sitting in this file in
    # exactly the shape the property matches.
    full_text = "full" + "Text"
    name_forms = "name" + "Forms"
    names = "name" + "s"
    document = {
        "person" + "s": [{"id": "p1", names: [{name_forms: [{full_text: "Quorvane Ashenmoor"}]}]}]
    }
    return json.dumps(document, separators=(",", ":")) + "\n"


def sqlite_bytes() -> bytes:
    """The first page of a SQLite database: magic header plus filler."""
    return b"SQLite format 3" + bytes(1) + bytes(496)


def unclassifiable_bytes() -> bytes:
    """Bytes that are neither valid UTF-8 nor any format the guard can name."""
    return bytes(range(200, 256)) * 4


def extended_unc_path(host: str, *parts: str) -> str:
    """The extended-length UNC spelling: the prefix, the marker, then the path."""
    return (
        (_BACKSLASH * 2)
        + "?"
        + _BACKSLASH
        + "UNC"
        + _BACKSLASH
        + host
        + _BACKSLASH
        + _BACKSLASH.join(parts)
    )


def extended_windows_path(*parts: str, drive: str = "C") -> str:
    """The extended-length drive spelling: the prefix, then a drive path."""
    return (_BACKSLASH * 2) + "?" + _BACKSLASH + drive + ":" + _BACKSLASH + _BACKSLASH.join(parts)


def bare_named_home_path(account: str) -> str:
    """A home directory named by its account and nothing else.

    A complete, valid home path on its own -- and the whole payload, because
    the account name is what identifies a person. Nothing follows it, which is
    exactly why the shape detector could not see one.
    """
    return "~" + account


def named_home_path(account: str, *parts: str) -> str:
    """The tilde spelling of a home directory: an account name, then a path.

    Assembled like everything else here. The account name is the payload: it
    identifies a person exactly as the home directory it stands for does.
    """
    return bare_named_home_path(account) + _SLASH + _SLASH.join(parts)


def repeated_separators(text: str) -> str:
    """``text`` with every separator written twice.

    A run of separators is the same separator: nothing sits between them, and
    the empty string they enclose is not a component. Every filesystem and
    every path library reads both spellings as one path, so a rule that judges
    the spelling disagrees with itself about which path it was given.

    Both spellings are doubled, because a path carries one or the other and a
    builder that handled only the separator this project types most would be
    the partial application this module keeps being fixed for.
    """
    for separator in (_SLASH, _BACKSLASH):
        text = text.replace(separator, separator * 2)
    return text


# A run long enough that no bounded quantifier written by accident admits it.
# The production rule is "one or more" with no upper bound; the ways that get
# narrowed are small numbers -- a fixed pair, or a run of two to three. This is
# past all of them, and short enough that the cost of matching over it stays
# flat.
LONG_SEPARATOR_RUN = 17


def separator_positions(text: str) -> int:
    """How many separator positions ``text`` has: one fewer than its parts."""
    return len(text.split(_SLASH)) - 1


def separator_run_at(text: str, position: int, length: int) -> str:
    """``text`` with one separator position written as a run of ``length``.

    Every other position stays single, and that is what makes it linear. The
    cross-product below is exponential in the number of separators, so a long
    run is reached one position at a time rather than by widening the product.

    ``position`` indexes the separators of ``text``, not its characters.
    """
    lengths = [1] * separator_positions(text)
    lengths[position] = length
    parts = text.split(_SLASH)
    return parts[0] + "".join(
        _SLASH * count + part for count, part in zip(lengths, parts[1:], strict=True)
    )


def every_separator_run_spelling(
    text: str, *, upto: int = 3, long_run: int = LONG_SEPARATOR_RUN
) -> list[str]:
    """Every way ``text`` can be written by repeating its separators.

    Each separator independently written once, twice, ... ``upto`` times, so
    the result covers the mixed spellings a hand-written list never does --
    a doubled separator in one position and a single one in the next. That
    half is a CROSS-PRODUCT, exponential in the number of separators, which is
    why its bound is small and stays small: raising it buys a slightly larger
    finite number and multiplies the cost of every caller by it.

    ``long_run`` is the other half, and it is added LINEARLY -- one spelling
    per separator position, that position written long and the rest single. A
    sample that stops at three is satisfied by a fold that stops at three, so
    short runs alone cannot speak for a rule with no upper bound; a long run at
    each position in turn costs ``positions`` extra cases rather than
    ``upto ** positions``. What it does not reach is several long runs at once,
    which makes this half a sample and is recorded as one where the criterion
    is stated.

    Derived from ``text``, which is the point of it. The finding this exists
    for was a rule proved against three named examples; three named examples
    are satisfied by three special cases, and walking the values the code
    itself holds is not.

    Both halves of B8 read this function -- the property and its negative
    control -- so a spelling added here reaches both by construction rather
    than by being remembered twice.
    """
    parts = text.split(_SLASH)
    spellings = {text}
    for counts in itertools.product(range(1, upto + 1), repeat=len(parts) - 1):
        spellings.add(
            parts[0]
            + "".join(_SLASH * count + part for count, part in zip(counts, parts[1:], strict=True))
        )
    for position in range(separator_positions(text)):
        spellings.add(separator_run_at(text, position, long_run))
    return sorted(spellings)


def json_escaped(text: str) -> str:
    """``text`` with every separator written as JSON's escaped solidus.

    Legal JSON and semantically identical to the unescaped form -- which is
    the point: it decodes to the same path a reader sees.
    """
    return text.replace(_SLASH, _BACKSLASH + _SLASH)


def prose_describing_json_keys_with_escaped_quotes() -> str:
    """A document *about* GEDCOM X whose quotes are written as escapes.

    Every quote here is a six-character escape sitting inside one string
    value, so the document holds exactly one member name -- the one describing
    it -- and no genealogy structure at all. Decoding the escapes without JSON
    context turns prose inside a single string into four apparent structural
    keys.

    Keys assembled at runtime, like every builder here: written whole they
    would be four real structural keys in a tracked file.
    """
    quote = _BACKSLASH + "u" + format(ord('"'), "04x")
    keys = ("person" + "s", "name" + "s", "fact" + "s", "note" + "s")
    named = " and ".join(f"{quote}{key}{quote}:" for key in keys)
    return '{"descri' + 'ption":"GEDCOM X uses ' + named + ' keys"}'


def unicode_escaped_key(document: str, key: str) -> str:
    """``document`` with the first letter of ``key`` written as an escape.

    JSON member names may be spelled with escapes; the parsed object is
    identical. One letter is enough to prove the point and keeps the rest of
    the document readable.
    """
    escaped = _BACKSLASH + "u" + format(ord(key[0]), "04x") + key[1:]
    return document.replace('"' + key + '"', '"' + escaped + '"')


# ---------------------------------------------------------------------------
# Serialized spelling versus logical value.
#
# One logical string has many legal serializations, and they are different
# lengths. Everything below builds the SAME value in several spellings, so a
# rule that measures the spelling instead of the value disagrees with itself.
# ---------------------------------------------------------------------------


def json_string_spellings(value: str) -> dict[str, str]:
    """Legal JSON string bodies for ``value``, keyed by how they are spelled.

    Every entry parses to ``value`` exactly. Their lengths differ by up to six
    to one, which is the whole point: a floor measuring the body rather than
    what it denotes gets a different answer from each of them.

    A bare quote is absent deliberately -- it is not legal inside a JSON string
    literal, so the two escaped spellings are the entire set for that
    character, and they still have to agree with each other.
    """
    escapable = '"' + _BACKSLASH + _SLASH
    spellings: dict[str, str] = {}
    if not any(character in '"' + _BACKSLASH for character in value):
        spellings["as written"] = value
    spellings["as a unicode escape"] = "".join(
        _BACKSLASH + "u" + format(ord(character), "04x") for character in value
    )
    if all(character in escapable for character in value):
        spellings["as a short escape"] = "".join(_BACKSLASH + character for character in value)
    return spellings


def xml_content_spellings(value: str) -> dict[str, str]:
    """Legal XML element content for ``value``, keyed by how it is spelled.

    The mirror of ``json_string_spellings`` for the other format. A bare ``<``
    or ``&`` is absent for the same reason a bare quote is absent there: not
    legal as content, so the references are the whole set for those characters.
    """
    predefined = {"&": "amp", "<": "lt", ">": "gt", '"': "quot", "'": "apos"}
    spellings: dict[str, str] = {}
    if not any(character in "<&" for character in value):
        spellings["as written"] = value
    if all(character in predefined for character in value):
        spellings["as a named reference"] = "".join(
            "&" + predefined[character] + ";" for character in value
        )
    spellings["as a decimal reference"] = "".join("&#" + str(ord(c)) + ";" for c in value)
    spellings["as a hex reference"] = "".join("&#x" + format(ord(c), "x") + ";" for c in value)
    return spellings


def inside_a_cdata_section(body: str) -> str:
    """``body`` in a CDATA section, where XML interprets nothing.

    The section is not another spelling of ``body`` -- it is the one place
    ``body`` spells ITSELF. A reference written inside one denotes the
    characters it is written with rather than the character it would name
    outside, so this builder takes a serialization and makes it literal.
    """
    return "<![" + "CDATA[" + body + "]" + "]>"


def inside_a_comment(body: str) -> str:
    """``body`` in an XML comment, which is markup rather than character data."""
    return "<!--" + body + "-->"


def inside_a_processing_instruction(body: str) -> str:
    """``body`` in a processing instruction, which is markup like a comment."""
    return "<" + "?transcriber " + body + "?>"


def xml_markup_in_content(body: str) -> dict[str, str]:
    """``body`` as each kind of markup XML lets sit between an element's tags.

    The ``content`` production is ``CharData? ((element | Reference | CDSect |
    PI | Comment) CharData?)*``. Of the members that are not elements or
    references, these three are what a document actually writes -- and all
    three interrupt character data without ending the element.

    Returned as a table so the tests walk every member rather than naming the
    one a reviewer happened to construct. A rule proved for one of these is
    this module's recurring defect: agreed, then applied in some of the places
    it holds.
    """
    return {"a CDATA section": inside_a_cdata_section(body), **xml_markup_denoting_nothing(body)}


def xml_markup_denoting_nothing(body: str) -> dict[str, str]:
    """The members of that table whose content is not character data.

    A CDATA section is absent, and its absence is the whole distinction: it
    denotes what it contains, so an element holding one holds that many
    characters of prose. A comment and a processing instruction denote no
    characters at all, which is why the two tables are not interchangeable and
    why the tests that ask *what the content is worth* take this one.
    """
    return {
        "a comment": inside_a_comment(body),
        "a processing instruction": inside_a_processing_instruction(body),
    }


def gramps_note_interrupted_by(markup: str = "") -> str:
    """A filled prose element carrying a life, with ``markup`` inside its text.

    ``markup`` empty is the uninterrupted control, so the assertion can be
    AGREEMENT between the spellings rather than "the interrupted one is
    caught". The second is satisfied by a special case for whichever
    interruption was named; the first is only satisfied by stating the rule.
    """
    head, tail = _BIOGRAPHY.split(" in ", 1)
    return _element("te" + "xt", body=head + " " + markup + " in " + tail)


def gramps_prose_holding_only(markup: str, *, copies: int = 1) -> str:
    """``copies`` prose elements whose entire content is ``markup``.

    No character data at all: the element is filled, and what fills it denotes
    nothing. What this is worth is the decision recorded in CONTRIBUTING --
    the same as any other short note, which is why ``copies`` is a parameter.
    """
    return _element("te" + "xt", body=markup) * copies


def labelled_diagram_holding(markup: str) -> str:
    """A chart whose one short label also carries ``markup``.

    The false-positive side. A label is a label whatever markup sits beside it,
    and it is inside its drawing, which is the container the discriminator asks
    about.
    """
    return _element(
        "svg", body=_element("te" + "xt", attributes='x="0" y="9"', body="0.5" + markup)
    )


def gedcom_x_notes_holding(body: str, *, copies: int = 2) -> str:
    """``copies`` GEDCOM X notes whose string body is written exactly as given.

    Built by hand rather than through ``json.dumps``, because the body is a
    *serialization* already and re-encoding it would escape its backslashes.
    Keys assembled, like every builder here.
    """
    notes = ",".join("{" + '"te' + 'xt":"' + body + '"}' for _ in range(copies))
    return '{"no' + 'tes":[' + notes + "]}"


def gramps_notes_holding(body: str, *, copies: int = 2) -> str:
    """``copies`` Gramps prose elements whose content is written exactly as given."""
    return "".join(_element("te" + "xt", body=body) for _ in range(copies))


def gedcom_x_biography_behind_an_escaped_quote() -> str:
    """A whole life in a note, with the note's own text quoted.

    An escaped quote is ordinary JSON and ordinary writing -- somebody quoting
    the register entry they transcribed. A capture that stops at the first
    quote it sees, rather than at the first UNESCAPED one, measures this whole
    biography as two characters.
    """
    quoted = _BACKSLASH + '"' + _BIOGRAPHY + _BACKSLASH + '"'
    return '{"no' + 'tes":[{"te' + 'xt":"' + quoted + '"}]}'


def gedcom_x_caption_spelled_with_escapes() -> str:
    """A four-character caption whose every character is a six-character escape.

    The other direction of the same defect: nothing here is prose, but the
    serialization is twenty-four characters long and a floor measuring it
    reports an ordinary caption as a family tree.
    """
    caption = "".join(_BACKSLASH + "u" + format(ord("<"), "04x") for _ in range(4))
    return '{"person' + 's":[],"no' + 'te":"' + caption + '"}'


def gramps_caption_spelled_with_character_references() -> str:
    """The XML spelling of the same shape: a short caption written long.

    A character reference is always longer than the character it stands for,
    so this is the false-positive direction only -- but it is the identical
    rule reading the identical serialization, in the format the floor was
    originally measured in.
    """
    return _element("te" + "xt", body="&amp;" * 4)


# ---------------------------------------------------------------------------
# A Gramps XML export, assembled -- what ``core.people`` reads
#
# ⚠️ **The whole document is built from ``_element`` for the reason at the top
# of this module, and the reason bites harder here than anywhere else.** A
# committed ``.gramps`` fixture carries a ``<database ... gramps...>`` line that
# trips ``_GENEALOGY_TEXT_SIGNATURES`` outright, so it would be a guaranteed
# finding and a red build with no way to fix it but to weaken the guard.
#
# The builders below take every field, so a test names the one shape it is
# about instead of reading a fixed cast and hoping the case it needs is in it.
# ---------------------------------------------------------------------------


def gramps_namespace(version: str = GRAMPS_XML_VERSION) -> str:
    """The declared namespace for one schema version, assembled.

    ⚠️ **Takes the version as an argument on purpose.** The reader must match on
    LOCAL NAME, so a document written by a different Gramps has to read the same
    -- and a test can only assert that if it can produce one.
    """
    return "http:" + "//gramps-project" + ".org/xml/" + version + _SLASH


def gramps_dateval(val: str, *, quality: str = "") -> str:
    """``<dateval val="..."/>`` -- one point in time, the commonest shape."""
    attributes = f'val="{val}"' + (f' quality="{quality}"' if quality else "")
    return _element("dateval", attributes=attributes, empty=True)


def gramps_daterange(start: str, stop: str) -> str:
    """``<daterange start="..." stop="..."/>`` -- somewhere between two dates."""
    return _element("daterange", attributes=f'start="{start}" stop="{stop}"', empty=True)


def gramps_datespan(start: str, stop: str) -> str:
    """``<datespan start="..." stop="..."/>`` -- an interval, not a point."""
    return _element("datespan", attributes=f'start="{start}" stop="{stop}"', empty=True)


def gramps_datestr(val: str) -> str:
    """``<datestr val="..."/>`` -- free text nobody could parse into a date."""
    return _element("datestr", attributes=f'val="{val}"', empty=True)


def gramps_event(
    *, handle: str, gramps_id: str = "", event_type: str = "Birth", date: str = ""
) -> str:
    """One ``<event>``, with whichever date shape the caller passed, or none."""
    attributes = f'handle="_{handle}"' + (f' id="{gramps_id}"' if gramps_id else "")
    return _element(
        "event",
        attributes=attributes,
        body=_element("type", body=event_type) + date,
    )


def gramps_name(
    *, first: str, surname: str, alt: bool = False, name_type: str = "Birth Name"
) -> str:
    """One ``<name>``. ``alt`` writes the ``alt="1"`` a display name never carries."""
    attributes = f'type="{name_type}"' + (' alt="1"' if alt else "")
    return _element(
        "name",
        attributes=attributes,
        body=_element("first", body=first) + _element("surname", body=surname),
    )


def gramps_person(
    *,
    handle: str,
    gramps_id: str,
    names: str = "",
    private: str = "",
    event_handles: tuple[tuple[str, str], ...] = (),
) -> str:
    """One ``<person>``, with its name blocks and its event references.

    ``private`` is written verbatim as the ``priv`` attribute when non-empty, so
    a test can produce the unstated case, the stated cases, and a value the
    schema does not declare. ``event_handles`` is ``(handle, role)`` pairs.
    """
    attributes = f'handle="_{handle}" id="{gramps_id}"'
    if private:
        attributes += f' priv="{private}"'
    references = "".join(
        _element(
            "eventref",
            attributes=f'hlink="_{event_handle}"' + (f' role="{role}"' if role else ""),
            empty=True,
        )
        for event_handle, role in event_handles
    )
    return _element(
        "person", attributes=attributes, body=_element("gender", body="U") + names + references
    )


def gramps_export_document(
    *, people: str = "", events: str = "", version: str = GRAMPS_XML_VERSION
) -> str:
    """A whole export: prolog, namespace, header, then the two collections.

    ⚠️ **``<events>`` is written AFTER ``<people>``**, which is the opposite of
    what a real export does, and deliberately: a reader that resolves an event
    reference as it meets it works on Gramps' ordering and fails on this one.
    Order-independence is the property, so the fixture is the hostile order.
    """
    header = _element(
        "header",
        body=_element("created", attributes='date="2026-08-17" version="6.0.8"', empty=True)
        + _element("researcher"),
    )
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _element(
        "database",
        attributes=f'xmlns="{gramps_namespace(version)}"',
        body=header + _element("people", body=people) + _element("events", body=events),
    )
