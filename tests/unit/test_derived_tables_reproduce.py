r"""Is each frozen table still what its own generator would emit? Offline, every run.

Three tables in this repository are frozen derivations: a generator in
``scripts/`` reads a published standard or an installed runtime, and prints a
module into ``src/gramps_agent_data_entry/core/``. The discipline's stated verification
is **re-fetch, compare digest, re-run, and the diff is empty**, and until this
file existed the last step had no test behind it. What the suite proved was that
each generator parses its source correctly and emits the same bytes twice.
**Nothing proved those bytes were the ones actually committed**, so a pin had the
shape of a derived table with the guarantees of a hand-written one.

⚠️ **The round trip below is VACUOUS FOR THE ROWS, and saying so is the point of
this paragraph rather than a caveat at the end.** It feeds the committed file's
own recorded data back into ``emit``, so every data argument is the file arguing
with itself. What it genuinely binds is the half that does NOT come from the
file: the generator's header, every docstring line ``emit`` writes, the quoting
and formatting rules, and -- for the note types -- the three selection constants
the generator holds and writes out. ⛔ **On its own it would NOT have caught the
change that motivated issue #238**: had two categories joined the unrenderable
class with the table left unregenerated, the round trip would pass, because the
table's own rows are its input.

⭐ **So the round trip is not the only check here.** The bindings further down
tie the values the committed tables carry to the constants the scripts select
them with. Each one's two sides come from two files and neither is derived from
the other, which is what makes them the ones that catch a class that moved
without a regeneration. A reader meets the round trip's limit next to the thing
that covers it, deliberately.

⚠️ **A selection constant reaches a table two ways, and only one of them is
visible to a round trip.** ``derive_note_types.emit`` names its three constants
itself, so feeding the committed rows back through it binds them for real.
``derive_unrenderable`` and ``derive_specified_containers`` do not: their
selecting constants reach the table as **data**, in a column, which the round
trip then hands straight back. Those two therefore get bindings of their own --
the unrenderable labels, and the container table's content models and declared
types.

⚠️ **No byte comparison, and that is measured rather than fastidious.**
``core.autocrlf`` is on and ``.gitattributes`` forces LF only for hooks and shell
scripts, so every committed module here is CRLF in a Windows working tree and LF
on a Linux runner, while ``emit`` returns ``\n`` throughout. Raw byte equality is
false for all three files today for a reason that has nothing to do with drift.
The committed file is therefore read with universal newlines, and line endings
are deliberately not asserted: they are a property of the checkout rather than of
the derivation.

⛔ **The WORKING TREE file, never ``git show``**, which hands back the stored blob
with that translation undone and reports every line as changed.

⚠️ **No network, no fetched artifact, no Gramps, and nothing here skips.** Every
``emit`` is drivable offline: none of them touches the filesystem, the network or
``unicodedata``, and only ``main`` reads paths. The published sources are not
needed to ask this question.

⚠️ **What is still NOT covered**, recorded here rather than left to be assumed:
the rows are not checked against the published source by anything automatic. What
covers them is the recorded digests plus the human re-fetch, and, for the
unrenderable class alone, the cross-check against the running interpreter's own
database in ``test_document_render_guard.py``. A table re-derived against a newer
release and committed half-way would pass everything in this file.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from gramps_agent_data_entry.core import _note_types, _specified_containers, _unrenderable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SCRIPT_DIRECTORY = "scripts"
"""Where the generators live, relative to the repository root."""

COMMITTED_DIRECTORY = "src/gramps_agent_data_entry/core"
"""Where the generated modules live, relative to the repository root."""

_BOM = b"\xef\xbb\xbf"
"""What PowerShell's ``>`` prepends. No generator emits it; see issue #47."""

_QUOTED_LIMIT = 200
"""How much of a differing line a failure quotes, per side.

⚠️ **A failure nobody can read is a failure people route around.** These modules
run to hundreds of lines and one of them carries thousands of ranges, so the
message names the first divergence and quotes it, and never hands pytest two
whole copies of a module to diff on the terminal.
"""


# ---------------------------------------------------------------------------
# The pairs, and how each one's emit is driven from its own committed module.
#
# ⚠️ **Every literal in this file is invented.** Nothing here writes out a copy of
# any table's rows, labels, header text or counts -- a second tally is the counter
# bug this repository has already paid for, twice. The adapters read the committed
# module's own names, and the controls append values no standard publishes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """One generator, the module it prints, and how to drive it from that module."""

    generator: str
    """The script's file name under ``scripts/``."""

    committed: str
    """The generated module's file name under ``src/gramps_agent_data_entry/core/``."""

    arguments: Callable[[], list[Any]]
    """``emit``'s arguments, rebuilt from the committed module's own names."""

    rows_argument: int
    """Which argument carries the table's rows, for the positive control below."""

    invented_row: Any
    """A row no published source states, appended by that control."""


