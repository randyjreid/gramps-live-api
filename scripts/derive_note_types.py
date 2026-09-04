r"""Derive the frozen note-type table from an installed Gramps' own source.

Run this by hand, never in CI. It reads two files out of one **installation
root** and prints ``_note_types.py`` on standard output:

    python scripts/derive_note_types.py <installation root> \
        > src/gramps_live_api/core/_note_types.py

⚠️ **On Windows, redirect through ``cmd /c``.** PowerShell's ``>`` rewrites the
stream with a BOM and CRLF line endings, so a *correct* re-derivation fails the
byte-for-byte check and looks like a defect. That is issue #47, and this script
is the third thing it can bite.

⚠️ **TWO files, and that is not an implementation detail.** The rows come from
``gramps/gen/lib/notetype.py``; the version comes from ``gramps/version.py``,
which is a different file, and ``VERSION_TUPLE`` is not present in the first one
at all. A generator given only the rows file cannot derive the version it claims
to record, so it would have to carry a typed literal -- and a table regenerated
against a newer Gramps would then keep the old version while staying
byte-reproducible and passing every row check. **A provenance field that looks
derived and is actually typed is worse than no field**, because the next reader
trusts it.

⚠️ **This differs from the two existing frozen tables in one way worth stating.**
``_unrenderable.py`` and ``_specified_containers.py`` derive from *published
standards* fetched once by a human, and their verification is re-fetch, compare
digest, re-run, diff. This table's source is **a runtime installed on a
machine**: it varies per machine and CI has none at all. The pattern still
applies and the verification splits in two -- an offline test that the committed
table is internally consistent, and a Gramps-present test that it still matches
the installation, which skips where there is none.

⚠️ **The output is the committed file, byte for byte**, so nothing here may vary
between runs over the same input. In particular it emits **no timestamp**: a
derivation date is a fact about a run rather than about the runtime, and stamping
one would make every re-derivation differ from the file it is checking.

⛔ **It FAILS CLOSED.** Any element of either declared list that it cannot read
stops the run and names the line. Without this the whole scheme is decorative: a
parser that silently skips what it does not recognise emits a table short by
exactly the rows nobody thought about, and **every check downstream still
passes**, because the committed rows and the parsed rows dropped the same row.
The near-miss that proves it is recorded on the plan: a first pass with a regexp
for ``(NAME, _("Label"), "Key")`` returned 27 rows and looked complete, having
dropped ``TODO`` and ``LINK``, which are written with the two-argument
translation call.

⚠️ **A fixed expected count is not the guard either.** A later ``notetype.py``
adding a thirtieth row in an unrecognised shape leaves 29 parsed rows and passes
any ``== 29``. The guard is that **every element of both lists was understood**,
not that a remembered number came back.

⭐ **Read as SYNTAX rather than as text, using ``ast``.** The two shapes that have
already broken a parser which looked correct -- the two-argument translation call
and a constant written ``SOURCE_TEXT = 21  # ...`` -- are ordinary syntax and
awkward text. A regexp for either is a second grammar for Python, maintained
here; ``ast`` is the one the interpreter uses. Stdlib only, deliberately: a build
input this repository cannot audit is worse than a build step somebody has to run
by hand.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

INSTALLATION_FILES: tuple[tuple[str, str], ...] = (
    ("gramps-version", "gramps/version.py"),
    ("gramps-notetype", "gramps/gen/lib/notetype.py"),
)
"""Each file this reads, labelled, relative to the installation root.

⚠️ **Labels rather than the paths themselves in the committed table.** The table
is tracked content in a public repository, and the root it was read from is a
path on somebody's machine. The relative part is a fact about Gramps' layout and
is recorded here, where a reader looking for the file can find it.
"""

CLASS_NAME = "NoteType"
"""The class whose two lists are the whole vocabulary."""

REAL_LIST = "_DATAMAPREAL"
"""The rows Gramps offers a person in the ordinary way."""

IGNORED_LIST = "_DATAMAPIGNORE"
"""The rows ``get_ignore_list`` returns, offered only in their own object's tab."""

EXCLUDED_FROM_ACCEPTED: tuple[str, ...] = ("CUSTOM", "UNKNOWN")
"""The two rows of ``_DATAMAPREAL`` the accepted set is computed by REMOVING.

``CUSTOM`` is the door custom note types would come through and the owner has
ruled them out. ``UNKNOWN`` is not a filing decision at all: it is what Gramps
holds when it does not know, and a caller choosing it is asking for the absence
of a choice. ⭐ Neither is dropped from the table, only from the accepted set --
they are two of the nineteen names a lookup written slightly wrong would let
through, so a test that names them needs them present.
"""

