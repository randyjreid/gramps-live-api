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
        run("pytest", python, "-m", "pytest", "-q")

    base = "origin/main"
    print(f"  {'pii_guard':<28}", end="", flush=True)
    if not git("rev-parse", "--verify", base):
        print(f"SKIPPED -- no {base} to compare against")
    elif git("rev-list", "--count", f"{base}..HEAD") in ("", "0"):
        # ⭐ ``pii_guard`` REFUSES an empty range -- *a range covering nothing is
        # never a pass* -- which is the principle this whole file is built on, so
        # the skip is announced rather than swallowed.
        print(f"SKIPPED -- nothing committed on top of {base} yet")
    else:
        print()
        run(
            "pii_guard",
            python,
            "-m",
            "gramps_live_api.core.pii_guard",
            "--range",
            f"{base}..HEAD",
            ".",
        )

    print("  ALL GATES PASS (exit 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
