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
# missing, and the two callers lean on it to different depths.
#
# The hook fixture constructs a PATH in Windows form and **prepends directories
# to it** -- a shadow of interpreter stubs that must all fail, and the utility
# directory git hands a hook -- then depends on the shell finding what is in
# them first. Inside the Subsystem the translated Windows entries are **appended
# after** the Linux ones, which is exactly how its own ``python3`` beat a planted
# stub and turned a test of an unrunnable gate into a test of a working one.
#
# ``pushes.py`` prepends nothing, and saying otherwise here was false. What it
# does is hand the shell the Windows-form PATH this process already holds, and a
# Windows working directory, and depend on the shell resolving the same tools
# out of them. The ordering above cannot bite it; a shell answering out of
# another operating system's filesystem still can.
#
# ⭐ So the probe builds its OWN prepend rather than reading either caller's:
# what it measures is then the shell, which is the thing both callers cannot
# predict from a path on disk. Applied to both flavours because the
# disqualifying condition is the one shell property, not either caller's use.
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


def _distribution_root() -> Path:
    """The Git for Windows installation root, derived from where git keeps its helpers."""
    exec_path = subprocess.run(
        ["git", "--exec-path"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # .../<git>/mingw64/libexec/git-core -- the distribution root is three up.
    return Path(exec_path).parents[2]


def _candidates(flavour: Flavour) -> list[Path]:
    if os.name != "nt":
        found = shutil.which(flavour)
        return [Path(found)] if found else []

    # The distribution ships both shells in both of the places named below.
    root = _distribution_root()
    if flavour == "bash":
        return [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    return [root / "usr" / "bin" / "sh.exe", root / "bin" / "sh.exe"]


def utility_directory(shell: Path) -> Path:
    """The directory holding the ``tr``, ``sed`` and ``grep`` a hook's shell reaches.

    ⛔ **Not ``shell.parent``**, which is right for the first candidate and an
    accident for the second: the distribution's ``usr`` subtree holds the whole
    utility set, ``tr`` among it, while its top-level ``bin`` holds ``git``,
    ``sh`` and ``bash`` and nothing else.

    ⚠️ **And "an accident" is the measured word, not "wrong".** The shell converts
    an inherited Windows PATH entry into a POSIX one, and its runtime then
    resolves the top-level ``bin`` onto the ``usr`` one behind it: handed only
    that three-executable directory, ``command -v tr`` answers out of it
    perfectly happily. So the fallback candidate's own directory would have
    supplied the utilities after all, and **no test in this repository can tell
    the two derivations apart** -- recorded rather than papered over, because
    claiming a defect that cannot be shown breaking is worth less than saying
    plainly that it cannot.

    ⭐ What the change buys is that the answer no longer rests on that mapping,
    which is a property of the runtime rather than of anything this suite states,
    and no longer depends on which candidate happened to answer. It is derived
    the way ``_candidates`` derives the shells themselves, from the distribution
    root.

    Off Windows the shell's own directory IS the utility directory -- there is no
    second layout to be wrong about, and ``_candidates`` locates the shell there
    by the same PATH lookup.
    """
    if os.name != "nt":
        return shell.parent
    return _distribution_root() / "usr" / "bin"


def shells_installed_beside_git(flavour: Flavour) -> list[Path]:
    """Every shell of this flavour a Git installation on this machine actually ships.

    ⛔ **A cross-check, never a source.** Nothing found here is returned to a
    caller as a shell to run. It exists so that a caller converting the error
    ``posix_shell`` raises can tell *"this machine has no POSIX shell"* from
    *"this module failed to locate the one it has"*. The first may honestly be
    skipped. The second is a defect in the locating logic, and a skip there
    retires every test that wanted a shell while reporting that there was
    nothing to cover.

    ⚠️ **The mechanism is deliberately a different one from ``_candidates``:**
    the git BINARY's own location, rather than ``git --exec-path`` -- which is a
    documented variable ``GIT_EXEC_PATH`` points anywhere it likes, and which is
    exactly how the derivation goes wrong while a working shell sits on disk.
    Agreement between two readings of the same source would prove nothing,
    because when that source is wrong both readings are wrong together.

    ⚠️ Best effort, and bounded on purpose: a ``git`` that is a shim somewhere
    unrelated to its distribution finds nothing here, and the caller falls back
    to the weaker answer. What it cannot do is report a shell that is not there,
    and that is the direction a wrong answer would be dangerous in.

    Empty off Windows, where nothing converts the error and ``shutil.which`` is
    already the locator.
    """
    if os.name != "nt":
        return []
    binary = shutil.which("git")
    if binary is None:
        return []
    found: list[Path] = []
    for ancestor in Path(binary).resolve().parents:
        for relative in (Path("usr") / "bin", Path("bin")):
            shell = ancestor / relative / f"{flavour}.exe"
            if shell.exists():
                found.append(shell)
    return found


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
