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


def test_DENYING_evidence_takes_the_UNION_of_both_reads() -> None:
    """⛔ A reread may not forget. Anything either read saw still governs."""
    first = [{"id": 1, "submitted_at": "2026-04-02T09:10:00Z"}]
    second = [{"id": 2, "submitted_at": "2026-04-02T09:20:00Z"}]

    assert pr_ready._both_reads(first, []) == first
    assert pr_ready._both_reads([], second) == second
    assert pr_ready._both_reads(first, first) == first
    assert pr_ready._both_reads(first, second) == first + second


def test_the_two_directions_are_OPPOSITE_rules_over_the_same_identity() -> None:
    """⭐ Not one merge helper: a union for what denies, an intersection for what
    grants. A single helper would need a mode flag, which is two rules in one
    place rather than one rule in one place.
    """
    kept = [{"id": 7}]
    lost: list[dict[str, object]] = []

    assert pr_ready._both_reads(kept, lost) == kept
    assert pr_ready._still_granted(kept, lost) == []


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


def test_the_FINAL_read_names_the_branch_whose_history_may_be_read() -> None:
    """⛔ The provisional name is provisional, exactly like the head and the base."""
    assert pr_ready._settled_branch(BRANCH, BRANCH) == (BRANCH, "")
    assert pr_ready._settled_branch("", BRANCH) == (BRANCH, "")

    name, reason = pr_ready._settled_branch(BRANCH, "")
    assert name == ""
    assert "final metadata read" in reason

    name, reason = pr_ready._settled_branch(BRANCH, "renamed-branch")
    assert name == ""
    assert "renamed" in reason


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


# ------------------------------------------------- shape B: a bare bot thumb

# ⛔ Invented, all of them. No SHA here is a real one extended, and no timestamp
# is copied from a real pull request.
THUMB_HEAD = "e" * 40
OTHER_HEAD = "f" * 40
BRANCH = "invented-branch"
REF = f"refs/heads/{BRANCH}"
ARRIVED = "2026-04-02T08:59:58Z"
THUMBED = "2026-04-02T09:06:00Z"
LATER = "2026-04-02T09:30:00Z"


def _reaction(when: str, content: str = "+1") -> dict[str, object]:
    """⛔ Already bot-filtered by the caller, exactly as the reviews are."""
    return {"content": content, "created_at": when}


def _activity_row(
    when: str, after: str = OTHER_HEAD, kind: str = "push", ref: str = REF
) -> dict[str, object]:
    return {"timestamp": when, "after": after, "activity_type": kind, "ref": ref}


def _arrival() -> dict[str, object]:
    """The row that shows this head reaching the branch, before the round began."""
    return _activity_row(ARRIVED, after=THUMB_HEAD, kind="branch_creation")


def _shape_b(**overrides: object) -> object:
    """The #232 shape before any override: a bare +1 on a head that never moved."""
    call: dict[str, object] = {
        "bot_reactions": [_reaction(THUMBED)],
        "bot_reviews": [],
        "bot_inline": [],
        "bot_conversation": [],
        "unsigned": [],
        "activity": [_arrival()],
        "head": THUMB_HEAD,
        "head_ref": BRANCH,
        "created_at": OPENED,
        "latest_trigger": "",
        "ready_events": [],
    }
    call.update(overrides)
    # ⛔ The second reactions read MIRRORS the first unless a test says otherwise,
    # which is exactly the pre-existing meaning of every fixture above: the +1 is
    # still there when the verdict is pronounced. A test that cares says so.
    call.setdefault("bot_reactions_now", call["bot_reactions"])
    return pr_ready._bare_thumb_clean(**call)


def test_the_bare_THUMB_that_232_reported_NOT_READY_is_accepted() -> None:
    """⛔ #233's named input, as a fixture. The bot's whole output was one 👍.

    The script counted that reaction, printed it, and then required a clean
    comment naming the commit -- a signal the bot does not always write. §5 of
    the gate definition makes the comment sufficient, never necessary.
    """
    verdict = _shape_b()

    assert verdict.reason == ""
    assert verdict.accepted == _reaction(THUMBED)


