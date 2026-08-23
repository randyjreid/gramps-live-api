"""Every gate, read by EXIT CODE. ⛔ Nothing here parses output.

**This exists because the gates were being read wrong, not run wrong.**
``ruff check . | tail -1`` printed a note about unsafe fixes and hid the
``Found 1 error.`` line above it, so a red gate reported clean for a whole
session and CI caught what the local gate did not.

⚠️ **Two rules are enforced by the shape of this file rather than by care:**

* the first failing step **aborts** -- nothing downstream can run on a broken
  tree and report success;
* every check is a subprocess whose **return code is the answer.** No pipes to
  ``tail``, no grepping for the word *passed*, nothing that can succeed while the
  thing it names has failed.

⚠️ **Python rather than a shell script, deliberately.** ``pii_guard`` refuses a
file type it cannot prove safe, and ``.sh`` is not on its list -- **widening a
safety guard's allowlist to admit a convenience file is the wrong trade** when
the two scripts already here are ``.py`` and this works identically.

Usage::

    python scripts/gate.py           # the whole gate
    python scripts/gate.py --quick   # skip the slow suite
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(label: str, *command: str) -> None:
    """One gate. ⛔ Its RETURN CODE is the verdict; its output is not consulted."""
    print(f"  {label:<28}", end="", flush=True)
    finished = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if finished.returncode != 0:
        print(f"FAILED (exit {finished.returncode})")
        sys.stdout.write(finished.stdout[-4000:])
        sys.stderr.write(finished.stderr[-4000:])
        raise SystemExit(finished.returncode)
    print("ok")


def run_visible(label: str, *command: str) -> None:
    """One gate, with its output left ON SCREEN. ⛔ Still judged by return code.

    ⚠️ **Not a softening of this file's rule.** The rule is that nothing *decides*
    from output; showing it to the person running the gate is the opposite of
    parsing it. ``run`` swallows stdout on success, which is right for a linter
    and wrong for ``pytest -rs``: the skip report is printed on a PASS, so
    capturing and discarding it recreates the exact defect ``-rs`` exists to
    prevent -- **a skip nobody can see reads exactly like a pass** (#31).
    """
    print(f"  {label:<28}(output follows)")
    finished = subprocess.run(command, cwd=ROOT, check=False)
    if finished.returncode != 0:
        print(f"  {label:<28}FAILED (exit {finished.returncode})")
        raise SystemExit(finished.returncode)
    print(f"  {label:<28}ok")


def git(*args: str) -> str:
    finished = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True, check=False)
    return finished.stdout.strip() if finished.returncode == 0 else ""


def main() -> int:
    quick = "--quick" in sys.argv
    python = sys.executable

    # ⛔ The tree is named before anything is measured. A refused checkout once
    # left three branches "measured" while a fourth was actually checked out, and
    # the results were reported under the wrong names.
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "(unknown)"
    dirty = "dirty" if git("status", "--porcelain") else "clean"
    print(f"  {'branch':<28}{branch} ({dirty})")

    run("ruff format", python, "-m", "ruff", "format", "--check", ".")
    run("ruff check", python, "-m", "ruff", "check", ".")
    run("mypy", python, "-m", "mypy", "src")
    if not quick:
        # ⛔ ``-rs``, which CONTRIBUTING requires, and its report is left visible.
        # ``-q`` with the output discarded said "pytest ok" while hiding which
        # tests had not run and why.
        run_visible("pytest", python, "-m", "pytest", "-rs")

    # ⛔ **The guard ALWAYS runs. There is no path here that skips it and then
    # prints ALL GATES PASS.**
    #
    # ⚠️ It used to skip when ``HEAD`` had no commits beyond ``origin/main`` --
    # which is the NORMAL state while preparing a branch's first commit. Staged
    # personal data was therefore never scanned, and the script said ALL GATES
    # PASS anyway: **a gate reporting success for a reason unrelated to the
    # property it names, inside the file written to end that class.**
    #
    # ⭐ Measured, not assumed: in a throwaway repository with no ``HEAD`` at all
    # and a drive-lettered path only ``git add``-ed, the guard exits 1. Repository
    # mode reads the INDEX (``git ls-files --stage`` then ``cat-file blob``),
    # which is what a commit publishes -- so it gates a first commit exactly as
    # well as a later one. Without ``--range`` is not a weaker scan; it is the
    # same scan without the extra history blobs a range adds.
    base = "origin/main"
    scope: list[str] = []
    if git("rev-parse", "--verify", base) and git("rev-list", "--count", f"{base}..HEAD") not in (
        "",
        "0",
    ):
        scope = ["--range", f"{base}..HEAD"]
    else:
        print(f"  {'pii_guard':<28}(no committed range yet -- tracked content only)")
    run("pii_guard", python, "-m", "gramps_live_api.core.pii_guard", *scope, ".")

    print("  ALL GATES PASS (exit 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
