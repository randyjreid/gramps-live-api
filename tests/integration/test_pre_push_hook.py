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

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "pre-push"
ZERO = "0" * 40

# ⛔ A string the guard is known to flag, built at runtime rather than written
# here as a literal. Writing a drive-letter path into this file would make the
# file itself a finding, and the repository's own gate would refuse it -- which
# is the guard working, and would look like this test failing.
PLANTED = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "thing.txt"


def _sh() -> str:
    """The shell git uses for hooks. Windows gets it from Git for Windows."""
    for candidate in ("sh", "bash"):
        found = shutil.which(candidate)
        if found:
            return found
    pytest.skip(
        "there is nothing to cover: git runs hooks through a POSIX shell, so a "
        "machine without one cannot run this hook at all and the behaviour under "
        "test does not exist there. Windows gets sh from Git for Windows, which is "
        "required to use git at all, and every CI runner is Linux."
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
    """
    environment = dict(os.environ)
    if interpreter is _THIS_RUNS_PYTHON:
        environment["GRAMPS_LIVE_API_PYTHON"] = sys.executable
    elif interpreter is None:
        environment["GRAMPS_LIVE_API_PYTHON"] = str(repo / "no-such-python")
        # ⛔ Emptied so the fallbacks cannot find one either -- otherwise this
        # asserts the behaviour of whatever happens to be installed.
        environment["PATH"] = str(repo / "empty")
    else:
        environment["GRAMPS_LIVE_API_PYTHON"] = str(interpreter)

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
        [_sh(), "scripts/hooks/pre-push", "origin", "https://example.invalid/r.git"],
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