def _unrenderable_arguments() -> list[Any]:
    """``derive_unrenderable.emit``'s arguments, from the committed class."""
    return [
        list(_unrenderable.SOURCE_DIGESTS),
        _unrenderable.UNICODE_VERSION,
        list(_unrenderable.UNRENDERABLE_RANGES),
    ]


def _note_types_arguments() -> list[Any]:
    """``derive_note_types.emit``'s arguments, from the committed vocabulary.

    ⭐ **The three selection constants are NOT among them.** ``REAL_LIST``,
    ``IGNORED_LIST`` and ``EXCLUDED_FROM_ACCEPTED`` are read by ``emit`` off the
    generator itself and written into the table, so the round trip binds them for
    real rather than vacuously. That is why this pair needs no separate label
    check of its own.
    """
    return [
        list(_note_types.SOURCE_DIGESTS),
        _note_types.GRAMPS_VERSION_TUPLE,
        _note_types.GRAMPS_PACKAGING_VERSION,
        list(_note_types.NOTE_TYPE_ROWS),
    ]


def _specified_containers_arguments() -> list[Any]:
    """``derive_specified_containers.emit``'s arguments, from the committed table.

    The markup names are rebuilt as a ``set`` rather than passed as the committed
    ``frozenset``, because that is the parameter's declared type; ``emit`` only
    sorts it, so the two are the same input written two ways.

    ⭐ **This generator's selection constants are not among these arguments and
    are not named by ``emit`` either.** They reach the table inside these very
    rows -- the content models in the second column of ``SPECIFIED_ELEMENTS``,
    the parser's name for an enumerated attribute in the third column of
    ``SPECIFIED_ATTRIBUTES`` -- so the round trip hands them back to itself. The
    bindings further down are what read them.
    """
    return [
        list(_specified_containers.SOURCE_DIGESTS),
        list(_specified_containers.SPECIFIED_ELEMENTS),
        list(_specified_containers.SPECIFIED_ATTRIBUTES),
        list(_specified_containers.FIXED_ATTRIBUTE_DEFAULTS),
        set(_specified_containers.MARKUP_ELEMENT_NAMES),
    ]


PAIRS: tuple[Pair, ...] = (
    Pair(
        generator="derive_unrenderable.py",
        committed="_unrenderable.py",
        arguments=_unrenderable_arguments,
        rows_argument=2,
        invented_row=(0x10FFFE, 0x10FFFE, "Invented_Property_Nobody_Publishes"),
    ),
    Pair(
        generator="derive_note_types.py",
        committed="_note_types.py",
        arguments=_note_types_arguments,
        rows_argument=3,
        invented_row=("BADGER", 4321, "An invented key", "_AN_INVENTED_LIST"),
    ),
    Pair(
        generator="derive_specified_containers.py",
        committed="_specified_containers.py",
        arguments=_specified_containers_arguments,
        rows_argument=1,
        invented_row=("aninventedcontainer", "an-invented-model"),
    ),
)
"""Every derived pair. ``test_every_derivation_script_has_a_round_trip`` guards it."""

_UNRENDERABLE = PAIRS[0]
"""The pair the label binding below is about."""

_IDENTIFIED = tuple(pair.committed for pair in PAIRS)
"""Parametrisation ids, so a failure line names which pair failed."""


def script_path(pair: Pair) -> Path:
    """The generator, as a path under this checkout."""
    return REPOSITORY_ROOT / SCRIPT_DIRECTORY / pair.generator


def committed_path(pair: Pair) -> Path:
    """The generated module, as a path under this checkout."""
    return REPOSITORY_ROOT / Path(COMMITTED_DIRECTORY) / pair.committed


