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


# ------------------------------------------------------- the final judgement


def _good(**overrides: object) -> dict[str, object]:
    """A metadata snapshot GitHub would call mergeable, before any override."""
    snapshot: dict[str, object] = {
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": "a" * 40,
        "baseRefOid": "b" * 40,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "baseRef": {"name": "main", "target": {"oid": "b" * 40}},
    }
    snapshot.update(overrides)
    return snapshot


def test_a_fully_good_snapshot_is_the_only_thing_that_passes() -> None:
    assert pr_ready._judge(_good(), "a" * 40) == []


def test_every_field_is_REQUIRED_not_merely_checked() -> None:
    """⛔ An absent field is not a field that is fine.

    ⚠️ GitHub omits what it cannot answer. Comparing a missing value against a
    good one happens to block, but only by luck -- so absence is named instead,
    and a schema change becomes a loud error rather than a quiet verdict.
    """
    for field in pr_ready.METADATA_FIELDS:
        snapshot = _good()
        del snapshot[field]

        reasons = pr_ready._judge(snapshot, "a" * 40)

        assert len(reasons) == 1, f"{field}: expected one reason, got {reasons}"
        assert field in reasons[0]


def test_BLOCKED_does_not_pass__the_tenth_defect() -> None:
    """⛔ The finding that proved an enumeration cannot stand in for a bound.

    The version this replaces rejected only CONFLICTING and DIRTY, so BLOCKED --
    branch protection awaiting an approval or a required check -- printed READY
    for a pull request GitHub refuses to merge.
    """
    reasons = pr_ready._judge(_good(mergeStateStatus="BLOCKED"), "a" * 40)

    assert reasons and "BLOCKED" in reasons[0]


def test_only_CLEAN_passes__every_other_merge_state_blocks() -> None:
    """⭐ The allowlist, asserted as one. A list of BAD states cannot be completed."""
    for status in ("BEHIND", "BLOCKED", "DIRTY", "DRAFT", "HAS_HOOKS", "UNKNOWN", "UNSTABLE"):
        assert pr_ready._judge(_good(mergeStateStatus=status), "a" * 40), status


def test_UNKNOWN_mergeability_blocks_and_says_to_run_again() -> None:
    """⚠️ Not rare -- GitHub computes it asynchronously. It blocks, and it clears."""
    reasons = pr_ready._judge(_good(mergeable="UNKNOWN"), "a" * 40)

    assert reasons and "run again" in reasons[0]


def test_a_base_that_moved_blocks__the_ninth_defect() -> None:
    """⛔ The live base tip rides in the SAME answer as the one it is compared to.

    ⚠️ mergeStateStatus alone cannot catch this: GitHub reports BEHIND only where
    the repository requires up-to-date branches, and otherwise says CLEAN. #175
    read CLEAN with its base seven commits behind.
    """
    moved = _good(baseRef={"name": "main", "target": {"oid": "c" * 40}})

    reasons = pr_ready._judge(moved, "a" * 40)

    assert reasons and "base has moved" in reasons[0]


def test_a_head_that_moved_during_the_sweep_blocks() -> None:
    """The evidence gathered earlier is about a commit that is no longer the head."""
    reasons = pr_ready._judge(_good(headRefOid="d" * 40), "a" * 40)

    assert reasons and "the head moved" in reasons[0]


def test_a_draft_blocks_however_green_everything_else_is() -> None:
    assert pr_ready._judge(_good(isDraft=True), "a" * 40)


def test_a_closed_pull_request_blocks() -> None:
    assert pr_ready._judge(_good(state="MERGED"), "a" * 40)


# ------------------------------------------------------------- the bot's name


def test_BOTH_spellings_of_the_bot_are_recognised() -> None:
    """⛔ REST appends [bot]; GraphQL does not. The same account either way.

    ⚠️ This mismatch already returned an empty count for a pull request with
    eight rounds -- an empty read presented as an absence.
    """
    assert pr_ready._is_bot("chatgpt-codex-connector[bot]")
    assert pr_ready._is_bot("chatgpt-codex-connector")
    assert not pr_ready._is_bot("randyjreid")
    assert not pr_ready._is_bot(None)


