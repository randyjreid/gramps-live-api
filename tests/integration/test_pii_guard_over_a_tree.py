"""Scanning real directory trees, including this repository itself."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import (
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
