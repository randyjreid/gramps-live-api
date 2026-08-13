"""Scanning real directory trees, including this repository itself."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import (
    count_range_commits,
    find_committed_denylists,
    main,
    scan_paths,
    scan_repository,
)
from tests.fixtures.expectations import rules
from tests.fixtures.synthetic import gedcom_document, posix_path, unclassifiable_bytes

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small directory tree: three clean files and three that must be caught."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nRelative paths only.\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("VALUE = 1\n")
    (tmp_path / "README.md").write_text("# Title\n")

    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "notes.txt").write_text(gedcom_document(), encoding="utf-8")
    (tmp_path / "records" / "scan.bin").write_bytes(unclassifiable_bytes())
    (tmp_path / "docs" / "install.md").write_text(
        f"unpack it into {posix_path('srv', 'trees', 'live')}\n"
    )
    return tmp_path


def test_scan_over_a_tree_finds_every_planted_problem(tree: Path) -> None:
    findings = scan_paths([tree])

    assert rules(findings) == ["P1", "P2"], f"expected P1 and P2 findings, got {findings}"
    sources = {finding.source.rendered(redact=False) for finding in findings}
    assert sources == {"records/notes.txt", "records/scan.bin", "docs/install.md"}


def test_scan_over_a_tree_reports_each_finding_once(tree: Path) -> None:
    findings = scan_paths([tree])
    assert len(findings) == 3, f"expected one finding per planted file, got {findings}"


def test_a_single_file_path_can_be_scanned(tree: Path) -> None:
    findings = scan_paths([tree / "records" / "notes.txt"])
    assert rules(findings) == ["P2"], f"expected a P2 finding, got {findings}"


def test_tooling_directories_are_not_scanned(tmp_path: Path) -> None:
    for excluded in (".git", "__pycache__", ".venv"):
        directory = tmp_path / excluded
        directory.mkdir()
        (directory / "notes.txt").write_text(gedcom_document(), encoding="utf-8")

    assert scan_paths([tmp_path]) == [], "tooling directories are not committed content"


def test_the_command_line_entry_point_reports_and_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(tree)])

    assert exit_code == 1
    assert "3" in capsys.readouterr().out


def test_the_command_line_entry_point_succeeds_on_a_clean_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# Title\n")

    assert main([str(tmp_path)]) == 0
    assert "0" in capsys.readouterr().out


def test_this_repository_is_clean() -> None:
    findings = scan_repository(REPOSITORY_ROOT)
    assert findings == [], f"this repository must not contain personal data, got {findings}"


def test_every_commit_this_repository_publishes_is_clean() -> None:
    """B8's second half: the tip is not what a push publishes.

    Content added in one commit and deleted in the next is gone from the tree
    the test above scans and is still reachable, so the criterion is measured
    over the commits as well. ``HEAD`` is everything reachable, which is a
    SUPERSET of any range a single push publishes and the same range the
    workflow's tag arm scans -- so it cannot be narrower than the thing it
    stands for, whatever event runs next.

    Two things make it a measurement rather than a formality. The scanner it
    uses is known to report when there is something to report -- that is
    ``test_a_blob_deleted_later_in_the_push_is_still_found``, over a fixture
    repository, and this test would be worth nothing without it. And the commit
    count is asserted before the verdict, because "scanned nothing" and "found
    nothing" must not read the same.

    ⚠️ **This is a measurement of THIS repository at THIS commit, and it costs a
    walk of the history** -- measured at 34.6 seconds over 74 commits, against
    the twelve seconds over thirty-six commits recorded when this was written.
    The two figures come from different machines, so read the pair as growth
    with the history rather than as a rate. Since issue #31 that walk is paid
    on each of CI's three Python legs as well as locally, which is the price of
    the assertion running there at all rather than skipping. It says nothing
    about content the repository does not yet contain.
    """
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
        # ⚠️ The same anchored environment the scan below runs under. Git
        # honours GIT_DIR and GIT_WORK_TREE ahead of cwd, so an unanchored
        # probe answers about whatever the environment points at -- and it
        # answers SUCCESSFULLY. A complete repository named there reports
        # "false", the skip does not fire, and count_range_commits and
        # scan_repository then run anchored on THIS repository and report
        # clean over history that was never fetched. The probe and the thing
        # it guards must not be able to disagree about which repository they
        # mean. The list is the guard's, which is git's own answer rather
        # than a second one written here.
        env=pii_guard._git_environment_anchored_on_the_target(),
    ).stdout.strip()

    # Fails closed on anything that is not exactly "false", like the workflow
    # step this defers to: a truncated history reports clean over the part that
    # was never fetched, which is the fail-open the range scans exist to close.
    if shallow != "false":
        pytest.skip(
            "the checkout is not provably complete, so a range scan here would report "
            "clean over history that was never fetched -- seam twin "
            "test_the_job_refuses_a_checkout_it_cannot_prove_is_complete"
        )

    covered = count_range_commits(REPOSITORY_ROOT, "HEAD")
    assert covered > 0, "the range covered no commits, so a clean verdict would cover nothing"

    findings = scan_repository(REPOSITORY_ROOT, revision_range="HEAD")

    assert findings == [], (
        f"the commits this repository publishes must not contain personal data, got {findings}"
    )


def test_the_guard_source_is_clean_under_its_own_rules() -> None:
    source = Path(pii_guard.__file__)
    assert scan_paths([source]) == [], "the guard must satisfy the properties it enforces"


def test_no_denylist_is_committed() -> None:
    committed = find_committed_denylists(REPOSITORY_ROOT)

    assert committed == [], (
        "a deny-list of personal literals must never be committed. Asking Git "
        "rather than the filesystem is the point: a developer who follows "
        "CONTRIBUTING has one on disk, correctly ignored, and that must not "
        "fail the suite"
    )


DENYLIST_VARIANTS = (
    ".pii-denylist",
    ".pii-denylist.md",
    ".pii-denylist.txt",
    ".pii-denylist.local",
    ".pii-denylist.bak",
    "src/.pii-denylist.py",
    "tests/.pii-denylist.py",
    ".github/.pii-denylist.yml",
)


@pytest.mark.parametrize("variant", DENYLIST_VARIANTS)
def test_every_denylist_variant_is_gitignored(variant: str) -> None:
    ignored = (
        subprocess.run(
            ["git", "check-ignore", "-q", variant],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )

    assert ignored, (
        f"{variant} can be staged. Ask Git by exit code, never by reading "
        ".gitignore and never from check-ignore output: the -v output prints "
        "the matching line even when that line is a negation, so a re-included "
        "path looks ignored"
    )
