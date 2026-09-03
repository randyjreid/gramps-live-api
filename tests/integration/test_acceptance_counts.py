"""The acceptance document's test counts, checked against the files they name.

⛔ **Issue #36.** ``docs/pii-guard-acceptance.md`` states a test count for each
file a criterion rests on, every one maintained by hand, and every change to a
counted file makes one of them wrong. ``test_repository_hygiene.py`` alone had
staled its count **three times in three separate changes**, by three pieces of
work that had nothing to do with the criterion it serves -- costing two review
rounds once, where the repair then miscounted which tests were the criterion's
evidence and *overstated what the criterion rested on*, the opposite of the
document's purpose.

⭐ **A stale count is now a red test in the same run that created it**, rather
than something the next reader may or may not notice.

⚠️ **THIS ASSERTS THE FILE'S COUNT AND NOTHING ELSE, and the distinction is the
whole reason the document is careful.** The document says so in its own words:
*"the count is the file's, as B1's is, and the two numbers are not the same
number."* **How many tests carry a criterion is a judgement no parser can make**,
and a test pretending otherwise would be worse than no test -- it would put a
green tick under a number nobody had checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = REPOSITORY_ROOT / "docs" / "pii-guard-acceptance.md"

# ⚠️ **Both shapes the document actually uses.** Most statements read
# ```path` -- **N tests**`` on one line, but at least one carries the count on
# the line after the path, so the gap is matched across newlines. It is bounded
# rather than open: a window wide enough for a sentence, not wide enough to pair
# a path with some other paragraph's number.
STATEMENT = re.compile(r"`(tests/[^`]+\.py)`[^`]{0,60}?\*\*(\d+) tests?\*\*", re.DOTALL)

# Every ``**N tests**`` in the document, whether or not a path was paired with it.
ANY_COUNT = re.compile(r"\*\*(\d+) tests?\*\*")

DEFINITION = re.compile(r"^def (test_\w+)", re.MULTILINE)


def documented() -> list[tuple[str, int]]:
    return [(path, int(count)) for path, count in STATEMENT.findall(_document())]


def _document() -> str:
    return ACCEPTANCE.read_text(encoding="utf-8")


def test_every_documented_count_was_paired_with_a_file() -> None:
    """⛔ Non-vacuity, and it is the assertion that keeps the rest honest.

    ⚠️ **A parser that silently pairs fewer statements than the document holds
    stops watching the ones it missed**, and reports nothing. This project has
    paid for a check that passed because it looked at less than it claimed, so
    the two totals are compared rather than assumed equal: every ``**N tests**``
    in the document must have been matched to a path.
    """
    paired = len(documented())
    present = len(ANY_COUNT.findall(_document()))

    assert paired, "no counts were parsed at all -- this test has stopped watching anything"
    assert paired == present, (
        f"the document states {present} test counts but only {paired} were paired with a "
        f"file path. A statement written in a shape this parser does not recognise is "
        f"unchecked, which is the failure this test exists to prevent -- widen STATEMENT "
        f"or reword the statement so the path and its count sit together."
    )


@pytest.mark.parametrize("path, claimed", documented(), ids=lambda value: str(value))
def test_a_documented_count_matches_the_file_it_names(path: str, claimed: int) -> None:
    """⭐ The document is the source; the file is the truth. They must agree.

    ⛔ **The failure names the fix**, because the reader is someone who changed a
    test file for an unrelated reason and has no idea a document mentions it.
    """
    target = REPOSITORY_ROOT / path
    assert target.is_file(), (
        f"{path} is named by docs/pii-guard-acceptance.md and does not exist. "
        f"Either the file moved and the document still points at the old path, "
        f"or the count belongs to something that was deleted."
    )

    actual = len(DEFINITION.findall(target.read_text(encoding="utf-8")))

    assert actual == claimed, (
        f"docs/pii-guard-acceptance.md says {path} has {claimed} tests; it defines "
        f"{actual}. Change the number in the document to {actual}.\n"
        f"⚠️ That is the FILE's count. Whether the criterion still rests on the same "
        f"tests is a separate question this check cannot answer -- if you added a test "
        f"for something else, the number moves and the criterion's evidence does not."
    )
