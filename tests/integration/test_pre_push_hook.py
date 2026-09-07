"""⛔ The publication gate: does the hook actually refuse a push?

``pii_guard`` is heavily tested and correct at what it does. **Nothing tested
that it was INVOKED** -- and it was not: no hook, no ``.pre-commit-config.yaml``,
no ``core.hooksPath``, and CI running ``on: push``, which is after GitHub already
holds the objects. Issue #171.

⚠️ **A hook that never fires and a hook that fires on everything look identical
to someone who tested one direction.** So every case here is run both ways, in a
throwaway repository, against the real hook file.

⛔ These tests drive the hook the way git does -- executing the file with the
ref line on stdin -- rather than importing anything from it. What must not
regress is the behaviour git will see.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.shell import posix_shell, shells_installed_beside_git, utility_directory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "pre-push"
ZERO = "0" * 40

# ⛔ A string the guard is known to flag, built at runtime rather than written
# here as a literal. Writing a drive-letter path into this file would make the
# file itself a finding, and the repository's own gate would refuse it -- which
# is the guard working, and would look like this test failing.
PLANTED = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "thing.txt"


def _hook_shell() -> str:
    """⛔ The shell git runs hooks through, PINNED rather than looked up on PATH.

    ⚠️ **This used to ask PATH for ``sh`` and then for ``bash``, so the answer was
    supplied by whoever launched pytest.** From a shell where ``sh`` does not
    resolve, that fell through to the Windows Subsystem launcher -- a different
    operating system, where the ``;``-separated Windows PATH this file constructs
    does not apply at all. The hook then found the Subsystem's own ``python3``,
    ran the guard for real, and allowed the clean push it was handed, so the test
    written to prove that an unrunnable gate is refused went red on a hook that
    was behaving correctly. Issue #225.

    ⭐ ``posix_shell`` derives it from ``git --exec-path`` on Windows and probes
    it, so the launcher is unreachable by construction rather than by an
    exclusion list. ``flavour="sh"`` and not bash: git runs hooks through ``sh``,
    the hook declares ``#!/bin/sh``, and on Linux that is dash -- the portability
    ``test_the_committed_hook_has_no_CARRIAGE_RETURNS`` exists to protect.
    """
    try:
        return str(posix_shell(flavour="sh"))
    except RuntimeError as absent:
        # ⛔ Converted to a skip HERE, and only on Windows. The fixture keeps
        # raising, because on Linux a missing sh means a broken container and a
        # suite that skips there fails open (#31).
        if os.name != "nt":
            raise

        # ⛔ **Two states, and only one of them is a skip.** The brief for this
        # conversion was: acceptable when no suitable shell EXISTS, not
        # acceptable when it hides one. Measured, it was hiding one -- with
        # ``GIT_EXEC_PATH`` set, a documented variable ``git --exec-path``
        # honours, the derivation three directories up points nowhere, and the
        # run reported **thirteen skips** while ``usr/bin/sh.exe`` sat on disk
        # and worked.
        #
        # ⚠️ A skip is the loudest thing this file can say when a shell is
        # genuinely absent and the quietest possible failure when the locating
        # logic is wrong -- and the wrong locating logic is the *interesting*
        # defect, because it is ours.
        installed = shells_installed_beside_git("sh")
        if installed:
            pytest.fail(
                "a POSIX sh IS installed on this machine and this suite failed to "
                "locate it, so this is the locating logic being wrong rather than a "
                "machine that cannot run the hook. Skipping here would retire every "
                "test in this file and report that there was nothing to cover. Found "
                f"beside the git binary: {[str(path) for path in installed]}. {absent}"
            )
        pytest.skip(
            "there is nothing to cover: git runs hooks through a POSIX shell, so a "
            "machine without one cannot run this hook at all and the behaviour under "
            "test does not exist there. Windows gets sh from Git for Windows, which "
            "is required to use git at all, and every CI runner is Linux. Nothing was "
            "found beside the git binary either, which is the cross-check that "
            f"separates an absent shell from an unfound one. {absent}"
        )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )


def _a_repository(tmp_path: Path) -> Path:
    """A throwaway repository carrying this project's guard and hook.

    ⭐ ``src`` is COPIED rather than referenced, so the scan runs against a tree
    that is genuinely this repository's guard but is not this repository -- a
    test that planted personal data in the real checkout would be planting it in
    the thing the real gate protects.
    """
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    # ⛔ Without the ignore, ``__pycache__`` rides along and every ``.pyc`` is a
    # P2 -- "the file type cannot be proved safe". The guard is right; the
    # fixture was wrong, and it made a clean-history push look like a finding.
    shutil.copytree(
        REPOSITORY_ROOT / "src",
        repo / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(HOOK, repo / "scripts" / "hooks" / "pre-push")

    _git(repo, "init", "-q", "-b", "main")
    # ⛔ The guard is IMPORTABLE here but not TRACKED here, and the difference is
    # the whole fixture. Tracked, its own non-Python files -- a ``py.typed``
    # marker and five others -- are P2 "cannot be proved safe" findings in every
    # scan, so a clean-history push came back refused with twelve findings that
    # had nothing to do with the case under test. The guard was right about all
    # twelve; they were the fixture's, not the subject's.
    (repo / ".gitignore").write_text("/src/\n/scripts/\n", encoding="utf-8")
    (repo / "README.md").write_text("nothing here\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


_THIS_RUNS_PYTHON = object()

# ⭐ The negative control's interpreter setting: the same pointer at nothing that
# ``interpreter=None`` uses, and **no shadow planted behind it**. Everything else
# about the run -- the shell, the working directory, the ref line, the rest of the
# environment -- is the same, so the shadow is the only variable between them.
_NOTHING_IS_PLANTED = object()

# ⛔ **The precondition that makes the shadow LOAD-BEARING, run in the hook's own
# shell, with the hook's own environment and working directory.**
#
# ⚠️ Without it the ``interpreter=None`` cases are green for a reason the fixture
# did not build. On the machine this was written on the ambient ``python`` and
# ``python3`` are the Microsoft Store shim, which exists, is executable and fails
# on every invocation -- so the hook refuses **whether or not the shadow
# directory is on PATH**, and an empty shadow would leave every assertion here
# passing. The green proved the hook refuses when nothing runs; it did not prove
# the test built that condition.
#
# ⚠️ It is also what would have reported the WSL run as a broken fixture rather
# than as a broken hook: inside WSL the ``;``-separated Windows PATH this fixture
# constructs does not apply, so ``python3`` resolves to WSL's own interpreter,
# which runs. That is the fixture failing to build its case, and it read as the
# hook accepting a push it should have refused.
#
# ⭐ Both halves are asserted, because either alone is satisfiable by the wrong
# thing: that the candidates RESOLVE inside the shadow, and that each of them
# FAILS the same ``-c ''`` probe the hook itself uses.
_THE_SHADOW_MUST_DECIDE = """\
set -u
directory=$(cd "${GADE_SHADOW:-}" 2>/dev/null && pwd) || directory=''
if [ -z "$directory" ]; then
    echo "the shell cannot reach the shadow directory at all"
    exit 3