# ------------------------------------------------------------- the round count


def test_the_backstop_line_is_silent_below_five() -> None:
    for rounds in range(pr_ready.BACKSTOP):
        assert pr_ready._round_note(rounds) == "", rounds


def test_the_backstop_line_fires_AT_five_and_above() -> None:
    """⚠️ #175 passed five unnoticed and ran to eight, because the count lived in
    nobody's head. Each round was defensible on its own; the aggregate was not.
    """
    assert "5 bot rounds" in pr_ready._round_note(5)
    assert "8 bot rounds" in pr_ready._round_note(8)
    assert "owner's call" in pr_ready._round_note(5)


def test_the_backstop_line_only_ADVISES() -> None:
    """⛔ It prints. It is not among the things that can block.

    The backstop is the owner's decision; a script enforcing it would be taking
    that decision rather than informing it.
    """
    eight_rounds_but_otherwise_perfect = _good()

    assert pr_ready._judge(eight_rounds_but_otherwise_perfect, "a" * 40) == []
    assert pr_ready._round_note(8)


def _review(body: str = "**Reviewed commit:** `abc123`") -> dict[str, object]:
    return {"body": body}


def test_a_CLEAN_round_is_counted__it_creates_no_review_object() -> None:
    """⛔ The undercount, on real numbers.

    A clean round arrives as a conversation comment and creates no review object,
    so counting review objects missed every one. ⚠️ **Measured on merged pull
    requests: #164 had 10 review objects and 2 clean comments -- 12 rounds
    counted as 10; #159 was 7 of 8.** #175 counted 8 of 8, which is precisely why
    the bug was invisible: not one of its rounds was ever clean.
    """
    reviews = [_review() for _ in range(10)]
    clean = [
        _comment(
            "2026-08-31T09:51:56Z",
            "Codex Review: Didn't find any major issues. Hooray! **Reviewed commit:** `ad5b704dac`",
        ),
        _comment(
            "2026-08-31T11:10:39Z",
            "Codex Review: Didn't find any major issues. **Reviewed commit:** `8d2bc15ade`",
        ),
    ]

    assert pr_ready._round_count(reviews, clean) == 12


def test_the_marker_is_the_discriminator__not_the_clean_phrasing() -> None:
    """⭐ Every artifact the bot publishes names the commit it reviewed.

    ⚠️ Matching the clean PHRASES instead would be an enumeration that goes stale
    the moment the bot varies its wording -- and it already varies the sentence
    after it ("Hooray!" / "Keep them coming!").
    """
    chatter = [_comment("2026-08-31T10:00:00Z", "some bot message that reviewed nothing")]

    assert pr_ready._round_count([], chatter) == 0
    assert pr_ready._round_count([], [_comment("x", "**Reviewed commit:** `deadbee`")]) == 1


def test_a_review_object_counts_even_WITHOUT_the_marker() -> None:
    """⚠️ Asymmetric on purpose: a review IS a round; a comment only announces one.

    Undercounting is the failure being repaired, so the side that can only ever
    undercount gets the benefit of the doubt.
    """
    assert pr_ready._round_count([_review(body="")], []) == 1


def test_the_undercount_would_have_hidden_the_backstop() -> None:
    """⛔ The two defects compose: a low count silences the advisory.

    Four findings-rounds and one clean round is five, which fires. Counting
    review objects alone says four, which does not -- so a pull request at the
    backstop looks like one below it.
    """
    four_with_findings = [_review() for _ in range(4)]
    one_clean = [_comment("x", "**Reviewed commit:** `abc1234`")]

    assert pr_ready._round_count(four_with_findings, one_clean) == 5
    assert pr_ready._round_note(pr_ready._round_count(four_with_findings, one_clean))
    assert not pr_ready._round_note(len(four_with_findings))