TRANSLATION_CALL = "_"
"""What ``notetype.py`` binds ``glocale.translation.sgettext`` to.

⚠️ **Both arities are real.** ``_("Research")`` is the ordinary form and
``_("To Do", "notetype")`` is the disambiguating one, and the second is how
``TODO`` and ``LINK`` are written.
"""


def parsed(text: str, source: str) -> ast.Module:
    """``text`` as syntax, or a refusal naming the artifact.

    A file this interpreter cannot parse is not a file this can read rows out
    of, and guessing at the parts it could read is the fail-open shape the whole
    script is written against.
    """
    try:
        return ast.parse(text)
    except SyntaxError as failure:
        raise SystemExit(
            f"{source} is not readable as Python ({failure}) -- the derivation "
            "would silently omit everything it could not parse"
        ) from failure


def note_type_class(module: ast.Module, source: str) -> ast.ClassDef:
    """The ``NoteType`` class node, or a refusal."""
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == CLASS_NAME:
            return node
    raise SystemExit(f"{source} declares no {CLASS_NAME} class, so there is nothing to derive from")


def integer_constants(class_node: ast.ClassDef) -> dict[str, int]:
    """Every class attribute assigned a plain integer, by name.

    ⚠️ **Plain integers only, and the aliases are excluded by that rather than by
    name.** ``_CUSTOM = CUSTOM`` and ``_DEFAULT = GENERAL`` are assignments of a
    *name*, not of a literal, so they never enter this mapping and no row can
    resolve through one. That matters: ``_DEFAULT`` is an int at runtime and
    equals ``GENERAL``, and a scheme that admitted it would carry an undocumented
    alias for a real note type into the table.

    ``UNKNOWN = -1`` is a unary minus applied to a literal rather than a literal,
    and ``SOURCE_TEXT = 21  # ...`` carries a trailing comment. Both are ordinary
    syntax and both have broken a parser that read the assignment as text.
    """
    found: dict[str, int] = {}
    for node in class_node.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            found[target.id] = value
    return found


def declared_list(class_node: ast.ClassDef, name: str, source: str) -> list[ast.expr]:
    """The elements of one declared list, or a refusal naming the list.

    ⛔ **An absent list is refused rather than read as empty.**
    ``_DATAMAPIGNORE`` is 17 of the 29 rows and none of the accepted 10, so a
    rename would produce a table whose accepted set was still right and whose
    refusal list had quietly lost seventeen names.
    """
    for node in class_node.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            if not isinstance(node.value, ast.List):
                raise SystemExit(
                    f"{CLASS_NAME}.{name} in {source} is not a list, so the "
                    "derivation would silently omit every row it holds"
                )
            return list(node.value.elts)
    raise SystemExit(
        f"{source} declares no {CLASS_NAME}.{name}, so the derivation would "
        f"silently omit every row that list holds"
    )


def _translation_call(node: ast.expr) -> bool:
    """Is ``node`` a call to the translation function with string literals only?

    ⚠️ **One argument or two, and both are real.** A pattern written for the
    one-argument form skipped ``TODO`` and ``LINK`` entirely while the output
    still looked like a full enumeration.
    """
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != TRANSLATION_CALL:
        return False
    if node.keywords or len(node.args) not in (1, 2):
        return False
    return all(
        isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        for argument in node.args
    )


def row_of(
    element: ast.expr,
    constants: dict[str, int],
    lines: list[str],
    source: str,
    declared_in: str,
) -> tuple[str, int, str, str]:
    """One ``(NAME, _("Label"), "Key")`` element as a table row, or a refusal.

    ⛔ Every part is required to be the shape Gramps writes: a **declared class
    constant** rather than an inline integer, a **translation call** of one or
    two string literals, and a **string key**. Anything else stops the run.

    ⚠️ **The translated label is read and NOT carried into the table.** It is
    what Gramps shows in whatever language is loaded, so it is a fact about a
    locale rather than about the vocabulary. What is required of it is only that
    it be a translation call of literals, because that is what says the element
    is a row of this list rather than something else in the same list.
    """

    def refuse() -> SystemExit:
        line_number = getattr(element, "lineno", 0)
        quoted_line = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
        return SystemExit(
            f"unread element of {CLASS_NAME}.{declared_in} at line {line_number} of "
            f"{source}: {quoted_line!r} -- the derivation would silently omit it"
        )

    if not isinstance(element, ast.Tuple) or len(element.elts) != 3:
        raise refuse()
    attribute, translated, key = element.elts
    if not isinstance(attribute, ast.Name) or attribute.id not in constants:
        raise refuse()
    if not _translation_call(translated):
        raise refuse()
    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
        raise refuse()
    return (attribute.id, constants[attribute.id], key.value, declared_in)


