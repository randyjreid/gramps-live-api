"""⛔ Does the committed note-type table still match the Gramps on this machine?

⚠️ **THIS TEST RUNS ON A MACHINE WITH GRAMPS AND SKIPS ON CI, BY NAME, AND THAT
IS THE COST OF THE TABLE RATHER THAN A GAP THAT SNUCK IN.** The two frozen tables
this one follows derive from *published standards*, which a human fetches and
which are the same bytes everywhere; their verification is re-fetch, compare
digest, re-run, diff. **This table's source is a runtime installed on a
machine.** It varies per machine, and CI has none at all.

So the verification splits in two, and this is the half that needs Gramps:

* ``tests/unit/test_note_types_table.py`` asks *is the committed table
  internally consistent?* -- the two lists partitioning the rows, the accepted
  set computed rather than listed -- and needs nothing but the file.
* This asks *was it derived from THIS Gramps, and does that Gramps still declare
  what it says?* -- which cannot be asked without an installation.

⛔ **The ROWS are the property; the digests are provenance.** A digest moves on
any edit to either file, including ones touching no note type at all, so a
digest-only assertion would fail on upgrades that change nothing this depends on.
So the rows and the version are what is asserted, and a failure's message names
the digests of whichever file differs, because that is what tells the reader
which of the two files to go and look at.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

from gramps_live_api import config
from gramps_live_api.core import _note_types

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPOSITORY_ROOT / "scripts" / "derive_note_types.py"

REGENERATE = (
    "python scripts/derive_note_types.py <installation root> "
    "> src/gramps_live_api/core/_note_types.py"
)
"""⛔ What a failure here tells somebody to run.

