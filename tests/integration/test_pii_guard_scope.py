"""What the gate looked at, and whether it says so truthfully.

Round 8. Redaction is closed; this is the other half of being a gate. Four
rounds fixed coverage by asserting, per mode, that *something* was scanned.
Each assertion was true and the fourth defect still got through, because the
words describing the scan were written by hand at the print site while the set
was enumerated somewhere else. Nothing compared them.

**Tracked content is a claim about a repository.** Every test here holds the
scan to that claim.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import main
from tests.fixtures.repositories import commit_all, commit_index, git, init_repository
from tests.fixtures.synthetic import gedcom_document, posix_path


@pytest.fixture
def repository_with_a_tree(tmp_path: Path) -> Path:
    """A repository whose tree sits at the root and whose subdirectory is clean."""
    root = init_repository(tmp_path / "repo")
    (root / "README.md").write_text("# Title\n", encoding="utf-8")
    (root / "family.ged").write_text(gedcom_document(), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    commit_all(root, "a repository with something in it")
    return root


def test_a_subdirectory_target_scans_the_whole_repository(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's reproduction, and the worst outcome this guard can produce.

    Listing tracked content from a subdirectory returns only that subtree,
    while the verdict still speaks for the repository. A committed family tree
    one directory up is reported clean.
    """
    exit_code = main([str(repository_with_a_tree / "src")])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"a clean verdict over a repository holding a family tree; got {exit_code} with {output!r}"
    )