def rows_of(text: str, source: str) -> list[tuple[str, int, str, str]]:
    """Every row of both lists, in declaration order, the real list first.

    That is ``_DATAMAP``'s own order, which is ``_DATAMAPREAL + _DATAMAPIGNORE``,
    and it is deterministic -- which is what the byte-for-byte reproduction of
    the committed table rests on.
    """
    class_node = note_type_class(parsed(text, source), source)
    constants = integer_constants(class_node)
    lines = text.splitlines()
    rows: list[tuple[str, int, str, str]] = []
    for declared_in in (REAL_LIST, IGNORED_LIST):
        for element in declared_list(class_node, declared_in, source):
            rows.append(row_of(element, constants, lines, source, declared_in))
    return rows


def version_of(text: str, source: str) -> tuple[tuple[int, ...], str]:
    """``(VERSION_TUPLE, the packaging string)`` from a ``version.py``.

    ⚠️ **``VERSION_TUPLE`` is what Gramps IS; ``VERSION`` is what built it.** An
    ordinary source install COMPUTES ``VERSION`` from the tuple, so there is no
    packaging string to record. The all-in-one build appends a second assignment
    at the end of the file overwriting it with its own string, and that string is
    a fact about an installer. Both are recorded, and neither is recoverable from
    the other.

    ⭐ **The packaging string is found by SHAPE, not by position**: it is the last
    ``VERSION`` assigned a string literal. A computed ``VERSION`` is an
    expression, so it never qualifies, and there is no rule here about which line
    of the file anything sits on.
    """
    version_tuple: tuple[int, ...] | None = None
    packaging = ""
    for node in parsed(text, source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == "VERSION_TUPLE":
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                value = None
            if not (
                isinstance(value, tuple)
                and value
                and all(isinstance(part, int) and not isinstance(part, bool) for part in value)
            ):
                raise SystemExit(
                    f"{source} declares a VERSION_TUPLE that is not a tuple of "
                    "integers, so the table would record a version derived from "
                    "nothing the file states"
                )
            version_tuple = tuple(value)
        if (
            target.id == "VERSION"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            packaging = node.value.value
    if version_tuple is None:
        raise SystemExit(
            f"{source} declares no VERSION_TUPLE, so the table would have to carry "
            "a typed literal -- a provenance field that looks derived and is "
            "actually typed is worse than no field"
        )
    return version_tuple, packaging


# ---------------------------------------------------------------------------
# Emitting the module.
# ---------------------------------------------------------------------------

_HEADER = '''"""The note types the installed Gramps declares, derived from its own source.

⚠️ **MACHINE-GENERATED. DO NOT HAND-EDIT.** Regenerate it with
``scripts/derive_note_types.py`` over an installation whose two files match the
digests below.

⚠️ **This module IS the vocabulary**, and both ``schema.py`` and the document
route import it. A hand-maintained copy would be the thing the derivation exists
to remove, and the ``TODO``/``LINK`` near-miss recorded on the plan is what a
hand-written list looks like when it is wrong: short by exactly the row nobody
thought about, and indistinguishable from a complete one.

⚠️ **Its source is a RUNTIME, not a published standard.** The two frozen tables
this follows derive from specifications a human fetched once, and their
verification is re-fetch, compare digest, re-run, diff. This one is derived from
a Gramps installed on a machine, so the verification splits in two: an offline
test that this file is internally consistent, and a Gramps-present test that it
still matches an installation, which SKIPS where there is none.

⚠️ **No derivation date is recorded here.** Verification is re-run and diff
against this file; a timestamp would make every such run differ from the file it
is checking.
"""

from __future__ import annotations
'''


def quoted(value: str) -> str:
    """A string literal the formatter will leave alone."""
    return '"' + value + '"'


def emit(
    digests: list[tuple[str, str]],
    version_tuple: tuple[int, ...],
    packaging: str,
    rows: list[tuple[str, int, str, str]],
) -> str:
    """The whole generated module, formatted as the repository formats code."""
    lines = [_HEADER]

    lines.append("SOURCE_DIGESTS: tuple[tuple[str, str], ...] = (")
    for label, digest in digests:
        lines.append(f"    ({quoted(label)}, {quoted(digest)}),")
    lines.append(")")
    lines.append('"""Each file this was derived from, and the SHA-256 it was read from.')
    lines.append("")
    lines.append("⚠️ **Two files, two digests.** The version is not in the file the rows come")
    lines.append("from, so a table claiming a provenance derived from one of them would be")
    lines.append("claiming something neither file states.")
    lines.append('"""\n')

    # ⚠️ **No trailing comma inside the parentheses**, and that is not cosmetic:
    # the formatter this repository runs treats a trailing comma as an
    # instruction to explode the literal over several lines, so emitting one
    # would make the committed table fail ``ruff format --check`` while being
    # a perfectly correct derivation.
    # A one-part tuple is the one place the comma is syntax rather than a
    # formatting hint, and the formatter knows that.
    written = ", ".join(str(part) for part in version_tuple)
    if len(version_tuple) == 1:
        written += ","
    lines.append(f"GRAMPS_VERSION_TUPLE: tuple[int, ...] = ({written})")
    lines.append('"""What the installation this was derived from says Gramps IS.')
    lines.append("")
    lines.append("Read from ``VERSION_TUPLE``, never from ``VERSION``: the all-in-one build")
    lines.append("appends a second assignment overwriting ``VERSION`` with its own packaging")
    lines.append("string, so that name says what the installer called the build.")
    lines.append('"""\n')

    lines.append(f"GRAMPS_PACKAGING_VERSION: str = {quoted(packaging)}")
    lines.append('"""What the installer called the build, or empty where nothing states one.')
    lines.append("")
    lines.append("A fact about a package rather than about Gramps, recorded beside the tuple")
    lines.append("because the two are not recoverable from each other.")
    lines.append('"""\n')

    lines.append(f"REAL_LIST: str = {quoted(REAL_LIST)}")
    lines.append('"""The list Gramps offers in the ordinary way, wherever a note sits."""\n')

    lines.append(f"IGNORED_LIST: str = {quoted(IGNORED_LIST)}")
    lines.append('"""The list ``get_ignore_list`` returns: offered in its own object\'s tab."""\n')

    lines.append("EXCLUDED_FROM_ACCEPTED: tuple[str, ...] = (")
    for name in EXCLUDED_FROM_ACCEPTED:
        lines.append(f"    {quoted(name)},")
    lines.append(")")
    lines.append('"""The two rows of the real list that are carried and NOT accepted.')
    lines.append("")
    lines.append("``CUSTOM`` is the door custom note types would come through, and they are")
    lines.append("ruled out. ``UNKNOWN`` is what Gramps holds when it does not know, so a")
    lines.append("caller choosing it is asking for the absence of a choice. Both stay in the")
    lines.append("table: they are two of the names a lookup written slightly wrong would let")
    lines.append("through, and a test that names them needs them here to name.")
    lines.append('"""\n')

    lines.append("NOTE_TYPE_ROWS: tuple[tuple[str, int, str, str], ...] = (")
    for attribute, value, key, declared_in in rows:
        lines.append(f"    ({quoted(attribute)}, {value}, {quoted(key)}, {quoted(declared_in)}),")
    lines.append(")")
    lines.append('"""Every row of both lists: attribute name, integer, key string, which list.')
    lines.append("")
    lines.append("In ``_DATAMAP``'s own order, which is the real list then the ignored one.")
    lines.append("")
    lines.append("⚠️ **The key strings are recorded and used by nothing**, deliberately. They")
    lines.append("are how Gramps spells these in XML and in its own interface, and they are")
    lines.append("NOT the attribute names -- ``SOURCE_TEXT`` is ``Source text``, ``TODO`` is")
    lines.append("``To Do``, ``PERSONNAME`` is ``Name Note`` -- so a later reader comparing")
    lines.append("the two vocabularies should not have to derive them again.")
    lines.append("")
    lines.append("⚠️ **The integers are recorded and used by nothing either.** Gramps'")
    lines.append("numbering is an implementation detail, and every lookup in this repository")
    lines.append("goes through ``getattr`` on the attribute name so that a renumbering cannot")
    lines.append("silently file a note under the wrong type.")
    lines.append('"""\n')

    lines.append("ACCEPTED_NOTE_TYPES: frozenset[str] = frozenset(")
    lines.append("    attribute.lower()")
    lines.append("    for attribute, _value, _key, declared_in in NOTE_TYPE_ROWS")
    lines.append("    if declared_in == REAL_LIST and attribute not in EXCLUDED_FROM_ACCEPTED")
    lines.append(")")
    lines.append('"""The wire vocabulary: what a caller may ask a note to be.')
    lines.append("")
    lines.append("⭐ **COMPUTED from the rows above, never listed**, so it cannot drift from")
    lines.append("them. A row moved between the two lists moves in or out of this set with")
    lines.append("nothing to remember.")
    lines.append("")
    lines.append("The wire name is the **lowercased attribute name**, because that is what")
    lines.append("``getattr`` resolves on Gramps' own class and what this repository's other")
    lines.append("type vocabularies already use.")
    lines.append('"""')
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: derive_note_types.py <gramps installation root>")
    root = Path(argv[0])
    raw = []
    for label, relative in INSTALLATION_FILES:
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"the installation holds no {relative}, so there is nothing to derive")
        raw.append((label, relative, path.read_bytes()))

    digests = [(label, hashlib.sha256(content).hexdigest()) for label, _, content in raw]
    texts = {label: content.decode("utf-8") for label, _, content in raw}

    version_tuple, packaging = version_of(texts["gramps-version"], "gramps-version")
    rows = rows_of(texts["gramps-notetype"], "gramps-notetype")

    sys.stdout.write(emit(digests, version_tuple, packaging, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
