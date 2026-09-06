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
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_a_request_from_any_HUMAN_counts() -> None:
    """The request comes from whoever drives the gate -- not only from one account."""
    comments = [
        _comment("2026-08-31T10:00:00Z", "some unrelated note"),
        _comment("2026-08-31T11:00:00Z", f"please {pr_ready.TRIGGER} now"),
        _comment("2026-08-31T10:30:00Z", pr_ready.TRIGGER.upper()),
    ]
    assert pr_ready._latest_request(comments) == "2026-08-31T11:00:00Z"


def test_the_BOTS_own_verdict_is_not_a_request__it_defeated_the_whole_rule() -> None:
    """⛔ Every clean verdict carries a footer documenting how to ask for a round.

    ⚠️ With every author counted, that verdict registered as a request timestamped
    **identically to itself**, could not postdate it, and was ruled superseded --
    so **no pull request could ever be READY again.** Observed live on this
    script's own pull request, round five, at 2026-09-01T01:55:03Z.

    ⭐ Documentation of a trigger is not a trigger, and the author is what
    separates them.
    """
    verdict = {
        "created_at": "2026-09-01T01:55:03Z",
        "user": {"login": "chatgpt-codex-connector[bot]"},
        "body": (
            "Codex Review: Didn't find any major issues. :tada:\n\n"
            "**Reviewed commit:** `569be32888`\n\n"
            "<details> <summary>About Codex in GitHub</summary>\n"
            "Reviews are triggered when you\n- Open a pull request for review\n"
            f'- Mark a draft as ready\n- Comment "{pr_ready.TRIGGER}".\n'
        ),
    }

    assert pr_ready._latest_request([verdict]) == ""
    assert pr_ready._still_current([verdict], pr_ready._latest_request([verdict])) == [verdict]


def test_a_HUMAN_request_still_supersedes_a_bot_verdict_that_precedes_it() -> None:
    """⚠️ The fix must not disarm the rule it repairs."""
    verdict = {
        "created_at": "2026-09-01T01:55:03Z",
        "user": {"login": "chatgpt-codex-connector[bot]"},
        "body": f'Didn\'t find any major issues. Comment "{pr_ready.TRIGGER}".',
    }
    request = {
        "created_at": "2026-09-01T02:10:00Z",
        "user": {"login": "randyjreid"},
        "body": pr_ready.TRIGGER,
    }

    latest = pr_ready._latest_request([verdict, request])

    assert latest == "2026-09-01T02:10:00Z"
    assert pr_ready._still_current([verdict], latest) == []


def test_no_request_at_all_leaves_the_other_evidence_standing() -> None:
    """⭐ The automatic review on open: there is no request to be stale against.

    ⚠️ The second assertion is arithmetic about ``_still_current``, not a mode
    the caller uses. ``_report`` now passes T, which is never empty when it
    compares at all -- it refuses instead. See ``_round_start``.
    """
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
    assert pr_ready._judge(_good(), "a" * 40, "b" * 40) == []


def test_every_field_is_REQUIRED_not_merely_checked() -> None:
    """⛔ An absent field is not a field that is fine.

    ⚠️ GitHub omits what it cannot answer. Comparing a missing value against a
    good one happens to block, but only by luck -- so absence is named instead,
    and a schema change becomes a loud error rather than a quiet verdict.
    """
    for field in pr_ready.METADATA_FIELDS:
        snapshot = _good()
        del snapshot[field]

        reasons = pr_ready._judge(snapshot, "a" * 40, "b" * 40)

        assert len(reasons) == 1, f"{field}: expected one reason, got {reasons}"
        assert field in reasons[0]


def test_BLOCKED_does_not_pass__the_tenth_defect() -> None:
    """⛔ The finding that proved an enumeration cannot stand in for a bound.

    The version this replaces rejected only CONFLICTING and DIRTY, so BLOCKED --
    branch protection awaiting an approval or a required check -- printed READY
    for a pull request GitHub refuses to merge.
    """
    reasons = pr_ready._judge(_good(mergeStateStatus="BLOCKED"), "a" * 40, "b" * 40)

    assert reasons and "BLOCKED" in reasons[0]


