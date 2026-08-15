r"""Derive the preview guard's unrenderable class from the published UCD.

Run this by hand, never in CI. It reads two artifacts that were fetched
**separately** and prints ``_unrenderable.py`` on standard output:

    python scripts/derive_unrenderable.py \
        <extracted/DerivedGeneralCategory.txt> <DerivedCoreProperties.txt> \
        > src/gramps_live_api/core/_unrenderable.py

⚠️ **On Windows, redirect through ``cmd /c``.** PowerShell's ``>`` rewrites the
stream with a BOM and CRLF line endings, so a *correct* re-derivation fails the
byte-for-byte check below and looks like a defect. That is issue #47, stated
here because this script is the second thing it can bite.

⚠️ **CI never fetches anything, and neither does this script.** The network
step is a human one, recorded in the derivation note with each artifact's
digest, so the offline suite can assert the committed table against the running
interpreter's own database without ever leaving the machine.

⚠️ **The output is the committed file, byte for byte.** Verification is
re-fetch, compare digest, re-run, and diff -- so nothing here may vary between
runs over the same inputs. In particular this emits **no timestamp**: a fetch
date is a fact about a fetch rather than about a standard, and stamping one
here would make every re-derivation differ from the file it is checking.

⚠️ **Two derived files, not the primary ``UnicodeData.txt``, and that is a
decision rather than a convenience.** ``UnicodeData.txt`` declares no version
anywhere in its content -- so the version this table claims would be attested
only by the URL somebody typed -- and it expresses ``Co`` and ``Cs`` **only** as
``<..., First>`` / ``<..., Last>`` row pairs, which a parser that does not pair
them drops silently: about 139,500 of the class's 139,700-odd code points, with
the output still looking like a working derivation. That is a check that cannot
see what it claims to check, and it is the failure this module has already been
bitten by. Both files read here state their own version in their first line and
write every range out in full, in one shape, so one parser reads both.

Stdlib only, deliberately: a build input this repository cannot audit is worse
than a build step somebody has to run by hand.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# What the class is, stated as the two published facts it is made of.
#
# ⚠️ **These are the WANTED sets, and there is no exclusion clause anywhere.**
# `Cn` is stated explicitly in the general-category artifact -- it is not
# absent from it -- so what keeps unassigned code points out of the table is
# that this tuple does not name the category, and nothing downstream has to
# remember a `!= "Cn"`. The same structure keeps every readable category out.
#
# The two sets OVERLAP and neither contains the other, which is why both are
# read. Default-ignorable reaches outside the "Other" group -- U+034F is `Mn`,
# U+115F and U+1160 are `Lo` -- and the group reaches outside default-ignorable,
# where the controls, the surrogates and the private-use areas live.
# ---------------------------------------------------------------------------

UNRENDERABLE_CATEGORIES: tuple[str, ...] = ("Cc", "Cf", "Co", "Cs")
"""The General_Category values the class holds, from UAX #44."""

DEFAULT_IGNORABLE = "Default_Ignorable_Code_Point"
"""The derived core property that carries the invisible characters outside those."""

_WANTED_CATEGORY_ROWS = frozenset((category,) for category in UNRENDERABLE_CATEGORIES)
"""A general-category row is wanted when its one field is a wanted category."""

_VERSION_HEADER = re.compile(r"^#\s*[A-Za-z]+-(?P<version>\d+\.\d+\.\d+)\.txt\s*$")
"""The first line of both artifacts, which is where each declares its version."""

# One data line of either file. UAX #44 section 4.2.1: a range is one code point
# or ``first..last``, and the fields that follow are separated by semicolons --
# one field for a binary property or a general category, two for an enumerated
# property such as ``InCB; Linker``, which DerivedCoreProperties.txt does write.
# A parser accepting exactly one field refuses a correct artifact, so the fields
# are read as written and the selection happens afterwards.
_ROW = re.compile(
    r"^(?P<first>[0-9A-F]{4,6})(?:\.\.(?P<last>[0-9A-F]{4,6}))?"
    r"\s*;\s*(?P<fields>\w+(?:\s*;\s*\w+)*)\s*$"
)