def derivation(pair: Pair) -> ModuleType:
    """The generator, loaded by path under a name that is not ``__main__``.

    Under ``__main__`` the script's own guard would run ``main`` on pytest's
    argument list, which is a confusing way to discover that a script has one.
    This is a fourth copy of the four-line loader the three derivation tests and
    the drift test already carry; consolidating them is a separate change.
    """
    path = script_path(pair)
    specification = importlib.util.spec_from_file_location(f"_reproduces_{pair.committed}", path)
    assert specification is not None and specification.loader is not None, (
        f"the derivation script is not loadable from {path}"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Reading the committed side, and saying what a divergence is.
# ---------------------------------------------------------------------------


def bom_refusal(name: str, raw: bytes) -> str | None:
    """The message a leading UTF-8 BOM earns, or ``None`` when there is none.

    ⚠️ **A BOM is read as its own failure rather than as a divergence**, because
    the two call for completely different actions. A correct re-derivation
    redirected through PowerShell's ``>`` comes out three bytes longer with the
    encoding rewritten, and every line then reads as changed -- so a reader told
    only that the table differs goes looking for drift that is not there. That is
    issue #47, and these generators are the second and third things it can bite.

    ⛔ **Which is also why the read below is ``utf-8`` and not ``utf-8-sig``.**
    The permissive encoding would swallow the BOM, the round trip would pass, and
    a module carrying three bytes no generator emits would be committed.
    """
    if not raw.startswith(_BOM):
        return None
    return (
        f"{name} begins with a UTF-8 BOM, which no generator here emits. That is issue "
        "#47: a re-derivation redirected through PowerShell's > is rewritten with a BOM "
        "and CRLF, so a CORRECT re-derivation comes out three bytes longer and looks "
        "exactly like a defect. Redirect through cmd /c, which redirects at byte level, "
        "and read the diff again."
    )


def first_divergence(committed: str, emitted: str) -> int | None:
    """The 1-based number of the first line where the two texts differ, or ``None``."""
    for number, (one, other) in enumerate(
        zip_longest(committed.split("\n"), emitted.split("\n")), start=1
    ):
        if one != other:
            return number
    return None


def _quoted(lines: Sequence[str], number: int) -> str:
    """One side's spelling of a line, clipped, or a note that the side ended first."""
    if number > len(lines):
        return "(this side has no line here; it ends first)"
    line = lines[number - 1]
    if len(line) > _QUOTED_LIMIT:
        return f"{line[:_QUOTED_LIMIT]!r} (clipped at {_QUOTED_LIMIT} characters)"
    return repr(line)


def divergence_report(pair: Pair, committed: str, emitted: str, number: int) -> str:
    """What a drifted table says, in the terms somebody can act on.

    ⚠️ **It does not claim to know which side moved**, because it cannot: the
    generator changing without a regeneration and the table being hand-edited
    produce the identical observation. What it does say is which CLASS of drift
    this is, which is the actionable half -- the data arguments came out of the
    committed file, so the difference is in the serialization and never in the
    rows.
    """
    left = committed.split("\n")
    right = emitted.split("\n")
    differing = sum(1 for one, other in zip_longest(left, right) if one != other)
    return (
        f"line {number} of {COMMITTED_DIRECTORY}/{pair.committed} is not what "
        f"{SCRIPT_DIRECTORY}/{pair.generator} would emit: {differing} line(s) differ, "
        f"committed {len(left)} lines against {len(right)} emitted.\n"
        f"  committed: {_quoted(left, number)}\n"
        f"  emitted:   {_quoted(right, number)}\n"
        "⚠️ The data arguments came from the committed file ITSELF, so this is "
        "SERIALIZATION drift and never a difference in the rows: either the generator "
        "changed and the table was not regenerated, or the table was hand-edited. The "
        "rows are covered by the recorded digests and the human re-fetch, not by this.\n"
        f"  Re-derive with {SCRIPT_DIRECTORY}/{pair.generator}, whose own module header "
        "names the command, and read the diff. ⛔ On Windows redirect through cmd /c: "
        "PowerShell's > adds a BOM and CRLF, so a correct re-derivation looks like a "
        "defect (issue #47)."
    )


def reproduction_divergence(pair: Pair, arguments: list[Any]) -> str | None:
    """The whole round trip for one pair, over the arguments it is handed.

    Handed the committed module's own values this is the property; handed a
    mutated copy of them it is the control that proves the comparison is still
    sensitive to what it is given.
    """
    path = committed_path(pair)
    raw = path.read_bytes()
    refusal = bom_refusal(f"{COMMITTED_DIRECTORY}/{pair.committed}", raw)
    if refusal is not None:
        return refusal
    committed = path.read_text(encoding="utf-8")
    emitted: str = derivation(pair).emit(*arguments)
    number = first_divergence(committed, emitted)
    if number is None:
        return None
    return divergence_report(pair, committed, emitted, number)


# ---------------------------------------------------------------------------
# Check one: the round trip.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pair", PAIRS, ids=_IDENTIFIED)
def test_the_committed_table_is_what_its_generator_would_emit(pair: Pair) -> None:
    """⛔ The reproduction step the discipline states and nothing performed.

    ⚠️ **Vacuous for the rows and not for the rest**, as the module docstring
    says at length. What fails here is a generator whose header, docstrings,
    quoting or formatting rules moved without the table being regenerated, or a
    table somebody edited by hand -- which its own header forbids in capitals and
    which is exactly what a "machine-generated" file stops being when nothing
    checks.
    """
    refusal = reproduction_divergence(pair, pair.arguments())

    assert refusal is None, refusal


# ---------------------------------------------------------------------------
# Check two: the label binding, which is the NON-VACUOUS half.
# ---------------------------------------------------------------------------

_INVENTED_LABEL = "Invented_Category_Nobody_Publishes"
"""A label no Unicode release states, used to drive the binding the other way."""


def label_divergence(ranges: Sequence[tuple[int, int, str]], script: ModuleType) -> str | None:
    """Do the table's own labels name exactly the classes the script declares?

    ⭐ **This is the check the round trip cannot be.** The two sides come out of
    two files and neither is derived from the other: the labels are what the
    committed table carries, and the classes are the constants the generator
    holds. Feed the table back through ``emit`` and a category that joined the
    class without a regeneration is invisible; ask this and it is not.

    ⚠️ **Equality both ways is load-bearing.** A class the script names with no
    row in the table is the drift issue #238 was filed for. A label in the table
    the script names nowhere is a hand edit or a table emitted by an older
    generator, and reads as an unexplained refusal reason to whoever meets it.

    ⚠️ **And neither direction may name which side moved**, for the reason
    ``divergence_report`` gives: the two causes produce the identical
    observation. A class named by the script and carried by no row is a table
    left unregenerated when the class moved -- or a class that stopped being
    published while the script still names it. What the message can say is which
    class, and what to run.

    ⚠️ **Its one assumption:** every class the script names has at least one code
    point in the published source. A General_Category with no members does not
    appear in the artifact at all, so a class that stopped being published would
    fail here loudly and once, which is the safe direction.

    ⭐ **It writes out no list.** Both sides are read; neither is typed here.
    """
    carried = {label for _first, _last, label in ranges}
    declared = set(script.UNRENDERABLE_CATEGORIES) | {script.DEFAULT_IGNORABLE}
    if carried == declared:
        return None

    said = [
        f"the labels {COMMITTED_DIRECTORY}/{_UNRENDERABLE.committed} carries are not the "
        f"classes {SCRIPT_DIRECTORY}/{_UNRENDERABLE.generator} declares."
    ]
    absent = sorted(declared - carried)
    if absent:
        said.append(
            f"⛔ Named by the SCRIPT and carried by no row of the table: {absent}. Either the "
            "class moved and the table was not regenerated -- the drift this check exists for "
            "-- or the class stopped being published and the script still names it."
        )
    unnamed = sorted(carried - declared)
    if unnamed:
        said.append(
            f"⛔ Carried by the TABLE and named nowhere in the script: {unnamed}. Either the "
            "table was hand-edited, or it was emitted by an older generator -- and a refusal "
            "would name a published fact the script no longer claims."
        )
    said.append(
        f"Re-derive with {SCRIPT_DIRECTORY}/{_UNRENDERABLE.generator} and read the diff; ⛔ on "
        "Windows redirect through cmd /c (issue #47)."
    )
    return " ".join(said)


def test_the_committed_labels_name_exactly_the_classes_the_script_declares() -> None:
    """⛔ The half of #238 the round trip is vacuous about, on the current head."""
    refusal = label_divergence(_unrenderable.UNRENDERABLE_RANGES, derivation(_UNRENDERABLE))

    assert refusal is None, refusal


def test_a_class_the_script_names_with_no_row_in_the_table_is_caught() -> None:
    """⛔ The drift that motivated the issue, reproduced.

    Every row carrying one of the declared classes is dropped from the table this
    is handed, which is what a class joining the script without a regeneration
    looks like from the table's side. ⚠️ **The class is COMPUTED, never typed**:
    naming one here would be a copy of the table's labels, and which one it is
    does not matter to the property.

    ⚠️ **What is asserted about the message is the class and the repair, not a
    diagnosis.** This observation has two causes and the check cannot tell them
    apart, so a test demanding it say "the table is stale" would be pinning the
    one sentence the message is not entitled to.
    """
    script = derivation(_UNRENDERABLE)
    dropped = min(script.UNRENDERABLE_CATEGORIES)
    thinned = [row for row in _unrenderable.UNRENDERABLE_RANGES if row[2] != dropped]
    assert len(thinned) < len(_unrenderable.UNRENDERABLE_RANGES), (
        f"the script declares {dropped} and the committed table carries no row labelled "
        "with it, so this control removed nothing and would pass whatever the binding did"
    )

    refusal = label_divergence(thinned, script)

    assert refusal is not None, (
        "a class the script declares was carried by no row of the table and the binding "
        "said nothing -- the check that catches a stale table has stopped catching one"
    )
    assert dropped in refusal, (
        f"the refusal must name {dropped}, which is the class that went missing; got {refusal!r}"
    )
    assert f"{SCRIPT_DIRECTORY}/{_UNRENDERABLE.generator}" in refusal, (
        "the refusal must name the generator to re-derive with, which is what a reader acts on "
        f"when the check itself cannot say which side moved; got {refusal!r}"
    )


def test_a_label_in_the_table_the_script_does_not_declare_is_caught() -> None:
    """⛔ The other direction: a hand edit, or a table an older generator emitted."""
    script = derivation(_UNRENDERABLE)
    widened = [*_unrenderable.UNRENDERABLE_RANGES, (0x10FFFE, 0x10FFFE, _INVENTED_LABEL)]

    refusal = label_divergence(widened, script)

    assert refusal is not None, (
        "the table carried a label the script names nowhere and the binding said nothing, "
        "so a hand-edited row would reach a refusal message unremarked"
    )
    assert _INVENTED_LABEL in refusal, (
        f"the refusal must name the label nothing declares; got {refusal!r}"
    )


# ---------------------------------------------------------------------------
# Check two, continued: the same binding for the container table.
#
# ⚠️ **Its selection constants reach the table as DATA, which is exactly why the
# round trip cannot see them.** ``derive_specified_containers.emit`` names only
# its header and its quoting helper -- no selection constant at all -- so the
# reading that this pair had none to bind was wrong. ``content_model``'s returns
# are the second column of ``SPECIFIED_ELEMENTS``, and the name the parser gives
# an enumerated attribute is the third column of every enumerated row. Rename
# either and the committed table is stale with nothing failing for it: measured
# on this branch before these bindings existed, once per constant, and both runs
# came back with the same single documented baseline failure they come back with
# unmutated.
# ---------------------------------------------------------------------------

_SPECIFIED = PAIRS[2]
"""The pair the two bindings below are about."""

_MODEL_FUNCTION = "content_model"
"""The generator's own name for the function whose returns ARE the models."""

_AN_INVENTED_MODEL = "an-invented-model"
_ANOTHER_INVENTED_MODEL = "another-invented-model"
"""Two models nothing publishes, for the reader of returns below."""

_INVENTED_MODEL_IN_A_TABLE = "an-invented-model-no-generator-returns"
"""What a hand-edited second column looks like, for the control."""

_INVENTED_ELEMENT = "aninventedelement"
_INVENTED_ATTRIBUTE = "aninventedattribute"
"""Names no schema declares, for the one-declaration probes below."""

_INVENTED_ENUMERATION = "(aninventedvalue|anotherinventedvalue)"
"""An enumerated declaration, so the SCRIPT says what it calls one."""

_INVENTED_TYPE = "AN_INVENTED_TYPE"
"""A declared type XML's ``AttType`` production does not have."""


def models_the_script_returns(source: str) -> tuple[frozenset[str], str | None]:
    """Every content model ``content_model`` returns, read off the script's text.

    ⚠️ **Read, never probed, and the difference is a fail-open.** Driving the
    function with invented declarations hands back only the models whose branch
    the probe happens to reach, so a model added to the script would sit outside
    the binding entirely -- which is the drift this file exists for, one level up.
    The return statements are what the function declares.

    ⛔ **A return this cannot read is a REFUSAL, never a smaller set**, because
    every model missing from the declared side makes the binding pass more
    readily. It takes the source as text rather than the loaded module so the
    controls can hand it a generator written here.
    """
    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == _MODEL_FUNCTION
    ]
    if len(functions) != 1:
        return frozenset(), (
            f"the generator holds {len(functions)} definitions of {_MODEL_FUNCTION} and this "
            "binding reads the returns of exactly one. Nothing is being checked until that is "
            "resolved, so this refuses rather than reading a subset."
        )
    returned = set()
    for node in ast.walk(functions[0]):
        if not isinstance(node, ast.Return):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            return frozenset(), (
                f"{_MODEL_FUNCTION} returns something other than a string literal at line "
                f"{node.lineno}, so the models it declares cannot be read from its text. ⛔ This "
                "refuses rather than reading the literals it CAN see: a shorter declared list is "
                "a binding that passes more, which is the wrong direction to fail in."
            )
        returned.add(node.value.value)
    if not returned:
        return frozenset(), (
            f"{_MODEL_FUNCTION} returns no string literal at all, so there is nothing for the "
            "committed content models to be bound to."
        )
    return frozenset(returned), None


