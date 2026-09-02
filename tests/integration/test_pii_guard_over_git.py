"""Root cause A -- the guard's scope is what Git contains, not the working tree.

Three ways the worktree lies about what a repository publishes:

* a blob added and then deleted within one push is gone from the tip and still
  reachable in history;
* a tracked file inside a directory whose *name* looks like tooling output is
  still committed content;
* a committed symlink's blob content is its target string, which can be an
  absolute personal path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import (
    DENYLIST_FILENAME,
    HISTORY_SOURCE,
    find_committed_denylists,
    main,
    scan_paths,
    scan_repository,
)
from tests.fixtures.expectations import rules
from tests.fixtures.repositories import (
    add_symlink,
    add_symlink_bytes,
    commit_all,
    commit_index,
    git,
    init_repository,
)
from tests.fixtures.synthetic import (
    gedcom_document,
    gedcom_x_json,
    posix_path,
    sqlite_bytes,
    unclassifiable_bytes,
    utf16le_gedcom_bytes,
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    return init_repository(tmp_path / "repo")


def test_a_clean_repository_has_no_findings(repository: Path) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")

    assert scan_repository(repository) == []


def test_untracked_files_are_not_scanned(repository: Path) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")
    (repository / "scratch.md").write_text(gedcom_document(), encoding="utf-8")

    assert scan_repository(repository) == [], "untracked content is not published"


def test_a_blob_deleted_later_in_the_push_is_still_found(repository: Path) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")

    (repository / "notes.md").write_text(gedcom_document(), encoding="utf-8")
    commit_all(repository, "add a tree")
    (repository / "notes.md").unlink()
    after = commit_all(repository, "remove the tree")

    assert scan_repository(repository) == [], "the tip really is clean"

    findings = scan_repository(repository, revision_range=f"{before}..{after}")

    assert rules(findings) == ["P2"], (
        f"a blob added and deleted within one push stays reachable, got {findings}"
    )


def test_a_tracked_file_in_a_tooling_directory_is_scanned(repository: Path) -> None:
    (repository / "build").mkdir()
    (repository / "build" / "notes.md").write_text(gedcom_document(), encoding="utf-8")
    git(repository, "add", "--force", "build/notes.md")
    commit_all(repository, "force-add a build artefact")

    findings = scan_repository(repository)

    assert rules(findings) == ["P2"], (
        f"a tracked file is committed content whatever its directory is called, got {findings}"
    )


def test_a_committed_symlink_target_is_scanned(repository: Path) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")

    add_symlink(repository, "tree", posix_path("home", "private-user", "tree"))
    commit_index(repository, "add a symlink")

    findings = scan_repository(repository)

    assert rules(findings) == ["P1"], (
        f"a symlink's committed blob is its target, an absolute path, got {findings}"
    )


def test_both_modes_reach_the_same_verdict_on_the_same_name(repository: Path) -> None:
    """The property, not "add a call here": a name means the same in both modes.

    Repository mode puts every committed path through the textual checks. The
    walk sent only bytes, so a deny-listed surname in a filename or in a parent
    directory was reported by one mode and not the other -- and the mode that
    missed it is the one that fails open.
    """
    (repository / "Ashenmoor-family").mkdir()
    (repository / "Ashenmoor-notes.md").write_text("nothing interesting\n", encoding="utf-8")
    (repository / "Ashenmoor-family" / "notes.md").write_text(
        "nothing interesting\n", encoding="utf-8"
    )
    commit_all(repository, "names that carry a surname")

    over_git = scan_repository(repository, denylist=["Ashenmoor"])
    over_the_tree = scan_paths([repository], denylist=["Ashenmoor"])

    assert rules(over_git) == rules(over_the_tree), (
        f"the same names, two verdicts: git says {rules(over_git)}, "
        f"the walk says {rules(over_the_tree)}"
    )
    assert len(over_git) == len(over_the_tree) == 2, (
        "a surname in a filename and a surname in a directory are two findings in both "
        f"modes; git found {len(over_git)}, the walk found {len(over_the_tree)}"
    )
    assert rules(over_the_tree) == ["LOCAL"], f"and both are deny-list hits, got {over_the_tree}"


def test_an_entry_with_no_content_still_has_its_name_classified() -> None:
    """A name rule was living in the content classifier, so a gitlink skipped it.

    A gitlink is the one entry with no bytes here -- it names another
    repository -- and it therefore skipped a rule about its own *name*. The
    branch did not need a special case; the rule needed to be in the funnel.

    Driven through the funnel with no content, which is exactly the shape a
    gitlink takes. Git will not hold the name itself: handing it bytes that are
    not UTF-8 makes it store their UTF-8 re-encoding, so the undecodable name
    can only arrive from a repository written on another platform.
    """
    undecodable = pii_guard.decode_path(b"caf\xe9-vendor")

    findings = pii_guard.scan_blob(None, undecodable)

    assert rules(findings) == ["P2"], (
        f"a name that cannot be decoded cannot be classified, content or not, got {findings}"
    )


def test_a_gitlink_goes_through_the_funnel(repository: Path) -> None:
    """And the gitlink branch is what reaches it, with no content."""
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "base")
    git(repository, "update-index", "--add", "--cacheinfo", "160000", "0" * 39 + "1", "Ashenmoor")
    commit_index(repository, "a submodule named after a person")

    findings = scan_repository(repository, denylist=["Ashenmoor"])

    assert rules(findings) == ["LOCAL"], (
        f"its name is published even though its content lives elsewhere, got {findings}"
    )


def test_the_walk_classifies_a_symlink_the_way_git_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The walk dropped the whole entry, not merely the name.

    Repository mode reads a committed symlink's blob -- which is its target, an
    absolute personal path -- and reports P1. The walk skipped the entry
    outright, so the same link on disk was invisible.

    Creating a real symlink needs a privilege Windows does not grant by
    default, so the seam is driven directly here and the end-to-end case is
    left to CI, where the next test runs for real.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tree").write_bytes(b"")
    target = posix_path("home", "quorvane", "trees")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "tree")
    monkeypatch.setattr(os, "readlink", lambda path, **_: target)

    findings = pii_guard.scan_paths([workspace])

    assert rules(findings) == ["P1"], (
        f"a link's target is an absolute path on somebody's machine, got {findings}"
    )


def test_a_symlink_named_as_the_target_is_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Naming the link itself, rather than finding it in a walk.

    Found by a surviving mutant: the branch that yields a named base is
    separate from the one inside the walk, so dropping it again failed
    nothing. Two branches, one rule -- the rule needs asserting on both.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tree").write_bytes(b"")
    target = posix_path("home", "quorvane", "trees")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "tree")
    monkeypatch.setattr(os, "readlink", lambda path, **_: target)

    findings = pii_guard.scan_paths([workspace / "tree"])

    assert rules(findings) == ["P1"], (
        f"a link given by name is still an entry with a target, got {findings}"
    )


def test_the_walk_classifies_a_real_symlink(tmp_path: Path) -> None:
    """The same thing without the seam, where the operating system allows it.

    SKIP TWIN: test_the_walk_classifies_a_symlink_the_way_git_does, in this
    file, asserts the same property through the Path.is_symlink seam and runs
    on every platform. A skip here is the operating system declining to make a
    link, not the behaviour going unchecked -- what is uncovered locally is
    narrowly the real directory entry, which CI supplies.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        (workspace / "tree").symlink_to(posix_path("home", "quorvane", "trees"))
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip(
            "creating a symlink needs a privilege this platform withholds; "
            "the property is covered here by the seam twin "
            "test_the_walk_classifies_a_symlink_the_way_git_does"
        )

    findings = pii_guard.scan_paths([workspace])

    assert rules(findings) == ["P1"], f"the walk must read the link it found, got {findings}"


