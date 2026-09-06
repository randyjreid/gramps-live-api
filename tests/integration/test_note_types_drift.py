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

    ⛔ **Two skips, not one, because there are two ways to have nothing to
    compare against.** The runtime may be absent, which is CI; or it may be
    present with its sources somewhere else, which is an ordinary Linux install
    where the launcher is dropped into a ``bin`` directory on PATH while the
    package lives under a ``dist-packages`` directory belonging to the system
    interpreter. ``Path(runtime).parent`` is the root of the all-in-one
    Windows build and of nothing else, and this file supports being pointed at
    any runtime through ``GRAMPS_LIVE_API_RUNTIME``.

    ⭐ **The layout is not widened to admit that install, and deliberately.**
    Adding the Linux one invites conda, flatpak, homebrew, portable builds and
    pip installs, which is an open set with no fixed point and, unlike a frozen
    table, cannot be re-derived and diffed. What the second skip does instead is
    say exactly what it looked for and where, so a reader can tell *no Gramps
    here* from *Gramps is here and this does not know its shape* and can point
    the derivation script at the right root by hand.
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
            "test_the_document_vocabulary_IS_the_table_and_not_a_copy"
            " -- neither of which can see a Gramps that moved underneath it, and "
            "nothing can on a runner with no Gramps on it."
        )

    root = Path(found).parent
    looked_for = [relative for _, relative in derivation().INSTALLATION_FILES]
    missing = [relative for relative in looked_for if not (root / relative).is_file()]
    if missing:
        # ⛔ Joined HERE rather than inside the call below.
        #
        # ⚠️ ``test_every_skip_names_a_seam_twin_that_exists`` reads a skip's text
        # with a non-greedy match up to the first ``)``, so a ``join`` inside the
        # call hands that test a message truncated before the twins it names, and
        # the coverage claim then reads as absent rather than as made.
        wanted = ", ".join(looked_for)
        absent = ", ".join(missing)
        pytest.skip(
            f"a Gramps runtime IS on this machine -- {found} -- but the two source "
            "files this reads are not laid out beside it, so there is still nothing "
            "here to compare the committed note-type table against. The root derived "
            f"from that runtime is {root}; under it this looked for {wanted}; what is "
            f"absent is {absent}. ⚠️ That is NOT the same as no Gramps at all: it is a "
            "layout this test does not know, which is expected wherever the launcher "
            "and the package are installed apart from each other, as on an ordinary "
            "Linux install. ⛔ The layouts are deliberately not enumerated here, so "
            "pointing this at such an install SKIPS rather than fails. What is still "
            "covered is that the committed table is internally consistent and that "
            "everything reading it reads that table, by the seam twins "
            "test_the_table_carries_every_row_of_both_lists_and_nothing_else"
            " and "
            "test_the_document_vocabulary_IS_the_table_and_not_a_copy"
            " -- and a drifted type is refused at write time by both write routes "
            "rather than only here. To check the table against THIS installation, "
            f"re-derive it against the root that does hold {wanted}: {REGENERATE}"
        )
    return root


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
    """Each labelled source file as ``(path within the installation, bytes)``.

    ⚠️ **The assertion below is an invariant, not the layout check.** A root that
    holds neither file is answered by ``installation_or_skip``, which is where a
    missing source becomes a skip; reaching this one means a file that was there
    when the root was accepted is not there now.
    """
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

    ⚠️ The note flow's Gramps-spelling map used to be two entries typed by hand
    beside a two-member frozenset, asserted total over it by a test. Once both
    came from one table that subtraction could not fail, and the map has since
    retired with the flow, so **the totality that actually needs checking is
    against Gramps**: every accepted attribute name must be something
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


def test_a_runtime_whose_ROOT_HOLDS_NO_SOURCES_skips_rather_than_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The layout assumption is a SKIP condition, not a failure.

    ⚠️ ``Path(runtime).parent`` is the installation root **on the all-in-one
    Windows build**, where the launcher sits beside the ``gramps`` package. It is
    not the root on an ordinary Linux install, where the launcher goes into a
    ``bin`` directory and the sources go under a ``dist-packages`` directory
    somewhere else entirely. This file's own contract is that it skips when it
    cannot see an installation, so a runtime it cannot read the sources beside is
    that same case rather than a defect in the table.

    ⭐ **And the message must tell the two skips apart.** *No Gramps here* and
    *Gramps is here, laid out some other way* call for different actions from a
    reader, so the second names the runtime it was handed, the root it derived
    from it, and each relative path it went looking for.

    A temporary file stands in for the launcher, so this runs on every machine,
    including a runner with no Gramps at all.
    """
    launcher = tmp_path / "gramps"
    launcher.write_text("not a real launcher", encoding="utf-8")
    monkeypatch.setenv(config.ENV_RUNTIME, str(launcher))

    with pytest.raises(pytest.skip.Exception) as refused:
        installation_or_skip()

    message = str(refused.value)
    assert str(launcher) in message, (
        f"the skip must name the runtime it was given, so a reader knows which "
        f"one was mislocated; got {message!r}"
    )
    assert str(tmp_path) in message, (
        f"the skip must name the root it derived, which is the assumption that "
        f"did not hold; got {message!r}"
    )
    for _, relative in derivation().INSTALLATION_FILES:
        assert relative in message, (
            f"the skip must name {relative}, since what it looked for is how a "
            f"reader tells a differently laid out Gramps from no Gramps at all; "
            f"got {message!r}"
        )
