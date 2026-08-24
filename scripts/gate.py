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

import os
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
    """Git's stdout, or ``""`` if it failed. ⚠️ **The two are indistinguishable.**

    ⛔ Only for questions where *failed* and *empty* deserve the same answer --
    ``rev-parse --verify`` on a ref that may not exist is exactly that. For
    anything where a failure must not read as an empty result, use ``git_or_die``.
    """
    finished = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True, check=False)
    return finished.stdout.strip() if finished.returncode == 0 else ""


def git_or_die(label: str, *args: str) -> str:
    """Git's stdout, ABORTING if the command failed.

    ⚠️ **``git`` above collapses failure into the empty string, and an empty
    string is a real answer to several of the questions this file asks.** A
    ``rev-list --count`` that dies on a missing or corrupt object returns ``""``,
    which reads as *zero commits*, which selects the index-only scan -- and the
    gate then prints ALL GATES PASS without ever looking at the branch history.

    ⛔ **A command that failed is not a command that answered.** Same shape as a
    PowerShell ``-ErrorAction SilentlyContinue`` turning a wrong query into an
    empty result, which is recorded in CONTRIBUTING for the same reason.
    """
    finished = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True, check=False)
    if finished.returncode != 0:
        print(f"  {label:<28}FAILED -- git could not answer (exit {finished.returncode})")
        sys.stderr.write(finished.stderr[-2000:])
        raise SystemExit(finished.returncode)
    return finished.stdout.strip()


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
    # ⛔ **An UNRESOLVABLE baseline REFUSES. It does not quietly scan less.**
    #
    # ⚠️ The previous version treated "no committed range" and "no baseline at
    # all" as the same case and ran the index-only scan for both. They are not the
    # same case. With a resolvable baseline and an empty range, the index IS
    # everything this branch adds, so index-only is complete. **With no baseline,
    # the range is unknown** -- and a branch that ADDS a file with personal data
    # and DELETES it again ends at a clean tip, passes an index-only scan, and
    # publishes the blob anyway. That is precisely what ``--range`` exists to
    # catch.
    #
    # ⚠️⚠️ **And the earlier fix made this worse rather than merely leaving it.**
    # The skip it replaced at least printed SKIPPED; the replacement printed
    # ``ok``, so coverage narrowed while the report got more confident. **A
    # regression that reads as an improvement is the worst shape this class
    # takes.**
    #
    # ⭐ ``GRAMPS_LIVE_API_GATE_BASE`` exists so that a refusal is not a dead end:
    # a clone whose canonical remote is ``upstream`` names it and carries on. A
    # gate nobody can satisfy gets worked around, and a gate worked around is not
    # a gate.
    # ⛔ **The baseline is operator-supplied and is NEVER echoed.**
    #
    # ⚠️ ``GRAMPS_LIVE_API_GATE_BASE`` is whatever someone typed, and the mistake
    # that puts it on this path is typing a PATH where a ref belongs -- so the
    # failure message is exactly where an absolute path would land, verbatim, in
    # captured output and CI logs. **The guard's own rule is that revision
    # expressions are operator-supplied and must not be echoed**, and a gate
    # script leaking one while reporting on leaks is the joke telling itself.
    #
    # ⭐ The remediation does not need the value: the person who set it can read
    # it back, and the person who did not set it wants the default named, which is
    # a constant in this file rather than an input.
    configured = "GRAMPS_LIVE_API_GATE_BASE" in os.environ
    base = os.environ.get("GRAMPS_LIVE_API_GATE_BASE", "origin/main")
    if not git("rev-parse", "--verify", base):
        source = "the ref named by GRAMPS_LIVE_API_GATE_BASE" if configured else "origin/main"
        print(f"  {'pii_guard':<28}FAILED -- cannot resolve the baseline")
        print(f"    The history scan needs a baseline, and {source} does not resolve here.")
        print("    Scanning only the index would miss a branch that adds personal data")
        print("    and deletes it again, which still publishes the blob.")
        print("    Fetch it (git fetch origin main), or name the right one:")
        print("        GRAMPS_LIVE_API_GATE_BASE=<remote>/main python scripts/gate.py")
        raise SystemExit(2)

    scope: list[str] = []
    # ⛔ ``git_or_die``: a rev-list that FAILS must not read as "zero commits".
    if git_or_die("pii_guard", "rev-list", "--count", f"{base}..HEAD") in ("", "0"):
        # Nothing committed on top of the baseline, so the index is the whole of
        # what this branch adds and the range would cover nothing.
        print(f"  {'pii_guard':<28}(nothing committed on top of the baseline -- index only)")
    else:
        scope = ["--range", f"{base}..HEAD"]
    run("pii_guard", python, "-m", "gramps_live_api.core.pii_guard", *scope, ".")

    print("  ALL GATES PASS (exit 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