def test_walk_mode_applies_the_denylist_it_says_is_in_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The coverage line was part of the defect.

    It stated the deny-list was in force while the deny-list had been applied
    to half of what was scanned -- the same shape as a count nobody compares to
    its scope word.
    """
    workspace = tmp_path / "workspace"
    (workspace / "Ashenmoor-family").mkdir(parents=True)
    (workspace / pii_guard.DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")
    (workspace / "Ashenmoor-notes.md").write_text("nothing interesting\n", encoding="utf-8")
    (workspace / "Ashenmoor-family" / "notes.md").write_text(
        "nothing interesting\n", encoding="utf-8"
    )
    monkeypatch.chdir(workspace)

    exit_code = main(["."])
    output = capsys.readouterr().out

    assert "deny-list in force" in output, "the claim under test"
    assert exit_code == 1, (
        f"in force means applied to the names as well as the contents; got {exit_code} "
        f"with {output!r}"
    )


def test_the_two_scanners_agree_about_a_symlink(repository: Path) -> None:
    """The tip and the history must classify identical bytes identically.

    The divergence is the defect, not either verdict: the tip scanner knew the
    mode and called it P1, while the history scanner had no mode and called the
    same blob an unknown file type.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")
    add_symlink(repository, "tree", posix_path("home", "private-user", "tree"))
    after = commit_index(repository, "add a symlink")

    at_tip = scan_repository(repository)
    in_history = [
        finding
        for finding in scan_repository(repository, revision_range=f"{before}..{after}")
        if finding.source.scope == HISTORY_SOURCE
    ]

    assert rules(at_tip) == ["P1"], f"the tip scanner reads the target, got {at_tip}"
    assert rules(in_history) == ["P1"], (
        f"the history scanner must read the same bytes the same way, got {in_history}"
    )