def model_divergence(elements: Sequence[tuple[str, str]], source: str) -> str | None:
    """Is every content model the table carries one the generator returns?

    ⭐ **The round trip cannot ask this.** The models are the second column of the
    rows it feeds back into ``emit``, so a literal renamed in ``content_model``
    leaves the committed table stale and the reproduction perfect. Here the two
    sides come out of two files: the column is what the table carries, the
    returns are what the script declares.

    ⚠️ **One direction, and it is measured rather than conceded.** The reverse --
    every model the script returns has a row -- is false on the committed table
    as this is written, and would be wrong in principle even where it holds: a
    model no element in the published schema exhibits regenerates to the
    identical table, so its absence from the column is not drift and there is
    nothing for a check to catch. What this direction does catch is the rename,
    because every row then carries a value the script no longer returns.

    ⚠️ **A table carrying no model at all is refused rather than passed.** An
    empty column satisfies "every model is declared" vacuously, which is the
    shape a check has when it has quietly stopped reading its input.
    """
    declared, unreadable = models_the_script_returns(source)
    if unreadable is not None:
        return unreadable
    carried = {model for _name, model in elements}
    if not carried:
        return (
            f"{COMMITTED_DIRECTORY}/{_SPECIFIED.committed} carries no content model at all, so "
            "this binding would hold whatever the generator declared. A table with no elements "
            "in it is a derivation that read nothing."
        )
    unnamed = sorted(carried - declared)
    if not unnamed:
        return None
    return (
        f"the content models {COMMITTED_DIRECTORY}/{_SPECIFIED.committed} carries are not all "
        f"models {SCRIPT_DIRECTORY}/{_SPECIFIED.generator}'s {_MODEL_FUNCTION} returns.\n"
        f"⛔ Carried by the TABLE and returned nowhere by {_MODEL_FUNCTION}: {unnamed}. Either a "
        "model literal moved in the script and the table was not regenerated, or the table was "
        "hand-edited -- the two produce the identical observation and this cannot tell them "
        "apart.\n"
        f"  Re-derive with {SCRIPT_DIRECTORY}/{_SPECIFIED.generator} and read the diff; ⛔ on "
        "Windows redirect through cmd /c (issue #47)."
    )


