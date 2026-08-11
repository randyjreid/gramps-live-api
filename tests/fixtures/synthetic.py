"""Builders for strings that *look like* the things the PII guard rejects.

Nothing in this module is a literal absolute path or genealogy record. Every
such value is assembled at runtime from harmless parts, because
the guard runs over this whole checkout in CI: a committed literal would be a
genuine finding, and suppressing it would mean weakening the guard to let the
tests pass.

All names used here are invented. See ``tests/fixtures/__init__``.
"""

from __future__ import annotations

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


_BIOGRAPHY = "Elowen Ashenmoor, born 2 April 1893 in Thornwick, wheelwright, died 1961."


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
        _element("note", body=_element("text", body=value))
        for value in ("Elowen Ashenmoor", "2 April 1893", "Thornwick")
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


def worded_diagram() -> str:
    """A chart whose labels are words rather than numbers.

    The shape that returns if the prose floor is lowered instead of the
    positioned-text discriminator being used.
    """
    labels = "".join(
        _element("text", attributes=f'x="0" y="{offset}"', body=value)
        for offset, value in ((9, "Temperature"), (18, "Pressure over time"))
    )
    return _element("svg", body=labels)


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


def named_home_path(account: str, *parts: str) -> str:
    """The tilde spelling of a home directory: an account name, then a path.

    Assembled like everything else here. The account name is the payload: it
    identifies a person exactly as the home directory it stands for does.
    """
    return "~" + account + _SLASH + _SLASH.join(parts)


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