def test_tracked_content_is_read_from_the_index_not_the_worktree(repository: Path) -> None:
    """What gets committed is what is staged, so that is what is scanned."""
    (repository / "notes.md").write_text("harmless\n", encoding="utf-8")
    commit_all(repository, "harmless")

    # Staged but not committed: this is about to be published.
    (repository / "notes.md").write_text(gedcom_document(), encoding="utf-8")
    git(repository, "add", "notes.md")
    # ...and then reverted in the worktree only, which changes nothing about
    # what the index will commit.
    (repository / "notes.md").write_text("harmless\n", encoding="utf-8")

    findings = scan_repository(repository)

    assert rules(findings) == ["P2"], (
        f"the index is what will be committed; the worktree is not, got {findings}"
    )


def test_a_denylisted_name_used_as_a_filename_is_a_finding(repository: Path) -> None:
    (repository / "Ashenmoor-family.md").write_text("nothing in here\n", encoding="utf-8")
    commit_all(repository, "add a file named after a person")

    findings = scan_repository(repository, denylist=["Ashenmoor"])

    assert rules(findings) == ["LOCAL"], (
        f"content is scanned and filenames were not; a name is a name, got {findings}"
    )


def test_a_committed_denylist_is_found_at_any_depth(repository: Path) -> None:
    (repository / "docs").mkdir()
    (repository / "docs" / ".pii-denylist").write_text("Ashenmoor\n", encoding="utf-8")
    git(repository, "add", "--force", "docs/.pii-denylist")
    commit_all(repository, "commit a deny-list in a subdirectory")

    assert find_committed_denylists(repository) == ["docs/.pii-denylist"], (
        "a root-anchored pathspec misses a deny-list committed in a "
        "subdirectory, which is exactly where a stray copy would sit"
    )


# ---------------------------------------------------------------------------
# Round 3: four ways the gate reported clean while publishing.
# ---------------------------------------------------------------------------