The honest reading of a mismatch is *this table was derived from a different
Gramps*, and the repair is to re-derive it and read the diff -- never to edit the
generated file, whose own header says so in the same words.
"""


def installation_or_skip() -> Path:
    """The installation root, or a skip. Same shape as ``runtime_or_skip``.

    ⚠️ **The root, not the runtime.** ``discover_runtime`` answers with the
    executable, and the two files this reads sit beside it rather than inside it.
    """
    found = os.environ.get(config.ENV_RUNTIME) or config.discover_runtime(os.environ)
    if found is None or not os.path.isfile(found):
        pytest.skip(
            "no Gramps runtime on this machine, so the committed note-type table "
            "cannot be compared against one -- this is EXPECTED on CI and is the "
            "stated cost of deriving a table from a runtime rather than from a "
            "published standard. What is still covered is that the committed table "
            "is internally consistent and that everything reading it reads that "
            "table rather than a copy, by the seam twins "
            "test_the_table_carries_every_row_of_both_lists_and_nothing_else"
            " and "
            "test_the_schema_vocabulary_IS_the_table_and_not_a_copy"
            " -- neither of which can see a Gramps that moved underneath it, and "
            "nothing can on a runner with no Gramps on it."
        )
    return Path(found).parent


def derivation() -> ModuleType:
    """The derivation script, loaded by path.

    ⭐ **The same parser the committed table came out of, deliberately.** Drift is
    *the table no longer equals what a re-run would produce*, so a second parser
    written here would answer a different question and would have its own bugs to
    be wrong about. What bounds this parser is
    ``tests/unit/test_derive_note_types.py``, which exercises it over synthetic
    class bodies, including shapes it must refuse.
    """
    specification = importlib.util.spec_from_file_location("_note_type_drift", _SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _sources(root: Path) -> dict[str, tuple[str, bytes]]:
    """Each labelled source file as ``(path within the installation, bytes)``."""
    found = {}
    for label, relative in derivation().INSTALLATION_FILES:
        path = root / relative
        assert path.is_file(), (
            f"the installation at this root holds no {relative}, so the committed "
            "table cannot be checked against it at all"
        )
        found[label] = (relative, path.read_bytes())
    return found


def _provenance(root: Path) -> str:
    """What to say about the digests when something else has failed.

    ⛔ **Never the assertion, always the explanation.** Naming which of the two
    files differs is the difference between *go and look at the vocabulary* and
    *go and look at the version*, and a reader who is told only that a table is
    stale has to work that out for themselves.
    """
    committed = dict(_note_types.SOURCE_DIGESTS)
    lines = []
    for label, (relative, content) in _sources(root).items():
        here = hashlib.sha256(content).hexdigest()
        was = committed.get(label, "(the table records no digest under this label)")
        verdict = "unchanged" if here == was else "DIFFERS"
        lines.append(f"  {relative} ({label}): {verdict}; committed {was}, installed {here}")
    return "\n".join(lines)


def test_the_committed_ROWS_are_what_the_installed_gramps_declares() -> None:
    """⛔ The property. A name in the table Gramps no longer declares is a
    document the owner approves and the writer then cannot write.

    ⚠️ **That failure lands AFTER the approval**, which is the one moment this
    route exists to make safe: the package validates the name against the frozen
    table, the writer's membership check passes, and ``getattr`` then finds
    nothing on the live class. This test is one of the two things watching for it,
    and **it is a test: it can be skipped, and it does not run on the machine
    doing the writing at the moment it writes.** That is why the writer refuses
    the whole document on the same drift rather than relying on this.
    """
    root = installation_or_skip()
    label = "gramps-notetype"
    declared = derivation().rows_of(_sources(root)[label][1].decode("utf-8"), label)

    assert [tuple(row) for row in _note_types.NOTE_TYPE_ROWS] == declared, (
        "the committed note-type table is not what the installed Gramps declares. "
        "The honest reading is that it was derived from a different Gramps, and the "
        "repair is to re-derive it and read the diff.\n"
        f"{_provenance(root)}\n"
        f"    {REGENERATE}"
    )


def test_the_committed_VERSION_is_what_the_installed_gramps_declares() -> None:
    """⛔ Checked separately, because the rows can be identical across releases.

    ⚠️ A table claiming the wrong provenance is the failure that survives every
    other check: the rows agree, the accepted set agrees, and the one field a
    reader would trust to say *which Gramps this came from* is quietly a fact
    about a different one. The version lives in a **different file** from the
    rows, which is what turns this from a footnote into its own assertion.

    ⚠️ **``VERSION_TUPLE``, not ``VERSION``.** The all-in-one build appends a
    second assignment overwriting ``VERSION`` with its own packaging string, so
    the two answer different questions and both are recorded.
    """
    root = installation_or_skip()
    label = "gramps-version"
    version_tuple, packaging = derivation().version_of(
        _sources(root)[label][1].decode("utf-8"), label
    )

    assert version_tuple == _note_types.GRAMPS_VERSION_TUPLE, (
        f"the table records Gramps {_note_types.GRAMPS_VERSION_TUPLE} and this "
        f"installation declares {version_tuple}.\n"
        f"{_provenance(root)}\n"
        f"    {REGENERATE}"
    )
    assert packaging == _note_types.GRAMPS_PACKAGING_VERSION, (
        "the table records a packaging string this installation does not declare, so "
        "its provenance is a fact about a different build of the same Gramps.\n"
        f"{_provenance(root)}\n"
        f"    {REGENERATE}"
    )


def test_every_ACCEPTED_type_exists_on_the_installed_NoteType_class() -> None:
    """⛔ What the retired totality test was replaced by.

    ⚠️ ``apply.NOTE_TYPE_ATTRIBUTES`` used to be two entries typed by hand beside
    a two-member frozenset, asserted total over it by a test. Once both come from
    one table that subtraction cannot fail, so **the totality that actually needs
    checking is against Gramps**: every accepted attribute name must be something
    ``getattr(NoteType, ...)`` reaches on the class the write will use.

    ⭐ **Read out of the class body rather than by importing Gramps.** Importing
    ``gramps.gen.lib`` pulls in a locale, a configuration directory and a GTK
    stack, none of which a test run has any business creating; the declaration is
    right there in the file the table was derived from.
    """
    root = installation_or_skip()
    label = "gramps-notetype"
    script = derivation()
    text = _sources(root)[label][1].decode("utf-8")
    declared = script.integer_constants(script.note_type_class(script.parsed(text, label), label))

    missing = sorted(
        name.upper() for name in _note_types.ACCEPTED_NOTE_TYPES if name.upper() not in declared
    )

    assert missing == [], (
        "these accepted note types name an attribute the installed Gramps does not "
        "declare as an integer, so the package would accept them, the writer's "
        "membership check would pass, and getattr would find nothing AFTER the owner "
        f"approved the document: {missing}\n    {REGENERATE}"
    )
