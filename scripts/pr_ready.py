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

REPOSITORY = "randyjreid/gramps-live-api"
BOT = "chatgpt-codex-connector[bot]"

# ⛔ What the bot says when it has looked and found nothing. Matched
# case-insensitively against a conversation comment, because the clean signal
# arrives there and creates no review object at all.
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
    body = _gh(*arguments).strip()
    return json.loads(body) if body else []


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
    meta = _json("pr", "view", str(pull), "--repo", REPOSITORY, "--json", "state,headRefOid,title")
    assert isinstance(meta, dict)
    state = meta.get("state", "?")
    print(f"  1. state                : {state}")
    if state != "OPEN":
        print("     -> not open; nothing further computed")
        print(f"  RESULT: NOT the owner's click -- the pull request is {state}")
        return False

    # -- 2. the head ---------------------------------------------------------
    head = str(meta["headRefOid"])
    commit = _json("api", f"repos/{REPOSITORY}/commits/{head}")
    assert isinstance(commit, dict)
    head_when = str(((commit.get("commit") or {}).get("committer") or {}).get("date", ""))
    print(f"  2. head                 : {head[:12]}  committed {head_when}")

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
    # ⚠️ A REACTION CARRIES NO commit_id. Freshness can only come from its
    # timestamp against the head's commit date -- a thumbs-up a day older than
    # the head was read as a verdict on it once, and that is this check.
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
        for c in fresh_conversation
        if any(phrase in (c.get("body") or "").lower() for phrase in CLEAN_PHRASES)
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

    if not (clean_comments or fresh_reactions):
        failures.append(
            "no CLEAN verdict on this head -- no fresh +1 on the body and no "
            "conversation comment saying it found nothing"
        )

    # -- 4. unresolved threads, by isResolved --------------------------------
    # ⛔ The discriminator. Not "has a reply", not "was filed" -- both were used
    # and both were wrong. A thread with a reply that is not resolved is not
    # answered, and neither is a finding recorded in an issue.
    query = (
        '{repository(owner:"randyjreid",name:"gramps-live-api")'
        f"{{pullRequest(number:{pull})"
        "{reviewThreads(first:100){nodes{id isResolved path "
        "comments(first:1){nodes{author{login}}}}}}}}"
    )
    graph = json.loads(_gh("api", "graphql", "-f", f"query={query}") or "{}")
    nodes = (
        graph.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    unresolved = [t for t in nodes if not t.get("isResolved")]
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
    not_success = sorted({row["name"] for row in checks if row["state"] != "SUCCESS"})
    print(
        f"  5. CI                   : {len(checks)} checks  "
        + " ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    )
    for name in not_success:
        print(f"       not SUCCESS        : {name}")
    if not checks:
        failures.append("no CI checks reported at all")
    elif not_success:
        failures.append(f"{len(not_success)} check(s) not SUCCESS")

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