fi
for name in python python3; do
    resolved=$(command -v "$name" 2>/dev/null) || resolved=''
    if [ -z "$resolved" ]; then
        echo "$name resolves to nothing, so the hook will not try it"
        exit 4
    fi
    case "$resolved" in
        "$directory"/*) ;;
        *)
            echo "$name resolves outside the shadow, to $resolved"
            exit 5
            ;;
    esac
    if "$name" -c '' >/dev/null 2>&1; then
        echo "$name at $resolved runs successfully, so nothing here is unrunnable"
        exit 6
    fi
done
"""


def _the_hooks_own_path(shell: str, ahead: Path | None = None) -> str:
    """⛔ The PATH git gives a hook: the shell's own utility directory, then the rest.

    ⚠️ **Measured, and it is the reason this function exists.** A real
    ``git push`` on this machine, launched from a shell where Git's utility
    directory is not on PATH, hands its pre-push hook a ``tr`` and a ``sed`` out
    of that directory: git puts it there itself. This fixture did not, and
    once the shell stopped being ambient the committed hook's first command --
    ``tr``, on the line that derives the all-zero object id -- was **not found**,
    so that derivation silently took its ``|| echo`` fallback. Launched from Git
    Bash the same fixture found ``tr``, because that launcher had already put the
    directory on PATH.

    ⭐ **That is this issue's own shape one layer down**, and it was invisible
    while the shell was ambient: the utility a shell can reach was supplied by
    whoever launched pytest, not by the fixture.

    ⚠️ The directory comes from ``utility_directory`` and **not** from
    ``Path(shell).parent``, which was right for the first candidate and only an
    accident for the second -- see that function for what was measured, including
    the reason no test here can tell the two derivations apart.

    ``ahead`` goes in front of everything, so a planted shadow still wins.
    """
    parts = [str(utility_directory(Path(shell))), os.environ.get("PATH", "")]
    if ahead is not None:
        parts.insert(0, str(ahead))
    return os.pathsep.join(part for part in parts if part)


# ⭐ Asked in the hook's own shell, because that is where the answer differs: the
# question is not whether THIS interpreter runs, it is whether the shell the hook
# is executed by can find one on the PATH it inherits.
_A_PATH_CANDIDATE_THAT_RUNS = """\
set -u
for name in python3 python; do
    if "$name" -c '' >/dev/null 2>&1; then
        echo "$name"
        exit 0
    fi
done
exit 1
"""


def _the_shadow_must_decide(
    shell: str, repo: Path, environment: dict[str, str], shadow: Path
) -> None:
    """⛔ Fail the test if the hook's interpreter candidates are not the planted ones.

    A defect in the fixture, not a skip: this file's other three
    ``the fixture did not build the case`` assertions all fail, and a fixture
    that cannot build its case has nothing to report but that.
    """
    probe = subprocess.run(
        [shell, "-c", _THE_SHADOW_MUST_DECIDE],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        # Forward slashes: the shell reads this out of its own environment, and a
        # backslash inside double quotes is not a separator there.
        env={**environment, "GADE_SHADOW": str(shadow).replace("\\", "/")},
    )
    assert probe.returncode == 0, (
        "the fixture did not build the case: the hook is about to look for an "
        "interpreter and the candidates it will try are not the failing stubs "
        "planted here, so a refusal would prove nothing about an unrunnable "
        f"gate -- {(probe.stdout + probe.stderr).strip()}"
    )


def _push(
    repo: Path,
    local_sha: str,
    remote_sha: str,
    *,
    interpreter: object = _THIS_RUNS_PYTHON,
    lines: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook exactly as git runs it: the ref line on stdin.

    ⭐ ``lines`` overrides the single ref, so a test can send the several git
    sends on a multi-ref push — which is where the abort/findings interaction
    lives, and which a one-line harness could never have reached.

    ⛔ The interpreter defaults to this test run's own Python, because the
    throwaway repository has no ``.venv`` and the hook would otherwise fall
    through to a bare ``python``. **On Windows that resolves to the Microsoft
    Store shim, which exists, is executable, and fails on every invocation.**

    ⚠️ The first version of this file did not do that, and two tests passed for
    the wrong reason: the hook was refusing every push because it could not run
    the guard at all, which looks exactly like the guard finding something. Pass
    ``None`` to exercise that path deliberately.

    ⭐ ``_NOTHING_IS_PLANTED`` is that same pointer at nothing with **no shadow
    behind it**, which is the negative control below: one variable between them.
    """
    shell = _hook_shell()
    environment = dict(os.environ)
    environment["PATH"] = _the_hooks_own_path(shell)
    if interpreter is _THIS_RUNS_PYTHON:
        environment["GRAMPS_AGENT_DATA_ENTRY_PYTHON"] = sys.executable
    elif interpreter is _NOTHING_IS_PLANTED:
        environment["GRAMPS_AGENT_DATA_ENTRY_PYTHON"] = str(repo / "no-such-python")
    elif interpreter is None:
        environment["GRAMPS_AGENT_DATA_ENTRY_PYTHON"] = str(repo / "no-such-python")
        # ⛔ Hide PYTHON, not everything. Emptying PATH also hid **git**, so the
        # hook refused at its commit-ish check instead -- the test then asserted
        # a message it was not written for, and only surfaced when the
        # interpreter lookup moved after that check.
        #
        # ⭐ A directory of stubs that exit non-zero goes FIRST on PATH, so the
        # fallbacks find something and it fails, while git still works.
        shadow = repo / "shadow"
        shadow.mkdir(exist_ok=True)
        for name in ("python", "python3"):
            for path in (shadow / name, shadow / f"{name}.bat"):
                path.write_text("#!/bin/sh" + chr(10) + "exit 1" + chr(10), encoding="utf-8")
                path.chmod(0o755)
        environment["PATH"] = _the_hooks_own_path(shell, ahead=shadow)
        _the_shadow_must_decide(shell, repo, environment, shadow)
    else:
        environment["GRAMPS_AGENT_DATA_ENTRY_PYTHON"] = str(interpreter)

    # ⛔ BYTES, and LF only. ``text=True`` translates the newline on Windows, so
    # the last field arrived with a trailing carriage return — **41 characters
    # rather than 40** — and every comparison against the all-zero sha was
    # false.
    #
    # ⚠️ **Four tests named a branch of the hook, never reached it, and passed
    # anyway:** the deletion case, the new-branch case, the tag-on-a-blob case
    # and the other-remote case. All four fell through to the update branch's
    # fallback, which scans the tip's whole history — so they refused for a
    # reason that had nothing to do with what they were testing.
    #
    # ⭐ Found by a control that stayed silent: restoring the defect this file
    # was written for did not fail anything. The measurement that settled it was
    # ``len``: 41 versus 40, NOMATCH versus MATCH.
    line = lines or f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    finished = subprocess.run(
        [shell, "scripts/hooks/pre-push", "origin", "https://example.invalid/r.git"],
        cwd=repo,
        input=line.encode("utf-8"),
        capture_output=True,
        check=False,
        env=environment,
    )
    return subprocess.CompletedProcess(
        finished.args,
        finished.returncode,
        finished.stdout.decode("utf-8", "replace"),
        finished.stderr.decode("utf-8", "replace"),
    )


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_a_push_carrying_a_guard_DETECTABLE_string_is_REFUSED(tmp_path: Path) -> None:
    """⛔ Direction one: it fires, and the refusal says what to do.

    ⚠️ Asserting only a non-zero exit would pass for a hook that failed because
    its interpreter was missing. The output has to name the guard's own verdict
    and the remedy.
    """
    repo = _a_repository(tmp_path)
    base = _head(repo)
    (repo / "notes.md").write_text(f"a path: {PLANTED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adds something that must not be published")

    result = _push(repo, _head(repo), base)

    assert result.returncode != 0, (
        f"the push was allowed. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PUSH REFUSED" in result.stdout, result.stdout
    assert "--show-matches" in result.stdout, (
        "the refusal must say how to see what matched; findings are redacted by default"
    )


def test_a_push_of_CLEAN_history_SUCCEEDS(tmp_path: Path) -> None:
    """⛔ Direction two, and the one that is easy to skip.

    ⚠️ A hook that refuses everything satisfies the test above perfectly. This is
    the half that separates a gate from a wall.
    """
    repo = _a_repository(tmp_path)
    base = _head(repo)
    (repo / "notes.md").write_text("an ordinary line of prose\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adds nothing of the kind")

    result = _push(repo, _head(repo), base)

    assert result.returncode == 0, (
        f"a clean push was refused. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PUSH REFUSED" not in result.stdout


def test_DELETING_a_ref_publishes_nothing_and_is_allowed(tmp_path: Path) -> None:
    """⚠️ A deletion carries an all-zero LOCAL sha. There is nothing to scan.

    ⭐ Left undefined, this reads as an unresolvable range and the guard refuses
    it -- so deleting a branch would fail for a reason that has nothing to do
    with personal data.
    """
    repo = _a_repository(tmp_path)

    result = _push(repo, ZERO, _head(repo))

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_NEW_branch_with_no_remote_counterpart_is_still_scanned(tmp_path: Path) -> None:
    """⛔ A first push carries an all-zero REMOTE sha, and must not skip.

    ⚠️ This is the case a prescription that says only *\"scan the pushed range\"*
    leaves undefined, and the failure is silent: the range is unresolvable, the
    scan does not run, and the push is allowed. Here there is no ``origin/main``
    either, so the hook must fall back to the tip's whole history rather than to
    nothing.
    """
    repo = _a_repository(tmp_path)
    (repo / "notes.md").write_text(f"a path: {PLANTED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adds something that must not be published")

    result = _push(repo, _head(repo), ZERO)

    assert result.returncode != 0, (
        f"a first push of a branch was not scanned. stdout={result.stdout!r}"
    )
    assert "PUSH REFUSED" in result.stdout


def test_a_range_that_covers_NOTHING_is_allowed_rather_than_refused(tmp_path: Path) -> None:
    """⚠️ Re-pushing an unchanged ref adds no commits.

    ⛔ The guard REFUSES an empty range -- *\"a range covering nothing is never a
    pass\"*, exit 2 -- which is right for the guard and wrong here. Read as a
    failure it would block every no-op push, and a gate that fires on ordinary
    operations is one people learn to bypass.
    """
    repo = _a_repository(tmp_path)
    head = _head(repo)

    result = _push(repo, head, head)

    assert result.returncode == 0, (
        f"a no-op push was refused. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_the_hook_is_not_claimed_to_be_unbypassable(tmp_path: Path) -> None:
    """⛔ ``--no-verify`` skips it, and the file must say so.

    ⭐ This asserts a property of the DOCUMENTATION because the property is about
    what a reader will believe. A hook that is quietly bypassable is worse than
    no hook: it produces confidence that does not correspond to a guarantee.
    """
    text = HOOK.read_text(encoding="utf-8")

    assert "--no-verify" in text, "the hook does not admit that --no-verify bypasses it"
    assert "not self-installing" in text or "never installs a hook" in text, (
        "the hook does not say that git will not install it from a clone"
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="PATH cannot hand back a shell from another operating system here, so the "
    "failure this asserts against is not reachable off Windows",
)
def test_the_shell_this_file_runs_the_hook_with_COMES_FROM_GIT() -> None:
    """⛔ The launcher in the system directory must be unreachable, not merely unpreferred.

    ⚠️ An exclusion list naming it would be an enumeration, and the next shell
    from another operating system would not be on it. Deriving the shell from
    ``git --exec-path`` and requiring the answer to live under that distribution
    root refuses the whole class: nothing outside Git for Windows can be
    returned, whatever PATH says today.

    ⭐ Both flavours, because ``pushes.py`` takes the default one and inherits
    exactly the same hazard.
    """
    exec_path = subprocess.run(
        ["git", "--exec-path"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    root = Path(exec_path).parents[2]

    for flavour in ("bash", "sh"):
        resolved = posix_shell(flavour=flavour)

        assert root in resolved.parents, (
            f"the {flavour} this suite drives is {resolved}, which is not under the "
            f"Git distribution at {root} -- a shell from anywhere else has its own "
            "filesystem and its own PATH, and its failures are indistinguishable "
            "from the thing under test failing"
        )


def test_the_hook_gets_the_UTILITIES_a_real_git_push_would_give_it() -> None:
    """⛔ A pinned shell with an unpinned PATH runs the hook in a way git never does.

    ⚠️ **Measured on this machine, from a shell where Git's utility directory is
    not on PATH:** a real ``git push`` hands its pre-push hook the ``tr`` that
    lives in that directory.
    The moment this file stopped taking whatever shell PATH offered, it stopped
    handing it anything -- and the committed hook's very first command is ``tr``,
    on the line deriving the all-zero object id. It was not found, the derivation
    fell through to its ``|| echo`` literal, and nothing said so. Launched from
    Git Bash the same code found ``tr``, because that launcher had already put
    the directory on PATH.

    ⭐ So this asserts the second half of the pin. Pinning the shell binary while
    leaving what the shell can REACH to the launching environment is the same
    defect with a smaller blast radius, and it would have been invisible: every
    assertion in this file stays green either way, because the fallback is
    correct for a SHA-1 repository.

    ⛔ **What is asserted is what the FIXTURE contributes, alone.** Asking
    whether the built PATH can reach ``tr`` is not this property: the ambient
    PATH answers that by itself from Git Bash, and on every Linux runner, where
    the system utility directory is always on it. Measured with the prepend
    reverted --
    ``1 failed, 14 passed`` from PowerShell, and ``15 passed, 2 skipped`` with
    Git's utility directory on the ambient PATH. **A guard that can only fail on
    one developer's shell is measuring that shell**, which is this issue's own
    defect reappearing in the test written to remove it.

    ⭐ So the prepended portion is separated from the ambient one and probed on
    its own. It is empty, or it does not supply ``tr``, exactly when the fixture
    has stopped handing the hook anything -- on any platform, whatever launched
    pytest.

    ``tr`` by name because it is the utility the committed hook actually calls;
    if the hook stops calling it, this test is measuring the wrong thing and
    should be pointed at whatever replaced it.
    """
    shell = _hook_shell()
    ambient = os.environ.get("PATH", "")
    built = _the_hooks_own_path(shell)

    assert built.endswith(ambient), (
        "this test can no longer separate what the fixture contributes from what it "
        f"inherited: the PATH it builds does not end in the ambient one. built={built!r}"
    )
    contributed = built[: len(built) - len(ambient)].strip(os.pathsep)

    assert contributed, (
        "the fixture prepends nothing, so what the hook's shell can reach is whatever "
        "launched pytest -- and git's own hook environment supplies the utility "
        "directory itself. The hook's first command is tr, on the line deriving the "
        "all-zero object id, and it takes its || echo fallback in silence when tr is "
        "not found"
    )

    resolved = subprocess.run(
        [shell, "-c", "command -v tr"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        # ⛔ The contributed portion ONLY. With the ambient PATH behind it this
        # assertion passes wherever tr happens to be reachable, which is every
        # CI runner this project has.
        env={**os.environ, "PATH": contributed},
    )

    assert resolved.returncode == 0 and resolved.stdout.strip(), (
        "what this fixture prepends does not supply tr, so the hook is being run "
        "through a shell that finds tr only if the launching environment happened to "
        f"offer it -- git's hook environment always does. prepended={contributed!r}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the mode bit is not meaningful on Windows")
def test_the_hook_is_executable() -> None:
    """⚠️ Git silently ignores a hook it cannot execute. Nothing reports it."""
    assert os.access(HOOK, os.X_OK), f"{HOOK} is not executable; git would skip it in silence"


def test_a_MISSING_interpreter_refuses_the_push_and_says_it_is_NOT_a_finding(
    tmp_path: Path,
) -> None:
    """⛔ The gate being unable to answer is refused, not assumed clean.

    ⚠️ **This case is why the file exists in this shape.** The first version of
    the hook fell through to a bare ``python``; on Windows that is the Microsoft
    Store shim, which exists, is executable, and fails on every invocation. Every
    push was refused, the two *"it fires"* tests here passed — and they passed
    **because the interpreter was missing, not because anything was found.**

    ⭐ The clean-push direction is what exposed it. A hook that refuses
    everything satisfies a one-directional test perfectly.

    So the refusal now has to distinguish the two, and it must not read as
    personal data when none was found.
    """
    repo = _a_repository(tmp_path)
    (repo / "empty").mkdir()
    base = _head(repo)
    (repo / "notes.md").write_text("an ordinary line of prose\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "clean")

    result = _push(repo, _head(repo), base, interpreter=None)

    assert result.returncode != 0, "an unrunnable gate must not be treated as a pass"
    combined = result.stdout + result.stderr
    assert "no working Python" in combined, combined
    assert "NOT a finding" in combined, (
        "the refusal reads as though personal data was found, when the gate "
        f"simply could not run: {combined}"
    )


def test_the_SHADOW_is_what_refuses_that_push_and_not_the_machine(tmp_path: Path) -> None:
    """⛔ The negative control for the test above: take the shadow away and it passes.

    ⚠️ **This control is CARRIED BY CI, and its local skip is not coverage.** On
    the machine this was written on the ambient ``python`` and ``python3`` are the
    Microsoft Store shim, which exists, is executable and fails on every
    invocation -- so the hook refuses with or without the shadow and the control
    cannot tell the two apart. It probes for that first and skips saying so. On a
    runner where a real interpreter is on PATH it runs, and it bites.

    ⭐ The layer that fires everywhere is the precondition inside ``_push``, which
    asserts that the candidates the hook is about to try are the planted stubs.
    This is the second layer, not the only one, and it is the weaker of the two.
    """
    repo = _a_repository(tmp_path)
    base = _head(repo)
    (repo / "notes.md").write_text("an ordinary line of prose\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "clean")

    # ⚠️ Only the two PATH candidates are probed. The two before them in the
    # hook's list cannot resolve here -- GRAMPS_AGENT_DATA_ENTRY_PYTHON is about to point
    # at a file that does not exist, and the throwaway repository has no .venv,
    # asserted rather than assumed -- and an over-narrow probe here costs a skip
    # that could have run, never a pass that measured nothing.
    assert not (repo / ".venv").exists(), (
        "the fixture did not build the case: a .venv in the throwaway repository "
        "would be tried before anything on PATH, so this probe would not be asking "
        "about the interpreter the hook will actually use"
    )
    shell = _hook_shell()
    runnable = subprocess.run(
        [shell, "-c", _A_PATH_CANDIDATE_THAT_RUNS],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        # The same PATH the push below will get, so the probe answers about the
        # run it is deciding, not about this process.
        env={**os.environ, "PATH": _the_hooks_own_path(shell)},
    )
    if runnable.returncode != 0:
        pytest.skip(
            "no interpreter the hook would try can execute here, so the push is "
            "refused with and without the shadow directory and this control cannot "
            "tell them apart -- on this development machine the ambient python and "
            "python3 are the Microsoft Store shim. It is carried by CI, where a real "
            "interpreter is on PATH. What still holds locally is the precondition "
            "inside _push, seam twin "
            "test_a_MISSING_interpreter_refuses_the_push_and_says_it_is_NOT_a_finding, "
            "which asserts that the candidates the hook resolves are the planted stubs "
            "and that each of them fails"
        )

    result = _push(repo, _head(repo), base, interpreter=_NOTHING_IS_PLANTED)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        "the same clean push was refused with no shadow planted, so the refusal in "
        f"the test above is not evidence that the shadow caused it: {combined}"
    )
    assert "no working Python" not in combined, combined


def test_a_TAG_pointing_at_a_BLOB_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    """⛔ A fail-open in the gate: the object publishes and nothing scans it.

    ⚠️ ``git tag`` accepts **any object**, not only a commit, so a tag can point
    straight at a blob. ``git rev-list --count`` then answers **0**, and the
    empty-range branch reads that as *nothing new to publish*. It is the
    opposite — the blob **is** published, and the guard never saw it.

    ⭐ Reproduced before fixing: a tag on a blob holding a drive-letter path,
    count ``0``, hook returned **success**.

    Refused rather than scanned. The guard's interface is a commit range, so
    nothing here could scan a loose blob honestly, and a gate that cannot see
    what a push carries must not wave it through. Same rule as the missing
    interpreter: **cannot answer means refuse.**
    """
    repo = _a_repository(tmp_path)
    (repo / "payload.txt").write_text(f"a path: {PLANTED}\n", encoding="utf-8")
    blob = _git(repo, "hash-object", "-w", "payload.txt").stdout.strip()
    _git(repo, "tag", "carried", blob)
    tag = _git(repo, "rev-parse", "carried").stdout.strip()

    assert _git(repo, "cat-file", "-t", tag).stdout.strip() == "blob", (
        "the fixture did not build the case: the tag does not point at a blob"
    )
    assert _git(repo, "rev-list", "--count", tag).stdout.strip() == "0", (
        "the fixture did not build the case: rev-list sees commits here"
    )

    result = _push(repo, tag, ZERO)

    assert result.returncode != 0, (
        f"a tag pointing at a blob was pushed unscanned. stdout={result.stdout!r}"
    )
    combined = result.stdout + result.stderr
    assert "blob rather than a commit" in combined, combined


def test_a_new_ref_on_a_DIFFERENT_remote_is_fully_scanned(tmp_path: Path) -> None:
    """⛔ The destination decides what is already published, not ``origin``.

    ⚠️ The hook used to subtract ``origin/main`` whatever remote it was pushing
    to. ``git push public main`` at a different or empty remote then computed an
    empty range **against a ref that remote has never seen** — count ``0``, hook
    exits 0 — while git sent the entire history.

    ⭐ Reproduced before fixing: with ``origin/main`` equal to ``HEAD``, the old
    range counted **0** commits and the new one counts **2**.

    Git passes the remote as ``$1``; its own ``pre-push.sample`` documents that,
    and this hook was ignoring it. A new ref now scans everything reachable from
    the tip, which is what that sample does and what cannot subtract something
    the destination never had.
    """
    repo = _a_repository(tmp_path)
    (repo / "notes.md").write_text(f"a path: {PLANTED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adds something that must not be published")

    # ⛔ The trap: a local origin/main that already contains the planted commit,
    # while the push goes somewhere that has never seen any of it.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _git(repo, "rev-list", "--count", "origin/main..HEAD").stdout.strip() == "0", (
        "the fixture did not build the case: origin/main must already contain the tip"
    )

    result = _push(repo, _head(repo), ZERO)

    assert result.returncode != 0, (
        f"a new ref on another remote was pushed unscanned. stdout={result.stdout!r}"
    )
    assert "PUSH REFUSED" in result.stdout, result.stdout


def test_the_committed_hook_has_no_CARRIAGE_RETURNS() -> None:
    """⛔ A shell script with CRLF is not a shell script on Linux.

    ⚠️ **This is asserted against the COMMITTED BLOB, not the working tree.**
    On a Windows checkout the file on disk may legitimately have CRLF; what
    breaks is what git stores and what a Linux runner checks out. Reading the
    working tree here would pass on the machine that caused the problem.

    ⭐ Measured when it happened: every Linux leg failed with
    ``set: Illegal option -^M`` before the file reached its second line, and
    ``core.autocrlf`` did not prevent it. ``.gitattributes`` pins ``eol=lf``;
    this is what notices if that pin is removed or stops applying.

    ⚠️ Second time carriage returns broke this hook. The first was the harness
    feeding CRLF on stdin, which made every comparison against the all-zero sha
    false and let four tests pass without reaching the branch they named.
    """
    blob = subprocess.run(
        # ⭐ The INDEX, not HEAD: it is what the next commit will store, and in a
        # clean checkout -- every CI run -- it equals HEAD. Reading HEAD would
        # make this fail on the very commit that fixes it.
        ["git", "show", ":scripts/hooks/pre-push"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
    ).stdout

    assert b"\r" not in blob, (
        "the committed hook contains carriage returns, so /bin/sh on Linux fails "
        "on its first line -- check .gitattributes still pins eol=lf for it"
    )


def test_an_ABORT_on_one_ref_does_not_hide_FINDINGS_on_another(tmp_path: Path) -> None:
    """⛔ A multi-ref push reports every ref's outcome, not just one.

    A refused ref and a ref carrying a finding are reported together: the
    operator learns both that one ref could not be scanned and that another
    contains personal data.

    ⚠️ **What this test does NOT prove, stated because a control caught me
    claiming it did.** The ``if``/``elif`` this change replaced is only reachable
    when the guard itself exits 2 — and that path is not reachable from here: a
    non-commit tip is refused *before* the guard runs, and an empty range is
    skipped before it runs. So the abort-suppresses-findings interaction is
    fixed defensively and **is not covered by this test**; restoring the ``elif``
    leaves this green.

    ⭐ The fix stands on its own terms — the two outcomes are independent facts
    and reporting one must not silence the other, least of all when the silenced
    one is *personal data was found*. But it is unproven, and saying so is worth
    more than a test that looks like proof.
    """
    repo = _a_repository(tmp_path)
    base = _head(repo)
    (repo / "notes.md").write_text(f"a path: {PLANTED}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "adds something that must not be published")
    tip = _head(repo)

    # ⛔ A tag on a blob aborts its ref; the branch update carries the finding.
    blob = _git(repo, "hash-object", "-w", "notes.md").stdout.strip()
    _git(repo, "tag", "carried", blob)
    tag = _git(repo, "rev-parse", "carried").stdout.strip()

    result = _push(
        repo,
        tip,
        base,
        lines=(
            f"refs/tags/carried {tag} refs/tags/carried {ZERO}\n"
            f"refs/heads/main {tip} refs/heads/main {base}\n"
        ),
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined
    assert "rather than a commit" in combined, f"the aborted ref was not reported: {combined}"
    assert "found something above" in combined, (
        "the abort suppressed the report of a real finding on the other ref -- "
        f"which is the more serious of the two facts: {combined}"
    )


def test_a_DELETION_is_allowed_even_with_no_interpreter(tmp_path: Path) -> None:
    """⛔ A gate must not block an operation it has no business blocking.

    ⚠️ The interpreter was looked up **before stdin was read**, so a push that
    only deletes a ref was refused — and a deletion publishes no objects at all,
    which the loop already allows explicitly. The guard had nothing to scan, so
    having nothing to scan it *with* could not matter.

    ⭐ That is the cry-wolf failure this project has recorded elsewhere: a gate
    that fires on ordinary operations is one people learn to pass `--no-verify`,
    and then it protects nothing at all.

    The lookup happens on first use now, so this case never reaches it.
    """
    repo = _a_repository(tmp_path)

    result = _push(repo, ZERO, _head(repo), interpreter=None)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"a deletion-only push was refused for want of an interpreter it never needed: {combined}"
    )
    assert "no working Python" not in combined, combined


def test_an_ANNOTATED_TAG_is_refused_because_its_message_is_not_scanned(
    tmp_path: Path,
) -> None:
    """⛔ A tag object carries a message, and nothing here reads it.

    ⚠️ The commit-ish check is satisfied — an annotated tag peels to a commit —
    but the range scan then examines commit **trees**. The tag object itself is
    never read, so a new annotated tag whose message holds a path is published
    unscanned. Same fail-open as the tag-on-a-blob case, reached by a tag that
    looks entirely ordinary.

    ⭐ Refused rather than scanned, for the reason the whole file uses: the
    guard's interface is a commit range, nothing here can scan a tag object
    honestly, and **a gate that cannot see what a push carries must not wave it
    through.**
    """
    repo = _a_repository(tmp_path)
    _git(repo, "tag", "-a", "annotated", "-m", f"a path: {PLANTED}")
    tag = _git(repo, "rev-parse", "annotated").stdout.strip()

    assert _git(repo, "cat-file", "-t", tag).stdout.strip() == "tag", (
        "the fixture did not build the case: this is not an annotated tag"
    )
    assert _git(repo, "rev-parse", "--verify", f"{tag}^{{commit}}").returncode == 0, (
        "the fixture did not build the case: the tag must peel to a commit, which "
        "is what makes it slip past the commit-ish check"
    )

    result = _push(repo, tag, ZERO)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, f"an annotated tag was pushed unscanned: {combined}"
    assert "annotated tag carries a message" in combined, combined