def type_the_script_reads(script: ModuleType, declared: str) -> str | None:
    """What the generator's own parser makes of one declaration of type ``declared``.

    ``None`` when it will not read one at all, which is what its fail-closed
    guarantee does with a type the specification does not have.

    ⭐ **The script's parser is the authority, rather than a copy of its
    productions kept here.** Asking it what an enumerated declaration is called
    is how the name reaches this file without being typed into it.
    """
    declaration = f"<!ATTLIST {_INVENTED_ELEMENT} {_INVENTED_ATTRIBUTE} {declared} #IMPLIED>"
    try:
        rows, _defaults = script.attributes_of(declaration)
    except SystemExit:
        return None
    if len(rows) != 1:
        return None
    _element, _attribute, read = rows[0]
    return str(read)


def declared_type_divergence(
    attributes: Sequence[tuple[str, str, str]], script: ModuleType
) -> str | None:
    """Do the table's declared types name what the generator's parser produces?

    ⚠️ **Equality both ways, in the only shape this column has one.** Most of the
    column is the schema's own vocabulary, read through the parser and written
    out unchanged, so a set equality against a list of constants would be a
    second copy of ``AttType``. Instead each side is asked of the script itself:

    * the name it gives an ENUMERATED attribute is a value it chooses rather than
      reads, so the table must carry it -- that is the constant-with-no-row
      direction, and it is what a rename of that constant fails;
    * every other type the table carries must be one the parser produces from a
      declaration of that type -- that is the value-the-script-does-not-declare
      direction, and it is what a hand-edited column fails.

    ⚠️ **Its one assumption:** the pinned schema declares at least one enumerated
    or ``NOTATION`` attribute. One that declared none would fail here loudly and
    once, which is the safe direction, and is the same assumption the label
    binding above records for itself.

    ⚠️ **It names no side.** A type carried by no row and a type no parser reads
    are each producible by an edit on either side of the pair.
    """
    carried = {declared for _element, _attribute, declared in attributes}
    enumerated = type_the_script_reads(script, _INVENTED_ENUMERATION)
    said = []
    if enumerated is None:
        said.append(
            f"⛔ {SCRIPT_DIRECTORY}/{_SPECIFIED.generator} would not read an enumerated "
            "declaration at all, so it cannot be asked what it calls one and this binding has "
            "no side to compare the table against."
        )
    elif enumerated not in carried:
        said.append(
            f"⛔ Named by the SCRIPT as {enumerated!r} -- what its parser calls an enumerated "
            "attribute -- and carried by no row of the table. Either that name moved and the "
            "table was not regenerated, or the schema stopped declaring an enumerated attribute "
            "at all."
        )
    unread = sorted(
        declared
        for declared in carried
        if declared != enumerated and type_the_script_reads(script, declared) != declared
    )
    if unread:
        said.append(
            f"⛔ Carried by the TABLE and not what the parser produces for a declaration of that "
            f"type: {unread}. Either the table was hand-edited, or it was emitted by a generator "
            "whose productions have since changed."
        )
    if not said:
        return None
    said.insert(
        0,
        f"the declared types {COMMITTED_DIRECTORY}/{_SPECIFIED.committed} carries are not the "
        f"ones {SCRIPT_DIRECTORY}/{_SPECIFIED.generator} produces.",
    )
    said.append(
        f"Re-derive with {SCRIPT_DIRECTORY}/{_SPECIFIED.generator} and read the diff; ⛔ on "
        "Windows redirect through cmd /c (issue #47)."
    )
    return " ".join(said)


