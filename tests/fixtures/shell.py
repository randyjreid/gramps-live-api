"""Find the shell the workflow's steps are written for, deliberately.

⚠️ **Never by looking ``bash`` up on PATH.** Measured on the development machine
this suite is written on, that answers with the Windows Subsystem launcher in
the system directory -- a different filesystem view, and a different or absent
Git. A step half-driven there exits non-zero, which reads **exactly like** the
step correctly refusing to resolve a range. A harness that cannot tell its own
breakage from the property it asserts is the fail-open this whole test file
exists to close, one level up.

So the shell is derived from Git, which every test in this suite already
requires, and then **probed**: it has to be able to answer where Git is. If it
cannot, that raises. It is not a skip -- a POSIX shell here is not a capability
the operating system withholds, it is a component of Git, and skipping would
retire the only evidence that the pushed-range arithmetic covers what a push
publishes.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path


def _candidates() -> list[Path]:
    if os.name != "nt":
        found = shutil.which("bash")
        return [Path(found)] if found else []

    exec_path = subprocess.run(
        ["git", "--exec-path"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # .../<git>/mingw64/libexec/git-core -- the distribution root is three up,
    # and it ships the shell in both of the places named below.
    root = Path(exec_path).parents[2]
    return [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]


@functools.lru_cache(maxsize=1)
def posix_shell() -> Path:
    """A shell that exists and can see Git, or a raised error naming what was tried."""
    tried = _candidates()
    for candidate in tried:
        if not candidate.exists():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "command -v git"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return candidate
    raise RuntimeError(
        "no shell able to run the workflow's steps was found. A shell that cannot "
        "see Git cannot drive them, and its failure is indistinguishable from the "
        f"step refusing to resolve a range. Tried: {[str(path) for path in tried]}"
    )