def test_only_CLEAN_passes__every_other_merge_state_blocks() -> None:
    """⭐ The allowlist, asserted as one. A list of BAD states cannot be completed."""
    for status in ("BEHIND", "BLOCKED", "DIRTY", "DRAFT", "HAS_HOOKS", "UNKNOWN", "UNSTABLE"):
        assert pr_ready._judge(_good(mergeStateStatus=status), "a" * 40, "b" * 40), status


def test_UNKNOWN_mergeability_blocks_and_says_to_run_again() -> None:
    """⚠️ Not rare -- GitHub computes it asynchronously. It blocks, and it clears."""
    reasons = pr_ready._judge(_good(mergeable="UNKNOWN"), "a" * 40, "b" * 40)

    assert reasons and "run again" in reasons[0]


def test_a_base_that_moved_blocks__the_ninth_defect() -> None:
    """⛔ The live base tip rides in the SAME answer as the one it is compared to.

    ⚠️ mergeStateStatus alone cannot catch this: GitHub reports BEHIND only where
    the repository requires up-to-date branches, and otherwise says CLEAN. #175
    read CLEAN with its base seven commits behind.
    """
    moved = _good(baseRef={"name": "main", "target": {"oid": "c" * 40}})

    reasons = pr_ready._judge(moved, "a" * 40, "b" * 40)

    assert reasons and "base has moved" in reasons[0]


def test_a_head_that_moved_during_the_sweep_blocks() -> None:
    """The evidence gathered earlier is about a commit that is no longer the head."""
    reasons = pr_ready._judge(_good(headRefOid="d" * 40), "a" * 40, "b" * 40)

    assert reasons and "the head moved" in reasons[0]


def test_a_draft_blocks_however_green_everything_else_is() -> None:
    assert pr_ready._judge(_good(isDraft=True), "a" * 40, "b" * 40)


def test_a_closed_pull_request_blocks() -> None:
    assert pr_ready._judge(_good(state="MERGED"), "a" * 40, "b" * 40)


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

    assert pr_ready._judge(eight_rounds_but_otherwise_perfect, "a" * 40, "b" * 40) == []
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


def test_the_base_moving_DURING_the_sweep_blocks() -> None:
    """⛔ The head was compared against its provisional value and the base was not.

    ⚠️ The evidence -- a verdict and a green matrix -- is about code sitting on a
    particular base. Nothing checked the base was still that one when the verdict
    was pronounced, so a base advancing mid-sweep left READY printed over stale
    evidence.
    """
    gathered_against = "b" * 40
    moved_to = "e" * 40
    snapshot = _good(baseRefOid=moved_to, baseRef={"name": "main", "target": {"oid": moved_to}})

    reasons = pr_ready._judge(snapshot, "a" * 40, gathered_against)

    assert any("moved WHILE this sweep ran" in reason for reason in reasons), reasons


def test_the_two_base_questions_are_DIFFERENT_and_both_asked() -> None:
    """⭐ up-to-date, and did-it-move-mid-sweep. One check cannot answer both.

    ⚠️ ``baseRefOid`` is a SNAPSHOT, not the live ref -- measured across five
    merged pull requests, where it read f385d3d / 9c31e67 / 9e14bca / a59df02 /
    a59df02 while the live tip read a3ba58a for every one of them. So comparing
    the two is a real question about staleness; it is simply not the same
    question as whether the base shifted underneath this sweep.
    """
    behind = _good(baseRefOid="f" * 40)
    assert any(
        "since this head was verified" in r for r in pr_ready._judge(behind, "a" * 40, "b" * 40)
    )

    moved = _good(baseRefOid="e" * 40, baseRef={"name": "main", "target": {"oid": "e" * 40}})
    assert any("WHILE this sweep ran" in r for r in pr_ready._judge(moved, "a" * 40, "b" * 40))


