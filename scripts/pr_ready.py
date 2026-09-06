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

⚠️ **The second row was ANSWERED for nine commits, and the answer is
WITHDRAWN.** #233 records what the blanket refusal costs -- a pull request the
bot had passed, reported NOT READY -- and a grant was built for it: a reaction
tied to a head by the branch's own arrival log. **It drew thirteen blocking
findings across three review rounds, eleven of them a false READY**, and one of
those lived inside an earlier round's own repair.

⭐ *No state produces a spurious grant* is a universally quantified negative over
an unbounded input space and has no fixed point. *Never grant on a bare thumb*
closes. **A reaction carries no ``commit_id``, so it is EVIDENCE and never a
verdict.** The report still reads it, still prints it, and names it in the
refusal so the reader knows the bot passed and left no comment naming this head.
An instrument reports; a human decides.

**The exit code is the verdict. The output is the evidence.** Nothing downstream
should restate either.

Usage::

    python scripts/pr_ready.py 165
    python scripts/pr_ready.py 165 166 170 172
"""

from __future__ import annotations

import json
import re
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

# ⛔ What every bot artifact carries, findings review and clean comment alike:
# "**Reviewed commit:** `<sha>`". Matched case-insensitively.
ROUND_MARKER = "reviewed commit"

# ⛔ What the bot says when it has looked and found nothing. Matched
# case-insensitively against a conversation comment, because the clean signal
# arrives there and creates no review object at all.
_WHITESPACE = frozenset({chr(32), chr(9), chr(13), chr(10)})
"""Space, tab, CR, LF -- built from ordinals so no escape layer can mangle them."""

CLEAN_PHRASES = ("didn't find any major issues", "didn't find any issues", "no major issues")

# ⛔ **The bot's own label on the opening line of a clean verdict.** Optional:
# stripped before the phrase is matched, never required.
#
# ⚠️ It exists because the phrase is now the body's OPENING CLAIM rather than a
# substring of it, and the bot writes the label in front of the sentence.
CLEAN_LABEL = "codex review:"

# ⛔ The commit a verdict line QUOTES: hex inside backticks, seven characters or
# more. Written as explicit ASCII classes rather than with ``re.IGNORECASE``,
# whose fold is the interpreter's and not this file's.
VERDICT_CLAIM = re.compile(r"`([0-9a-fA-F]{7,40})`")

# ⛔ The four spacings ``_WHITESPACE`` names, as a string ``str.strip`` accepts.
#
# ⚠️ NOT bare ``.strip()``. Python's default set is 26 characters wide and comes
# from the interpreter; this one is four, written here. A guard whose definition
# arrives from the runtime is the defect class this repository has recorded four
# times in one week.
TRIM = "".join(sorted(_WHITESPACE))

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


def _ascii_lower(text: str) -> str:
    """Lowercase ``A``-``Z`` and nothing else. ⛔ **Length-preserving by construction.**

    ⚠️ ``str.lower()`` is a Unicode operation and it can change a string's
    LENGTH -- ``U+0130`` lowercases to two code points. An offset found in a
    lowered copy and then used to index the original is off by that much, which
    would let a body place its real claim outside the slice this file searches.
    Every character here maps to exactly one character, so the two strings index
    identically.

    ⭐ And the fold is written here, in ASCII code points, rather than taken from
    whatever Unicode table the interpreter shipped. That is this repository's
    recorded rule: a check whose definition depends on where it runs is not a
    check on what it names.
    """
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in text)


def _verdict_names_the_head(body: str, head: str) -> bool:
    """Does this comment's own ``Reviewed commit:`` LINE claim this head?

    ⛔ **Anchored to the line, and this is the repair.** It read the whole body
    lowercased and counted the head's hex anywhere in it, and its docstring said
    *the association is explicit* -- which was exactly what was untrue. Nothing
    tied the hex it found to the verdict. Named input, run with every other gate
    perfect: ``Didn't find any major issues. **Reviewed commit:** `abc1234567`.
    Rebased onto eeeeeeeeee.`` **printed READY on a verdict naming a different
    commit.**

    ⛔ **Fail closed, three ways.** No marker line is no claim. A marker line
    this read cannot parse is no claim. And a body making TWO claims cannot show
    which is true, so every marker line must name this head or none of them
    grants -- ``all`` over a non-empty list.

    ⭐ **Cut to a MEASURED shape.** Across pull requests #150 to #245 the bot
    published 40 conversation verdicts: 40 of 40 carry exactly one line reading
    ``**Reviewed commit:** `<sha>` ``, and every abbreviation is ten characters.
    The seven-character floor is the older, wider bound and is kept.

    ⚠️ ``splitlines`` rather than ``split(chr(10))`` on purpose. It breaks on
    strictly more characters, so a marker line it produces is a PREFIX of the one
    a newline split would give -- and truncating a line's tail can only drop a
    candidate claim, never promote a later one ahead of an earlier. The wider
    splitter is the stricter reading here.
    """
    claims: list[str] = []
    for line in body.splitlines():
        marker = _ascii_lower(line).find(ROUND_MARKER)
        if marker < 0:
            continue
        quoted = VERDICT_CLAIM.search(line, marker + len(ROUND_MARKER))
        claims.append(quoted.group(1) if quoted else "")
    if not claims:
        return False
    return all(bool(c) and _ascii_lower(head).startswith(_ascii_lower(c)) for c in claims)


def _opens_with_a_clean_phrase(body: str) -> bool:
    """Is a clean verdict what this comment OPENS by saying?

    ⛔ **Anchored to the opening line, and this is the other half of the repair.**
    The phrase was matched anywhere in the body, so a findings comment carrying
    one as a substring granted the merge. Named input, run with every other gate
    perfect: ``P3 - no major issues, but consider X. **Reviewed commit:**
    `eeeeeeeeee``` **printed READY on a findings comment.**

    ⭐ **Measured, not guessed.** All 40 of the bot's conversation verdicts over
    pull requests #150 to #245 open ``Codex Review: Didn't find any major
    issues.`` and then vary only the tail -- sixteen distinct flourishes, from
    ``Hooray!`` to ``Chef's kiss.`` So the anchor asks for the opening sentence
    the bot has never once departed from, and the varying part stays free.

    ⚠️ **The label is optional and the phrase list is unchanged.** Widening
    either would be this file's own recorded mistake -- a fix widening the claim
    it fixes. A wording the bot has not used yet is refused, which costs a
    re-trigger and is the direction this instrument fails in.
    """
    opening = ""
    for line in body.splitlines():
        opening = _ascii_lower(line.strip(TRIM))
        if opening:
            break
    if opening.startswith(CLEAN_LABEL):
        opening = opening[len(CLEAN_LABEL) :].lstrip(TRIM)
    return any(opening.startswith(phrase) for phrase in CLEAN_PHRASES)


def _clean_verdicts(comments: list[dict[str, Any]], head: str) -> list[dict[str, Any]]:
    """The comments that ARE a clean verdict on this head. ⛔ **All three, or none.**

    ⛔ Bot-authored, matching a clean phrase, and naming the head. This is the
    only granting evidence the file has left, so it is a named predicate rather
    than a comprehension, and it runs over **both** reads.

    ⚠️ It was inline over the first read only, and the second read confirmed it
    by identity: ``_still_granted`` compares ``id``, and **identity survives an
    edit that destroys content**. Named input: the bot posts a clean comment
    naming this head, the sweep reads it, the bot edits that same comment into a
    findings report -- or edits the quoted commit to a different one -- and the
    final read returns the same id with the new body. The first read's row stood
    and READY printed over a body no longer carrying a clean verdict.

    ⭐ **Confirmation is on CONTENT; identity only pairs the rows.** Filtering
    both sides is what makes ``_still_granted``'s identity test safe, and it is
    cheaper than teaching that helper what a clean verdict is.

    ⛔ **Both content questions are now ANCHORED, and neither was.** They were
    two independent substring searches over the whole body, and once the bare-👍
    grant was deleted they were the only granting evidence in the file. The
    phrase is the body's opening claim; the head match is the verdict line's own
    claim. Each helper names the input it was shown failing on.
    """
    return [
        c
        for c in comments
        if _is_bot((c.get("user") or {}).get("login"))
        and _opens_with_a_clean_phrase(c.get("body") or "")
        and _verdict_names_the_head(c.get("body") or "", head)
    ]


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _said(answer: str | None, nothing: str) -> str:
    """Render a three-answer value for the report. ⛔ **Three renderings, not two.**

    ⚠️ ``value or "(none)"`` prints the same words for *the read says nobody
    asked* and *the read did not say*, which is the collapse this file spent a
    false READY on. A reader deciding whether to re-trigger needs to know which
    one they are looking at.
    """
    if answer is None:
        return "(UNREADABLE -- a request carries no timestamp)"
    return answer or nothing


def _latest_request(comments: list[dict[str, Any]]) -> str | None:
    """When a new round was most recently ASKED FOR. ⛔ **Three answers, not two.**

    ⛔ A timestamp; ``""`` when **no round was ever asked for**; ``None`` when a
    request exists that this read **cannot place in time**.

    ⚠️ **The first two used to be the same value, and that was a false READY.**
    This built ``str(c.get("created_at") or "")`` and returned
    ``max(stamps, default="")``, so a trigger comment whose timestamp is absent
    or null contributed ``""`` -- and if it was the only one, the function
    answered *nobody asked*. T fell back to the open time, the PREVIOUS round's
    clean comment postdated it, and the verdict for a round that had published
    nothing was printed as this round's. **An empty read presented as an
    absence**, which is this project's most-recorded defect class.

    ⭐ The three-answer shape is ``_ready_for_review``'s, already in this file:
    readable / empty / did not say. ``""`` is a real answer and stays cheap;
    ``None`` is an unanswered question and refuses.

    ⛔ **The BOT'S own comments are excluded, and skipping that made this rule
    defeat itself.**

    ⚠️ Every clean verdict the bot posts carries an *About Codex* footer that
    documents how to ask for a round -- so it contains the trigger phrase. With
    every author counted, a clean verdict registered as a **request timestamped
    identically to itself**, could not postdate it, and was ruled superseded.
    **No pull request could ever have been READY again.** Observed on this
    script's own pull request at 2026-09-01T01:55:03Z, on the fifth round.

    ⭐ The reasoning that produced the bug was right about *who posts requests* --
    a human driving the gate, never the bot -- and wrong about what else contains
    the phrase. **Documentation of a trigger is not a trigger**, and the author is
    what separates them.

    ⚠️ A HUMAN comment carrying the phrase is a request even when it is meant as
    prose, and that is not a flaw here: the bot matches a substring too, so such a
    comment really does start a round. It is why CONTRIBUTING forbids the phrase
    in prose at all.
    """
    stamps = [
        str(c.get("created_at") or "")
        for c in comments
        if TRIGGER in (c.get("body") or "").lower()
        and not _is_bot((c.get("user") or {}).get("login"))
    ]
    # ⛔ Any unreadable one, not only the newest: the newest is what T needs, and
    # a request that cannot be ordered cannot be shown not to be the newest.
    if any(not stamp for stamp in stamps):
        return None
    return max(stamps, default="")


def _both_triggers(first: str | None, second: str | None) -> str | None:
    """The request across TWO reads. ⛔ **T never goes BACKWARDS between them.**

    ⚠️ A request present while gathering and gone from the final read leaves
    ``_request_arrived_mid_sweep`` silent -- that rule fires on a request moving
    FORWARD -- so the final read alone would drop T back to the open time and
    make the previous round's clean comment read as this round's verdict.

    ⭐ Max for the movable term, ``None`` propagating for the unreadable one:
    exactly ``_both_timelines``, on the other thing that starts a round.
    """
    if first is None or second is None:
        return None
    return max(first, second)


def _still_current(comments: list[dict[str, Any]], began: str) -> list[dict[str, Any]]:
    """Those comments that POSTDATE the start of the current round.

    ⛔ Lexicographic comparison is correct here and only here: every timestamp
    GitHub returns is the same fixed-width UTC format, so string order is time
    order. It would not be for mixed offsets, and nothing in this file has any.

    ⛔ **``began`` is T, not the trigger comment.** It was the trigger alone for
    this function's whole life, and #183's input walked through the gap: a
    mark-ready starts a round and leaves no comment, so the previous round's
    clean verdict still postdated the last request and was still accepted.

    ⚠️ **Never call this with ``""``.** Every timestamp sorts after it, so every
    comment would read as current -- absence of evidence becoming permission.
    ``_round_start`` returns ``""`` to say T is unknown, and the caller refuses
    instead of comparing. The empty case survives here only as arithmetic; it is
    not a mode of operation.
    """
    return [c for c in comments if str(c.get("created_at") or "") > began]


def _is_bot(login: object) -> bool:
    """⛔ Either spelling. See ``BOT_LOGINS``."""
    return str(login or "") in BOT_LOGINS


def _same_row(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Are these two reads showing the SAME row?

    ⛔ ``id`` when either row carries one, whole-row equality otherwise. Equality
    alone is defeated by any field the two reads render differently; ``id`` alone
    is defeated by a row that has none.
    """
    if one.get("id") is not None or other.get("id") is not None:
        return one.get("id") == other.get("id")
    return one == other


