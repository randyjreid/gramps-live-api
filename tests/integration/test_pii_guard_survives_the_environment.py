"""The gate must fail loudly, never crash and never quietly pass.

Round 5, from a second reviewer on a second operating system. Four rounds on
Windows alone did not find these, which is the finding behind the findings: two
reviewers on one platform is one reviewer for anything platform-shaped.

⚠️ Some assertions here are weaker on Windows than on Linux and say so. The
leak in the first test is Linux-only -- CPython puts the working directory in
the message there, and leaves it empty here -- so **CI is what proves it**, not
a local run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import is_git_work_tree, main, scan_repository
from tests.fixtures.expectations import rules
from tests.fixtures.repositories import commit_all, commit_index, git, init_repository
from tests.fixtures.synthetic import gedcom_document

CANARY = "quorvane-ashenmoor"


# ---------------------------------------------------------------------------
# Finding 1 -- the crash, the leak, and the fail-open the naive fix creates.
# ---------------------------------------------------------------------------


def test_a_missing_target_is_refused_not_crashed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit code, and -- since round 8 -- the message that goes with it.

    Coverage now catches this case downstream too, so removing the explicit
    refusal stopped failing anything: the run still exits 2, but by way of a
    message about a directory that could not be listed. Third
    unpinned-diagnosability finding in three rounds, so the wording is pinned.
    """
    exit_code = main([str(tmp_path / "no-such-file.md")])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        "a target that cannot be read is neither a crash nor a clean report; "
        f"got {exit_code} with {output!r}"
    )
    assert "does not exist" in output, (
        f"the operator mistyped a path and must be told that, not something else; got {output!r}"
    )


def test_a_missing_target_never_reports_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fail-open that swallowing the error would create.

    Handling the exception without this check turns a crash into "0 findings,
    exit 0" -- a clean report over a target nobody looked at, which is the
    invariant the coverage assertion already exists to protect.
    """
    exit_code = main([str(tmp_path / "no-such-directory") + "/deeper"])
    output = capsys.readouterr().out

    assert exit_code != 0, f"scanning nothing is never a pass; got {output!r}"
    assert "0 finding" not in output


def test_an_unreadable_target_does_not_print_its_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Weaker on Windows than on Linux, deliberately.

    The operating-system error carries the working directory in its message on
    Linux and not here, so this passes locally for the wrong reason. It is
    written for CI.
    """
    target = tmp_path / f"{CANARY}-workspace" / "no-such-file.md"

    main([str(target)])
    streams = capsys.readouterr()

    assert CANARY not in streams.out + streams.err, (
        "the operating-system error message is the leak on Linux; it must not be printed raw"
    )


def test_a_work_tree_check_on_an_unreadable_path_is_false_not_fatal(tmp_path: Path) -> None:
    assert is_git_work_tree(tmp_path / "no-such-directory") is False


def test_a_missing_git_binary_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Git absent is an environment problem, and must read as one."""
    init_repository(tmp_path)
    (tmp_path / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(tmp_path, "base")

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise OSError(2, "No such file or directory", "git")

    monkeypatch.setattr(subprocess, "run", refuse)

    assert main([str(tmp_path)]) == 2
    assert "aborted" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# Round 6 -- the paths nobody drove.
#
# The matrix found these, not a reviewer. Two mutants survived because no test
# reached the code they broke, and looking for siblings of that turned up two
# reads that escape as a traceback carrying somebody's absolute path. Every
# test below drives an error through a route the suite had never taken.
# ---------------------------------------------------------------------------


def test_a_git_failure_after_the_work_tree_check_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The wrapper's own conversion, which the missing-binary test never reaches.

    That test replaces every subprocess call, so the work-tree check fails
    first and aborts before a single command goes through the wrapper. Git
    going away *after* the check -- uninstalled mid-scan, or a directory that
    stops being enterable -- is the route left undriven, and it is the route
    where an unconverted error would escape as a traceback.
    """
    repository = init_repository(tmp_path / f"{CANARY}-workspace")
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "base")

    real_run = subprocess.run
    calls = 0

    def fail_after_the_check(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls > 1:
            # The filename is what CPython puts in this message on Linux, and
            # it is the leak: an absolute path on somebody's machine.
            raise OSError(2, "No such file or directory", str(repository))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_after_the_check)

    exit_code = main([str(repository)])
    streams = capsys.readouterr()

    assert calls > 1, "the work-tree check short-circuited; the wrapper was never reached"
    assert exit_code == 2, f"a scan that could not run is never a pass; got {exit_code}"
    assert CANARY not in streams.out + streams.err, (
        "the operating-system message names the directory; it must not be printed raw"
    )