def test_the_committed_content_models_are_ones_the_generator_returns() -> None:
    """⛔ The half of #238 the round trip is vacuous about, for this pair."""
    refusal = model_divergence(
        _specified_containers.SPECIFIED_ELEMENTS,
        script_path(_SPECIFIED).read_text(encoding="utf-8"),
    )

    assert refusal is None, refusal


def test_a_content_model_the_generator_does_not_return_is_caught() -> None:
    """⛔ The drift, from the table's side: a column carrying what nothing returns.

    ⚠️ **The invented model REPLACES a carried one rather than joining it**, so
    this cannot pass on the strength of the rows that were already right.
    """
    source = script_path(_SPECIFIED).read_text(encoding="utf-8")
    carried = list(_specified_containers.SPECIFIED_ELEMENTS)
    assert carried, "the committed table carries no element at all, so this control proves nothing"
    edited = [(carried[0][0], _INVENTED_MODEL_IN_A_TABLE), *carried[1:]]

    refusal = model_divergence(edited, source)

    assert refusal is not None, (
        "a content model no generator returns was carried by a row and the binding said nothing "
        "-- a renamed model literal would leave the committed table stale and every gate green"
    )
    assert _INVENTED_MODEL_IN_A_TABLE in refusal, (
        f"the refusal must name the model nothing returns; got {refusal!r}"
    )


