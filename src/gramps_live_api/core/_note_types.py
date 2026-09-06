"""The note types the installed Gramps declares, derived from its own source.

⚠️ **MACHINE-GENERATED. DO NOT HAND-EDIT.** Regenerate it with
``scripts/derive_note_types.py`` over an installation whose two files match the
digests below.

⚠️ **This module IS the vocabulary**, and the document route imports it. A
hand-maintained copy would be the thing the derivation exists to remove, and the
``TODO``/``LINK`` near-miss recorded on the plan is what a hand-written list
looks like when it is wrong: short by exactly the row nobody thought about, and
indistinguishable from a complete one.

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

SOURCE_DIGESTS: tuple[tuple[str, str], ...] = (
    ("gramps-version", "b3bf7ac5e561b93af3e9a195f2844e8d8248d29556a0043629af523767cf3e02"),
    ("gramps-notetype", "c67cfc820a346bc0bb1ec0497494a781090e69c00df79c30d2c998ddbaa1d348"),
)
"""Each file this was derived from, and the SHA-256 it was read from.

⚠️ **Two files, two digests.** The version is not in the file the rows come
from, so a table claiming a provenance derived from one of them would be
claiming something neither file states.
"""

GRAMPS_VERSION_TUPLE: tuple[int, ...] = (6, 0, 8)
"""What the installation this was derived from says Gramps IS.

Read from ``VERSION_TUPLE``, never from ``VERSION``: the all-in-one build
appends a second assignment overwriting ``VERSION`` with its own packaging
string, so that name says what the installer called the build.
"""

GRAMPS_PACKAGING_VERSION: str = "AIO64-6.0.8--1"
"""What the installer called the build, or empty where nothing states one.

A fact about a package rather than about Gramps, recorded beside the tuple
because the two are not recoverable from each other.
"""

REAL_LIST: str = "_DATAMAPREAL"
"""The list Gramps offers in the ordinary way, wherever a note sits."""

IGNORED_LIST: str = "_DATAMAPIGNORE"
"""The list ``get_ignore_list`` returns: offered in its own object's tab."""

EXCLUDED_FROM_ACCEPTED: tuple[str, ...] = (
    "CUSTOM",
    "UNKNOWN",
)
"""The two rows of the real list that are carried and NOT accepted.

``CUSTOM`` is the door custom note types would come through, and they are
ruled out. ``UNKNOWN`` is what Gramps holds when it does not know, so a
caller choosing it is asking for the absence of a choice. Both stay in the
table: they are two of the names a lookup written slightly wrong would let
through, and a test that names them needs them here to name.
"""

NOTE_TYPE_ROWS: tuple[tuple[str, int, str, str], ...] = (
    ("UNKNOWN", -1, "Unknown", "_DATAMAPREAL"),
    ("CUSTOM", 0, "Custom", "_DATAMAPREAL"),
    ("GENERAL", 1, "General", "_DATAMAPREAL"),
    ("RESEARCH", 2, "Research", "_DATAMAPREAL"),
    ("ANALYSIS", 27, "Analysis", "_DATAMAPREAL"),
    ("TRANSCRIPT", 3, "Transcript", "_DATAMAPREAL"),
    ("SOURCE_TEXT", 21, "Source text", "_DATAMAPREAL"),
    ("CITATION", 22, "Citation", "_DATAMAPREAL"),
    ("REPORT_TEXT", 23, "Report", "_DATAMAPREAL"),
    ("HTML_CODE", 24, "Html code", "_DATAMAPREAL"),
    ("TODO", 25, "To Do", "_DATAMAPREAL"),
    ("LINK", 26, "Link", "_DATAMAPREAL"),
    ("PERSON", 4, "Person Note", "_DATAMAPIGNORE"),
    ("PERSONNAME", 20, "Name Note", "_DATAMAPIGNORE"),
    ("ATTRIBUTE", 5, "Attribute Note", "_DATAMAPIGNORE"),
    ("ADDRESS", 6, "Address Note", "_DATAMAPIGNORE"),
    ("ASSOCIATION", 7, "Association Note", "_DATAMAPIGNORE"),
    ("LDS", 8, "LDS Note", "_DATAMAPIGNORE"),
    ("FAMILY", 9, "Family Note", "_DATAMAPIGNORE"),
    ("EVENT", 10, "Event Note", "_DATAMAPIGNORE"),
    ("EVENTREF", 11, "Event Reference Note", "_DATAMAPIGNORE"),
    ("SOURCE", 12, "Source Note", "_DATAMAPIGNORE"),
    ("SOURCEREF", 13, "Source Reference Note", "_DATAMAPIGNORE"),
    ("PLACE", 14, "Place Note", "_DATAMAPIGNORE"),
    ("REPO", 15, "Repository Note", "_DATAMAPIGNORE"),
    ("REPOREF", 16, "Repository Reference Note", "_DATAMAPIGNORE"),
    ("MEDIA", 17, "Media Note", "_DATAMAPIGNORE"),
    ("MEDIAREF", 18, "Media Reference Note", "_DATAMAPIGNORE"),
    ("CHILDREF", 19, "Child Reference Note", "_DATAMAPIGNORE"),
)
"""Every row of both lists: attribute name, integer, key string, which list.

In ``_DATAMAP``'s own order, which is the real list then the ignored one.

⚠️ **The key strings are recorded and used by nothing**, deliberately. They
are how Gramps spells these in XML and in its own interface, and they are
NOT the attribute names -- ``SOURCE_TEXT`` is ``Source text``, ``TODO`` is
``To Do``, ``PERSONNAME`` is ``Name Note`` -- so a later reader comparing
the two vocabularies should not have to derive them again.

⚠️ **The integers are recorded and used by nothing either.** Gramps'
numbering is an implementation detail, and every lookup in this repository
goes through ``getattr`` on the attribute name so that a renumbering cannot
silently file a note under the wrong type.
"""

ACCEPTED_NOTE_TYPES: frozenset[str] = frozenset(
    attribute.lower()
    for attribute, _value, _key, declared_in in NOTE_TYPE_ROWS
    if declared_in == REAL_LIST and attribute not in EXCLUDED_FROM_ACCEPTED
)
"""The wire vocabulary: what a caller may ask a note to be.

⭐ **COMPUTED from the rows above, never listed**, so it cannot drift from
them. A row moved between the two lists moves in or out of this set with
nothing to remember.

The wire name is the **lowercased attribute name**, because that is what
``getattr`` resolves on Gramps' own class and what this repository's other
type vocabularies already use.
"""