def test_an_untracked_file_inside_a_repository_is_refused(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fail-open the widening created, and the last one of its kind.

    Any path inside a work tree widens to the repository, including a file Git
    does not track -- which the widened scan then excludes. A new draft was
    therefore reported clean by the repository half while never being looked at
    by anything, and the same bytes outside a repository are a finding.

    A named path is scanned or the run is refused. It is never silently outside
    the scope it caused.
    """
    draft = repository_with_a_tree / "draft.md"
    draft.write_text(gedcom_document(), encoding="utf-8")

    exit_code = main([str(draft)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        f"a clean report over a file nobody looked at; got {exit_code} with {output!r}"
    )
    assert "does not track" in output, (
        f"the operator needs the file's status, not just a failure; got {output!r}"
    )


def test_naming_the_denylist_does_not_advise_staging_it(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one path where "stage it" is exactly the wrong instruction.

    A deny-list holds the personal literals this guard exists to keep out of
    the repository. Staging one draws a DENYLIST finding, and the generic
    refusal was recommending it.
    """
    denylist = repository_with_a_tree / pii_guard.DENYLIST_FILENAME
    denylist.write_text("Ashenmoor\n", encoding="utf-8")

    exit_code = main([str(denylist)])
    output = capsys.readouterr().out

    assert exit_code == 2, f"it is untracked, so the run is still refused; got {exit_code}"
    assert "stage" not in output.lower(), (
        f"never advise staging the one file that must not be committed; got {output!r}"
    )
    assert "deny-list" in output, f"and say which file this is about; got {output!r}"


def test_an_untracked_directory_inside_a_repository_is_refused(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same hole one level up: a whole directory Git has never seen."""
    drafts = repository_with_a_tree / "drafts"
    drafts.mkdir()
    (drafts / "notes.md").write_text(gedcom_document(), encoding="utf-8")

    exit_code = main([str(drafts)])

    assert exit_code == 2, f"nothing under the named path is in the widened scope; got {exit_code}"


def test_a_tracked_file_inside_a_repository_still_widens(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal is about being outside the scope, not about being a file."""
    exit_code = main([str(repository_with_a_tree / "src" / "module.py")])
    output = capsys.readouterr().out

    assert exit_code == 1, f"the tree at the root is still found; got {exit_code} with {output!r}"
    assert "whole repository" in output


def test_a_subdirectory_target_says_it_widened(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Surprising-but-safe only stays safe while it is impossible to miss.

    Someone who types a subdirectory must not come away believing that is what
    was scanned.
    """
    main([str(repository_with_a_tree / "src")])
    output = capsys.readouterr().out

    assert "whole repository" in output, (
        f"the widening has to be stated, not inferred from a count; got {output!r}"
    )


def test_the_scope_word_and_the_count_cannot_disagree(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One phrase must not describe three different sets.

    Measured before the fix: the same words over 29, 6 and 4 entries depending
    on which directory was named.
    """
    main([str(repository_with_a_tree)])
    from_the_root = capsys.readouterr().out.splitlines()[-1]
    main([str(repository_with_a_tree / "src")])
    from_below = capsys.readouterr().out.splitlines()[-1]

    assert from_the_root == from_below, (
        "the same repository described two ways depending on where you stood:\n"
        f"  {from_the_root!r}\n  {from_below!r}"
    )
    # Found by a surviving mutant: two identical phrases prove nothing if the
    # phrase carries no count. Dropping the number is what made three earlier
    # coverage defects invisible, so the number is part of the claim.
    assert "3 entries" in from_the_root, (
        f"the claim has to carry what it is claiming about; got {from_the_root!r}"
    )


def test_the_tip_and_the_range_agree_about_what_is_in_scope(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One run contradicting itself.

    The range enumeration was never limited to the named directory while the
    tip enumeration always was, so half a run could report a blob the other
    half considered out of scope. Had that blob sat in an already-baselined
    commit, both halves would miss it.
    """
    head = git(repository_with_a_tree, "rev-parse", "HEAD")
    (repository_with_a_tree / "src" / "notes.md").write_text("# Notes\n", encoding="utf-8")
    commit_all(repository_with_a_tree, "a second commit")

    main([str(repository_with_a_tree / "src"), "--range", f"{head}..HEAD"])
    from_below = capsys.readouterr().out.splitlines()[-1]
    main([str(repository_with_a_tree), "--range", f"{head}..HEAD"])
    from_the_root = capsys.readouterr().out.splitlines()[-1]

    assert from_below == from_the_root, (
        f"the two halves of one run disagree about scope:\n  {from_below!r}\n  {from_the_root!r}"
    )


def test_two_targets_in_one_work_tree_are_still_the_repository(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Naming two paths silently downgraded the gate to a filesystem walk.

    Low while the scope word stayed honest -- and the scope word going
    dishonest is exactly the defect above.
    """
    exit_code = main(
        [str(repository_with_a_tree / "src"), str(repository_with_a_tree / "README.md")]
    )
    output = capsys.readouterr().out

    assert "tracked content" in output, (
        f"two paths in one work tree are still that work tree; got {output!r}"
    )
    assert exit_code == 1, f"and the tree at the root is still found; got {exit_code}"


def test_a_repository_whose_tip_tracks_nothing_can_still_be_range_scanned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """FIX REGRESSION from round 7: the tip check preempts the range check.

    Add-then-delete within one push is the case ``--range`` exists for. The
    scanner catches it; the command line refused first, and told the operator
    to stage something when they had supplied a perfectly good range.
    """
    root = init_repository(tmp_path / "repo")
    (root / "README.md").write_text("# Title\n", encoding="utf-8")
    before = commit_all(root, "a base commit")
    (root / "family.ged").write_text(gedcom_document(), encoding="utf-8")
    commit_all(root, "add a tree")
    (root / "family.ged").unlink()
    (root / "README.md").unlink()
    commit_all(root, "delete everything again")

    exit_code = main([str(root), "--range", f"{before}..HEAD"])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"the blob is still reachable and the range was valid; got {exit_code} with {output!r}"
    )
    assert "stage" not in output, f"the operator is not the one who did anything wrong: {output!r}"


def test_the_coverage_line_says_whether_a_denylist_was_in_force(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one property with a documented dependency must not fail silently."""
    main([str(repository_with_a_tree)])
    without = capsys.readouterr().out

    (repository_with_a_tree / pii_guard.DENYLIST_FILENAME).write_text(
        "Ashenmoor\n", encoding="utf-8"
    )
    main([str(repository_with_a_tree)])
    with_one = capsys.readouterr().out

    assert "deny-list" in without and "deny-list" in with_one, (
        f"a run must say whether the local property was in force:\n  {without!r}\n  {with_one!r}"
    )
    assert without != with_one, "and it must say which of the two happened"


def test_the_denylist_is_read_from_the_target_not_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Walk mode read it from wherever you happened to be standing.

    Run from anywhere but the target, the LOCAL property was silently absent --
    and it is the documented backstop for what P1 deliberately does not catch.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / pii_guard.DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")
    (workspace / "notes.md").write_text("a note about Ashenmoor\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    exit_code = main([str(workspace)])

    assert exit_code == 1, (
        f"the deny-list travels with the target, not with the shell; got {exit_code}"
    )


def test_a_denylist_that_cannot_be_decoded_names_the_denylist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An accented surname typed in the wrong editor is this project's own case.

    The decode failure did not go through the wrapper the document describes;
    it was safe only because of which exception type it happens to be.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (workspace / pii_guard.DENYLIST_FILENAME).write_bytes("Ashenmoör\n".encode("latin-1"))
    monkeypatch.chdir(workspace)

    exit_code = main(["."])
    output = capsys.readouterr().out

    assert exit_code == 2, f"a deny-list that cannot be read is never a clean run; got {exit_code}"
    assert "deny-list" in output, f"the message must name what failed; got {output!r}"
    assert "UnicodeDecodeError" in output, f"and what kind of failure it was; got {output!r}"


def test_walk_mode_names_what_it_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The repository half names its gaps; the walk named none of them.

    The reviewer's target: three documents, two of them genealogy, two of them
    under directories the walk skips. One file scanned, exit 0, and nothing
    saying that anything had been passed over.
    """
    workspace = tmp_path / "workspace"
    (workspace / "build").mkdir(parents=True)
    (workspace / "dist").mkdir()
    (workspace / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (workspace / "build" / "export.md").write_text(gedcom_document(), encoding="utf-8")
    (workspace / "dist" / "tree.md").write_text(gedcom_document(), encoding="utf-8")

    main([str(workspace)])
    output = capsys.readouterr().out

    assert "excluded" in output or "not scanned" in output, (
        f"a walk that skipped two of three documents must say so; got {output!r}"
    )


def test_the_refusal_says_what_is_never_scanned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hint the old abort message carried and the rewrite dropped."""
    workspace = tmp_path / "empty"
    workspace.mkdir()

    assert main([str(workspace)]) == 2
    output = capsys.readouterr().out

    assert "deny-list" in output, (
        f"an operator staring at an empty result needs the reason; got {output!r}"
    )


def test_a_repository_of_gitlinks_says_its_content_is_elsewhere(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The count is honest and the reader still cannot tell.

    A gitlink names another repository. Its path is scanned -- it can draw a
    deny-list or a path finding -- but there is no blob here to classify, so
    entries were covered while no content was.
    """
    repository = init_repository(tmp_path / "repo")
    git(repository, "update-index", "--add", "--cacheinfo", "160000", "0" * 39 + "1", "vendor")
    git(repository, "update-index", "--add", "--cacheinfo", "160000", "0" * 39 + "2", "theme")
    commit_index(repository, "two submodules and nothing else")

    exit_code = main([str(repository)])
    output = capsys.readouterr().out

    assert exit_code == 0, f"there is genuinely nothing here to report; got {exit_code}"
    assert "submodule" in output, (
        f"the entries counted cannot contribute content findings; got {output!r}"
    )


def staged_but_not_on_disk(where: Path) -> Path:
    """A repository whose INDEX holds a tree and whose working copy does not.

    The whole reproduction in one fixture: what the next commit publishes is
    not what a filesystem walk can see, so a run that quietly switches from one
    to the other reports clean over content that is about to be committed.
    """
    root = init_repository(where)
    (root / "notes.md").write_text(gedcom_document(), encoding="utf-8")
    git(root, "add", "notes.md")
    (root / "notes.md").write_text("# perfectly harmless\n", encoding="utf-8")
    return root


def test_a_repository_target_is_never_silently_walked_when_git_cannot_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Git running and failing looked exactly like "not a repository".

    Both produced False, so an unreadable or rejected checkout downgraded the
    run to a filesystem walk. The walk is not a safer subset of the index scan;
    it is a different question, and it misses precisely what the index holds.

    Driven through the seam now rather than by aiming the environment at a
    broken git directory, which is how it used to be driven. The guard clears
    those variables so that it asks about the target rather than about the
    environment, and that trigger no longer produces a failure at all -- but a
    genuine one, a checkout Git declines to trust, still must refuse.
    """
    root = staged_but_not_on_disk(tmp_path / "repo")

    real_run = subprocess.run

    def decline_to_answer(*args: object, **kwargs: object) -> object:
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, list) and "--is-inside-work-tree" in command:
            return subprocess.CompletedProcess(command, 128, "", "fatal: unsafe repository")
        return real_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", decline_to_answer)

    exit_code = main([str(root)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        f"a staged tree reported clean by a walk that could not see it; got {exit_code} "
        f"with {output!r}"
    )


def test_targets_in_two_repositories_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two indexes ignored at once, and each one alone would have been read."""
    first = staged_but_not_on_disk(tmp_path / "A")
    second = staged_but_not_on_disk(tmp_path / "B")

    exit_code = main([str(first), str(second)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        f"both repositories' staged content went unexamined; got {exit_code} with {output!r}"
    )


def test_a_repository_beside_a_plain_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third trigger, found by looking for it.

    One target in a work tree and one outside resolves to no single root, so
    the repository target joined the walk and its index went unread.
    """
    root = staged_but_not_on_disk(tmp_path / "repo")
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "readme.md").write_text("# Title\n", encoding="utf-8")

    exit_code = main([str(root), str(plain)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        f"a repository target quietly became a walk target; got {exit_code} with {output!r}"
    )


def test_a_named_symlink_is_judged_before_it_is_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Git was asked about the destination rather than about the entry.

    Resolving the named path before handing it to Git means an untracked link
    is accepted because whatever it points at is tracked -- and the repository
    scan then never enumerates the link, so the run reports clean instead of
    refusing an untracked target.

    Driven through the seam, because creating the link needs a privilege
    Windows withholds; the test below does it for real where the platform
    allows, and CI is what proves that one.
    """
    root = init_repository(tmp_path / "repo")
    (root / "safe.md").write_text("# Title\n", encoding="utf-8")
    git(root, "add", "safe.md")
    commit_index(root, "one tracked file")
    link = root / "tree.ged"
    link.write_bytes(b"")

    real_resolve = Path.resolve

    def resolve_through_the_link(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "tree.ged":
            return real_resolve(root / "safe.md")
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", resolve_through_the_link)

    exit_code = main([str(link)])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        "an untracked link was accepted because its destination is tracked, and the "
        f"scan then left the link out; got {exit_code} with {output!r}"
    )


def test_a_real_untracked_symlink_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same thing without the seam, where the operating system allows it.

    SKIP TWIN: test_a_named_symlink_is_judged_before_it_is_resolved, above,
    asserts the same property through the seam and runs everywhere. Only the
    real directory entry is uncovered when this skips.
    """
    root = init_repository(tmp_path / "repo")
    (root / "safe.md").write_text("# Title\n", encoding="utf-8")
    git(root, "add", "safe.md")
    commit_index(root, "one tracked file")
    try:
        (root / "tree.ged").symlink_to(root / "safe.md")
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip(
            "creating a symlink needs a privilege this platform withholds; "
            "the property is covered here by the seam twin "
            "test_a_named_symlink_is_judged_before_it_is_resolved"
        )

    exit_code = main([str(root / "tree.ged")])

    assert exit_code == 2, f"the link is untracked whatever it points at; got {exit_code}"


def test_a_symlink_named_like_a_tooling_directory_is_still_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exclusion consumed the entry before the symlink loop could see it.

    Tooling directories are skipped by name, and that filter ran first -- so a
    link merely sharing one of those names was dropped, target unread, while
    the coverage line went on claiming symlink targets are classified.

    The seam again: a real directory stands in for the link, and the same case
    runs for real in the test below wherever symlinks can be created.
    """
    workspace = tmp_path / "workspace"
    (workspace / "build").mkdir(parents=True)
    (workspace / "notes.md").write_text("# Title\n", encoding="utf-8")
    target = posix_path("home", "private-user", "tree")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "build")
    monkeypatch.setattr(os, "readlink", lambda path, **_: target)

    exit_code = main([str(workspace)])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"an excluded NAME is not an excluded entry; got {exit_code} with {output!r}"
    )
    assert "not descended into" in output, (
        "an exclusion prunes a real directory from the walk; it does not decide what "
        f"counts as an entry, and the line has to say which it means: {output!r}"
    )


def test_a_real_symlink_named_like_a_tooling_directory_is_classified(tmp_path: Path) -> None:
    """The same case for real, skipped where the platform withholds symlinks.

    SKIP TWIN: test_a_symlink_named_like_a_tooling_directory_is_still_classified,
    directly above, asserts the same property through the seam and runs
    everywhere. Only the real directory entry is uncovered when this skips.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Title\n", encoding="utf-8")
    try:
        (workspace / "build").symlink_to(posix_path("home", "private-user", "tree"))
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip(
            "creating a symlink needs a privilege this platform withholds; "
            "the property is covered here by the seam twin "
            "test_a_symlink_named_like_a_tooling_directory_is_still_classified"
        )

    findings = pii_guard.scan_paths([workspace])

    assert [finding.rule for finding in findings] == ["P1"], (
        f"the link's target is an absolute personal path, got {findings}"
    )


def test_a_plain_directory_still_takes_the_walk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not a repository is the ONE condition that may walk, and it still does."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "notes.md").write_text(gedcom_document(), encoding="utf-8")

    exit_code = main([str(plain)])
    output = capsys.readouterr().out

    assert exit_code == 1, f"refusing everything is not the fix; got {exit_code} with {output!r}"
    assert "over files" in output, f"and it is the walk that ran; got {output!r}"


def test_a_redirected_git_directory_does_not_silently_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Git answering the wrong question successfully, which is worse than failing.

    The earlier fix covered rev-parse FAILING. Pointed at a bare repository it
    exits zero and prints false, so the metadata check never runs and the named
    repository silently becomes a filesystem walk -- and the walk cannot see
    what the index holds.
    """
    root = staged_but_not_on_disk(tmp_path / "repo")
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "--bare", "--quiet", str(bare))
    monkeypatch.setenv("GIT_DIR", str(bare))

    exit_code = main([str(root)])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"the staged tree is what the next commit publishes; got {exit_code} with {output!r}"
    )


def test_a_git_directory_pointing_at_another_tree_scans_the_named_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The nastier flavour, which neither reviewer reported.

    Pointed at a different *work tree*, rev-parse exits zero and says true --
    about that other tree. The run then resolves someone else's repository as
    its root and reports on it while naming this one.
    """
    root = staged_but_not_on_disk(tmp_path / "repo")
    elsewhere = init_repository(tmp_path / "elsewhere")
    (elsewhere / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(elsewhere, "an unrelated repository")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))

    exit_code = main([str(root)])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"the named repository's index is the one that matters; got {exit_code} with {output!r}"
    )


def test_a_link_does_not_choose_which_repository_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second site the link-following helper covers.

    Choosing the directory to ask Git about by following the link asks the
    repository at the destination, so a link pointing into another checkout
    made that checkout the root while this one was named.

    A real nested repository stands in for the destination, since this platform
    withholds symlink creation; the property is the same either way.
    """
    outer = staged_but_not_on_disk(tmp_path / "outer")
    nested = init_repository(outer / "vendor")
    (nested / "README.md").write_text("# Title\n", encoding="utf-8")
    commit_all(nested, "an unrelated checkout")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "vendor")

    exit_code = main([str(outer / "vendor")])
    output = capsys.readouterr().out

    assert exit_code == 2, (
        "the named entry belongs to the outer repository, which does not track it; "
        f"got {exit_code} with {output!r}"
    )


def test_a_link_to_the_scan_root_is_still_judged_as_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third site: comparing a target to the root by resolving it.

    A link pointing at the scan root compared equal to the root, which skipped
    the check that a named entry must be tracked -- so the link itself was
    never judged at all.
    """
    root = staged_but_not_on_disk(tmp_path / "repo")
    (root / "self").write_bytes(b"")

    real_resolve = Path.resolve

    def resolve_to_the_root(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "self":
            return real_resolve(root)
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "resolve", resolve_to_the_root)

    exit_code = main([str(root / "self")])
    output = capsys.readouterr().out

    assert exit_code == 2, f"a link is not the thing it points at; got {exit_code} with {output!r}"


def test_a_denylist_loads_beside_the_link_not_its_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's reproduction, and the item I filed wrongly as a design question.

    A deny-list sits beside a link that is *named* after one of its entries and
    points at an empty directory. Following the link to choose where the list
    loads reads the empty directory, so the deny-listed name passes -- a bypass
    of the documented personal-literal backstop, not a question of taste.

    Driven through the seam because this platform withholds symlink creation;
    the real version below skips here and CI proves it.
    """
    workspace = tmp_path / "workspace"
    (workspace / "Ashenmoor").mkdir(parents=True)
    (workspace / pii_guard.DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "Ashenmoor")
    monkeypatch.setattr(os, "readlink", lambda path, **_: "../empty")

    exit_code = main([str(workspace / "Ashenmoor")])
    output = capsys.readouterr().out

    assert exit_code == 1, (
        f"the deny-list beside the named entry is the one in force; got {exit_code} with {output!r}"
    )


def test_a_real_denylist_loads_beside_the_link(tmp_path: Path) -> None:
    """The same thing without the seam, where symlinks can be created.

    SKIP TWIN: test_a_denylist_loads_beside_the_link_not_its_destination,
    directly above, asserts the same property through the seam and runs
    everywhere. Only the real directory entry is uncovered when this skips.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / pii_guard.DENYLIST_FILENAME).write_text("Ashenmoor\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    try:
        (workspace / "Ashenmoor").symlink_to("../empty", target_is_directory=True)
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip(
            "creating a symlink needs a privilege this platform withholds; "
            "the property is covered here by the seam twin "
            "test_a_denylist_loads_beside_the_link_not_its_destination"
        )

    exit_code = main([str(workspace / "Ashenmoor")])

    assert exit_code == 1, (
        f"a link named after a deny-listed literal is still that name; got {exit_code}"
    )


def test_every_target_keeps_its_own_denylist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adding a target silently disabled that target's protection.

    Only the deny-list beside the FIRST target was loaded, and it was applied
    to all of them, so scanning two directories together missed a literal that
    scanning either one alone caught. The property it disabled is the one
    holding real personal names.
    """
    for name, literal in (("A", "Ashenmoor"), ("B", "Quorvane")):
        directory = tmp_path / name
        directory.mkdir()
        (directory / pii_guard.DENYLIST_FILENAME).write_text(f"{literal}\n", encoding="utf-8")
        (directory / "notes.md").write_text(f"a note mentioning {literal}\n", encoding="utf-8")

    main([str(tmp_path / "A"), str(tmp_path / "B")])
    together = capsys.readouterr().out

    assert together.startswith("2 finding") or "\n2 finding" in together, (
        f"each target's own deny-list must survive being scanned alongside another: {together!r}"
    )


def test_the_coverage_line_does_not_deny_scanning_what_it_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Asserted against behaviour, not against a fixed string.

    The consolidation made the walk classify symlink targets and left the
    summary claiming the opposite, so a run counted and scanned a link while
    saying it had not. That line is the one thing an operator reads to know
    what was covered, and it has now drifted three times.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (workspace / "tree").write_bytes(b"")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "tree")
    monkeypatch.setattr(os, "readlink", lambda path, **_: posix_path("srv", "data", "trees"))

    exit_code = main([str(workspace)])
    output = capsys.readouterr().out
    summary = output.splitlines()[-1]

    assert exit_code == 1, f"the link was scanned and its target reported; got {exit_code}"

    unscanned = [clause for clause in summary.split(";") if "not scanned" in clause]
    assert unscanned, f"the line must still say what it leaves out; got {summary!r}"
    assert not any("symlink" in clause for clause in unscanned), (
        f"the run scanned a symlink while listing symlinks as unscanned: {summary!r}"
    )
    assert "not followed" in summary, (
        "the link is classified and its target is not descended into -- both are true "
        f"and the second is worth saying; got {summary!r}"
    )


def test_the_coverage_line_is_honest_about_what_is_never_scanned(
    repository_with_a_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Annotated tags and notes are enumerated by neither scanner.

    Not chased this round. A gap nobody has written down is indistinguishable
    from coverage.
    """
    main([str(repository_with_a_tree)])
    output = capsys.readouterr().out

    assert "tags" in output and "notes" in output, (
        f"the line names commit messages as unscanned but not these; got {output!r}"
    )