def test_a_PUSH_after_the_round_began_refuses() -> None:
    """⛔ A reaction carries no commit id, so it can only ever be read against a
    branch that has not moved. Any ref event after T ends that.
    """
    verdict = _shape_b(activity=[_arrival(), _activity_row(LATER)])

    assert verdict.accepted is None
    assert "moved" in verdict.reason


def test_a_FORCE_PUSH_back_onto_the_same_head_refuses_too() -> None:
    """⚠️ The arrival row still exists and the head is still the head -- so the
    arrival test alone passes. It is the SECOND half of condition 2, no row of
    any kind after T, that catches this.
    """
    verdict = _shape_b(activity=[_arrival(), _activity_row(LATER, after=THUMB_HEAD)])

    assert verdict.accepted is None
    assert "moved" in verdict.reason


def test_a_bot_CONVERSATION_comment_after_the_round_began_refuses() -> None:
    """⛔ If the bot spoke, its artifact governs, not a reaction beside it."""
    verdict = _shape_b(bot_conversation=[_comment(LATER, "some finding")])

    assert verdict.accepted is None
    assert "conversation comment" in verdict.reason


def test_a_bot_REVIEW_after_the_round_began_refuses() -> None:
    """⛔ The window this closes spans most of the sweep, not the final call: the
    bot can submit a review carrying a finding at any point after the first
    reads, with the head, the checks and the conversation all unchanged.
    """
    verdict = _shape_b(bot_reviews=[{"submitted_at": LATER}])

    assert verdict.accepted is None
    assert "review" in verdict.reason


def test_a_bot_INLINE_comment_after_the_round_began_refuses() -> None:
    """⛔ All three endpoints, because outstanding findings live in all three."""
    verdict = _shape_b(bot_inline=[_comment(LATER, "a finding on a line")])

    assert verdict.accepted is None
    assert "inline comment" in verdict.reason


def test_a_bot_artifact_with_NO_timestamp_refuses_rather_than_reading_as_old() -> None:
    """⛔ ``"" > T`` is false, so an unstamped artifact would silently read as
    belonging to an earlier round -- absence of evidence becoming permission,
    on the exact endpoint whose job is to deny.
    """
    for override in (
        {"bot_reviews": [{"body": "no submitted_at at all"}]},
        {"bot_inline": [{"body": "no created_at at all"}]},
        {"bot_conversation": [{"body": "no created_at at all"}]},
    ):
        verdict = _shape_b(**override)

        assert verdict.accepted is None, override
        assert "no timestamp" in verdict.reason, override


def test_a_thumb_PREDATING_the_round_start_refuses() -> None:
    """⛔ A reaction from the round before. #233 says so itself: the 👍 can be
    trusted only while the head has not changed since the round began.
    """
    verdict = _shape_b(bot_reactions=[_reaction(ARRIVED)])

    assert verdict.accepted is None
    assert "predates" in verdict.reason


def test_a_thumb_exactly_AT_the_round_start_refuses() -> None:
    """⚠️ Strictly after, never at. The reaction has to be a response to the round."""
    verdict = _shape_b(bot_reactions=[_reaction(OPENED)])

    assert verdict.accepted is None
    assert "predates" in verdict.reason


def test_no_thumb_at_all_refuses() -> None:
    verdict = _shape_b(bot_reactions=[])

    assert verdict.accepted is None
    assert "no bot +1" in verdict.reason


def test_a_reaction_that_is_not_a_PLUS_ONE_is_meaningless() -> None:
    """⛔ No widening. 👀 is liveness, and every other reaction says nothing."""
    verdict = _shape_b(bot_reactions=[_reaction(THUMBED, content="eyes")])

    assert verdict.accepted is None
    assert "no bot +1" in verdict.reason


def test_an_EMPTY_activity_log_refuses__an_empty_read_is_not_an_absence() -> None:
    """⛔ The fork case (#235) arrives here: the branch lives in the fork, this
    read finds nothing, and nothing is not proof the head has not moved.
    """
    verdict = _shape_b(activity=[])

    assert verdict.accepted is None
    assert "no activity" in verdict.reason