def test_a_table_carrying_no_content_model_at_all_is_refused() -> None:
    """The vacuity the binding would otherwise pass on."""
    refusal = model_divergence([], script_path(_SPECIFIED).read_text(encoding="utf-8"))

    assert refusal is not None, (
        "an empty table satisfied the binding, so a reader that had stopped reading its input "
        "would report the tightest possible agreement"
    )


def test_the_models_are_read_from_the_generators_own_return_statements() -> None:
    """⭐ The instrument, over a generator written HERE, with known returns.

    ⚠️ **A reader nobody has calibrated is not evidence.** The property above is
    a negative -- no model outside the declared set -- and a reader that quietly
    returned every string in the file would satisfy it forever.
    """
    invented = (
        f"def {_MODEL_FUNCTION}(declared: str) -> str:\n"
        '    if declared == "an invented declaration":\n'
        f'        return "{_AN_INVENTED_MODEL}"\n'
        f'    return "{_ANOTHER_INVENTED_MODEL}"\n'
    )

    returned, unreadable = models_the_script_returns(invented)

    assert unreadable is None, f"a generator returning two literals was refused: {unreadable}"
    assert returned == frozenset({_AN_INVENTED_MODEL, _ANOTHER_INVENTED_MODEL}), (
        f"the reader must see every return and nothing else; got {sorted(returned)}"
    )


def test_a_generator_whose_models_are_not_literals_is_refused() -> None:
    """⛔ And it refuses rather than reading a subset, which would pass more."""
    invented = f"def {_MODEL_FUNCTION}(declared: str) -> str:\n    return declared.lower()\n"

    returned, unreadable = models_the_script_returns(invented)

    assert unreadable is not None, (
        "a generator whose models cannot be read from its text was accepted, so the binding "
        "would have compared the table against an empty declared set and passed"
    )
    assert returned == frozenset(), f"a refusal declares nothing; got {sorted(returned)}"


def test_the_committed_declared_types_are_the_ones_the_generator_produces() -> None:
    """⛔ The second column-borne constant of this pair, on the current head."""
    refusal = declared_type_divergence(
        _specified_containers.SPECIFIED_ATTRIBUTES, derivation(_SPECIFIED)
    )

    assert refusal is None, refusal


def test_the_name_the_parser_gives_an_enumeration_must_be_carried_by_the_table() -> None:
    """⛔ The constant-with-no-row direction, which is what a rename of it fails.

    Every row carrying that name is dropped, which is what renaming the constant
    looks like from the table's side. ⚠️ **The name is COMPUTED, never typed**:
    it is read back out of the script's own parser.
    """
    script = derivation(_SPECIFIED)
    enumerated = type_the_script_reads(script, _INVENTED_ENUMERATION)
    assert enumerated is not None, (
        "the generator would not read an invented enumerated declaration, so this control cannot "
        "say what the name is that the table must carry"
    )
    thinned = [row for row in _specified_containers.SPECIFIED_ATTRIBUTES if row[2] != enumerated]
    assert len(thinned) < len(_specified_containers.SPECIFIED_ATTRIBUTES), (
        f"the parser calls an enumerated attribute {enumerated!r} and the committed table carries "
        "no row of that type, so this control removed nothing and would pass whatever the binding "
        "did"
    )

    refusal = declared_type_divergence(thinned, script)

    assert refusal is not None, (
        "the name the script gives an enumerated attribute was carried by no row and the binding "
        "said nothing -- renaming that constant would leave the table stale and the suite green"
    )
    assert enumerated in refusal, (
        f"the refusal must name the value that went missing; got {refusal!r}"
    )


def test_a_declared_type_the_generator_cannot_read_is_caught() -> None:
    """⛔ The other direction: a hand edit, or an older generator's productions."""
    script = derivation(_SPECIFIED)
    widened = [
        *_specified_containers.SPECIFIED_ATTRIBUTES,
        (_INVENTED_ELEMENT, _INVENTED_ATTRIBUTE, _INVENTED_TYPE),
    ]

    refusal = declared_type_divergence(widened, script)

    assert refusal is not None, (
        "the table carried a declared type XML's AttType production does not have and the "
        "binding said nothing, so a hand-edited column would reach the audit unremarked"
    )
    assert _INVENTED_TYPE in refusal, (
        f"the refusal must name the type nothing produces; got {refusal!r}"
    )