def test_a_committed_denylist_in_history_is_a_finding(repository: Path) -> None:
    """The highest-severity case: that file holds real names.

    Only an *untracked* local deny-list may be skipped. A Git entry with that
    name is itself a finding, whether it survives to the tip or not.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")

    (repository / DENYLIST_FILENAME).write_text("Ashenmoor\nQuorvane\n", encoding="utf-8")
    git(repository, "add", "--force", DENYLIST_FILENAME)
    commit_index(repository, "force-add a deny-list")
    (repository / DENYLIST_FILENAME).unlink()
    after = commit_all(repository, "remove it again")

    findings = scan_repository(repository, revision_range=f"{before}..{after}")

    assert [finding.rule for finding in findings] == ["DENYLIST"], (
        f"a deny-list blob stays publicly reachable after deletion, got {findings}"
    )
    assert findings[0].match == "", "its contents must never be echoed, not even redacted"


def test_a_committed_denylist_at_the_tip_is_a_finding(repository: Path) -> None:
    (repository / DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")
    git(repository, "add", "--force", DENYLIST_FILENAME)
    commit_index(repository, "force-add a deny-list")

    assert [finding.rule for finding in scan_repository(repository)] == ["DENYLIST"], (
        "the skip applies to both enumerations, so the tip was exempt too"
    )


def test_coverage_counts_only_what_is_scanned(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty commit carries a message and no blobs.

    Commit-message scanning is deferred, so the claim must not include it:
    counting commits while scanning entries is how a clean report was issued
    over content nobody looked at.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")
    git(repository, "commit", "--quiet", "--allow-empty", "-m", "an empty commit")
    after = git(repository, "rev-parse", "HEAD")

    exit_code = main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 2, f"nothing was scanned, so this is not a pass; got {output!r}"
    assert "commit message" in output.lower(), (
        f"the report must name what it does not cover, got {output!r}"
    )


def test_a_path_bearing_filename_is_a_finding(repository: Path) -> None:
    # Round 3's F3: a committed path NAME is content too, and gets every
    # textual property, not only the deny-list. Re-expressed on a surviving
    # property after P3's removal; the assertion it makes is the same one.
    #
    # A repository-relative path has no leading separator, so it can never look
    # absolute by shape. It can carry a path-bearing *position*, though: the
    # separator between a directory and a file is a real separator, so a
    # directory named like a path variable makes the whole path one.
    (repository / "backup_dir=").mkdir()
    (repository / "backup_dir=" / "tree.md").write_text("nothing\n", encoding="utf-8")
    commit_all(repository, "a path that is itself a path expression")

    findings = scan_repository(repository)

    assert rules(findings) == ["P1"], (
        f"a filename is committed content and gets every textual property, got {findings}"
    )


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("sqlite", sqlite_bytes()),
        ("utf16le gedcom", utf16le_gedcom_bytes()),
        ("arbitrary binary", unclassifiable_bytes()),
    ],
    ids=["sqlite", "utf16le-gedcom", "arbitrary-binary"],
)
def test_non_textual_content_hidden_in_a_symlink_blob_is_a_finding(
    repository: Path, label: str, payload: bytes
) -> None:
    """Genealogy *text* was already caught; these are what actually escaped.

    A symlink blob was routed straight to the text properties, skipping file
    magic, the UTF-8 decode and the control-character check.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")
    add_symlink_bytes(repository, "tree", payload)
    commit_index(repository, f"symlink-mode {label}")

    findings = scan_repository(repository)

    assert rules(findings) == ["P2"], (
        f"{label} in a symlink blob must be classified like any other blob, got {findings}"
    )