def _still_granted(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Rows the SECOND read still shows. ⛔ **Granting evidence must SURVIVE to the verdict.**

    ⚠️ Named input: the bot posts a clean comment naming this head at 09:07, the
    sweep reads it, the comment is DELETED before the verdict is pronounced, and
    the final read lacks it. Built from the first read alone, that comment still
    granted -- READY over a body no longer carrying a clean signal.

    ⭐ And the remedy is CONFIRMATION, not replacement. Taking the second read
    alone would let a clean comment that arrived mid-sweep grant a verdict on
    evidence gathered before it: the checks, the threads and the head were all
    read before it existed. The intersection refuses both ways.

    ⛔ **Identity PAIRS the rows; it does not judge them.** ``_same_row``
    compares ``id``, which survives an edit that destroys content -- so the
    caller filters BOTH arguments through ``_clean_verdicts`` first. This helper
    sees only what it is given, and that is deliberate: it holds one rule.
    """
    return [row for row in first if any(_same_row(row, other) for other in second)]


def _ready_for_review(meta: dict[str, Any]) -> list[str] | None:
    """When this pull request was marked ready, or ``None`` if that cannot be read.

    ⛔ **``None`` and ``[]`` are DIFFERENT answers and the caller must not merge
    them.** ``[]`` means the pull request was never a draft, which is the common
    case and a real answer. ``None`` means the read did not say -- an absent key,
    a node that is not an object, a node with no timestamp -- and an unanswerable
    question is refused rather than skipped.

    ⚠️ **A missing event would leave T too EARLY**, which is the permissive
    direction: the PREVIOUS round's clean comment would then postdate it and read
    as this round's verdict. That is this project's most-recorded defect, an
    empty read presented as an absence.
    """
    timeline = meta.get("timelineItems")
    if not isinstance(timeline, dict):
        return None
    nodes = timeline.get("nodes")
    if not isinstance(nodes, list):
        return None
    stamps: list[str] = []
    for node in nodes:
        when = str(node.get("createdAt") or "") if isinstance(node, dict) else ""
        if not when:
            return None
        stamps.append(when)
    return stamps


def _both_timelines(first: list[str] | None, second: list[str] | None) -> list[str] | None:
    """Round-start instants across TWO reads. ⛔ **Either read unreadable is unreadable.**

    ⚠️ T is built from this, and T going BACKWARDS between two reads is the
    permissive direction: a mark-ready observed while gathering and missing from
    the final answer would drop T back to the open time, and the clean comment
    from the round before would postdate it and read as this round's verdict.

    ⭐ Union rather than a regression check: every term here can only ever move
    T later, and later is stricter. There is nothing to trade, so keeping both
    reads needs no new failure path.
    """
    if first is None or second is None:
        return None
    return sorted(set(first) | set(second))


def _round_began(created_at: str, latest_trigger: str, ready_events: list[str]) -> str:
    """T -- the instant the CURRENT round began. ⛔ **Three triggers, not one.**

    ⚠️ The bot names all three in the footer of every verdict it posts: opening a
    pull request for review, marking a draft as ready, and commenting the phrase.
    ``_latest_request`` watches the third only, and #183 records the second as a
    door the rule does not watch: a clean signal, a conversion back to draft, a
    mark-ready, and the OLD signal still postdates the last comment.

    ⭐ Lexicographic max for the same reason ``_still_current`` compares that way:
    every timestamp here is fixed-width UTC, so string order is time order.

    ⚠️ ``latest_trigger`` is ``""`` when no round was ever asked for, and ``""``
    sorts before every timestamp -- so it loses, which is what it should do.
    **``created_at`` is the floor and it is never empty on a real read**;
    ``_round_start`` refuses outright if it is, because a T of ``""`` would let
    every clean comment ever posted read as this round's verdict.
    """
    return max([created_at, latest_trigger, *ready_events])


def _round_start(
    created_at: str, latest_trigger: str | None, ready_events: list[str] | None
) -> str:
    """T, or ``""`` when it cannot be computed.

    ⛔ **``""`` is a refusal and never a floor.** Callers must not compare
    against it: ``""`` sorts before every timestamp, so every artifact ever
    published would postdate it -- absence of evidence becoming permission one
    more time.

    ⭐ The clean comment is judged against the instant this returns, and against
    nothing else. A second answer to *when did this round begin* is this
    project's most-recorded defect class, so there is exactly one.

    ⚠️ **Two of the three terms have an unreadable answer and BOTH refuse here.**
    ``ready_events is None`` is an unreadable timeline; ``latest_trigger is
    None`` is a request this read cannot place. Either left to collapse into a
    falsy value loses the ``max`` to ``created_at``, and T reads as the open
    time -- which is the fallback that accepted the previous round's verdict.
    """
    if not created_at or ready_events is None or latest_trigger is None:
        return ""
    return _round_began(created_at, latest_trigger, ready_events)


def _request_arrived_mid_sweep(before: str | None, after: str | None) -> str:
    """A reason, or ``""``. ⛔ **The trigger is evidence, and evidence goes stale.**

    ⚠️ The latest request is read while gathering, and the verdict is pronounced
    several calls later -- thread pagination and the checks query both run in
    between. A round requested inside that gap was invisible, so the earlier
    clean comment stayed accepted and READY printed while a new round was
    starting. **That is the twelfth defect again, one level up:** the rule was
    applied to a snapshot instead of to the state at the verdict.

    ⭐ So this is the third mid-sweep comparison, and they are all one shape --
    head, base, and now the request -- each captured while gathering and checked
    against the final moment.

    ⚠️ **The window is not zero and cannot be.** A request landing after the
    final read is still missed; that residual is the one the ruling on #179
    accepted explicitly. What changes is its size: from the whole sweep down to
    one call, which is the same bound every other field here gets.
    """
    # ⛔ **``None`` blocks in its own words**, and it is the SECOND condition an
    # unreadable request meets: ``_round_start`` already refuses T for it. Two
    # independent branches rather than one, because a single one standing between
    # an unanswered read and a READY is what this file exists to avoid -- and
    # because *T could not be computed* does not tell the reader which read was
    # unreadable, where this does.
    if before is None or after is None:
        return (
            "a review round was requested in a comment whose timestamp this read did not "
            "carry, so nothing can show which round the clean verdict above belongs to"
        )
    if after and after != before:
        return (
            f"a review round was requested while this sweep ran ({after}) -- the "
            "clean verdict above is about the round before it"
        )
    return ""


def _round_count(bot_reviews: list[dict[str, Any]], bot_conversation: list[dict[str, Any]]) -> int:
    """How many rounds the bot has actually published.

    ⛔ **A CLEAN round creates no review object.** This file says so a few
    hundred lines up -- the clean signal arrives as a conversation comment plus a
    reaction -- and then counted review objects anyway, so every clean round was
    invisible to the backstop. **Measured on merged pull requests: #164 counted
    10 where 12 rounds had run, #159 counted 7 of 8.** #175 counted 8 of 8, which
    is exactly why it looked right: not one of its rounds was ever clean.

    ⭐ **The discriminator is the bot's own marker, not the clean phrases.**
    Every artifact it publishes -- findings review and clean comment alike --
    carries ``Reviewed commit:``. Measured: 10 of 10 review bodies on #164. So one
    rule covers both object types, and it does not go stale when the wording of a
    clean verdict changes.

    ⚠️ **A review object counts even without the marker.** A review IS a round;
    a conversation comment is only a round if it announces one. The asymmetry is
    deliberate -- undercounting is the failure this repairs, so the side that can
    only ever undercount is the side that gets the benefit of the doubt.

    ⚠️ **If one round ever published BOTH, this counts two.** That overcounts
    toward surfacing the backstop earlier, which for an advisory is the harmless
    direction: it costs a conversation with the owner, where undercounting costs
    another #175.
    """
    announced = [c for c in bot_conversation if ROUND_MARKER in (c.get("body") or "").lower()]
    return len(bot_reviews) + len(announced)


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
    # ⛔ ``createdAt`` and the ready-for-review events ride here rather than in
    # reads of their own, for the reason the docstring gives: the facts a verdict
    # rests on must come back in ONE answer or they can disagree about when they
    # were true. They are deliberately NOT in ``METADATA_FIELDS`` -- ``_judge``
    # does not judge them; the clean comment is refused without them.
    #
    # ⚠️ ``headRefName`` rode here too, for the branch-activity read that tied a
    # bare 👍 to a head. #233 withdrew that grant, so nothing asks a branch about
    # its own quiet any more and the field is gone with its only consumer.
    #
    # ⚠️ ``last:100``, never ``first``. ``first`` anchors at the OLDEST end, so on
    # a long timeline it would return the earliest events and miss the newest --
    # which is the only one T needs. Anchored at the newest end, the maximum over
    # what comes back is the true maximum whatever the page size.
    query = (
        '{repository(owner:"randyjreid",name:"gramps-live-api")'
        f"{{pullRequest(number:{pull})"
        "{state isDraft headRefOid baseRefOid mergeable mergeStateStatus "
        "createdAt baseRef{name target{oid}} "
        "timelineItems(itemTypes:[READY_FOR_REVIEW_EVENT], last:100)"
        "{nodes{... on ReadyForReviewEvent{createdAt}}}}}}"
    )
    graph = json.loads(_gh("api", "graphql", "-f", f"query={query}") or "{}")
    pull_request = ((graph.get("data") or {}).get("repository") or {}).get("pullRequest")
    if not pull_request:
        raise RuntimeError(f"no pull request #{pull} in the graph response")
    return pull_request


def _base_tip(meta: dict[str, Any]) -> str:
    """The LIVE tip of the base branch, as of this read.

    ⛔ Not ``baseRefOid``. **They are different facts and the difference is
    measurable:** across five merged pull requests ``baseRefOid`` read
    ``f385d3d``, ``9c31e67``, ``9e14bca``, ``a59df02``, ``a59df02`` -- each frozen
    near its own pull request -- while this value read ``a3ba58a`` for every one
    of them, the live tip.
    """
    return str(((meta.get("baseRef") or {}).get("target") or {}).get("oid") or "")


def _judge(meta: dict[str, Any], expected_head: str, expected_base_tip: str) -> list[str]:
    """The verdict on one metadata snapshot. ⛔ **Every field required.**

    ⚠️ A field that is absent is not a field that is fine. GitHub omits what it
    cannot answer, and ``.get()`` returning ``None`` compared against a good
    value would simply read as *not good* -- which happens to be right here, but
    only by luck. **It is asserted instead**, so a schema change is a loud error
    rather than a quiet verdict.

    ⭐ **Two DIFFERENT questions are asked about the base, and this file used to
    ask only one.** ``baseRefOid`` against the live tip asks *is this branch up to
    date?* -- finding 9. ``expected_base_tip`` against the live tip asks *did the
    base move WHILE the evidence was being gathered?*, which is the same question
    already asked of the head via ``expected_head``.

    ⚠️ **The head was compared against its provisional value and the base was
    not.** That asymmetry was the gap: the evidence -- a verdict and a green
    matrix -- is about code sitting on a particular base, and nothing checked
    that it was still the same base when the verdict was pronounced.
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
    live_base = _base_tip(meta)
    if not live_base:
        failures.append("the base branch tip could not be read")
    else:
        if live_base != str(meta["baseRefOid"]):
            failures.append(
                f"base has moved since this head was verified ({str(meta['baseRefOid'])[:12]} "
                f"-> {live_base[:12]}) -- the tests that passed ran under different code"
            )
        # ⛔ **An unanswerable check is REFUSED, never skipped.**
        #
        # ⚠️ This read ``if expected_base_tip and ...``, so a provisional response
        # with a null ``baseRef.target`` -- a partial answer, or a base ref
        # deleted and recreated mid-sweep -- silently disabled the comparison and
        # left READY printable. **The condition was true for a reason unrelated
        # to the property it names**, which is this project's most-repeated
        # defect, and ``scripts/hooks/pre-push`` already answers it the right way:
        # a gate that cannot see what it is judging must not wave it through.
        if not expected_base_tip:
            failures.append(
                "the base tip was not captured when the evidence was gathered, so "
                "nothing can show the verdict and checks apply to the base below"
            )
        elif live_base != expected_base_tip:
            failures.append(
                f"the base moved WHILE this sweep ran ({expected_base_tip[:12]} -> "
                f"{live_base[:12]}) -- the verdict and checks above are about the old base"
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
    # ⛔ Kept so the FINAL read can be compared against it, exactly as the head is.
    base_tip_when_gathering = _base_tip(provisional)
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
    # ⛔ ``--paginate``, and it stays load-bearing even though a reaction now
    # grants nothing. The report must still know a bare 👍 EXISTS in order to say
    # so: a 👍 stranded on a later page would silently degrade the actionable
    # refusal -- *the bot passed and left no comment naming this head, re-trigger
    # it* -- into the generic one, which tells the reader nothing they can act on.
    reactions = _json("api", f"repos/{REPOSITORY}/issues/{pull}/reactions", "--paginate")
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
    #
    # ⛔ **A reaction carries no commit_id, so it is EVIDENCE and never a
    # verdict.** #233 built a grant on one anyway, tying it to a head through the
    # branch's arrival log; that path produced eleven false READYs across three
    # review rounds and was withdrawn. What is counted here is counted so the
    # refusal at step 8 can NAME it -- *the bot passed and left no comment naming
    # this head* is actionable where *no clean verdict was found* is not.
    #
    # ⛔ **Counted, not classified.** An earlier version split these into fresh
    # and stale on the head's COMMITTER DATE -- the comparison the paragraph
    # above calls unsound. Nothing here decides freshness, because nothing here
    # decides anything.
    bot_thumbs = [r for r in by_bot(reactions) if r.get("content") == "+1"]
    fresh_conversation = [
        c for c in by_bot(conversation) if head_when and c.get("created_at", "") > head_when
    ]
    clean_comments = _clean_verdicts(conversation, head)

    # ⛔ **A clean verdict must postdate THE ROUND IT CLAIMS TO BE ABOUT.**
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
    # round it claims to be about.
    #
    # ⛔ **And that round is T, not the trigger comment. RECORDED SCOPE CHANGE,
    # owner approved** -- see `docs/plans/pr-ready-thumb.plan.md`. The trigger is
    # only ONE of the three things that start a round, so #183's input still
    # produced a false READY through this path: a clean comment naming head H, a
    # conversion back to draft, a mark-ready on the same head, no push, and the
    # previous round's verdict still accepted.
    #
    # ⚠️ **The comparison itself happens at step 8**, because T is not known
    # until the final reads. What is computed here is evidence.
    latest_trigger = _latest_request(conversation)

    print("  2. bot verdict on head  :")
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
        f"       clean verdict on head: {len(clean_comments)}"
        + (f"  ({clean_comments[-1].get('created_at')})" if clean_comments else "")
    )
    print(
        f"       bot +1 on body     : {len(bot_thumbs)}"
        + (f"  ({bot_thumbs[-1].get('created_at')})" if bot_thumbs else "")
        + "  (evidence, never a verdict)"
    )

    print(
        f"       last round requested: {_said(latest_trigger, '(never -- automatic review only)')}"
    )

    # ⛔ **The verdict on the clean signal is pronounced at step 8, not here.**
    # The reads above are several calls old by the time this returns, so what is
    # printed here is evidence; what decides is read again at the end.

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
    rounds = _round_count(by_bot(reviews), by_bot(conversation))
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
    failures.extend(_judge(final, head, base_tip_when_gathering))

    # -- 8. the clean verdict, on what the bot has published BY NOW -----------
    #
    # ⛔ **ONE endpoint is re-read here, and it is the one the grant rests on.**
    #
    # ⚠️ The reads at step 2 are a dozen calls old by now, and the clean comment
    # was built from that first read alone: a comment deleted -- or edited out of
    # a clean verdict -- inside that window still granted. So the conversation is
    # asked again and the two answers are intersected.
    #
    # ⚠️ **The reviews and inline endpoints were re-read here too, and they are
    # not any more.** Their second answer fed one consumer, ``_both_reads`` into
    # the bare-👍 judgement, whose premise was that the bot had said nothing since
    # T. #233 withdrew that judgement; nothing else ever read those answers, so
    # two ``gh`` calls a report were being spent on a value no branch consulted.
    # Removed with their consumer rather than left behind to read as load-bearing.
    final_conversation = _json("api", f"repos/{REPOSITORY}/issues/{pull}/comments", "--paginate")
    assert isinstance(final_conversation, list)

    # ⛔ The request is evidence too, and it was read several calls ago.
    trigger_now = _latest_request(final_conversation)
    print(f"       last request now   : {_said(trigger_now, '(none)')}")
    moved = _request_arrived_mid_sweep(latest_trigger, trigger_now)
    if moved:
        failures.append(moved)

    # ⛔ **T NEVER GOES BACKWARDS between two reads**, and both of its movable
    # terms could take it there. A trigger that vanishes from the final
    # conversation leaves ``_request_arrived_mid_sweep`` silent -- that rule
    # fires on a request moving FORWARD -- and a ready-for-review event missing
    # from the final timeline drops T to the open time. Either regression makes
    # the PREVIOUS round's clean comment read as this round's verdict.
    began_trigger = _both_triggers(latest_trigger, trigger_now)
    seen_ready = _both_timelines(_ready_for_review(provisional), _ready_for_review(final))

    # ⛔ **T, once**, and the clean comment is judged against it rather than
    # against the trigger alone. ``""`` is a refusal here: the comment must not
    # fall back to the old comparison when the timeline cannot be read, because
    # an unreadable timeline is exactly the input that produced the defect -- a
    # fallback would be it returning under a different name.
    began = _round_start(str(final.get("createdAt") or ""), began_trigger, seen_ready)
    print(f"       round began at     : {began or '(UNREADABLE -- nothing can be placed in it)'}")

    # ⛔ **The clean comment is confirmed against the FINAL read.**
    # ``clean_comments`` came from the first conversation read alone.
    #
    # ⚠️ Named input: the bot posts a clean comment naming this head at 09:07,
    # this sweep reads it, the comment is DELETED before the verdict, the final
    # read lacks it, every other gate is clean -- and READY printed over a body
    # that no longer carries a clean signal.
    #
    # ⭐ Intersection, not replacement -- ``_still_granted``. Taking the final
    # read alone would let a clean comment ARRIVING mid-sweep grant a verdict on
    # evidence gathered before it: the checks, the threads and the head were all
    # read before it existed.
    #
    # ⛔ **``_clean_verdicts`` over the FINAL read too, not ``by_bot`` alone.**
    #
    # ⚠️ ``_same_row`` compares ``id``, and identity survives an edit that
    # destroys content. With the second read unfiltered, a comment edited from a
    # clean verdict into a findings report -- same id, new body -- still matched,
    # and the FIRST read's row granted. **Confirmation is on content; identity
    # only pairs the rows.**
    standing_clean = _still_granted(clean_comments, _clean_verdicts(final_conversation, head))
    withdrawn_clean = [c for c in clean_comments if c not in standing_clean]
    if withdrawn_clean:
        print(
            f"       WITHDRAWN clean     : {len(withdrawn_clean)}"
            f"  ({withdrawn_clean[-1].get('created_at')}"
            " -- deleted, or edited out of a clean verdict, before the final read)"
        )

    accepted_clean = _still_current(standing_clean, began) if began else []
    superseded_clean = [c for c in standing_clean if c not in accepted_clean]
    if superseded_clean:
        print(
            f"       SUPERSEDED clean    : {len(superseded_clean)}"
            f"  ({superseded_clean[-1].get('created_at')} <= the round start above)"
        )

    # ⛔ **The four branches are EXHAUSTIVE over an empty ``accepted_clean``**, and
    # that is what makes the one ``return True`` below checkable: no clean comment
    # at all, none surviving the final read, T uncomputable, all of them
    # superseded by T. Whichever holds, ``failures`` gains an entry.
    #
    # ⚠️ **Each names the input it is true of.** A reason true of a different
    # input is evidence nobody can act on -- a withdrawn verdict does not predate
    # anything, and a T that cannot be computed is not fixed by re-triggering,
    # which is why the last sentence is not appended to that one.
    if not accepted_clean:
        if not clean_comments:
            # ⛔ **The bare-👍 case, said in ONE sentence rather than two.** The
            # generic reason plus a separate *the +1 is not a clean verdict* line
            # left the reader with two half-answers; this branch is the whole one.
            if bot_thumbs:
                failures.append(
                    f"the bot left a +1 on the pull request body at "
                    f"{bot_thumbs[-1].get('created_at')} and no comment naming this head: "
                    f"a reaction carries no commit id, so nothing ties it to {head[:12]}. "
                    "Re-trigger the bot on this head so it publishes a comment naming the "
                    "commit it reviewed."
                )
            else:
                failures.append(
                    "no CLEAN verdict naming this head -- the bot's clean comment quotes "
                    "the commit it reviewed, and none quoting this one was found. "
                    "Re-trigger the bot on this head."
                )
        elif not standing_clean:
            failures.append(
                "the CLEAN verdict naming this head no longer stands -- it was there when "
                "this sweep began, and the final read shows it deleted or edited into "
                "something that is no longer a clean verdict on this head. "
                "Re-trigger the bot on this head."
            )
        elif not began:
            failures.append(
                "a CLEAN verdict names this head, but the start of the current round "
                "could not be computed, so nothing can show the verdict belongs to it"
            )
        else:
            failures.append(
                f"the CLEAN verdict predates the start of the current round ({began}) -- "
                "the round was opened, re-triggered or marked ready after that verdict, "
                "so it is about an earlier one. Re-trigger the bot on this head."
            )

    if failures:
        print("  RESULT: NOT the owner's click")
        for reason in failures:
            print(f"     - {reason}")
        return False
    print("  RESULT: READY -- every check above passed")
    return True


def main(argv: list[str]) -> int:
    # ⛔ **#219: this tool's output encoding is its OWN, not the console's.**
    #
    # ⚠️ It printed three sections and then died on ``⚠`` -- and the reason that
    # mattered was in the part that never printed. A crash reporting *the check
    # could not complete* is indistinguishable at a glance from a genuine
    # NOT-READY, and the exit code is 1 either way.
    #
    # ⭐ Not by removing the glyphs: they carry meaning here, and the next one
    # added would reintroduce this. ``errors="replace"`` so a codec that still
    # cannot render something loses that character rather than the verdict.
    #
    # ⚠️ **stderr too, and it is not symmetry for its own sake.** A traceback
    # quotes the source line it failed on, and the lines in this file carry these
    # same glyphs -- so a crash could die again while reporting itself, on the
    # stream that carries the only remaining evidence.
    #
    # ⚠️ ``hasattr`` because a captured stream need not be a text wrapper.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
