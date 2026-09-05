# Plan: #233, accept a fresh bare 👍 as CLEAN in `pr_ready.py` (and #219's encoding crash)

## Context

`scripts/pr_ready.py` is the merge-readiness instrument. It requires a clean-phrase
conversation comment naming the reviewed commit as the only acceptable clean verdict.
On PR #232 the bot marked the head clean with a bare 👍 on the PR body and wrote no
comment at all; the script counted the 👍, printed it, and still said NOT READY. The
gate definition (workflow contract, PR-bot gate §5) says clean is EITHER a 👍 from the
bot OR a review naming the final head declaring no issues. The comment is sufficient,
not necessary. Issue #233 records the case; #219 records a second defect in the same
script (crashes rendering its own verdict on a cp1252 console).

Files that change: `scripts/pr_ready.py`, `tests/unit/test_pr_ready.py`. Nothing else.

## The two clean shapes

Shape A (exists today, unchanged): a bot conversation comment matching a clean phrase
AND naming the head (`_names_the_head`) AND postdating the latest trigger
(`_still_current`). This is `accepted_clean` at `scripts/pr_ready.py:503`.

Shape B (new): a bare bot 👍 on the PR body, accepted only when ALL of:

Let T = the latest of THREE instants, not two: the PR's `createdAt`, the latest human
trigger comment's `created_at`, and **the latest ready-for-review event's timestamp**
(all fixed-width UTC strings; lexicographic max, same rule as `_still_current`). T is
the instant the current round began.

⛔ **The third term is a review-round FIX, and it closes #183.** Marking a draft
ready is one of the three things that starts a bot round, which this repository's own
test fixture quotes from the bot's comment, but it moves neither `createdAt` nor
`_latest_request`. Without the third term a pull request that received a bare clean 👍,
was converted back to draft, and was marked ready again on the same head would satisfy
shape B with the PREVIOUS round's reaction and report READY before the new round
published anything. #183 records this today as a missed trigger; adding shape B without
the third term would promote it into a false pass. Close #183 when this lands.

1. A bot reaction with `content == "+1"` on the PR body has `created_at > T`.
2. The head has not moved since T, shown from the repository activity log
   (see next section): a row with `after == headRefOid` exists, and NO row of any
   `activity_type` has `timestamp > T`. An empty or unreadable log REFUSES
   (fail closed; an empty read is not an absence).
3. The bot has published nothing since T: no bot review with `submitted_at > T`,
   no bot inline comment with `created_at > T`, no bot conversation comment with
   `created_at > T`. If the bot spoke, its artifacts govern, not the reaction.
   ⛔ **All THREE bot endpoints are re-read after the freshness computation
and before the verdict, not conversation alone. Review-round FIX.** The first draft
re-checked only conversation comments and recorded the reviews and inline residual in a
code comment. That residual is not narrow: the bot can submit a review carrying a
finding at any point between the initial reads and the verdict, with the head, the
checks and the conversation all unchanged, and shape B would then report READY over a
review nobody has read. The window is most of the sweep, not the final call. So reviews,
inline comments and conversation comments are all re-fetched at the same point, and any
bot artifact newer than T refuses.

The verdict change: the failure at `scripts/pr_ready.py:542-551` fires only when
NEITHER shape holds. When shape B refuses despite a bot 👍 existing, its refusal
reason prints so the reader sees why the reaction did not count.

## Why the stale-👍 refusal cannot be swallowed

A 👍 followed by a push: the sweep's head is then the new SHA, whose activity
arrival row has `timestamp > T`, and condition 2 refuses twice over (a row after T
exists, and the arrival row postdates T). This does not rest on commit committer
dates, which the file already records as unsound (a commit created before a verdict
and pushed after has an old committer date; `scripts/pr_ready.py:456-461`). If the
activity log cannot show the head's arrival, shape B refuses rather than assumes.
A 👍 predating T (from a round before the latest trigger) fails condition 1.
Force pushes, and any ref event at all after T, fail condition 2.

## The data, field by field

- `createdAt` and `headRefName`: added to the GraphQL query in `_metadata`
  (`scripts/pr_ready.py:303-307`). Not added to `METADATA_FIELDS` (those are the
  judged fields); if either is absent the pure function refuses shape B.
