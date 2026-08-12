"""Findings sort without reaching through the Secret wrapper.

``Secret`` has no ordering, deliberately. The sort key used to end in the
matched value, which is only reached when two findings share both line and
rule -- so this crashed on the first file that had two of anything on one line,
and not before.

It was never range-specific. The narrowest reproduction is a single line of
text with two paths on it; the range scan was merely the first invocation to
meet such a file.
"""

from __future__ import annotations

from gramps_live_api.core.pii_guard import scan_text
from tests.fixtures.synthetic import posix_path


def test_two_paths_on_one_line_are_both_reported() -> None:
    line = (
        "copied from "
        + posix_path("home", "private-user", "trees")
        + " to "
        + posix_path("var", "backups", "trees")
    )

    findings = scan_text(line)

    assert [finding.rule for finding in findings] == ["P1", "P1"], (
        "sorting two findings that share a line and a rule reaches the third "
        f"key element, and the matched value is not orderable; got {findings}"
    )


def test_two_denylisted_names_on_one_line_are_both_reported() -> None:
    # The collision this file exists for, carried by a rule that survives P3's
    # removal. The two entries must DIFFER: two equal values compare equal all
    # the way along the key, so the ordering operator is never reached and the
    # test passes without exercising anything.
    findings = scan_text("the Ashenmoor and Quorvane papers", denylist=["Ashenmoor", "Quorvane"])

    assert [finding.rule for finding in findings] == ["LOCAL", "LOCAL"], (
        f"the same collision through a surviving rule; got {findings}"
    )


def test_the_order_of_findings_is_deterministic() -> None:
    text = "\n".join(
        [
            "copied from "
            + posix_path("home", "private-user", "trees")
            + " to "
            + posix_path("var", "backups", "trees"),
            "the Ashenmoor and Quorvane papers",
        ]
    )

    renderings = [
        [str(finding) for finding in scan_text(text, denylist=["Ashenmoor", "Quorvane"])]
        for _ in range(3)
    ]

    assert renderings[0] == renderings[1] == renderings[2], (
        "a gate people diff must not reorder between runs"
    )
    assert len(renderings[0]) == 4


def test_a_file_given_directly_is_named_by_its_own_name() -> None:
    # Round 5, finding 3: relative_to returns a single dot when the path IS
    # the base, and a dot is truthy, so the fallback never fired and every
    # file argument reported the same unlocatable source.
    from pathlib import Path

    from gramps_live_api.core.pii_guard import _relative_source

    base = Path("some") / "where" / "notes.md"
    other = Path("some") / "where" / "other.md"

    assert _relative_source(base, [base, other]) == "notes.md"
    assert _relative_source(other, [base, other]) == "other.md"
