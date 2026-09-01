"""⛔ The readiness gate's judgement, bound by tests rather than by review.

``scripts/pr_ready.py`` was written to stop merge-readiness being re-derived in
prose, and it worked -- it caught two merged pull requests being reported as
awaiting the click. ⚠️ **But it shipped with no tests, and was then wrong twelve
times.** Every one of those defects was found by a reviewer READING it. Not one
was found by running it.

⭐ **So the judgement lives in pure functions and the tests call them directly.**
The API calls feed those functions; they decide nothing themselves. That split is
the point of the simplification, not a convenience for testing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ⛔ ``scripts`` is not a package and is not importable by name. Loaded by path,
# which is also how a contributor runs it.
_spec = importlib.util.spec_from_file_location("_pr_ready", ROOT / "scripts" / "pr_ready.py")
assert _spec is not None and _spec.loader is not None
pr_ready = importlib.util.module_from_spec(_spec)
sys.modules["_pr_ready"] = pr_ready
_spec.loader.exec_module(pr_ready)


def _comment(when: str, body: str = "") -> dict[str, object]:
    return {"created_at": when, "body": body}


# ---------------------------------------------------------------- the trigger


def test_the_phrase_is_not_written_literally_in_the_source() -> None:
    """⛔ This file's own source must not contain a review request.

    ⚠️ The bot matches a substring, and both this test and the script appear in
    their own pull request's diff. Assembling the phrase from parts is what keeps
    a source file from reading as a request -- and this asserts it stays that way.
    """
    for path in (ROOT / "scripts" / "pr_ready.py", Path(__file__)):
        assert pr_ready.TRIGGER not in path.read_text(encoding="utf-8")


def test_a_request_is_found_whoever_posted_it() -> None:
    """⚠️ Not filtered to the bot -- the request comes from whoever drives the gate."""
    comments = [
        _comment("2026-08-31T10:00:00Z", "some unrelated note"),
        _comment("2026-08-31T11:00:00Z", f"please {pr_ready.TRIGGER} now"),
        _comment("2026-08-31T10:30:00Z", pr_ready.TRIGGER.upper()),
    ]
    assert pr_ready._latest_request(comments) == "2026-08-31T11:00:00Z"


def test_no_request_at_all_leaves_the_other_evidence_standing() -> None:
    """⭐ The automatic review on open: there is no request to be stale against."""
    clean = [_comment("2026-08-31T10:00:00Z")]
    assert pr_ready._latest_request([_comment("2026-08-31T09:00:00Z", "hi")]) == ""
    assert pr_ready._still_current(clean, "") == clean


def test_a_verdict_PREDATING_the_latest_request_is_superseded() -> None:
    """⛔ The twelfth defect, and it fired on the path this project uses constantly.

    A round is requested without changing the head -- which is what every
    disputed or filed finding produces, since neither involves a push. The
    previous round's clean comment still names that head, so naming alone
    accepted it while the new round was still running.
    """
    clean = [_comment("2026-08-31T10:31:00Z")]
    request = "2026-08-31T11:10:00Z"

    assert pr_ready._still_current(clean, request) == []


def test_a_verdict_POSTDATING_the_latest_request_stands() -> None:
    clean = [_comment("2026-08-31T11:13:55Z")]
    request = "2026-08-31T11:10:00Z"

    assert pr_ready._still_current(clean, request) == clean


def test_the_case_that_was_live_during_the_session_that_found_this() -> None:
    """⚠️ #159 was declared READY on an unchanged head with a prior round on it.

    It was sound -- but only because a sweep happened to run before the trigger,
    which is luck, not a check. These are the real timestamps: the earlier round
    at 10:32 produced findings, the request went out at ~11:10, and the clean
    comment landed at 11:13:55. ⭐ **The rule accepts the second and rejects the
    first**, which is what makes the outcome deliberate instead of lucky.
    """
    earlier_round = _comment("2026-08-31T10:32:00Z")
    the_clean_one = _comment("2026-08-31T11:13:55Z")
    request = "2026-08-31T11:10:39Z"

    current = pr_ready._still_current([earlier_round, the_clean_one], request)

    assert current == [the_clean_one]
