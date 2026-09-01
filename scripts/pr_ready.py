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
BOT = "chatgpt-codex-connector[bot]"

# ⛔ What the bot says when it has looked and found nothing. Matched
# case-insensitively against a conversation comment, because the clean signal
# arrives there and creates no review object at all.
_WHITESPACE = frozenset({chr(32), chr(9), chr(13), chr(10)})
"""Space, tab, CR, LF -- built from ordinals so no escape layer can mangle them."""

_RUNNING = frozenset({"IN_PROGRESS", "QUEUED", "PENDING"})
"""States that are neither a pass nor a failure. Both block; only one is bad news."""

CLEAN_PHRASES = ("didn't find any major issues", "didn't find any issues", "no major issues")


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


def _report(pull: int) -> bool:
    """Print the evidence for one pull request. True only if it is the click."""
    failures: list[str] = []
    swept = datetime.now(timezone.utc)
    print(f"=== PR #{pull} " + "=" * 52)

    # -- 1. state, FIRST -----------------------------------------------------
    # ⛔ Nothing else is computed for a pull request that is not open. This is
    # the #160/#161 failure: both were merged and both were reported as awaiting
    # the click, because readiness was derived from CI and a verdict alone.
    meta = _json(
        "pr",
        "view",
        str(pull),
        "--repo",
        REPOSITORY,
        "--json",
        "state,headRefOid,title,baseRefName,baseRefOid,mergeable,mergeStateStatus,isDraft",
    )
    assert isinstance(meta, dict)
    state = meta.get("state", "?")
    draft = bool(meta.get("isDraft"))
    print(f"  1. state                : {state}" + ("  (DRAFT)" if draft else ""))
    if state != "OPEN":
        print("     -> not open; nothing further computed")
        print(f"  RESULT: NOT the owner's click -- the pull request is {state}")
        return False
    if draft:
        # ⛔ A draft can carry an explicit review, no unresolved threads and a
        # green matrix -- it passes every check below. GitHub still refuses to
        # merge it, so READY would be a claim the platform contradicts.
        failures.append("the pull request is a DRAFT and GitHub will not merge it")

    # -- 2. the head ---------------------------------------------------------
    head = str(meta["headRefOid"])
    commit = _json("api", f"repos/{REPOSITORY}/commits/{head}")
    assert isinstance(commit, dict)
    head_when = str(((commit.get("commit") or {}).get("committer") or {}).get("date", ""))
    print(f"  2. head                 : {head[:12]}  committed {head_when}")

    # -- 2b. is the BASE still where it was when this head was verified? -----
    #
    # ⛔ **A clean verdict and a green matrix on a stale base say nothing about
    # what would actually merge.** The whole point of the gate is that what was
    # reviewed is what merges, and once the base moves that stops being true --
    # the tests that passed ran against code that is no longer underneath it.
    #
    # ⚠️ ``mergeStateStatus`` is NOT sufficient on its own. GitHub reports
    # ``BEHIND`` only where the repository requires branches to be up to date;
    # otherwise a pull request whose base has moved reports ``CLEAN``. Measured:
    # #175 read CLEAN with a base seven commits behind. So the base OID is
    # compared directly, and the status is used for the conflict case where it
    # is authoritative.
    base_ref = str(meta.get("baseRefName") or "main")
    base_oid = str(meta.get("baseRefOid") or "")
    current_base = _gh(
        "api", f"repos/{REPOSITORY}/git/ref/heads/{base_ref}", "-q", ".object.sha"
    ).strip()
    mergeable = str(meta.get("mergeable") or "?")
    merge_state = str(meta.get("mergeStateStatus") or "?")
    print(f"  2b. base                : {base_ref}")
    print(f"       verified against   : {base_oid[:12] or '(unknown)'}")
    print(f"       {base_ref} is now      : {current_base[:12] or '(unknown)'}")
    print(f"       mergeable          : {mergeable}  ({merge_state})")

    if mergeable == "CONFLICTING" or merge_state == "DIRTY":
        failures.append("merge conflict with base")
    elif current_base and base_oid and current_base != base_oid:
        failures.append(
            f"base has moved since this head was verified ({base_oid[:12]} -> {current_base[:12]})"
        )

    # -- 3. a bot verdict ON THAT HEAD ---------------------------------------
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
        return [r for r in rows if (r.get("user") or {}).get("login") == BOT]

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

    if not clean_comments:
        failures.append(
            "no CLEAN verdict naming this head -- the bot's clean comment quotes "
            "the commit it reviewed, and none quoting this one was found"
        )

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

    # -- 5. CI, counted from JSON --------------------------------------------
    # ⛔ From JSON, never from columns. An awk pipe over `gh pr checks` output
    # read six RED legs as green and that reached a report.
    checks = _json("pr", "checks", str(pull), "--repo", REPOSITORY, "--json", "name,state")
    assert isinstance(checks, list)
    tally: dict[str, int] = {}
    for row in checks:
        tally[row["state"]] = tally.get(row["state"], 0) + 1
    # ⛔ STILL RUNNING and FAILED are different facts, and collapsing them made
    # this print "7 check(s) not SUCCESS" for a matrix that was merely mid-run.
    # Both block, so the exit code is the same -- but a reason line that says
    # "failed" about a run in progress is the kind of wrong that gets acted on.
    running = sorted({r["name"] for r in checks if r["state"] in _RUNNING})
    failed = sorted({r["name"] for r in checks if r["state"] not in _RUNNING | {"SUCCESS"}})
    print(
        f"  5. CI                   : {len(checks)} checks  "
        + " ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    for name in failed:
        print(f"       FAILED             : {name}")
    for name in running:
        print(f"       still running      : {name}")
    if not checks:
        failures.append("no CI checks reported at all")
    if failed:
        failures.append(f"{len(failed)} check(s) FAILED")
    if running:
        failures.append(f"{len(running)} check(s) still running -- the matrix is not finished")

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

    # -- 7. has anything moved WHILE this sweep ran? -------------------------
    #
    # ⛔ Every check above is a separate API call, and the CI query is near the
    # end. A push, close or merge between the first call and the last would leave
    # this printing READY about a state that no longer exists -- the same
    # time-of-check/time-of-use gap the sweep-freshness line was added for, one
    # level up.
    again = _json("pr", "view", str(pull), "--repo", REPOSITORY, "--json", "state,headRefOid")
    assert isinstance(again, dict)
    if again.get("state") != state or str(again.get("headRefOid") or "") != head:
        print(
            f"  7. re-checked           : CHANGED during the sweep -- "
            f"{state}/{head[:12]} became {again.get('state')}/"
            f"{str(again.get('headRefOid') or '')[:12]}"
        )
        failures.append("the pull request changed while this sweep was running")
    else:
        print(f"  7. re-checked           : unchanged ({state}, {head[:12]})")

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
