"""Is this pull request the owner's click? Answer by running, not by reasoning.

⛔ **This exists because the prose version was wrong five times running, and every
time it failed toward "ready".**

Each report re-derived merge-readiness by hand, and each used a proxy that was
true for the wrong reason:

===========================  =============================================
CI green + a bot verdict     never read ``state`` -- two MERGED pull
                             requests were reported as awaiting the click
a thumbs-up on the body      reactions carry no ``commit_id``; one was a
                             day older than the head it was read against
"filed" or "replied"         neither is ``isResolved``; eleven threads sat
                             unanswered while the summary said clean
a table written per report   nothing carried forward, so each retelling
                             could be wrong in a new way
===========================  =============================================

⭐ **The fix is the one #174 recommends for ``_source_check`` and the one that
settled the interpreter question: stop re-implementing the judgement in prose and
run it.** A script cannot forget ``state``, cannot decide a stale reaction looks
recent enough, and cannot round "answered" up to "resolved".

**The exit code is the verdict. The output is the evidence.** Nothing downstream
should restate either.

Usage::

    python scripts/pr_ready.py 165
    python scripts/pr_ready.py 165 166 170 172
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

REPOSITORY = "randyjreid/gramps-live-api"

# ⛔ **The SAME account, spelled differently by the two APIs.** REST appends the
# ``[bot]`` suffix; GraphQL does not.
#
# ⚠️ **That mismatch already hid a count once.** A filter written with the REST
# spelling and run against GraphQL matched nothing, and reported ZERO bot rounds
# on a pull request that had had eight -- an empty result reading as an absence,
# which is this project's recorded defect class.
#
# ⭐ So membership is asked of a set rather than of one literal, and no caller
# has to remember which API it is holding.
BOT_LOGINS = frozenset({"chatgpt-codex-connector[bot]", "chatgpt-codex-connector"})
BOT = "chatgpt-codex-connector[bot]"
"""The REST spelling, kept for callers that build a REST query string."""

# ⛔ The backstop is the OWNER'S call, so this number only ever prints.
BACKSTOP = 5

# ⛔ What the bot says when it has looked and found nothing. Matched
# case-insensitively against a conversation comment, because the clean signal
# arrives there and creates no review object at all.
_WHITESPACE = frozenset({chr(32), chr(9), chr(13), chr(10)})
"""Space, tab, CR, LF -- built from ordinals so no escape layer can mangle them."""

CLEAN_PHRASES = ("didn't find any major issues", "didn't find any issues", "no major issues")

# ⛔ **Assembled from parts so this file never CONTAINS the phrase it looks for.**
#
# ⚠️ The bot matches a substring, and this source is rendered in its own pull
# request's diff. A literal here would be a review request written into a file --
# the same reason CONTRIBUTING forbids the phrase in prose.
TRIGGER = "@" + "codex" + " " + "review"


def _gh(*arguments: str) -> str:
    """One ``gh`` call.

    ⛔ ``encoding``/``errors`` explicitly, never bare ``text=True``. The locale
    encoding on this project's development machine is cp1252, bot comments carry
    emoji, and a decode failure there returns ``None`` rather than raising -- the
    same defect this project already fixed once in ``scripts/gate.py``.
    """
    finished = subprocess.run(
        ["gh", *arguments],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if finished.returncode != 0:
        raise RuntimeError(f"gh {' '.join(arguments)} failed: {(finished.stderr or '').strip()}")
    return finished.stdout or ""


def _json(*arguments: str) -> object:
    """Decode ``gh`` output, tolerating MULTIPLE concatenated JSON documents.

    ⚠️ ``gh api --paginate`` may emit one document per page — its own help says
    so — and a single ``json.loads`` then raises ``Extra data``. That failed
    SAFE here, because the caller turns any exception into NOT READY, but a gate
    that breaks on large pull requests is a gate nobody can use on the ones that
    need it most.

    ⭐ Not reproduced on this ``gh``: a 30-comment thread came back as one
    document. Handled anyway — two lines against a version-dependent hazard.
    """
    body = _gh(*arguments).strip()
    if not body:
        return []
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    decoder, index, merged = json.JSONDecoder(), 0, []
    while index < len(body):
        page, index = decoder.raw_decode(body, index)
        merged.extend(page if isinstance(page, list) else [page])
        while index < len(body) and body[index] in _WHITESPACE:
            index += 1
    return merged


def _names_the_head(body: str, head: str) -> bool:
    """Does this comment quote the head SHA?

    ⛔ The bot writes ``**Reviewed commit:** `<abbreviated sha>`​``, so the
    association is explicit and does not depend on any clock. Matched against
    every prefix length the abbreviation might use rather than one guess.
    """
    lowered = body.lower()
    return any(lowered.count(head[:length].lower()) for length in range(7, len(head) + 1))


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _latest_request(comments: list[dict[str, Any]]) -> str:
    """When a new review round was most recently ASKED FOR, or ``""``.

    ⚠️ Every author, not only the bot -- the request is posted by whoever is
    driving the gate, and it is their comment that invalidates an older verdict.
    """
    stamps = [
        str(c.get("created_at") or "") for c in comments if TRIGGER in (c.get("body") or "").lower()
    ]
    return max(stamps, default="")


def _still_current(comments: list[dict[str, Any]], latest_request: str) -> list[dict[str, Any]]:
    """Those comments that POSTDATE the most recent request for a round.

    ⛔ Lexicographic comparison is correct here and only here: every timestamp
    GitHub returns is the same fixed-width UTC format, so string order is time
    order. It would not be for mixed offsets, and nothing in this file has any.

    ⭐ With ``latest_request`` empty -- the automatic review on open, never
    re-triggered -- every comment postdates it and the caller's other evidence
    stands alone. That is deliberate: there is no request to be stale against.
    """
    return [c for c in comments if str(c.get("created_at") or "") > latest_request]


def _is_bot(login: object) -> bool:
    """⛔ Either spelling. See ``BOT_LOGINS``."""
    return str(login or "") in BOT_LOGINS


def _round_note(rounds: int) -> str:
    """The backstop line, or ``""``. ⛔ **Advisory. It never blocks.**

    ⚠️ The five-round backstop is the owner's decision about whether the work is
    still worth reviewing. A script that enforced it would be taking that
    decision instead of informing it -- and the failure this repairs was not a
    missing rule, it was a count nobody could see.
    """
    if rounds < BACKSTOP:
        return ""
    return f"⚠ {rounds} bot rounds -- the backstop is the owner's call"


# ⛔ **The ONLY state GitHub calls good.** Everything else -- BEHIND, BLOCKED,
# DIRTY, DRAFT, HAS_HOOKS, UNKNOWN, UNSTABLE -- blocks.
#
# ⚠️ **An allowlist, deliberately, and this is the whole lesson of the twelve.**
# The version this replaces named the two BAD states it thought of, so every
# state nobody thought of passed -- BLOCKED printed READY for a pull request
# GitHub refuses to merge. **A list of bad states cannot be completed. A list of
# good ones is the entire check.**
#
# ⚠️ The trade, stated rather than discovered later: ``UNSTABLE`` (a non-required
# check failing) and ``HAS_HOOKS`` block here, and a reader may consider one of
# those mergeable. **Erring toward a false NOT-READY is the direction this script
# exists to choose** -- it costs a re-run; the other direction costs a bad merge.
GOOD_MERGE_STATE = "CLEAN"
GOOD_MERGEABLE = "MERGEABLE"

METADATA_FIELDS = ("state", "isDraft", "headRefOid", "baseRefOid", "mergeable", "mergeStateStatus")


def _metadata(pull: int) -> dict[str, Any]:
    """⭐ **ONE call for every fact the verdict rests on**, including the live base.

    ⛔ The three checks this replaces each took their own snapshot at a different
    moment -- the open/draft read at the start, the base comparison in the middle,
    the re-read at the end -- so a pull request could satisfy all three while
    never having been in a mergeable state at any single instant. Findings 6, 8
    and 9 were that gap, three times, differing only in which field went stale.

    ⚠️ **The window is not closed, it is SHRUNK** -- from the whole sweep to one
    request. A final read is still a snapshot, and something can change the
    instant after GitHub answers. That is as small as this can be made without
    holding a lock GitHub does not offer, and it is smaller than any arrangement
    of separate reads can be.

    ⭐ GraphQL rather than ``gh pr view`` because ``baseRef{target{oid}}`` rides
    along: the live base tip and the base the head was verified against come back
    **in the same answer**, which is what makes the comparison meaningful.
    """
    query = (
        '{repository(owner:"randyjreid",name:"gramps-live-api")'
        f"{{pullRequest(number:{pull})"
        "{state isDraft headRefOid baseRefOid mergeable mergeStateStatus "
        "baseRef{name target{oid}}}}}"
    )
    graph = json.loads(_gh("api", "graphql", "-f", f"query={query}") or "{}")
    pull_request = ((graph.get("data") or {}).get("repository") or {}).get("pullRequest")
    if not pull_request:
        raise RuntimeError(f"no pull request #{pull} in the graph response")
    return pull_request


def _judge(meta: dict[str, Any], expected_head: str) -> list[str]:
    """The verdict on one metadata snapshot. ⛔ **Every field required.**

    ⚠️ A field that is absent is not a field that is fine. GitHub omits what it
    cannot answer, and ``.get()`` returning ``None`` compared against a good
    value would simply read as *not good* -- which happens to be right here, but
    only by luck. **It is asserted instead**, so a schema change is a loud error
    rather than a quiet verdict.
    """
    missing = [field for field in METADATA_FIELDS if field not in meta]
    if missing:
        return [f"the metadata read did not answer: {', '.join(missing)}"]

    failures: list[str] = []
    if meta["state"] != "OPEN":
        failures.append(f"the pull request is {meta['state']}, not OPEN")
    if meta["isDraft"]:
        failures.append("the pull request is a DRAFT and GitHub will not merge it")
    if str(meta["headRefOid"]) != expected_head:
        failures.append(
            f"the head moved while this sweep ran ({expected_head[:12]} -> "
            f"{str(meta['headRefOid'])[:12]}) -- the evidence above is about the old one"
        )
    live_base = str(((meta.get("baseRef") or {}).get("target") or {}).get("oid") or "")
    if not live_base:
        failures.append("the base branch tip could not be read")
    elif live_base != str(meta["baseRefOid"]):
        failures.append(
            f"base has moved since this head was verified ({str(meta['baseRefOid'])[:12]} "
            f"-> {live_base[:12]}) -- the tests that passed ran under different code"
        )
    if meta["mergeable"] != GOOD_MERGEABLE:
        # ⚠️ UNKNOWN is not rare: GitHub computes mergeability asynchronously and
        # answers UNKNOWN until it has. It blocks, and it clears on a re-run.
        failures.append(
            f"mergeable is {meta['mergeable']}, not {GOOD_MERGEABLE}"
            + (
                " -- GitHub has not computed it yet; run again"
                if meta["mergeable"] == "UNKNOWN"
                else ""
            )
        )
    if meta["mergeStateStatus"] != GOOD_MERGE_STATE:
        failures.append(f"mergeStateStatus is {meta['mergeStateStatus']}, not {GOOD_MERGE_STATE}")
    return failures


def _report(pull: int) -> bool:
    """Print the evidence for one pull request. True only if it is the click."""
    failures: list[str] = []
    swept = datetime.now(timezone.utc)
    print(f"=== PR #{pull} " + "=" * 52)

    # -- 1. which head is the evidence ABOUT? --------------------------------
    #
    # ⛔ **Provisional, and it decides nothing.** Gathering evidence needs a SHA
    # to filter on, so one read happens first -- but every field it returns is
    # read again at the end, and it is that later answer the verdict rests on.
    #
    # ⚠️ The early exit for a closed pull request is the #160/#161 failure and it
    # stays: both were MERGED and both were reported as awaiting the click,
    # because readiness was derived from CI and a verdict without ever reading
    # ``state``. Stopping here costs nothing and says something useful.
    provisional = _metadata(pull)
    state = str(provisional.get("state") or "?")
    if state != "OPEN":
        print(f"  1. state                : {state}")
        print("     -> not open; nothing further computed")
        print(f"  RESULT: NOT the owner's click -- the pull request is {state}")
        return False

    head = str(provisional["headRefOid"])
    commit = _json("api", f"repos/{REPOSITORY}/commits/{head}")
    assert isinstance(commit, dict)
    head_when = str(((commit.get("commit") or {}).get("committer") or {}).get("date", ""))
    print(f"  1. head under review    : {head[:12]}  committed {head_when}")
    print("       (state and mergeability are judged at step 7, not here)")

    # -- 2. a bot verdict ON THAT HEAD ---------------------------------------
    # ⛔ All three object types, because the clean signal is not in the one that
    # is easiest to query: it arrives as a conversation comment plus a reaction
    # and creates NO review object.
    reviews = _json("api", f"repos/{REPOSITORY}/pulls/{pull}/reviews", "--paginate")
    inline = _json("api", f"repos/{REPOSITORY}/pulls/{pull}/comments", "--paginate")
    conversation = _json("api", f"repos/{REPOSITORY}/issues/{pull}/comments", "--paginate")
    reactions = _json("api", f"repos/{REPOSITORY}/issues/{pull}/reactions")
    assert isinstance(reviews, list) and isinstance(inline, list)
    assert isinstance(conversation, list) and isinstance(reactions, list)

    def by_bot(rows: list) -> list:
        return [r for r in rows if _is_bot((r.get("user") or {}).get("login"))]

    on_head_reviews = [r for r in by_bot(reviews) if r.get("commit_id") == head]
    on_head_inline = [c for c in by_bot(inline) if c.get("commit_id") == head]
    # ⛔ **A clean verdict must NAME the head, not merely postdate it.**
    #
    # ⚠️ Timestamps were the first attempt and they are not sound: a commit
    # created locally BEFORE a verdict and pushed as the head afterwards has a
    # committer date that predates that stale verdict, so a date comparison
    # accepts the old comment as a verdict on the new SHA -- a false READY, which
    # is the direction this whole script exists to stop.
    #
    # ⭐ The bot's clean comment names its subject: "**Reviewed commit:**
    # `7905da6ddd`". That is evidence explicitly associated with a SHA, so the
    # comparison is against the head's own hex rather than against a clock.
    # A reaction carries no commit_id and can never be tied to a head, so it is
    # corroboration only and is no longer sufficient on its own.
    fresh_reactions = [
        r
        for r in by_bot(reactions)
        if r.get("content") == "+1" and head_when and r.get("created_at", "") > head_when
    ]
    fresh_conversation = [
        c for c in by_bot(conversation) if head_when and c.get("created_at", "") > head_when
    ]
    clean_comments = [
        c
        for c in by_bot(conversation)
        if any(phrase in (c.get("body") or "").lower() for phrase in CLEAN_PHRASES)
        and _names_the_head(c.get("body") or "", head)
    ]

    # ⛔ **A clean verdict must postdate the TRIGGER THAT ASKED FOR IT.**
    #
    # ⚠️ Naming the head is not enough, because a round can be requested without
    # changing the head -- which is this project's ordinary path, not an edge
    # case: every finding that is disputed or filed rather than fixed produces no
    # push, and the procedure then requires a re-trigger on the same SHA. The
    # previous round's clean comment still names that head, so it satisfies the
    # check above while the NEW round is still running, and READY is printed
    # before the findings land.
    #
    # ⭐ CONTRIBUTING already stated this for a human operator -- *"when the head
    # has not changed, baseline the review count and wait for it to increase"* --
    # and this script did not implement it. **The script and the written
    # procedure disagreed, and the procedure was right.**
    #
    # ⚠️ A one-shot sweep cannot "capture and wait", so the same rule is applied
    # to what is already recorded: the accepted verdict must be NEWER than the
    # most recent request. With no request at all -- the automatic review on
    # open -- there is nothing to postdate, and naming the head stands alone.
    latest_trigger = _latest_request(conversation)
    accepted_clean = _still_current(clean_comments, latest_trigger)
    superseded_clean = [c for c in clean_comments if c not in accepted_clean]

    print("  3. bot verdict on head  :")
    print(
        f"       reviews on head    : {len(on_head_reviews)}"
        + (f"  ({on_head_reviews[-1].get('submitted_at')})" if on_head_reviews else "")
    )
    print(f"       inline on head     : {len(on_head_inline)}")
    print(
        f"       conversation after : {len(fresh_conversation)}"
        + (f"  ({fresh_conversation[-1].get('created_at')})" if fresh_conversation else "")
    )
    print(
        f"       clean-phrase comment: {len(clean_comments)}"
        + (f"  ({clean_comments[-1].get('created_at')})" if clean_comments else "")
    )
    print(
        f"       fresh +1 on body   : {len(fresh_reactions)}"
        + (f"  ({fresh_reactions[-1].get('created_at')})" if fresh_reactions else "")
    )
    stale_reactions = [
        r
        for r in by_bot(reactions)
        if r.get("content") == "+1" and head_when and r.get("created_at", "") <= head_when
    ]
    if stale_reactions:
        print(
            f"       STALE +1 ignored   : {len(stale_reactions)}"
            f"  ({stale_reactions[-1].get('created_at')} <= head)"
        )

    print(f"       last round requested: {latest_trigger or '(never -- automatic review only)'}")
    if superseded_clean:
        print(
            f"       SUPERSEDED clean    : {len(superseded_clean)}"
            f"  ({superseded_clean[-1].get('created_at')} <= the request above)"
        )

    if not clean_comments:
        failures.append(
            "no CLEAN verdict naming this head -- the bot's clean comment quotes "
            "the commit it reviewed, and none quoting this one was found"
        )
    elif not accepted_clean:
        failures.append(
            "the CLEAN verdict predates the most recent review request -- a round "
            "was asked for after it, so that verdict is about an earlier round"
        )

    # -- 3. how many rounds has this had? ------------------------------------
    #
    # ⛔ **This PRINTS. It never blocks**, and the difference is the whole point:
    # the five-round backstop is the owner's decision about whether the work is
    # still worth reviewing, and a script that enforced it would be taking that
    # decision rather than informing it.
    #
    # ⚠️ **It exists because the count lived in nobody's head.** #175 passed
    # round five unnoticed and ran to EIGHT -- every round producing genuine
    # findings, none ever clean -- because each round was read on its own merits,
    # where continuing is always defensible. **An unimplemented ceiling cannot
    # fire**, which is the same defect as every other one here: a judgement
    # remembered instead of run.
    rounds = len(by_bot(reviews))
    print(f"  3. bot review rounds    : {rounds} total, {len(on_head_reviews)} on this head")
    note = _round_note(rounds)
    if note:
        print(f"       {note}")

    # -- 4. unresolved threads, by isResolved --------------------------------
    # ⛔ The discriminator. Not "has a reply", not "was filed" -- both were used
    # and both were wrong. A thread with a reply that is not resolved is not
    # answered, and neither is a finding recorded in an issue.
    # ⛔ PAGINATED. `first:100` silently drops every thread after the
    # hundredth, so an unresolved thread beyond it would be invisible and this
    # would print READY -- the failure direction the whole file exists to stop.
    # No pull request here has reached 100 yet; that is not a reason to rely on
    # it, and the same reasoning is why the REST calls above are --paginate.
    nodes: list[dict[str, Any]] = []
    cursor = "null"
    while True:
        query = (
            '{repository(owner:"randyjreid",name:"gramps-live-api")'
            f"{{pullRequest(number:{pull})"
            f"{{reviewThreads(first:100, after:{cursor})"
            "{pageInfo{hasNextPage endCursor} nodes{id isResolved path "
            "comments(first:1){nodes{author{login}}}}}}}}"
        )
        graph = json.loads(_gh("api", "graphql", "-f", f"query={query}") or "{}")
        threads = (
            graph.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
        )
        nodes.extend(threads.get("nodes", []))
        info = threads.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        cursor = chr(34) + str(info.get("endCursor")) + chr(34)
    unresolved = [t for t in nodes if not (t or {}).get("isResolved")]
    print(f"  4. review threads       : {len(nodes)} total, {len(unresolved)} UNRESOLVED")
    for thread in unresolved:
        started = (thread.get("comments", {}).get("nodes") or [{}])[0]
        print(
            f"       unresolved         : {thread['id']}  {thread.get('path')}"
            f"  (started by {(started.get('author') or {}).get('login')})"
        )
    if unresolved:
        failures.append(f"{len(unresolved)} unresolved review thread(s)")

    # -- 5. CI, as EVIDENCE -- the verdict on it comes from step 7 -----------
    #
    # ⛔ From JSON, never from columns. An awk pipe over `gh pr checks` output
    # read six RED legs as green and that reached a report.
    #
    # ⛔ **This no longer decides anything, and that is finding 11's repair.**
    # The version this replaces classified states itself against a hand-written
    # set of in-flight ones, so ``SKIPPED`` and ``NEUTRAL`` -- legitimate, common,
    # and neither a pass nor a failure -- were counted as failures and would have
    # blocked a pull request indefinitely.
    #
    # ⭐ ``mergeStateStatus`` at step 7 already carries GitHub's own answer:
    # ``CLEAN`` means mergeable with passing checks, ``UNSTABLE`` means a check is
    # not passing, ``BLOCKED`` means protection is unsatisfied. **Classifying the
    # states here as well was a second way of deciding one question** -- this
    # project's most-recorded defect class -- and the two could disagree.
    #
    # ⚠️ ``bucket`` rather than ``state`` for the display, so the printed line is
    # right about what it shows: gh categorises every state into pass, fail,
    # pending, skipping or cancel, and does not go stale when a state is added.
    checks = _json("pr", "checks", str(pull), "--repo", REPOSITORY, "--json", "name,state,bucket")
    assert isinstance(checks, list)
    tally: dict[str, int] = {}
    for row in checks:
        bucket = str(row.get("bucket") or row.get("state") or "?")
        tally[bucket] = tally.get(bucket, 0) + 1
    print(
        f"  5. CI                   : {len(checks)} checks  "
        + " ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    for row in sorted(checks, key=lambda r: str(r.get("name") or "")):
        if str(row.get("bucket") or "") not in ("pass", "skipping"):
            print(f"       {str(row.get('bucket') or '?'):<18} : {row.get('name')}")
    if not checks:
        # ⚠️ Kept as a failure: no checks at all is not a green matrix, and
        # mergeStateStatus can read CLEAN on a repository with no protection.
        failures.append("no CI checks reported at all")

    # -- 6. how fresh is this sweep ------------------------------------------
    # ⚠️ So a run taken BEFORE a verdict landed is visible as such rather than
    # reading as "the bot said nothing".
    stamps = [
        r.get("submitted_at") or r.get("created_at")
        for r in by_bot(reviews) + by_bot(inline) + by_bot(conversation)
    ]
    newest = max((s for s in stamps if s), default=None)
    print(f"  6. swept at             : {swept.isoformat(timespec='seconds')}")
    print(f"       newest bot activity: {newest or '(none)'}")
    if newest and (swept - _when(newest)).total_seconds() < 120:
        print(
            "       ⚠️ swept within 2 minutes of the newest bot activity --"
            " a round may still be arriving"
        )

    # -- 7. ONE final metadata read -- and it is the verdict ------------------
    #
    # ⛔ **Every check above is evidence. This is the judgement**, and it is one
    # API call so that the six fields cannot disagree with each other about when
    # they were true. Three separate snapshots -- open/draft at the start, the
    # base in the middle, a re-read at the end -- let a pull request satisfy all
    # three without ever having been mergeable at any single instant.
    #
    # ⚠️ **The window is shrunk, NOT closed.** A final read is still a snapshot;
    # something can change the instant after GitHub answers. One request is as
    # small as this can be made, and it is not zero.
    final = _metadata(pull)
    print(f"  7. final metadata read  : state={final.get('state')} draft={final.get('isDraft')}")
    print(f"       head               : {str(final.get('headRefOid') or '')[:12]}")
    print(
        f"       base {str((final.get('baseRef') or {}).get('name') or '?'):<14}: "
        f"{str(final.get('baseRefOid') or '')[:12]} verified, "
        f"{str(((final.get('baseRef') or {}).get('target') or {}).get('oid') or '')[:12]} now"
    )
    print(
        f"       mergeable          : {final.get('mergeable')}  ({final.get('mergeStateStatus')})"
    )
    failures.extend(_judge(final, head))

    if failures:
        print("  RESULT: NOT the owner's click")
        for reason in failures:
            print(f"     - {reason}")
        return False
    print("  RESULT: READY -- every check above passed")
    return True


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    ready: list[str] = []
    blocked: list[str] = []
    for raw in argv:
        try:
            ok = _report(int(raw))
        except Exception as failure:  # noqa: BLE001 - any failure means "cannot say yes"
            print(f"=== PR #{raw} ===\n  ERROR: {failure}")
            print("  RESULT: NOT the owner's click -- the check could not complete")
            ok = False
        (ready if ok else blocked).append(raw)
        print()
    print(f"READY: {', '.join('#' + n for n in ready) if ready else '(none)'}")
    print(f"NOT READY: {', '.join('#' + n for n in blocked) if blocked else '(none)'}")
    # ⛔ Non-zero if ANY pull request asked about is not ready. A caller checking
    # one gets that one's answer; a caller checking several must read the lines.
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