- Latest trigger: existing `_latest_request(conversation)` result, already computed.
- Activity log: `gh api "repos/randyjreid/gramps-live-api/activity?ref=refs/heads/{headRefName}&per_page=100" --paginate`
  ⛔ **This hard codes THIS repository, and for a fork's pull request the branch
  lives in the fork, so the read finds no row and shape B refuses. FILED AS #235, NOT FIXED
  HERE, by owner decision.** The direction is safe, a stalled merge rather than an unreviewed
  one, and the fix needs to establish first whether `gh` can read a fork's activity log at all.
  Measured for the record: this repository has had three cross-repository pull requests, #209,
  #220 and #221, all from one external fork, so the case is real and not hypothetical.
  ⚠️ **The build must not relax the failing direction to make forks work.** An
  unreadable activity log stays a refusal.
  through the existing `_json`. Rows carry `timestamp` (ISO UTC, fixed width),
  `before`, `after`, `activity_type`, `actor`. Probed 2026-09-05 against PR #232's
  ref: one `branch_creation` row with `after` = the head, timestamp 2 seconds before
  the PR opened, then nothing until the post-merge `branch_deletion`. The recorded
  facts of #232 (👍 at 11:53:44Z > createdAt 11:48:04Z, bot otherwise silent) satisfy
  shape B exactly.
- Reactions, reviews, inline, conversation: the reads at `scripts/pr_ready.py:443-446`,
  already bot-filtered by `by_bot`.

⚠️ **RECORDED SCOPE CHANGE, owner approved: the reactions read gains `--paginate`.**
  Line 446 reads reactions without it while lines 444 and 445 read inline and conversation
  comments with it. Today that is latent, because no reaction is judged. This change makes
  reactions load-bearing, and a pull request body with more than one page of them would hide
  the qualifying 👍 on a later page, reporting NOT READY over a clean signal. One token, in a
  file this change already opens. ⛔ **Recorded here rather than slipped in**, so
  the diff carries no line whose reason is not written down.

## Where the judgement lives

The test file's thesis holds: the decision is a pure function, the API feeds it.
Add one pure function (suggested name `_bare_thumb_clean`) taking the bot-filtered
reactions, reviews, inline and conversation rows, the activity rows, the head SHA,
the PR `createdAt`, and the latest trigger; returning the accepted reaction plus a
shape label on success, or a refusal reason string. `_report` calls it and prints
either `clean shape: comment naming head` or `clean shape: bare +1, head unmoved`
on READY, so the two shapes are distinguishable in output.

## #219: in scope, recommended