def test_a_MISSING_provisional_base_tip_is_refused_not_skipped() -> None:
    """⛔ An unanswerable check is refused. Skipping it is a fail-open.

    ⚠️ The condition was ``if expected_base_tip and ...``, so a provisional
    response with a null ``baseRef.target`` -- a partial answer, or a base ref
    deleted and recreated mid-sweep -- silently disabled the comparison while
    every other field looked fine. **The condition was true for a reason
    unrelated to the property it names.**

    ⭐ ``scripts/hooks/pre-push`` already answers this the right way: it refuses a
    push whose objects it cannot scan rather than assuming them clean.
    """
    reasons = pr_ready._judge(_good(), "a" * 40, "")

    assert reasons and "not captured" in reasons[0]


def test_a_missing_LIVE_base_tip_is_refused_too() -> None:
    """The same rule at the other end -- neither side may be silently absent."""
    unreadable = _good(baseRef={"name": "main", "target": None})

    assert pr_ready._judge(unreadable, "a" * 40, "b" * 40)


def test_a_round_requested_MID_SWEEP_blocks() -> None:
    """⛔ The twelfth defect one level up: the rule applied to a stale snapshot.

    The latest request is read while gathering; the verdict is pronounced several
    calls later. A request landing in that gap was invisible, so the earlier clean
    comment stayed accepted and READY printed while a new round was starting.
    """
    reason = pr_ready._request_arrived_mid_sweep("2026-09-01T01:20:41Z", "2026-09-01T01:34:49Z")

    assert "requested while this sweep ran" in reason


def test_an_unchanged_request_does_not_block() -> None:
    assert pr_ready._request_arrived_mid_sweep("2026-09-01T01:20:41Z", "2026-09-01T01:20:41Z") == ""


def test_no_request_at_either_end_does_not_block() -> None:
    """⭐ The automatic review on open, never re-triggered."""
    assert pr_ready._request_arrived_mid_sweep("", "") == ""


def test_a_FIRST_request_arriving_mid_sweep_blocks_too() -> None:
    """⚠️ From none to one is the same event, and an early-return on empty would
    have missed exactly the case where a round starts during the sweep.
    """
    assert pr_ready._request_arrived_mid_sweep("", "2026-09-01T01:34:49Z")


# ------------------------------- two reads of the same thing, merged by rule


def test_a_ROUND_START_INSTANT_seen_in_either_read_still_counts() -> None:
    """⛔ T never goes backwards. A mark-ready that vanishes from the final read
    would drop T to the open time and make a stale reaction look fresh.
    """
    assert pr_ready._both_timelines([MARKED_READY], []) == [MARKED_READY]
    assert pr_ready._both_timelines([], [MARKED_READY]) == [MARKED_READY]
    assert pr_ready._both_timelines([MARKED_READY], [MARKED_READY]) == [MARKED_READY]
    assert pr_ready._both_timelines([], []) == []


def test_an_UNREADABLE_timeline_in_EITHER_read_is_unreadable() -> None:
    """⛔ ``None`` propagates. Half an answer about when the round began is not
    an answer, and the readable half cannot show the other half held nothing.
    """
    assert pr_ready._both_timelines(None, []) is None
    assert pr_ready._both_timelines([], None) is None
    assert pr_ready._both_timelines(None, None) is None


def test_T_is_EMPTY_rather_than_early_when_it_cannot_be_computed() -> None:
    """⛔ ``""`` is a refusal, and callers may never compare against it: it sorts
    before every timestamp, so every artifact ever published would postdate it.
    """
    assert pr_ready._round_start(OPENED, "", []) == OPENED
    assert pr_ready._round_start(OPENED, REQUESTED, [MARKED_READY]) == REQUESTED
    assert pr_ready._round_start("", "", []) == ""
    assert pr_ready._round_start(OPENED, "", None) == ""


# ------------------------------------------- T, when the current round began

# ⛔ Every value here is INVENTED. No SHA is completed from a real one, no
# timestamp is copied from a real pull request.
OPENED = "2026-04-02T09:00:00Z"
MARKED_READY = "2026-04-02T10:30:00Z"
REQUESTED = "2026-04-02T11:00:00Z"