def test_a_git_failure_names_the_error_type_and_redacts_the_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Diagnosability was a deliverable, and nothing pinned it.

    A message saying only that git could not be run tells an operator nothing
    they can act on, so the type is named in clear and the detail travels
    redacted. Both halves matter: a mutant that stripped them left every test
    passing.
    """
    init_repository(tmp_path)
    (tmp_path / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(tmp_path, "base")

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError(2, "No such file or directory", f"{CANARY}-git")

    monkeypatch.setattr(subprocess, "run", refuse)

    assert main([str(tmp_path)]) == 2
    output = capsys.readouterr().out

    assert "FileNotFoundError" in output, f"the operator cannot act on this message: {output!r}"
    assert "redacted" in output, f"the detail must travel redacted, not vanish: {output!r}"
    assert CANARY not in output, f"the detail is redacted, not printed: {output!r}"


def test_a_file_that_cannot_be_read_is_refused_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read that fails mid-scan is the same class as a git call that fails.

    It leaves the scan covering less than it claims, so it aborts rather than
    reporting what it managed to look at.
    """
    workspace = tmp_path / f"{CANARY}-workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("nothing\n", encoding="utf-8")

    def refuse(self: Path) -> bytes:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "read_bytes", refuse)

    assert main([str(workspace)]) == 2