Two lines in the same file: at the top of `main()`, reconfigure `sys.stdout` to
UTF-8 with `errors="replace"` (guarded by `hasattr` for safety), per the bounded
fix #219 itself states. Argument for bundling: the trigger is use-derived and
recorded (it bit the merge gate on PR #210); and unfixed it hides exactly the
output this change adds, since a NOT READY verdict containing the backstop's
U+26A0 dies before its reasons print on a default Windows console, which is the
console this instrument is read on. The glyphs stay; only the stream changes.
The "check other scripts" tail of #219 is out of scope here.

## Tests (all values invented; no real Gramps data)

New tests call the pure function directly, fixture dicts like the existing ones:

1. The #232 shape: 👍 postdating PR open, arrival row before open, no other rows,
   bot otherwise silent: ACCEPTED, labeled as the bare-👍 shape.
2. 👍 then a later push (activity row with `timestamp > T`): REFUSED.
3. 👍 then a later bot conversation comment: REFUSED. Same for a later bot review.
4. 👍 with `created_at <= T` (stale, from before the latest trigger): REFUSED.
5. Empty activity log, or no row with `after == head`: REFUSED.
6. Trigger later than open: T moves to the trigger; a 👍 between open and trigger
   REFUSED, a 👍 after the trigger with head unmoved ACCEPTED.
7. Clean-phrase path unchanged: every existing test passes unedited (protected
   assertions; additions beside them only), plus one test that a clean comment
   naming the head still accepts even though it makes shape B refuse.
8. #219: subprocess runs `python scripts/pr_ready.py` with no arguments and
   `PYTHONIOENCODING=cp1252` in the environment (portable; the cp1252 codec exists
   on every platform, and the no-argument path makes no API call). Assert exit
   code 2 and stdout decoding as UTF-8 containing the doc's glyphs. Without the
   fix this run dies with UnicodeEncodeError on any OS.

## Acceptance criteria

- `pytest tests/unit/test_pr_ready.py` green, containing tests 1-8 above.
- No existing assertion in that file edited.
- The pure function returns a shape label and the tests assert both labels.
- The project's own gates (ruff, mypy, full suite) green.
- Demo, delivery-mode: after the fix's own PR draws a bare 👍 from the bot,
  `python scripts/pr_ready.py <that PR>` on a plain Windows console with no
  `PYTHONIOENCODING` prints READY naming the bare-👍 shape. The instrument
  demonstrates itself on its own pull request.

## ⛔ Plan review dispositions, owner ruled 2026-09-05

One Codex plan review round raised four findings, each self-labelled BLOCKING with a named
input and a named wrong output. All four are genuine. The owner sorted them by direction of
failure, since this instrument exists to refuse.

### Fixed in this plan: the two that produce a false READY

> **[P1] Include ready-for-review events in T.** BLOCKING. Input: a PR previously received a
> bare clean 👍, is converted back to draft, and is then marked ready again on the same head;
> run the script before the newly triggered review publishes anything. Marking a draft ready
> is a bot-review trigger already recorded in `tests/unit/test_pr_ready.py:74-78`, but it
> changes neither `createdAt` nor `_latest_request`, so the old reaction satisfies Shape B and
> the script outputs READY for the prior round. T must include the latest ready-for-review
> event.

> **[P1] Re-read bot artifacts before accepting Shape B.** BLOCKING. Input: the initial reads
> see a qualifying 👍 and no bot review or inline comment, then after those reads the bot
> submits a review with a finding while the head, checks, and conversation remain unchanged.
> Because reviews and inline comments are not refreshed, `final_conversation` cannot reveal
> that review and the script outputs READY even though condition 3 requires the bot artifact
> to govern. This window spans most of the sweep, not merely the final-call residual.

Both are fixed above. ⭐ **They share a shape worth naming: each makes the
instrument report a verdict for the WRONG ROUND**, one by missing the instant a new round
began, the other by missing what the current round said.

### Fixed cheaply, as a recorded scope change

> **[P2] Paginate reactions before evaluating Shape B.** BLOCKING. Input: a PR body has more
> than the REST endpoint's default page of reactions and the qualifying bot `+1` is on a later
> page. The existing reactions call at `scripts/pr_ready.py:446` lacks `--paginate`, and this
> plan reuses that read, so the pure function receives no bot reaction and the script outputs
> NOT READY despite the fresh clean signal.

One token, in a file this change already opens, and recorded above where the read is described
so the scope change is written down rather than smuggled.

### Filed, not fixed: #235

> **[P2] Query activity from the pull request's head repository.** BLOCKING. Input: a
> fork-based PR has an unchanged source head and a fresh bare bot 👍. `headRefName` names a
> branch in the fork, but this endpoint always queries `randyjreid/gramps-live-api`, so the
> read has no matching `after == headRefOid` row and the script outputs NOT READY instead of
> READY. The metadata must include the head repository identity and query activity there; fork
> PRs are explicitly supported elsewhere in `.github/workflows/ci.yml:371-380`.

Filed as **#235** with the finding quoted. Safe direction, and it needs to establish whether
`gh` reaches a fork's activity log at all before anything is written.

### Accepted: #219 stays in scope

The plan's own recommendation to fold in the encoding crash is accepted. A script that dies
on a cp1252 console cannot print the verdict this change adds.

### Depth

**Codex review rounds only. No Fable `/code-review` pass.** This is a script, not a write
surface. Contrast #228, which is the write surface and takes both.

## Out of scope

- Counting a bare-👍 clean round in `_round_count`: such a round creates no review
  object and no marker comment, so the backstop undercounts it. Real, but a
  different property than #233 names. File as its own issue at build time, quoted.
- The sweep of other `scripts/*.py` for the same encoding defect (#219's tail).
- The conductor's scratch watcher named in #233; it lives outside this repository.
- Fork pull requests whose branch activity lives in the fork. Filed as #235.
- Any widening: reactions other than `+1`, reactions from non-bot users, reactions
  anywhere but the PR body all stay meaningless.

## Questions left to the build, numbered

1. Exact signature and return type of the pure function (reason string vs tuple).
2. Whether the display-only `fresh +1 / STALE +1` lines at
   `scripts/pr_ready.py:521-533` keep their committer-date split or move to the
   T-based one. The verdict uses T either way; this is presentation.
3. Whether the activity read happens once up front beside the other reads at
   `scripts/pr_ready.py:443-446` or lazily only when a bot 👍 exists. One extra
   read either way.
4. Whether `sys.stderr` gets the same reconfigure as `sys.stdout` for #219.