_FIELD_SEPARATOR = ";"
_COMMENT = "#"


def declared_version(text: str, source: str) -> str:
    """The Unicode version ``source`` states in its own first line.

    ⚠️ **Read from the artifact, never from where it was fetched.** A version
    the note records because somebody typed it into a URL is provenance in name
    only, and choosing files that declare their own is most of why these two are
    the sources.
    """
    first_line = text.split("\n", 1)[0]
    found = _VERSION_HEADER.match(first_line)
    if found is None:
        raise SystemExit(
            f"{source} declares no Unicode version in its first line: {first_line.strip()!r} "
            "-- the derivation would record a version nothing in the artifact states"
        )
    return found.group("version")


def agreed_version(artifacts: list[tuple[str, str]]) -> str:
    """The one version every artifact declares, or a refusal naming what each said.

    ⚠️ **Two files from different releases produce a table that is a fact about
    neither**, and it is an easy mistake to make -- one artifact refetched and
    the other not. It leaves no trace in the output, so it is refused here
    rather than reported anywhere.
    """
    declared = [(source, declared_version(text, source)) for source, text in artifacts]
    if len({version for _, version in declared}) != 1:
        spelled = ", ".join(f"{source} declares {version}" for source, version in declared)
        raise SystemExit(
            f"the artifacts are from different releases ({spelled}); a class derived from "
            "both would be a fact about neither"
        )
    return declared[0][1]


def rows(text: str, source: str) -> list[tuple[int, int, tuple[str, ...]]]:
    """Every data line of ``source`` as ``(first, last, fields)``, in file order.

    ⚠️ **A line this cannot read is a failure, not a shortfall.** A range
    silently skipped is a hole in the class that the re-derivation diff cannot
    show -- the fabricated row would be visible there and the omission is not --
    so it stops the derivation and quotes the line somebody has to go and look
    at. That is the same guarantee C1's parser makes, for the same reason.

    Comments and blank lines are skipped rather than read. The ``@missing``
    annotations UAX #44 defines are comments, so they are covered by that.
    """
    read: list[tuple[int, int, tuple[str, ...]]] = []
    for line in text.split("\n"):
        content = line.split(_COMMENT, 1)[0].strip()
        if not content:
            continue
        found = _ROW.match(content)
        if found is None:
            raise SystemExit(
                f"unread line in {source}: {line.strip()!r} "
                "-- the derivation would silently omit it"
            )
        first = int(found.group("first"), 16)
        last = found.group("last")
        read.append(
            (
                first,
                first if last is None else int(last, 16),
                tuple(field.strip() for field in found.group("fields").split(_FIELD_SEPARATOR)),
            )
        )
    return read


def labelled(
    general_category: list[tuple[int, int, tuple[str, ...]]],
    core_properties: list[tuple[int, int, tuple[str, ...]]],
) -> dict[int, str]:
    """Every code point in the class, with the published fact that put it there.

    ⚠️ **The general category wins where the two sources overlap**, and the
    precedence is written down because the label is what a refusal message
    names. Most format characters are both ``Cf`` and default-ignorable; naming
    the category is the more specific answer and the one a reader can look up.
    Deterministic either way, which is what the byte-for-byte reproduction of
    this table rests on.

    Expanded to individual code points rather than kept as intervals: about
    140,000 dictionary entries is nothing a hand-run script needs to be clever
    about, and interval arithmetic is where an off-by-one hides.
    """
    labels: dict[int, str] = {}
    for first, last, fields in general_category:
        if fields not in _WANTED_CATEGORY_ROWS:
            continue
        for code_point in range(first, last + 1):
            labels[code_point] = fields[0]
    for first, last, fields in core_properties:
        if fields != (DEFAULT_IGNORABLE,):
            continue
        for code_point in range(first, last + 1):
            labels.setdefault(code_point, DEFAULT_IGNORABLE)
    return labels


