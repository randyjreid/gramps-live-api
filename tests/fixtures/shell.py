"""Find the shell a test's subject must run under, deliberately.

⚠️ **Never by looking the name up on PATH.** Measured on the development machine
this suite is written on, ``bash`` answers with the Windows Subsystem launcher in
the system directory -- a different operating system, with a different filesystem
view and a different or absent Git. A step half-driven there exits non-zero, which
reads **exactly like** the step correctly refusing to resolve a range. A harness
that cannot tell its own breakage from the property it asserts is the fail-open
this whole test suite exists to close, one level up.

So on Windows the shell is derived from Git, which every test that wants one
already requires, and then **probed**. On any other platform the PATH lookup
stays, and that is deliberate rather than an omission: there, PATH cannot hand
back a shell belonging to another operating system, so the failure this module
exists for is not reachable.

Two flavours, because the two callers need different things:

* ``posix_shell()`` -- **bash**, for the workflow steps. ``ci.yml`` writes
  ``set -euo pipefail``, which is not a ``/bin/sh`` guarantee.
* ``posix_shell(flavour="sh")`` -- **sh**, for the pre-push hook. Git runs hooks
  through ``sh``, the hook declares ``#!/bin/sh``, and on Linux that is dash.
  Quietly upgrading it to bash would retire the portability coverage
  ``test_the_committed_hook_has_no_CARRIAGE_RETURNS`` exists to protect.

⛔ **Under no branch does the Subsystem launcher become the fallback.** It does
not live under the Git distribution root, so on Windows it is unreachable by
construction rather than by an exclusion list -- and the probe below refuses it a
second time, on its behaviour rather than on its path.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

Flavour = Literal["bash", "sh"]

_MARKER = "glapi-shell-probe"

# ⛔ **Two questions, and the second one is the whole point of this module.**
#
# ⚠️ *Can it see Git* was the only question here before, and the Subsystem
# launcher **passes it** whenever Git is installed inside the Subsystem. It is
# still asked, because a shell that cannot see Git cannot drive a workflow step
# and its failure is indistinguishable from the step refusing a range.
#
# ⚠️ *Does it resolve the PATH ITS CALLER BUILT* is the question that was
# missing. Both callers construct a PATH in Windows form, prepend a directory to
# it, and then depend on the shell finding what is in that directory first.
# Inside the Subsystem the translated Windows entries are **appended after** the
# Linux ones, which is exactly how its own ``python3`` beat a planted stub and
# turned a test of an unrunnable gate into a test of a working one.
#
# ⭐ Applied to both flavours: it is the same hazard, and the workflow fixture
# inherits it just as the hook fixture did.
_PROBE = """\
set -u
command -v git >/dev/null 2>&1 || { echo 'this shell cannot see git'; exit 3; }
directory=$(cd "${GLAPI_PROBE_DIRECTORY:-}" 2>/dev/null && pwd) || directory=''
if [ -z "$directory" ]; then
    echo 'this shell cannot reach the directory the probe prepended to PATH'
    exit 4
fi
where=$(command -v "$GLAPI_PROBE_MARKER" 2>/dev/null) || where=''
if [ -z "$where" ]; then
    echo 'this shell did not find the marker the probe put first on PATH'
    exit 5
fi
case "$where" in
    "$directory"/*) ;;
    *)
        echo "this shell resolved the marker outside the prepended directory"
        exit 6
        ;;
esac
"""


def _candidates(flavour: Flavour) -> list[Path]:
    if os.name != "nt":
        found = shutil.which(flavour)
        return [Path(found)] if found else []

    exec_path = subprocess.run(
        ["git", "--exec-path"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # .../<git>/mingw64/libexec/git-core -- the distribution root is three up,
    # and it ships both shells in both of the places named below.
    root = Path(exec_path).parents[2]
    if flavour == "bash":
        return [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    return [root / "usr" / "bin" / "sh.exe", root / "bin" / "sh.exe"]


def _answers_for_the_path_its_caller_builds(candidate: Path) -> bool:
    """Does this shell see Git, and does it resolve a directory prepended to PATH?

    The marker is written and looked up rather than reasoned about, because the
    translation a shell applies to an inherited Windows PATH is not something a
    caller can predict from the shell's path on disk.
    """
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        for name in (_MARKER, f"{_MARKER}.bat"):
            marker = directory / name
            marker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
            marker.chmod(0o755)
        probe = subprocess.run(
            [str(candidate), "-c", _PROBE],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env={
                **os.environ,
                "PATH": str(directory) + os.pathsep + os.environ.get("PATH", ""),
                # Forward slashes: the shell reads this out of its own
                # environment, and a backslash inside double quotes is not a
                # separator there.
                "GLAPI_PROBE_DIRECTORY": str(directory).replace("\\", "/"),
                "GLAPI_PROBE_MARKER": _MARKER,
            },
        )
        return probe.returncode == 0


@functools.lru_cache(maxsize=2)
def posix_shell(flavour: Flavour = "bash") -> Path:
    """A shell that exists and answers correctly, or a raised error naming what was tried.

    ⛔ It raises rather than skipping. A POSIX shell here is not a capability the
    operating system withholds, it is a component of Git, and a silent skip would
    retire the only evidence these fixtures produce. A caller that has a reason to
    treat the absence as untestable converts the error itself, and says why.
    """
    tried = _candidates(flavour)
    for candidate in tried:
        if not candidate.exists():
            continue
        if _answers_for_the_path_its_caller_builds(candidate):
            return candidate
    raise RuntimeError(
        f"no {flavour} able to run what this suite drives was found. A shell that "
        "cannot see Git, or that does not resolve the PATH its caller built, cannot "
        "be told apart from the thing under test failing. Tried: "
        f"{[str(path) for path in tried]}"
    )
