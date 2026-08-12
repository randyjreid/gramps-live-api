"""The local-only personal deny-list.

Personal literals are the one thing that must never be committed, so they live
in a gitignored file that each developer writes for themselves. The guard reads
it if it is there and works without it if it is not.

Every literal used here is invented.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from gramps_live_api.core.pii_guard import (
    DENYLIST_FILENAME,
    load_denylist,
    main,
    scan_paths,
    scan_text,
)
from tests.fixtures.expectations import rules


def write_denylist(root: Path, body: str) -> Path:
    location = root / DENYLIST_FILENAME
    location.write_text(body, encoding="utf-8")
    return location


def test_absent_denylist_yields_no_patterns(tmp_path: Path) -> None:
    assert load_denylist(tmp_path) == []


def test_denylist_is_one_literal_per_line_ignoring_blanks_and_comments(tmp_path: Path) -> None:
    write_denylist(tmp_path, "# people\nAshenmoor\n\n  Quorvane  \n")

    assert load_denylist(tmp_path) == ["Ashenmoor", "Quorvane"]


def test_denylisted_literal_is_a_finding() -> None:
    findings = scan_text("born to the Ashenmoor family", denylist=["Ashenmoor"])

    assert rules(findings) == ["LOCAL"], f"expected a LOCAL finding, got {findings}"
    assert findings[0].line == 1


def test_denylist_matching_ignores_case() -> None:
    findings = scan_text("the ASHENMOOR papers", denylist=["Ashenmoor"])

    assert rules(findings) == ["LOCAL"], f"expected a LOCAL finding, got {findings}"


def test_denylist_finding_does_not_echo_the_literal() -> None:
    findings = scan_text("the Ashenmoor papers", denylist=["Ashenmoor"])

    assert findings, "expected a LOCAL finding"
    assert "Ashenmoor" not in str(findings[0]), (
        "reporting the deny-listed literal would republish the thing being hidden"
    )


def test_text_without_the_literal_is_not_a_finding() -> None:
    assert scan_text("no such family here", denylist=["Ashenmoor"]) == []


def test_the_denylist_is_never_scanned_as_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "notes.md").write_text("nothing to see\n", encoding="utf-8")
    write_denylist(tmp_path, "Ashenmoor\nQuorvane\n")
    monkeypatch.chdir(tmp_path)

    findings = scan_paths([tmp_path])

    assert findings == [], (
        "every literal in the deny-list matches itself, so scanning the file "
        f"makes the documented command fail on a clean checkout, got {findings}"
    )


def test_following_the_documentation_leaves_the_command_passing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notes.md").write_text("nothing to see\n", encoding="utf-8")
    write_denylist(tmp_path, "# my people\nAshenmoor\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main([str(tmp_path)])
    capsys.readouterr()

    assert exit_code == 0, "a contributor who follows CONTRIBUTING must not be punished for it"


def test_scan_paths_picks_up_a_denylist_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "notes.md").write_text("a note about Quorvane\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    write_denylist(tmp_path, "Quorvane\n")

    findings = scan_paths([tree])

    assert rules(findings) == ["LOCAL"], f"expected a LOCAL finding, got {findings}"


def test_matching_survives_unicode_normalisation() -> None:
    """The deny-list is the recorded backstop for P1's residual, and the names
    it protects carry accents. Lower-casing does not normalise, so a composed
    entry missed canonically equivalent decomposed text entirely."""
    composed = unicodedata.normalize("NFC", "Ashenmoör")
    decomposed = unicodedata.normalize("NFD", "Ashenmoör")
    assert composed != decomposed, "the fixture must actually differ byte for byte"

    findings = scan_text(f"the {decomposed} papers", denylist=[composed])

    assert rules(findings) == ["LOCAL"], (
        f"canonically equivalent text is the same name, got {findings}"
    )


def test_normalisation_applies_in_both_directions() -> None:
    composed = unicodedata.normalize("NFC", "Ashenmoör")
    decomposed = unicodedata.normalize("NFD", "Ashenmoör")

    findings = scan_text(f"the {composed} papers", denylist=[decomposed])

    assert rules(findings) == ["LOCAL"], f"both sides are normalised, got {findings}"