def test_activity_for_ANOTHER_ref_is_not_this_branchs_history() -> None:
    """⚠️ Rows are filtered here as well as in the query, so a server that
    ignored the ref parameter could not make another branch's quiet stand in
    for this one's.
    """
    verdict = _shape_b(activity=[_activity_row(ARRIVED, after=THUMB_HEAD, ref="refs/heads/other")])

    assert verdict.accepted is None
    assert "no activity" in verdict.reason


def test_no_row_showing_the_head_ARRIVING_refuses() -> None:
    """⛔ The log has to show this head reaching this branch. Without that row,
    nothing in the read is about the commit the verdict is supposed to be about.
    """
    verdict = _shape_b(activity=[_activity_row(ARRIVED, after=OTHER_HEAD)])

    assert verdict.accepted is None
    assert "arriving" in verdict.reason


def test_an_activity_row_with_NO_timestamp_refuses() -> None:
    """⚠️ The same fail-closed rule as the bot artifacts: a row that cannot be
    ordered cannot be shown to predate T.
    """
    verdict = _shape_b(activity=[_arrival(), _activity_row("", after=OTHER_HEAD)])

    assert verdict.accepted is None
    assert "no timestamp" in verdict.reason


def test_a_thumb_REMOVED_before_the_verdict_stops_granting() -> None:
    """⛔ **A reaction can be DELETED, so a stale read does not only ever lose one.**

    ⚠️ Named input: the first reactions read carries a fresh bot +1 which the bot
    removes before the verdict is pronounced. With activity quiet and no bot
    artifacts, the stale read still produced READY although the body no longer
    carries a clean signal.

    ⭐ The remedy is CONFIRMATION, not replacement: a +1 counts only if BOTH
    reads show it. Using the second read alone would widen what is accepted --
    a +1 arriving mid-sweep would grant -- which is the direction the file's own
    comment was right to refuse.
    """
    verdict = _shape_b(bot_reactions=[_reaction(THUMBED)], bot_reactions_now=[])

    assert verdict.accepted is None
    assert "no longer" in verdict.reason


def test_a_thumb_that_ARRIVED_mid_sweep_does_not_grant_either() -> None:
    """⛔ The confirmation may not become a widening. Only what BOTH reads show."""
    verdict = _shape_b(bot_reactions=[], bot_reactions_now=[_reaction(THUMBED)])

    assert verdict.accepted is None
    assert "no bot +1" in verdict.reason


def test_confirmation_is_by_ID_where_the_rows_carry_one() -> None:
    """⭐ One identity rule, shared by the merging helper and the confirming one.

    ⚠️ Whole-row equality alone would be defeated by any field the two reads
    render differently; an ``id`` comparison alone would be defeated by a
    fixture that has none. So it is ``id`` when either row carries one, and
    equality otherwise.
    """
    first = [{"id": 11, "content": "+1", "created_at": THUMBED}]
    renamed = [{"id": 11, "content": "+1", "created_at": THUMBED, "extra": "field"}]
    other = [{"id": 12, "content": "+1", "created_at": THUMBED}]

    assert pr_ready._still_granted(first, renamed) == first
    assert pr_ready._still_granted(first, other) == []
    assert pr_ready._still_granted([_reaction(THUMBED)], [_reaction(THUMBED)]) == [
        _reaction(THUMBED)
    ]
    assert pr_ready._still_granted([_reaction(THUMBED)], [_reaction(LATER)]) == []


def test_an_activity_row_with_NO_REF_refuses_rather_than_being_dropped() -> None:
    """⛔ The ref filter DROPS what it cannot match, and a dropped row read as quiet.

    ⚠️ Named input: a valid pre-T arrival row, plus a post-T row carrying a
    timestamp and a SHA but no ``ref``. It is excluded from ``mine``, so no
    post-T movement is seen and the reaction is accepted. **The queried log
    cannot prove where an unlabelled row belongs**, and this file already
    defends against a server that ignores the ``ref`` parameter -- a row with no
    ref at all is the same hazard with the label missing instead of wrong.
    """
    unplaceable = {"timestamp": LATER, "after": OTHER_HEAD, "activity_type": "push"}

    verdict = _shape_b(activity=[_arrival(), unplaceable])

    assert verdict.accepted is None
    assert "no ref" in verdict.reason