def test_a_range_covering_no_commits_is_refused(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    head = commit_all(repository, "docs: readme")

    exit_code = main(["--range", f"{head}..{head}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        "a range covering nothing is never a pass. This is how the zero-SHA "
        "fail-open hid: an empty range scanned nothing and reported clean"
    )
    assert "covers no commits" in output


def test_a_range_that_only_deletes_is_clean_and_says_what_it_covered(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """⭐ Issue #193: the one range shape that is trivially safe was refused.

    **A deletion publishes no blob.** ``iter_range_entries`` has always skipped
    deletions for exactly that reason, so the zero it produced was a fact about
    the range and not a failure to look -- and the abort read it as the latter.

    ⚠️ The abort's stated reason was that commit messages go unscanned. That is
    true of **every** range, including the ones it passed, so it could not single
    this shape out.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    (repository / "STALE.md").write_text("# Stale\n", encoding="utf-8")
    before = commit_all(repository, "docs: two files")
    (repository / "STALE.md").unlink()
    after = commit_all(repository, "docs: drop the stale one")

    exit_code = main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 0, f"a deletion-only range publishes nothing, so it passes: {output}"
    assert "introducing no file content" in output, output
    assert "a deletion publishes no blob" in output, output


def test_a_deletion_only_range_still_fails_on_a_finding_in_tracked_content(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """⛔ The control. Clean-because-deletions must NOT be clean-regardless.

    ⚠️ Without this, the change above is indistinguishable from one that reports
    a deletion-only push clean **without scanning anything at all** -- and the
    tip is still scanned on every run, which is where the coverage actually is.
    """
    (repository / "README.md").write_text(gedcom_document(), encoding="utf-8")
    (repository / "STALE.md").write_text("# Stale\n", encoding="utf-8")
    before = commit_all(repository, "docs: two files")
    (repository / "STALE.md").unlink()
    after = commit_all(repository, "docs: drop the stale one")

    exit_code = main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        "the range added nothing, but the TIP still carries personal data and "
        f"the tip is scanned on every run: {output}"
    )


def test_an_empty_commit_beside_a_deletion_is_still_a_deletion_range(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """⭐ The two contentless shapes, in one range, judged on the property.

    ⛔ **Zero introduced entries is true of both**, which is why the check
    asks whether the range REMOVED something rather than how much it added. An
    empty commit alone stays unscannable -- ``test_coverage_counts_only_what_is
    _scanned`` holds that line and is untouched -- and it does not make a
    deletion beside it unscannable too.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    (repository / "STALE.md").write_text("# Stale\n", encoding="utf-8")
    before = commit_all(repository, "docs: two files")
    git(repository, "commit", "--quiet", "--allow-empty", "-m", "an empty commit")
    (repository / "STALE.md").unlink()
    after = commit_all(repository, "docs: drop the stale one")

    exit_code = main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 0, f"the range removes content, so it is a deletion range: {output}"
    assert "introducing no file content" in output, output


def test_the_scan_states_how_much_it_covered(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "one")
    (repository / "NOTES.md").write_text("# Notes\n", encoding="utf-8")
    after = commit_all(repository, "two")

    assert main(["--range", f"{before}..{after}", str(repository)]) == 0
    output = capsys.readouterr().out

    assert "1 commit" in output, (
        "a gate that cannot tell 'scanned everything, found nothing' from "
        f"'scanned nothing' is not a gate; got {output!r}"
    )


def test_the_range_entry_point_completes_when_it_finds_something(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate's own invocation, driven all the way through with findings.

    Every other range test either expects nothing or aborts before scanning, so
    the path that reports findings over a range had no coverage at all -- which
    is where the sort ran and crashed.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")

    (repository / "install.md").write_text(
        "copied from "
        + posix_path("home", "private-user", "trees")
        + " to "
        + posix_path("var", "backups", "trees")
        + "\n",
        encoding="utf-8",
    )
    after = commit_all(repository, "two paths on one line")

    exit_code = main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 1, f"findings mean exit 1, not a crash and not a pass; got {output!r}"
    # Four, not two: a range run reports tracked content *and* the range, and
    # this file is in both. The same content appearing once per scope -- and
    # once per blob version within the range -- is a reporting characteristic,
    # noted in CONTRIBUTING so the count is not read as distinct problems.
    assert output.count("P1") == 4, f"both findings, in both scopes, in one piece; got {output!r}"


def test_the_scanned_revision_range_must_be_resolvable(repository: Path) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")

    with pytest.raises(ValueError):
        scan_repository(repository, revision_range="0" * 40 + "..HEAD")


def test_an_unresolvable_whole_history_range_is_refused_not_reported_clean(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gate that cannot determine its scope must not report clean.

    CI scans a tag push as everything reachable from the checkout, so the one
    way that scope can fail to resolve is a HEAD that names no commit. The twin
    above asserts that the resolution raises; this asserts what the job
    actually reads -- the exit code and the words -- because a raise that were
    ever caught and reported as nothing-found would still satisfy the twin.
    """
    exit_code = main(["--range", "HEAD", str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 2, "a range that cannot be resolved must never exit as a clean scan"
    assert "scan aborted" in output
    assert "0 finding(s)" not in output


def test_a_genealogy_document_hidden_in_a_symlink_blob_is_a_finding(repository: Path) -> None:
    """The fail-open on the primary threat.

    Round 3 closed this for file magic, encodings and non-UTF-8 binary. A
    genealogy format the guard has never heard of is valid UTF-8, matches no
    signature, and depends entirely on the unknown-type refusal -- which the
    symlink exemption skipped.
    """
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(repository, "docs: readme")
    add_symlink_bytes(repository, "tree", gedcom_x_json().encode("utf-8"))
    commit_index(repository, "a document wearing the symlink mode")

    findings = scan_repository(repository)

    assert rules(findings) == ["P2"], (
        f"a symlink blob is exempt from the extension gate, not from classification; got {findings}"
    )


def test_a_committed_name_that_is_the_match_is_redacted(repository: Path) -> None:
    (repository / "Ashenmoor-family.md").write_text("nothing\n", encoding="utf-8")
    commit_all(repository, "a file named after a person")

    finding = scan_repository(repository, denylist=["Ashenmoor"])[0]
    rendered = str(finding)

    assert "Ashenmoor" not in rendered, (
        "the value is redacted and the source is not -- and here they are the "
        f"same string, so the name is republished anyway; got {rendered}"
    )
    assert "family" not in rendered or "..." in rendered or "<" in rendered, (
        "the basename is what is redacted"
    )


def test_a_revision_expression_is_not_echoed(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(repository, "docs: readme")
    (repository / "notes.md").write_text("harmless\n", encoding="utf-8")
    after = commit_all(repository, "more")

    main(["--range", f"{before}..{after}", str(repository)])
    output = capsys.readouterr().out

    assert before not in output and after not in output, (
        "a revision expression is operator-supplied text of unknown content -- "
        f"a filesystem path has reached git through that argument before; got {output!r}"
    )


def test_a_replaced_object_does_not_decide_what_the_scan_reads(tmp_path: Path) -> None:
    """Git was asked for the object; it answered with the substitute.

    ``git replace`` binds a reference that makes every ordinary object read
    return a different object -- so a GEDCOM in the index reads as harmless
    Markdown, the scan reports clean, and the commit still references the
    original. Nothing about the published content changed; only what this
    guard was shown did.

    ⚠️ **The suffix is deliberately safe.** Under a .ged name the type gate
    answers first and the scan looks fine while the content check is being
    fooled -- which is exactly how this hid, and the reason the negative
    control asserts content rows under a safe suffix.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    init_repository(workspace)
    (workspace / "notes.md").write_text(gedcom_document(), encoding="utf-8")
    commit_all(workspace, "add notes")

    real = git(workspace, "rev-parse", "HEAD:notes.md").strip()
    substitute = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=workspace,
        input="# Title\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    git(workspace, "replace", "-f", real, substitute)

    findings = pii_guard.scan_repository(workspace)

    assert rules(findings) == ["P2"], (
        f"a replacement reference chose what the guard read, so the committed "
        f"GEDCOM was never seen; got {findings}"
    )