def test_T_is_the_LATEST_of_the_three_instants_that_start_a_round() -> None:
    """⛔ Three, not two. The bot documents three triggers and only one is a comment."""
    assert pr_ready._round_began(OPENED, "", []) == OPENED
    assert pr_ready._round_began(OPENED, REQUESTED, []) == REQUESTED
    assert pr_ready._round_began(OPENED, "", [MARKED_READY]) == MARKED_READY
    assert pr_ready._round_began(OPENED, REQUESTED, [MARKED_READY]) == REQUESTED
    assert pr_ready._round_began(OPENED, "", [OPENED, MARKED_READY]) == MARKED_READY


def test_T_never_falls_back_to_the_EMPTY_trigger() -> None:
    """⚠️ ``""`` is what ``_latest_request`` returns when no round was ever asked
    for, and it sorts before every timestamp. If it could win, every reaction
    ever left would postdate T -- absence of evidence becoming permission.
    """
    assert pr_ready._round_began(OPENED, "", []) == OPENED


def test_the_ready_for_review_events_are_read_from_the_metadata() -> None:
    """⭐ #183's trigger: marking a draft ready starts a round and leaves no comment."""
    meta = {"timelineItems": {"nodes": [{"createdAt": MARKED_READY}]}}

    assert pr_ready._ready_for_review(meta) == [MARKED_READY]


def test_a_pull_request_that_was_never_a_draft_has_NO_ready_events() -> None:
    """⚠️ Empty is a real answer here and must not be confused with unreadable."""
    assert pr_ready._ready_for_review({"timelineItems": {"nodes": []}}) == []


def test_an_UNREADABLE_ready_for_review_timeline_is_not_an_empty_one() -> None:
    """⛔ ``None`` rather than ``[]``, and the difference is the whole fail-closed rule.

    ⚠️ An absent key, a node that is not an object, a node with no ``createdAt``:
    each would silently contribute nothing to T, leaving T too EARLY and a stale
    reaction looking fresh. This project's recorded defect class is an empty read
    presented as an absence.
    """
    assert pr_ready._ready_for_review({}) is None
    assert pr_ready._ready_for_review({"timelineItems": None}) is None
    assert pr_ready._ready_for_review({"timelineItems": {}}) is None
    assert pr_ready._ready_for_review({"timelineItems": {"nodes": [{}]}}) is None
    assert pr_ready._ready_for_review({"timelineItems": {"nodes": ["not an object"]}}) is None


# ------------------------------- the WHOLE sweep, with every ``gh`` call faked
#
# ⛔ **Every value below is INVENTED.** No SHA is a real one extended, no
# timestamp is copied from a real pull request, and no Gramps datum appears.
#
# ⭐ The pure functions above bind the judgement. **This binds the WIRING**, and
# the wiring is where five of this round's six findings actually lived: the right
# rule fed the wrong argument. A named input that only ever reaches a helper
# directly cannot show that.

# ⚠️ ``HEAD_SHA`` and ``EARLIER`` were ``THUMB_HEAD`` and ``ARRIVED`` while a
# bare 👍 could grant and an activity row recorded a head ARRIVING on a branch.
# Both readings are gone with #233's granting path, and a constant named for a
# rule this file now exists to deny is a trap for the next reader. The rename
# changes no assertion.
HEAD_SHA = "e" * 40
OTHER_HEAD = "f" * 40
EARLIER = "2026-04-02T08:59:58Z"
THUMBED = "2026-04-02T09:06:00Z"
LATER = "2026-04-02T09:30:00Z"

BASE_TIP = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
CLEAN_AT = "2026-04-02T09:07:00Z"
CLEAN_BODY = f"Codex Review: Didn't find any major issues. **Reviewed commit:** `{HEAD_SHA[:10]}`"


def _bot_comment(when: str, body: str) -> dict[str, object]:
    return {"created_at": when, "body": body, "user": {"login": "chatgpt-codex-connector[bot]"}}


def _bot_thumb(when: str) -> dict[str, object]:
    """A +1 on the pull request BODY, as the reactions endpoint renders one."""
    return {"content": "+1", "created_at": when, "user": {"login": "chatgpt-codex-connector"}}


def _meta(**overrides: object) -> dict[str, object]:
    """One metadata answer GitHub would call mergeable, before any override."""
    snapshot: dict[str, object] = {
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": HEAD_SHA,
        "baseRefOid": BASE_TIP,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "createdAt": OPENED,
        "baseRef": {"name": "main", "target": {"oid": BASE_TIP}},
        "timelineItems": {"nodes": []},
    }
    snapshot.update(overrides)
    return snapshot