def test_an_activity_row_with_a_NULL_ref_refuses_too() -> None:
    """⚠️ Absent and null are the same unanswered question."""
    verdict = _shape_b(activity=[_arrival(), _activity_row(LATER, ref="")])

    assert verdict.accepted is None
    assert "no ref" in verdict.reason


def test_an_artifact_whose_AUTHOR_is_unreadable_refuses() -> None:
    """⛔ ``by_bot`` drops a row it cannot classify, and a dropped row is silence.

    ⚠️ Named input: a post-T review carrying a finding and a timestamp whose
    ``user`` is absent or null. Shape B then sees a quiet bot and can print
    READY. **Absence of an author cannot prove the artifact was not the bot's**,
    so on these denying endpoints an unclassifiable row refuses.
    """
    verdict = _shape_b(unsigned=[LATER])

    assert verdict.accepted is None
    assert "author" in verdict.reason


def test_an_unsigned_artifact_with_NO_TIMESTAMP_refuses() -> None:
    """⚠️ Neither question answered: it can be placed in no round at all."""
    verdict = _shape_b(unsigned=[""])

    assert verdict.accepted is None
    assert "author" in verdict.reason


def test_an_unsigned_artifact_from_BEFORE_the_round_does_not_refuse() -> None:
    """⭐ No widening. A row from an earlier round is a row from an earlier round,
    whoever wrote it -- refusing on those would refuse every pull request that
    ever had a comment from a deleted account.
    """
    verdict = _shape_b(unsigned=[ARRIVED])

    assert verdict.reason == ""
    assert verdict.accepted == _reaction(THUMBED)


def test_a_NULL_user_is_UNSIGNED_rather_than_somebody_elses() -> None:
    """⛔ Three answers, not two: the bot, somebody else, and *the read did not say*."""
    assert pr_ready._author({"user": {"login": "randyjreid"}}) == "randyjreid"
    assert pr_ready._author({"user": None}) is None
    assert pr_ready._author({}) is None
    assert pr_ready._author({"user": {"login": None}}) is None
    assert pr_ready._author({"user": "chatgpt-codex-connector[bot]"}) is None

    rows = [
        {"submitted_at": LATER, "user": None},
        {"submitted_at": LATER, "user": {"login": "chatgpt-codex-connector[bot]"}},
        {"submitted_at": LATER, "user": {"login": "randyjreid"}},
        {"body": "no author and no timestamp either"},
    ]

    assert pr_ready._unsigned_stamps((rows, "submitted_at")) == [LATER, ""]


def test_a_TRIGGER_after_the_open_moves_T() -> None:
    """⭐ Both directions, because a rule that only ever refuses is not a rule."""
    between = _shape_b(bot_reactions=[_reaction(THUMBED)], latest_trigger=REQUESTED)
    assert between.accepted is None
    assert "predates" in between.reason

    after = _shape_b(bot_reactions=[_reaction(LATER)], latest_trigger="2026-04-02T09:20:00Z")
    assert after.reason == ""
    assert after.accepted == _reaction(LATER)


def test_a_READY_FOR_REVIEW_event_moves_T__the_183_input() -> None:
    """⛔ #183's named input, promoted from a stale reading into a false pass.

    A pull request receives a bare clean 👍, is converted back to draft, and is
    marked ready again on the same head. That starts a round and leaves no
    comment, so neither the open time nor the latest request moves -- and
    without the third term the OLD reaction reports READY for the previous round.
    """
    verdict = _shape_b(ready_events=[MARKED_READY])

    assert verdict.accepted is None
    assert "predates" in verdict.reason


def test_an_UNREADABLE_ready_timeline_refuses_the_whole_shape() -> None:
    """⛔ ``None`` is not ``[]``. T computed without a term it should have had is
    too early, and too early is the permissive direction.
    """
    verdict = _shape_b(ready_events=None)

    assert verdict.accepted is None
    assert "ready-for-review" in verdict.reason


