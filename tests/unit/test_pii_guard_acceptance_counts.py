"""The acceptance document's file-level test counts must match the files they name.

Issue #36: those numbers are maintained by hand, and every change to a counted
file stales one. A stale count that once matched is the worst kind, because it
reads as considered.

⭐ Both sides are derived. The document is the source; this test does not list
the files. A hand-written list here would be a second copy that can itself go
stale -- the same move as ``test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row``.

⚠️ This asserts the FILE's count of ``def test_`` definitions, not pytest's
collected items and not the criterion's evidence. B7 records that distinction
on purpose: one definition is parametrized, so collection is a different number
that moves for reasons the criterion has nothing to do with.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = REPOSITORY_ROOT / "docs" / "pii-guard-acceptance.md"

# A backticked tests/*.py path, then **N tests** close enough that it is THAT
# file's count. Criterion-only numbers ("thirty-five", "four of the twelve")
# do not use this spelling and are not this test's business.
FILE_COUNT = re.compile(
    r"`(tests/[\w./-]+\.py)`[\s,.\-–—]{0,20}\*\*(\d+) tests\*\*",
    re.DOTALL,
)
TEST_DEF = re.compile(r"^def test_", re.MULTILINE)


def test_acceptance_file_counts_match_the_named_files() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")
    claims = FILE_COUNT.findall(text)
    assert claims, (
        f"{ACCEPTANCE.relative_to(REPOSITORY_ROOT)} states no file-level test "
        "counts of the form `tests/….py` -- **N tests**, so this test has "
        "stopped watching anything"
    )

    documented: dict[str, int] = {}
    disagreements: list[str] = []
    for path, raw in claims:
        count = int(raw)
        previous = documented.get(path)
        if previous is not None and previous != count:
            disagreements.append(f"{path}: the document claims both {previous} and {count} tests")
        documented[path] = count

    for path, count in documented.items():
        source = REPOSITORY_ROOT / path
        assert source.is_file(), f"{path}: named in {ACCEPTANCE.name} but the file is not there"
        actual = len(TEST_DEF.findall(source.read_text(encoding="utf-8")))
        if actual != count:
            disagreements.append(
                f"{path}: the document says {count} tests, the file has {actual} "
                f"def test_ functions. Update the count in {ACCEPTANCE.name} -- "
                "this is the file's count of definitions, not pytest's collected items"
            )

    assert disagreements == [], "; ".join(disagreements)