PULL = 900


def _sweep(patch: pytest.MonkeyPatch, **overrides: object) -> bool:
    """Run ``_report`` end to end against canned answers. ⛔ No network, no ``gh``.

    ⚠️ Each endpoint the sweep reads TWICE has a ``final_`` twin. ``None`` there
    means *the second read agrees with the first*, which is the ordinary case;
    a test that is about a reread says what the second read returned.

    ⛔ **Only ``meta`` and ``conversation`` are read twice now.** The reviews,
    inline and reactions endpoints lost their second read with #233's granting
    path, and the branch-activity read went with it -- ``activity?ref=`` is not
    stubbed here because ``_report`` no longer asks for it, so a reintroduction
    raises *the sweep made a gh call nothing stubs* rather than passing quietly.
    """
    facts: dict[str, object] = {
        "meta": _meta(),
        "final_meta": None,
        "commit_date": EARLIER,
        "reviews": [],
        "inline": [],
        "conversation": [],
        "final_conversation": None,
        "reactions": [],
        "threads": [],
        "checks": [{"name": "invented-check", "state": "SUCCESS", "bucket": "pass"}],
    }
    facts.update(overrides)
    seen: dict[str, int] = {}

    def read(key: str) -> object:
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 1:
            return facts[key]
        later = facts.get(f"final_{key}")
        return facts[key] if later is None else later

    def fake_gh(*arguments: str) -> str:
        joined = " ".join(arguments)
        if "reviewThreads" in joined:
            threads = {"pageInfo": {"hasNextPage": False}, "nodes": facts["threads"]}
            return json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": threads}}}})
        if "pullRequest" in joined:
            return json.dumps({"data": {"repository": {"pullRequest": read("meta")}}})
        if "/commits/" in joined:
            return json.dumps({"commit": {"committer": {"date": facts["commit_date"]}}})
        if f"pulls/{PULL}/reviews" in joined:
            return json.dumps(read("reviews"))
        if f"pulls/{PULL}/comments" in joined:
            return json.dumps(read("inline"))
        if f"issues/{PULL}/comments" in joined:
            return json.dumps(read("conversation"))
        if f"issues/{PULL}/reactions" in joined:
            return json.dumps(read("reactions"))
        if arguments[:2] == ("pr", "checks"):
            return json.dumps(facts["checks"])
        raise AssertionError(f"the sweep made a gh call nothing stubs: {joined}")

    patch.setattr(pr_ready, "_gh", fake_gh)
    verdict = pr_ready._report(PULL)
    assert isinstance(verdict, bool)
    return verdict


def test_the_harness_itself_reports_READY_on_a_clean_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ **The known positive.** A NOT-READY from an uncalibrated instrument is
    not evidence: every test below asserts a refusal, and without this one they
    would all pass against a harness that refuses for a reason nobody intended.
    """
    assert _sweep(monkeypatch, conversation=[_bot_comment(CLEAN_AT, CLEAN_BODY)]) is True


def test_a_ready_event_that_DISAPPEARS_from_the_final_read_still_moves_T(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ T never goes backwards between two reads of the same timeline.

    ⚠️ Named input: a pull request opened at 09:00, the bot's clean comment
    naming this head at 09:07, the provisional metadata seeing a ready-for-review
    event at 10:30, and the final timeline returning ``[]``. Only the final read
    fed T, so T fell back to the open time, the 09:07 comment postdated it, and
    READY printed for the round before the one the mark-ready started.

    ⛔ **RE-FIXTURED, and the reason is that the old fixture would have passed
    for the wrong reason.** It drove its refusal through a bare 👍 with an empty
    conversation. With #233's granting path deleted that sweep has no clean
    signal at all, so it returns False whatever T does -- green, and testing
    nothing. The pair below is what makes the mark-ready the cause: the two
    sweeps differ only in that event.
    """
    clean = _bot_comment(CLEAN_AT, CLEAN_BODY)
    marked_ready = {"nodes": [{"createdAt": MARKED_READY}]}

    assert (
        _sweep(
            monkeypatch,
            conversation=[clean],
            meta=_meta(timelineItems=marked_ready),
            final_meta=_meta(timelineItems={"nodes": []}),
        )
        is False
    )
    assert _sweep(monkeypatch, conversation=[clean]) is True