def test_an_unread_HEAD_or_OPEN_TIME_or_BRANCH_refuses() -> None:
    """⛔ ``createdAt`` is T's floor. With it empty, T is ``""`` and EVERY
    reaction ever left postdates it -- a missing field turning into permission,
    which is the one direction this instrument may never fail in.
    """
    for override in ({"head": ""}, {"created_at": ""}, {"head_ref": ""}):
        verdict = _shape_b(**override)

        assert verdict.accepted is None, override
        assert verdict.reason, override


def test_EVERY_refusal_says_no_twice__no_reason_can_mean_accepted() -> None:
    """⛔ The two signals are independent on purpose.

    ⚠️ A refusal that returned only an empty reason, or only a null reaction,
    would let one slipped branch become permission. The caller requires both,
    and this asserts every refusal path supplies both.
    """
    refusals = (
        _shape_b(bot_reactions=[]),
        _shape_b(bot_reactions=[_reaction(ARRIVED)]),
        _shape_b(activity=[]),
        _shape_b(activity=[_activity_row(ARRIVED, after=OTHER_HEAD)]),
        _shape_b(activity=[_arrival(), _activity_row(LATER)]),
        _shape_b(bot_reviews=[{"submitted_at": LATER}]),
        _shape_b(bot_inline=[_comment(LATER)]),
        _shape_b(bot_conversation=[_comment(LATER)]),
        _shape_b(ready_events=None),
        _shape_b(created_at=""),
        _shape_b(head=""),
        _shape_b(head_ref=""),
    )

    for verdict in refusals:
        assert verdict.accepted is None, verdict
        assert verdict.reason, verdict


# ------------------------------------------------ which shape the verdict has


def test_the_two_clean_shapes_are_NAMED_in_the_verdict() -> None:
    """⭐ #233 asks for this by name: print which of the two shapes it found."""
    accepted_comment = [_comment("2026-04-02T09:07:00Z")]

    assert pr_ready._clean_shape(accepted_comment, _shape_b()) == pr_ready.SHAPE_COMMENT
    assert pr_ready._clean_shape([], _shape_b()) == pr_ready.SHAPE_THUMB


def test_the_clean_COMMENT_path_still_accepts_when_shape_B_refuses() -> None:
    """⛔ Shape A is unchanged by this work, and this is what asserts it.

    A pull request whose bot wrote a clean comment naming the head has a
    verdict, whatever the reactions do -- here the branch moved after T, so
    shape B refuses, and the comment stands alone.
    """
    moved = _shape_b(activity=[_arrival(), _activity_row(LATER)])
    assert moved.accepted is None

    assert pr_ready._clean_shape([_comment(LATER)], moved) == pr_ready.SHAPE_COMMENT


def test_NEITHER_shape_is_the_empty_label_and_that_is_what_blocks() -> None:
    assert pr_ready._clean_shape([], _shape_b(bot_reactions=[])) == ""


# ------------------------------- the WHOLE sweep, with every ``gh`` call faked
#
# ⛔ **Every value below is INVENTED.** No SHA is a real one extended, no
# timestamp is copied from a real pull request, and no Gramps datum appears.
#
# ⭐ The pure functions above bind the judgement. **This binds the WIRING**, and
# the wiring is where five of this round's six findings actually lived: the right
# rule fed the wrong argument. A named input that only ever reaches a helper
# directly cannot show that.