# ---------------------------------------------------------------------------
# Check three: the positive controls.
#
# ⚠️ **A round trip that has stopped being sensitive to its inputs passes
# forever**, and it passes for the same reason a correct one does. Each control
# below asserts the comparison FAILS where it must.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pair", PAIRS, ids=_IDENTIFIED)
def test_an_invented_row_makes_the_round_trip_fail(pair: Pair) -> None:
    """The adapter wired the rows through rather than handing ``emit`` a constant."""
    arguments = pair.arguments()
    arguments[pair.rows_argument] = [*arguments[pair.rows_argument], pair.invented_row]

    refusal = reproduction_divergence(pair, arguments)

    assert refusal is not None, (
        f"a row no published source states was appended to {pair.committed}'s data and the "
        "round trip still passed, so the comparison is not reading the argument it is given"
    )
    assert pair.committed in refusal, f"the failure must name which pair drifted; got {refusal!r}"


@pytest.mark.parametrize("pair", PAIRS, ids=_IDENTIFIED)
def test_a_moved_generator_header_makes_the_round_trip_fail(
    pair: Pair, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ The half of the round trip that is NOT vacuous, asserted as a control.

    The header is the generator's own text rather than the table's, so this is
    the drift the round trip is genuinely for: a generator edited without the
    table being regenerated.
    """
    script = derivation(pair)
    monkeypatch.setattr(script, "_HEADER", script._HEADER + "\n")
    committed = committed_path(pair).read_text(encoding="utf-8")
    emitted: str = script.emit(*pair.arguments())

    assert first_divergence(committed, emitted) is not None, (
        f"the generator's header moved and {pair.committed} still reproduced, so the "
        "comparison is not seeing the generator's own text at all"
    )


# ---------------------------------------------------------------------------
# Check four: the BOM, and discovery.
# ---------------------------------------------------------------------------


def test_a_bom_on_a_committed_table_is_refused_by_name(tmp_path: Path) -> None:
    """⛔ Over a temporary copy, never by touching a tracked file.

    ⚠️ **The failure must name issue #47 and ``cmd /c``**, because the reader who
    meets it has almost certainly just re-derived the table CORRECTLY through
    PowerShell, and every other message would send them looking for a defect in
    the derivation.
    """
    invented = tmp_path / "_an_invented_table.py"
    invented.write_bytes(_BOM + b'"""An invented module."""\n')

    refusal = bom_refusal(invented.name, invented.read_bytes())

    assert refusal is not None, (
        "a module beginning with a UTF-8 BOM was accepted, so a re-derivation redirected "
        "through PowerShell would commit three bytes no generator emits"
    )
    assert "#47" in refusal, f"the refusal must name the issue that owns this; got {refusal!r}"
    assert "cmd /c" in refusal, (
        f"the refusal must name the redirection that avoids it; got {refusal!r}"
    )


def test_a_table_without_a_bom_is_not_refused_for_one(tmp_path: Path) -> None:
    """The other direction, so the check above cannot be a constant refusal."""
    invented = tmp_path / "_an_invented_table.py"
    invented.write_bytes(b'"""An invented module."""\n')

    assert bom_refusal(invented.name, invented.read_bytes()) is None, (
        "a module with no BOM was refused for having one, which would make every "
        "reproduction report the wrong repair"
    )


def test_every_derivation_script_has_a_round_trip() -> None:
    """⛔ So a fourth derived table cannot arrive without this check reaching it.

    ⚠️ **A check whose case table is maintained by hand covers what somebody
    remembered.** The naming is already regular -- ``derive_X.py`` prints
    ``core/_X.py`` for all three -- so the scripts directory itself is the
    inventory, and a new generator fails here until it is listed above.
    """
    found = sorted(path.name for path in (REPOSITORY_ROOT / SCRIPT_DIRECTORY).glob("derive_*.py"))
    covered = sorted(pair.generator for pair in PAIRS)

    assert found == covered, (
        f"{SCRIPT_DIRECTORY}/ holds {found} and this file covers {covered}. A derived table "
        "whose generator is not listed here is one nothing checks against its own generator, "
        "which is the state issue #238 was filed about."
    )


def test_every_case_names_a_generator_and_a_module_that_exist() -> None:
    """The case table's paths are real, so a typo cannot quietly cover nothing."""
    missing = [
        f"{SCRIPT_DIRECTORY}/{pair.generator}" for pair in PAIRS if not script_path(pair).is_file()
    ] + [
        f"{COMMITTED_DIRECTORY}/{pair.committed}"
        for pair in PAIRS
        if not committed_path(pair).is_file()
    ]

    assert missing == [], (
        f"these cases name files this checkout does not hold: {missing} -- a case whose "
        "paths are wrong is a pair nothing checks"
    )