def test_a_TRIGGER_that_disappears_from_the_final_read_still_moves_T(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠️ The same regression through the other term, and
    ``_request_arrived_mid_sweep`` does not catch it: that rule fires when the
    request moves FORWARD, and a request going from one to none leaves ``after``
    empty, so it says nothing at all.

    ⛔ **RE-FIXTURED for the reason above.** Its old shape refused through a bare
    👍 that can no longer grant, so it would have gone green without exercising T.
    Here the request at 10:30 supersedes the 09:07 clean comment; drop the request
    from BOTH reads and the same sweep is READY.
    """
    clean = _bot_comment(CLEAN_AT, CLEAN_BODY)
    asked = {
        "created_at": "2026-04-02T10:30:00Z",
        "body": pr_ready.TRIGGER,
        "user": {"login": "randyjreid"},
    }

    assert _sweep(monkeypatch, conversation=[clean, asked], final_conversation=[clean]) is False
    assert _sweep(monkeypatch, conversation=[clean], final_conversation=[clean]) is True


# ------------------------------------------------- #183, closed by measurement


def test_183s_own_named_input_is_NOT_READY(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ **#183, demonstrated rather than asserted.** Its own named input, run.

    A clean comment naming head ``H``, a conversion back to draft, a mark-ready
    on the same head, and no push. Marking a draft ready is one of the three
    things that starts a bot round -- the bot says so in the footer of every
    verdict it publishes -- and it moves neither the open time nor the latest
    request. The clean-comment path compared its comment against the trigger
    alone, so the PREVIOUS round's verdict was still accepted and READY printed
    while the new round had published nothing.

    ⭐ The pair below is the whole proof. The only difference between the two
    sweeps is the mark-ready event; everything else -- head, comment, branch,
    checks, threads, base -- is identical. So the refusal is that event's doing
    and not some unrelated gate's, which a single negative could never show.
    """
    clean = _bot_comment(CLEAN_AT, CLEAN_BODY)
    marked_ready_after_the_clean_comment = {"nodes": [{"createdAt": MARKED_READY}]}

    assert _sweep(monkeypatch, conversation=[clean]) is True
    assert (
        _sweep(
            monkeypatch,
            conversation=[clean],
            meta=_meta(timelineItems=marked_ready_after_the_clean_comment),
        )
        is False
    )


def test_a_clean_comment_still_stands_when_the_mark_ready_PRECEDES_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⭐ Both directions, because a rule that only ever refuses is not a rule.

    The mark-ready starts the round; a clean comment published after it is that
    round's verdict and still accepts.
    """
    earlier = {"nodes": [{"createdAt": "2026-04-02T09:01:00Z"}]}

    verdict = _sweep(
        monkeypatch,
        conversation=[_bot_comment(CLEAN_AT, CLEAN_BODY)],
        meta=_meta(timelineItems=earlier),
    )

    assert verdict is True


def test_an_unreadable_timeline_REFUSES_shape_A_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ **No fallback.** Restoring the old comparison when the timeline cannot
    be read would be this defect returning under a different name: the input
    that produces it is exactly an unreadable timeline.

    ⚠️ The owner ruled the trade explicitly. Coupling the clean comment to T
    makes it depend on a read it did not need before, so an unreadable timeline
    stalls a pull request the comment path could have passed. **That is an
    availability cost, not a correctness one, and it fails toward NOT READY.**
    """
    verdict = _sweep(
        monkeypatch,
        conversation=[_bot_comment(CLEAN_AT, CLEAN_BODY)],
        meta=_meta(timelineItems=None),
    )

    assert verdict is False


# -------------------- the clean comment, confirmed against the FINAL read


def test_confirmation_is_by_ID_where_the_rows_carry_one() -> None:
    """⭐ One identity rule, and the only granting evidence left uses it.

    ⚠️ Whole-row equality alone would be defeated by any field the two reads
    render differently; an ``id`` comparison alone would be defeated by a
    fixture that has none. So it is ``id`` when either row carries one, and
    equality otherwise.

    ⛔ **Identity PAIRS the rows; it does not judge them.** ``_still_granted``
    sees only what its caller passes, and identity survives an edit that
    destroys content -- so both of its arguments are filtered for the clean
    verdict first. That is asserted by
    ``test_a_clean_comment_EDITED_into_a_findings_report_stops_granting``.
    """
    first = [{"id": 4815162342, "created_at": CLEAN_AT, "body": CLEAN_BODY}]
    rendered_differently = [
        {"id": 4815162342, "created_at": CLEAN_AT, "body": CLEAN_BODY, "extra": "field"}
    ]
    a_different_comment = [{"id": 4815162343, "created_at": CLEAN_AT, "body": CLEAN_BODY}]

    assert pr_ready._still_granted(first, rendered_differently) == first
    assert pr_ready._still_granted(first, a_different_comment) == []
    assert pr_ready._still_granted([_comment(CLEAN_AT)], [_comment(CLEAN_AT)]) == [
        _comment(CLEAN_AT)
    ]
    assert pr_ready._still_granted([_comment(CLEAN_AT)], [_comment(LATER)]) == []


def test_a_clean_comment_DELETED_before_the_verdict_stops_granting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ **The clean comment granted on evidence it never re-confirmed.**

    ⚠️ Named input: the bot posts a clean comment naming head ``H`` at 09:07, the
    sweep reads it, the comment is deleted before the verdict is pronounced, the
    final conversation read lacks it, and every other gate is clean. The comment
    was built from the FIRST read alone and reached the verdict through
    ``_still_current`` only, so READY printed over a body that no longer carries
    a clean signal.

    ⭐ The pair is the proof, exactly as ``test_183s_own_named_input_is_NOT_READY``
    pairs. The two sweeps are byte-identical apart from the second read: with the
    comment surviving it is still READY, so the refusal is the deletion's doing
    and not some unrelated gate's.
    """
    clean = _bot_comment(CLEAN_AT, CLEAN_BODY)

    assert _sweep(monkeypatch, conversation=[clean]) is True
    assert _sweep(monkeypatch, conversation=[clean], final_conversation=[]) is False


def test_a_clean_comment_that_ARRIVED_mid_sweep_does_not_grant_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ **Confirmation may not become admission.**

    ⚠️ Taking the final read alone would let a clean comment published mid-sweep
    grant a verdict on evidence gathered before it -- the checks, the threads and
    the head were all read before that comment existed. Intersection, not
    replacement: only what BOTH reads show.
    """
    clean = _bot_comment(CLEAN_AT, CLEAN_BODY)

    verdict = _sweep(monkeypatch, conversation=[], final_conversation=[clean])

    assert verdict is False


# --------------------------------------------- #219: printing its own verdict


def test_the_verdict_prints_on_a_console_that_cannot_ENCODE_it() -> None:
    """⛔ #219: the tool died rendering the answer it had already computed.

    ⚠️ The failure was indistinguishable at a glance from a real NOT-READY --
    ``the check could not complete``, exit non-zero -- while the finding that
    mattered sat in the part that never printed.

    ⭐ **The parent is pinned to cp1252 so inheritance cannot supply the answer**,
    exactly as ``test_gate_child_encoding`` does: under a UTF-8 parent this test
    would pass with the fix deleted. The no-argument path makes no API call, and
    the cp1252 codec exists on every platform, so this binds on CI's Linux
    runners too.
    """
    hostile = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    hostile.pop("PYTHONUTF8", None)

    finished = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pr_ready.py")],
        capture_output=True,
        env=hostile,
        check=False,
    )

    # ⛔ 2 is the usage exit. Without the fix this is 1, from an unhandled
    # UnicodeEncodeError -- which is why the code is asserted and not just the text.
    assert finished.returncode == 2, finished.stderr.decode("utf-8", "replace")
    printed = finished.stdout.decode("utf-8")
    assert "⛔" in printed
    assert "⭐" in printed