BASE_TIP = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
CLEAN_AT = "2026-04-02T09:07:00Z"
CLEAN_BODY = f"Codex Review: Didn't find any major issues. **Reviewed commit:** `{THUMB_HEAD[:10]}`"


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
        "headRefOid": THUMB_HEAD,
        "baseRefOid": BASE_TIP,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "createdAt": OPENED,
        "headRefName": BRANCH,
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
    """
    facts: dict[str, object] = {
        "meta": _meta(),
        "final_meta": None,
        "commit_date": ARRIVED,
        "reviews": [],
        "final_reviews": None,
        "inline": [],
        "final_inline": None,
        "conversation": [],
        "final_conversation": None,
        "reactions": [],
        "final_reactions": None,
        "activity": [_arrival()],
        "threads": [],
        "checks": [{"name": "invented-check", "state": "SUCCESS", "bucket": "pass"}],
    }
    facts.update(overrides)
    seen: dict[str, int] = {}

    def read(key: str) -> object:
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 1:
            return facts[key]
        later = facts[f"final_{key}"]
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
        if "activity?ref=" in joined:
            return json.dumps(facts["activity"])
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


def test_the_bare_thumb_sweep_reports_READY_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ The second known positive, and shape B's own: #233's case end to end.

    ⚠️ The refusals below all withhold a BARE-THUMB verdict, so a harness that
    could never grant one would pass every one of them for the wrong reason.
    """
    assert _sweep(monkeypatch, reactions=[_bot_thumb(THUMBED)]) is True


def test_a_bot_review_seen_ONLY_IN_THE_FIRST_READ_still_governs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ A reread may not FORGET. The second read was trusted alone.

    ⚠️ Named input: the first reviews read carries a bot finding submitted after
    T; the final reviews request comes back empty or short (a replica behind, a
    truncated page). Those final-only arguments discarded the review already
    observed, so a fresh thumb and otherwise clean gates printed READY over a
    finding the sweep had already seen. **Any post-T artifact governs**, so both
    reads are kept.
    """
    finding = {
        "submitted_at": LATER,
        "body": "a finding",
        "user": {"login": "chatgpt-codex-connector"},
    }

    verdict = _sweep(
        monkeypatch, reactions=[_bot_thumb(THUMBED)], reviews=[finding], final_reviews=[]
    )

    assert verdict is False


def test_a_ready_event_that_DISAPPEARS_from_the_final_read_still_moves_T(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ T never goes backwards between two reads of the same timeline.

    ⚠️ Named input: a pull request opened at 09:00 has a thumb at 10:00, the
    provisional metadata sees a ready-for-review event at 11:00, and the final
    timeline returns ``[]``. Only the final read fed T, so T fell back to the
    open time, the stale thumb postdated it, and READY printed for the round
    before the one the mark-ready started.
    """
    verdict = _sweep(
        monkeypatch,
        meta=_meta(timelineItems={"nodes": [{"createdAt": "2026-04-02T11:00:00Z"}]}),
        final_meta=_meta(timelineItems={"nodes": []}),
        reactions=[_bot_thumb("2026-04-02T10:00:00Z")],
    )

    assert verdict is False


def test_a_TRIGGER_that_disappears_from_the_final_read_still_moves_T(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠️ The same regression through the other term, and
    ``_request_arrived_mid_sweep`` does not catch it: that rule fires when the
    request moves FORWARD, and a request going from one to none leaves ``after``
    empty, so it says nothing at all.
    """
    asked = {
        "created_at": "2026-04-02T10:30:00Z",
        "body": pr_ready.TRIGGER,
        "user": {"login": "randyjreid"},
    }

    verdict = _sweep(
        monkeypatch,
        conversation=[asked],
        final_conversation=[],
        reactions=[_bot_thumb("2026-04-02T10:00:00Z")],
    )

    assert verdict is False


def test_a_final_read_that_cannot_name_the_HEAD_BRANCH_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ The final read decides the branch, exactly as it decides the head SHA.

    ⚠️ Named input: the provisional metadata reports a head branch, the final
    metadata omits or nulls ``headRefName``, and the old branch's activity looks
    valid. The cached provisional name was passed to shape B, so READY printed
    although the final branch identity was unreadable.
    """
    unreadable = _meta()
    del unreadable["headRefName"]

    verdict = _sweep(monkeypatch, final_meta=unreadable, reactions=[_bot_thumb(THUMBED)])

    assert verdict is False


def test_a_head_branch_RENAMED_mid_sweep_refuses_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠️ A rename keeps the head SHA, so step 7's head comparison says nothing --
    and the activity read would then ask a different ref about this one's quiet.
    """
    verdict = _sweep(
        monkeypatch,
        final_meta=_meta(headRefName="another-invented-branch"),
        reactions=[_bot_thumb(THUMBED)],
    )

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
