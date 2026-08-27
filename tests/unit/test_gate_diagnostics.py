"""⛔ The gate's suppression key, and the command it offers instead.

``scripts/gate.py`` withholds a failing command's diagnostics when the command
line carried something a person typed, because a tool's stderr quotes its
arguments back and the mistake that reaches these paths is a **path** typed
where a ref belongs.

⚠️ **Suppression is not free: it costs the operator the finding.** So the key
has to be exactly right, and it has now been wrong twice -- ``bool(scope)``
alone, then ``configured`` alone. This file is why there will not be a third.

⭐ **No subprocess, no git.** The condition is a function of two values, and
that is the whole of what these tests need.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# ⛔ ``scripts`` is not a package and is not importable by name. Loaded by path,
# which is also how a contributor runs it.
_spec = importlib.util.spec_from_file_location("_gate", ROOT / "scripts" / "gate.py")
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
sys.modules["_gate"] = gate
_spec.loader.exec_module(gate)


# (configured, scope, withheld, why)
KEY = (
    (
        False,
        [],
        False,
        "nothing configured and no range: the command is this file's own constant",
    ),
    (
        False,
        ["--range", "origin/main..HEAD"],
        False,
        "the ordinary failure path -- the baseline is the constant, and keying on "
        "scope alone discarded pii_guard's own already-redacted findings here",
    ),
    (
        True,
        [],
        False,
        "GRAMPS_LIVE_API_GATE_BASE resolved to HEAD, so the range covers nothing "
        "and was dropped -- the command carries no operator value at all",
    ),
    (
        True,
        ["--range", "typo..HEAD"],
        True,
        "configured AND carried: this is the only shape that can echo back a path "
        "typed where a ref belongs",
    ),
)


@pytest.mark.parametrize("configured, scope, withheld, why", KEY)
def test_diagnostics_are_withheld_only_when_the_command_really_carries_input(
    configured: bool, scope: list[str], withheld: bool, why: str
) -> None:
    """⛔ All four combinations, named. Two of them were once wrong."""
    assert gate.carries_operator_input(configured, scope) is withheld, why


def test_the_case_that_had_NO_WAY_OUT_is_the_one_that_now_shows_them() -> None:
    """⛔ Configured to HEAD, staged personal data, and no path to the finding.

    ⚠️ Diagnostics were withheld **and** the rerun offered alongside them added
    ``--range <base>..HEAD``, which the guard refuses outright -- *"the given
    range covers no commits"*. So the operator was handed a suppressed
    diagnostic and a command that could not produce it either.

    ⭐ This asserts the half that is this file's to assert: in that shape,
    nothing is withheld. The rerun is never printed when nothing is withheld,
    so the unrunnable pairing cannot recur.
    """
    assert gate.carries_operator_input(True, []) is False


def test_the_rerun_hint_is_offered_for_BOTH_SHELLS() -> None:
    """⛔ ``$env:NAME`` is PowerShell-only, and the hint was PowerShell-only.

    ⚠️ Run in bash it expands to ``:GRAMPS_LIVE_API_GATE_BASE..HEAD``, which git
    reads as a **path** -- *"path 'GRAMPS_LIVE_API_GATE_BASE..HEAD' does not
    exist"*. The project's docs are PowerShell throughout; CI and contributors
    are not. **An advertised recovery command that cannot be followed is exactly
    what the finding this replaced was about.**

    ⭐ Asserted against the source of ``main`` rather than against a captured
    run, because the failing run needs staged personal data to provoke -- and
    the thing that must not regress is that both spellings are there at all.
    """
    source = (ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
    assert '"$env:GRAMPS_LIVE_API_GATE_BASE..HEAD"' in source, (
        "the PowerShell spelling of the rerun hint is gone"
    )
    assert '"$GRAMPS_LIVE_API_GATE_BASE..HEAD"' in source, (
        "the POSIX spelling of the rerun hint is gone -- in bash the PowerShell "
        "one expands to ':GRAMPS_LIVE_API_GATE_BASE..HEAD' and git reads it as a path"
    )


def test_a_multi_line_hint_is_printed_as_lines_rather_than_as_one_string() -> None:
    """⚠️ Two shells means two lines, and ``run`` used to print one string.

    ⭐ ``rerun`` is a **sequence of lines**, so no escape appears in the gate's
    source at all -- which is worth stating, because getting a literal newline
    into that string through three layers of quoting is where this went wrong.
    """
    import inspect

    signature = inspect.signature(gate.run)
    assert signature.parameters["rerun"].default == (), (
        "rerun should default to an empty sequence, not to a string"
    )