def test_a_file_that_cannot_be_read_does_not_print_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The escaping exception is itself the leak.

    Unlike the missing-target message, this one carries the absolute path on
    every platform, because the interpreter puts the file it could not read
    into it.
    """
    workspace = tmp_path / f"{CANARY}-workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("nothing\n", encoding="utf-8")

    def refuse(self: Path) -> bytes:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "read_bytes", refuse)

    main([str(workspace)])
    streams = capsys.readouterr()

    assert CANARY not in streams.out + streams.err, (
        "an unreadable file must not republish its own path while complaining about it"
    )


def test_a_local_denylist_that_cannot_be_read_is_refused_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The deny-list read is the third of the same class, and the quietest.

    It happens before any file is scanned, so an unhandled error here aborts
    the run before a single finding could exist -- and the deny-list is the
    one file in the project guaranteed to contain personal names.
    """
    workspace = tmp_path / f"{CANARY}-workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("nothing\n", encoding="utf-8")
    (workspace / pii_guard.DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")

    real_read_text = Path.read_text

    def refuse(self: Path, **kwargs: object) -> str:
        if self.name.startswith(pii_guard.DENYLIST_PREFIX):
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_text(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.chdir(workspace)

    exit_code = main(["."])
    streams = capsys.readouterr()

    assert exit_code == 2, f"a deny-list that cannot be read is never a clean run; got {exit_code}"
    assert CANARY not in streams.out + streams.err


# ---------------------------------------------------------------------------
# Round 7 -- scanning nothing is never a pass, in every mode there is.
#
# An unreadable FILE refuses the run. An unlistable DIRECTORY was silently
# dropped and the run passed, which is the same class failing the opposite
# way. Both are instances of one rule the project already has, so it is
# asserted here once per mode rather than restated per code path.
# ---------------------------------------------------------------------------


def test_a_directory_that_cannot_be_listed_refuses_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's reproduction: a denied listing over a directory holding a tree.

    The walk took the default error handler, which drops the directory and
    keeps going. Everything inside it -- here, a whole GEDCOM -- was never
    looked at, and the run reported clean.
    """
    workspace = tmp_path / f"{CANARY}-workspace"
    (workspace / "records").mkdir(parents=True)
    (workspace / "records" / "tree.ged").write_text(gedcom_document(), encoding="utf-8")
    (workspace / "README.md").write_text("# Title\n", encoding="utf-8")

    real_scandir = os.scandir

    def refuse(path: object = ".", *args: object, **kwargs: object) -> object:
        if Path(str(path)).name == "records":
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "scandir", refuse)

    exit_code = main([str(workspace)])
    streams = capsys.readouterr()

    assert exit_code == 2, (
        "a directory nobody could list holds content nobody looked at; "
        f"got {exit_code} with {streams.out!r}"
    )
    assert CANARY not in streams.out + streams.err


def test_a_target_holding_no_scannable_file_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sibling one step up, found while measuring the first.

    A target that yields no files at all reported zero findings and exited
    zero -- a clean report over nothing, which is the same fail-open as the
    range that covers no commits.
    """
    workspace = tmp_path / "empty-workspace"
    workspace.mkdir()

    exit_code = main([str(workspace)])

    assert exit_code == 2, f"scanning nothing is never a pass; got {exit_code}"
    assert "0 finding" not in capsys.readouterr().out


def test_a_repository_with_no_tracked_content_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third instance, found by looking for it rather than by being told.

    A working tree Git tracks nothing in passes through the same clean report:
    the gate scans tracked content, and there was none.
    """
    repository = init_repository(tmp_path / "repo")

    exit_code = main([str(repository)])

    assert exit_code == 2, f"a repository with nothing tracked covers nothing; got {exit_code}"
    assert "0 finding" not in capsys.readouterr().out


def test_a_denylist_named_directly_is_still_never_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exemption was written in the walk and not on the direct argument.

    Naming the file scanned it, and every literal in it matched itself, so the
    one file guaranteed to hold personal names printed them all. The document
    said flatly that the guard never scans it.
    """
    # Both spellings, because both are needed to reproduce it: the bare name
    # is the one that gets loaded, and the suffixed one -- which the document
    # tells contributors to create -- carries a safe file type, so its content
    # is read rather than refused, and every literal then matches itself.
    literals = "Ashenmoor\nQuorvane\n"
    (tmp_path / pii_guard.DENYLIST_FILENAME).write_text(literals, encoding="utf-8")
    denylist = tmp_path / f"{pii_guard.DENYLIST_FILENAME}.md"
    denylist.write_text(literals, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--show-matches", str(denylist)])
    output = capsys.readouterr().out

    assert "Ashenmoor" not in output and "Quorvane" not in output, (
        f"the deny-list republished its own literals; got {output!r}"
    )
    assert exit_code == 2, (
        f"naming only the deny-list scans nothing, which is never a pass; got {exit_code}"
    )


def test_a_denylist_that_is_not_utf8_is_refused_without_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Correct today, and one refactor from being a leak. Pinned, not fixed.

    A decoding failure is not an operating-system error, so it misses the
    handler that redacts those -- it survives only because it is a kind of
    value error, which is what the caller happens to catch. Nothing said so
    until this test.
    """
    workspace = tmp_path / f"{CANARY}-workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Title\n", encoding="utf-8")
    (workspace / pii_guard.DENYLIST_FILENAME).write_bytes(bytes((0xFF, 0xFE)) + b"Ashenmoor\n")
    monkeypatch.chdir(workspace)

    exit_code = main(["."])
    streams = capsys.readouterr()

    assert exit_code == 2, f"a deny-list that cannot be decoded is never a clean run; {exit_code}"
    assert CANARY not in streams.out + streams.err


def test_a_scan_over_files_says_how_much_it_covered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Coverage is stated in every mode, not only over a repository.

    Without it a run that skipped almost everything is indistinguishable from
    one that looked at the lot.
    """
    (tmp_path / "README.md").write_text("# Title\n", encoding="utf-8")
    (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")

    assert main([str(tmp_path)]) == 0
    assert "2 file(s)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Finding 5 -- a submodule must not brick the gate.
# ---------------------------------------------------------------------------


def test_a_gitlink_does_not_abort_the_scan(tmp_path: Path) -> None:
    repository = init_repository(tmp_path / "repo")
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "base")
    git(repository, "update-index", "--add", "--cacheinfo", "160000", "0" * 39 + "1", "vendor")
    commit_index(repository, "add a gitlink")

    assert scan_repository(repository) == [], (
        "a gitlink names another repository; its content is not here, and it "
        "must not abort the gate"
    )


def test_a_gitlink_path_is_still_scanned(tmp_path: Path) -> None:
    repository = init_repository(tmp_path / "repo")
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "base")
    git(repository, "update-index", "--add", "--cacheinfo", "160000", "0" * 39 + "1", "Ashenmoor")
    commit_index(repository, "add a gitlink named after a person")

    findings = scan_repository(repository, denylist=["Ashenmoor"])

    assert rules(findings) == ["LOCAL"], (
        f"the entry's path is published even though its content is not, got {findings}"
    )


# ---------------------------------------------------------------------------
# Finding 4 -- one decoder, and an undecodable name is a finding.
# ---------------------------------------------------------------------------


def test_a_name_that_is_not_utf8_is_a_finding_not_an_abort() -> None:
    undecodable = "caf\udce9-notes.md".encode("utf-8", errors="surrogateescape")

    decoded = pii_guard.decode_path(undecodable)

    assert pii_guard.UNDECODABLE_MARKER in decoded, (
        "the two enumerations decoded differently -- one strict, one replacing "
        "-- so a single such name aborted the tip scan entirely"
    )
    findings = pii_guard.scan_blob(b"nothing\n", decoded)
    assert rules(findings) == ["P2"], (
        "a name that cannot be decoded cannot be classified, which is already "
        f"P2's rule; got {findings}"
    )


def test_the_same_bytes_are_judged_the_same_however_the_name_arrived() -> None:
    """Git decodes an invalid byte to the replacement character; the filesystem
    hands it back as a surrogate escape. Same bytes, two representations, and
    only one of them was recognised -- so a name Git rejected was clean once it
    came off a POSIX disk instead.

    This fails on Windows too, deliberately: the surrogate form is constructed
    here rather than read from a filesystem, so the property is tested
    everywhere even though only POSIX can produce it naturally.
    """
    raw = b"caf\xe9-notes.md"
    through_git = pii_guard.decode_path(raw)
    off_the_filesystem = raw.decode("utf-8", errors="surrogateescape")

    verdicts = {
        "git": rules(pii_guard.scan_blob(b"nothing\n", through_git)),
        "filesystem": rules(pii_guard.scan_blob(b"nothing\n", off_the_filesystem)),
    }

    assert verdicts["git"] == verdicts["filesystem"] == ["P2"], (
        f"one name, two representations, two verdicts: {verdicts}"
    )


def test_a_denylisted_surname_in_the_wrong_encoding_does_not_pass() -> None:
    """Why the rule exists, in the form this archive will actually meet it.

    An unclassifiable name cannot be matched against the deny-list, so a
    surname typed in an editor that was not saving UTF-8 goes straight through.
    The names this guard protects carry accents.
    """
    name = b"Ashenmo\xf6r-notes.md".decode("utf-8", errors="surrogateescape")

    findings = pii_guard.scan_blob(b"nothing\n", name, denylist=["Ashenmoör"])

    assert rules(findings) == ["P2"], (
        f"a name that cannot be decoded cannot be checked against a deny-list; got {findings}"
    )


def test_a_real_undecodable_filename_on_disk_is_refused(tmp_path: Path) -> None:
    """The same thing end to end, where the operating system can hold the name.

    ⚠️ **This cannot fail on Windows**, whose filenames are UTF-16 and which
    refuses to create this one at all -- so it skips here and CI proves it.

    SKIP TWINS: test_a_name_that_is_not_utf8_is_a_finding_not_an_abort and
    test_the_same_bytes_are_judged_the_same_however_the_name_arrived, both
    above, assert the property from constructed surrogates and run on every
    platform. Only the path from a real directory entry is uncovered here.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        target = os.path.join(os.fsencode(workspace), b"caf\xe9-notes.md")
        with open(target, "wb") as handle:
            handle.write(b"nothing interesting\n")
    except (OSError, UnicodeError):  # pragma: no cover - Windows
        pytest.skip(
            "this platform cannot hold a filename that is not valid UTF-8; the "
            "property is covered here by the seam twins "
            "test_a_name_that_is_not_utf8_is_a_finding_not_an_abort and "
            "test_the_same_bytes_are_judged_the_same_however_the_name_arrived"
        )

    findings = pii_guard.scan_paths([workspace])

    assert rules(findings) == ["P2"], (
        f"a directory entry nobody can decode is a directory entry nobody can check; {findings}"
    )


def test_both_enumerations_use_the_same_decoder() -> None:
    source = Path(pii_guard.__file__).read_text(encoding="utf-8")

    strict = [
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if '.decode("utf-8")' in line and "decode_path" not in line
    ]

    assert strict == [], f"a strict decode outside the shared helper aborts a scan; lines {strict}"


# ---------------------------------------------------------------------------
# The environment anchor, applied to every variable Git says is repository-local.
# ---------------------------------------------------------------------------


def test_an_alternate_index_does_not_decide_what_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anchor cleared two variables; Git has fifteen.

    GIT_DIR and GIT_WORK_TREE answer "which repository", and clearing them was
    the fix. GIT_INDEX_FILE answers "which staged content", which decides just
    as much for a scan that reads the index -- so an alternate index holding
    one harmless file made a staged GEDCOM invisible and the scan exited clean.

    Fail-open, from our own fix being one variable short. The same partial
    application this project keeps producing, which is why the replacement
    asks Git for the list rather than extending it by one.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    init_repository(workspace)
    (workspace / "tree.ged").write_text(gedcom_document(), encoding="utf-8")
    git(workspace, "add", "tree.ged")

    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (workspace / "notes.md").write_text("# Title\n", encoding="utf-8")
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / "index"))
    git(workspace, "add", "notes.md")

    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / "index"))
    findings = scan_repository(workspace)

    assert rules(findings) == ["P2"], (
        f"an alternate index chose what was scanned, so the staged GEDCOM was "
        f"never read; got {findings}"
    )


def test_the_anchor_drops_every_variable_git_calls_repository_local() -> None:
    """The property, not the one variable that was missed.

    Testing GIT_INDEX_FILE alone would leave the next omission to the next
    reviewer -- the fix is that the set is Git's answer rather than ours, so
    that is what gets asserted. Every name Git lists is set to a decoy value
    and none may survive into the environment a command runs with.
    """
    named = pii_guard._repository_local_git_variables()

    assert {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} <= named, (
        f"git no longer names the variables this guard was built around: {sorted(named)}"
    )

    with pytest.MonkeyPatch.context() as patch:
        for name in named:
            patch.setenv(name, "decoy")
        anchored = pii_guard._git_environment_anchored_on_the_target()

    survivors = sorted(named & anchored.keys())
    assert not survivors, f"the anchor let repository-local variables through: {survivors}"
    assert "PATH" in anchored, "the anchor dropped the environment git needs to run at all"


def test_the_anchor_fails_closed_when_git_will_not_name_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent fallback would restore the fail-open it replaced.

    The tempting failure branch is "ask git; if that does not work, use the
    pair we used to hard-code". That reinstates the exact hole being closed,
    at the moment there is least reason to trust the environment. It refuses
    instead, and callers already turn that into a refusal rather than a pass.
    """
    pii_guard._repository_local_git_variables.cache_clear()
    monkeypatch.setattr(
        pii_guard.subprocess,
        "run",
        lambda *arguments, **keywords: (_ for _ in ()).throw(OSError("no git here")),
    )
    try:
        with pytest.raises(ValueError, match="cannot be anchored"):
            pii_guard._git_environment_anchored_on_the_target()
    finally:
        pii_guard._repository_local_git_variables.cache_clear()


def test_the_anchor_refuses_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """An answer of nothing is not an answer.

    A git that exits zero and names no variables would leave the anchor with
    nothing to drop -- it would filter the environment against an empty set
    and hand every redirecting variable straight through, while every visible
    sign said the query had worked. That is worse than the query failing.

    Added because the mutant deleting this check survived: the branch was
    written on principle and nothing exercised it, which is how a guard clause
    becomes decoration.
    """

    class Answered:
        returncode = 0
        stdout = b"\n  \n"
        stderr = b""

    pii_guard._repository_local_git_variables.cache_clear()
    monkeypatch.setattr(pii_guard.subprocess, "run", lambda *a, **k: Answered())
    try:
        with pytest.raises(ValueError, match="named nothing"):
            pii_guard._git_environment_anchored_on_the_target()
    finally:
        pii_guard._repository_local_git_variables.cache_clear()