def runs(labels: dict[int, str]) -> list[tuple[int, int, str]]:
    """``labels`` as sorted inclusive ranges, coalesced only where the label agrees.

    Merging across labels would name the wrong published fact in a refusal, so
    a run ends at a gap **or** at a change of label.
    """
    found: list[tuple[int, int, str]] = []
    for code_point in sorted(labels):
        label = labels[code_point]
        if found and found[-1][2] == label and found[-1][1] == code_point - 1:
            found[-1] = (found[-1][0], code_point, label)
            continue
        found.append((code_point, code_point, label))
    return found


# ---------------------------------------------------------------------------
# Emitting the module.
# ---------------------------------------------------------------------------

_HEADER = '''"""The characters ``preview`` refuses, derived from the published UCD.

⚠️ **MACHINE-GENERATED. DO NOT HAND-EDIT.** Regenerate it with
``scripts/derive_unrenderable.py`` over artifacts matching the digests below,
and see the derivation note in ``docs`` for where each one comes from.

⚠️ **This module IS the class**, and ``schema.py`` imports it. That is a stated
deviation from the precedent this table follows, whose generated module nothing
imports: there the table was a checklist beside a hand-written weighting, and
duplicating it by hand was tractable. Here a hand-maintained copy would be the
thing the derivation exists to remove.

⚠️ **No fetch date is recorded here.** Verification is re-fetch, compare digest,
re-run, and diff against this file; a timestamp would make every such run differ
from the file it is checking. Dates belong to the note.
"""

from __future__ import annotations
'''


def quoted(value: str) -> str:
    """A string literal the formatter will leave alone."""
    return '"' + value + '"'


def emit(
    digests: list[tuple[str, str]],
    version: str,
    ranges: list[tuple[int, int, str]],
) -> str:
    """The whole generated module, formatted as the repository formats code."""
    lines = [_HEADER]

    lines.append("SOURCE_DIGESTS: tuple[tuple[str, str], ...] = (")
    for label, digest in digests:
        lines.append(f"    ({quoted(label)}, {quoted(digest)}),")
    lines.append(')\n"""Each source artifact and the SHA-256 it was read from."""\n')

    lines.append("UNICODE_VERSION: str = " + quoted(version))
    lines.append('"""The Unicode version both artifacts declare in their own first line.')
    lines.append("")
    lines.append("The class is a fact about THIS version of the standard and does not track a")
    lines.append("later one until somebody re-derives it. That is the cost of determinism, and")
    lines.append("it is recorded in the costs block the guard carries.")
    lines.append('"""\n')

    lines.append("UNRENDERABLE_RANGES: tuple[tuple[int, int, str], ...] = (")
    for first, last, label in ranges:
        lines.append(f"    (0x{first:04X}, 0x{last:04X}, {quoted(label)}),")
    lines.append(")")
    lines.append('"""Every inclusive range of the class, sorted, with what put it there.')
    lines.append("")
    lines.append("Non-overlapping, and no two adjacent ranges share a label -- which is what")
    lines.append("says the coalesce ran. The label is a General_Category value or the derived")
    lines.append("core property, and it is what a refusal message names.")
    lines.append('"""')
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(
            "usage: derive_unrenderable.py <extracted/DerivedGeneralCategory.txt> "
            "<DerivedCoreProperties.txt>"
        )
    labels = ("general-category", "core-properties")
    raw = [Path(argument).read_bytes() for argument in argv]
    digests = [
        (label, hashlib.sha256(content).hexdigest())
        for label, content in zip(labels, raw, strict=True)
    ]
    texts = [content.decode("utf-8") for content in raw]
    version = agreed_version(list(zip(labels, texts, strict=True)))
    general_category, core_properties = (
        rows(text, label) for text, label in zip(texts, labels, strict=True)
    )

    sys.stdout.write(emit(digests, version, runs(labelled(general_category, core_properties))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
