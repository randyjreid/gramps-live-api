"""⛔ What a child speaks, and what ``gate.py`` assumes it speaks.

``run()`` decodes captured output as UTF-8. That is not a property of the
children -- it is a property ``run()`` has to CREATE, because the steps it
invokes do not agree:

* ``ruff`` is Rust and writes UTF-8 whatever the locale says;
* ``mypy``, ``pytest`` and ``pii_guard`` are Python, and a **redirected**
  Python stdout uses ``locale.getpreferredencoding()`` -- cp1252 on the
  maintainer's box.

⚠️ **So the UTF-8 decode was right for one half and wrong for the other**, and
the wrongness was silent: a Python child's ``e``-acute arrived as ``b'\\xe9'``
and the decode replaced it with U+FFFD. The gate still failed correctly; the
operator was just shown a corrupted reason.

⛔ **Every test here sets a HOSTILE parent encoding first**, and that is the
whole design of this file rather than a detail of it.

⚠️ **The obvious version of these tests is vacuous, and was written before this
one.** A child inherits its parent's environment, so a suite run under a UTF-8
parent gets a UTF-8 child **whether or not ``run()`` does anything** -- the
tests passed with the fix deleted. That is this project's recorded *silent
control*: a check succeeding for a reason unrelated to the property it names.

⭐ Pinning the parent to ``cp1252`` removes the inheritance, so the only way the
child can report UTF-8 is if ``run()`` overrode it. It also makes these bind on
**CI's Linux runners**, where the ambient locale is UTF-8 and a
platform-dependent version of this file would prove nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# ⛔ ``scripts`` is not a package and is not importable by name. Loaded by path,
# which is also how a contributor runs it.
_spec = importlib.util.spec_from_file_location("_gate_enc", ROOT / "scripts" / "gate.py")
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
sys.modules["_gate_enc"] = gate
_spec.loader.exec_module(gate)


# ⛔ Two characters, chosen for OPPOSITE failure modes -- one corrupts, one
# kills the child. A single sample would have bound only half the defect.
IN_CP1252 = "é"  # e-acute: cp1252 CAN encode it, so the child survives and lies
NOT_IN_CP1252 = "→"  # rightwards arrow: cp1252 cannot, so the child DIES


@pytest.fixture
def hostile_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ The parent claims cp1252, so inheritance cannot supply the answer."""
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    monkeypatch.delenv("PYTHONUTF8", raising=False)


def _child_printing(text: str) -> tuple[str, ...]:
    """A failing Python child that prints ``text`` first.

    ⚠️ It must exit NON-ZERO: ``run()`` forwards a child's output only on
    failure, which is the only path where the operator ever sees it.
    """
    return (sys.executable, "-c", f"print({text!r})\nraise SystemExit(1)")


@pytest.mark.parametrize("sample", [IN_CP1252, NOT_IN_CP1252], ids=["in-cp1252", "not-in-cp1252"])
@pytest.mark.usefixtures("hostile_parent")
def test_a_python_childs_non_ascii_diagnostic_reaches_the_operator(
    sample: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """⭐ The property: what the child printed is what the operator reads.

    Without the override, ``é`` becomes U+FFFD and ``→`` never arrives at all --
    the child dies encoding it, and the gate reports that traceback instead of
    the failure it was run to find.
    """
    with pytest.raises(SystemExit):
        gate.run("encoding probe", *_child_printing(sample))

    assert sample in capsys.readouterr().out


@pytest.mark.usefixtures("hostile_parent")
def test_the_child_is_TOLD_to_speak_utf8_rather_than_inheriting_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ The mechanism, asserted on ``run()``'s OWN child.

    ⚠️ An earlier version of this test called ``run()`` and then asserted a
    **separate** subprocess it built itself -- so it passed no matter what
    ``run()`` did. It is the child ``run()`` launches that has to answer.
    """
    probe = (sys.executable, "-c", "import sys; print(sys.stdout.encoding)\nraise SystemExit(1)")

    with pytest.raises(SystemExit):
        gate.run("encoding probe", *probe)

    # ``utf-8``/``UTF-8``/``utf8`` are all spellings Python may report back.
    reported = capsys.readouterr().out.strip().splitlines()[-1]
    assert reported.strip().lower().replace("-", "") == "utf8"


@pytest.mark.usefixtures("hostile_parent")
def test_the_override_does_not_discard_the_rest_of_the_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """⛔ A child that speaks UTF-8 and can no longer find anything is not a fix.

    ⚠️ ``env=`` REPLACES the environment rather than adding to it, so building
    it from a bare dict would strip ``PATH``, ``SYSTEMROOT`` and the virtualenv
    -- every step would then fail for a reason having nothing to do with
    encoding. The spread is what keeps it additive, and nothing else asserts it.
    """
    probe = (
        sys.executable,
        "-c",
        "import os, sys; print(bool(os.environ.get('PATH')))\nraise SystemExit(1)",
    )

    with pytest.raises(SystemExit):
        gate.run("environment probe", *probe)

    assert capsys.readouterr().out.strip().splitlines()[-1] == "True"
