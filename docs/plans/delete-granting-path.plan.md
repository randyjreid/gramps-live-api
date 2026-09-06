# Plan: delete the granting path from `scripts/pr_ready.py` (#233)

Branch `pr-ready-thumb`, head `48b8e41`.

> ⛔ **This line once carried an absolute drive-letter path to a working copy,
> and `pii_guard` reported it.** It arrived with the plan-approval commit and was
> the only finding the guard raised against this repository's tree.
>
> ⭐ **The branch has since been rebuilt, and no commit it publishes contains
> such a path.** Measured at this head rather than asserted: `git log -S` over
> everything reachable from `HEAD` -- 700 commits -- finds none, the same search
> across all refs finds two as a positive control, and neither of those two is an
> ancestor of this head. The personal-data suite passes here, 33 tests,
> `test_every_commit_this_repository_publishes_is_clean` among them.
>
> ⚠️ **The two commits still exist**, on a local backup branch with no upstream
> that is contained in no remote-tracking ref. Nothing pushes them, and nothing
> in this pull request publishes them. Said plainly because *the string is gone*
> and *the string is unreachable from what we publish* are different claims, and
> only the second one is true.
>
> ⚠️ Section 7's third bullet -- `_names_the_head` matching an unanchored
> substring, recorded there as out of scope and left to be filed -- was not
> filed. It was raised as a blocking review finding on this branch instead and
> **fixed on this head**: both the head match and the clean phrase are now
> anchored to the verdict's own opening line and `Reviewed commit:` line.

Every line number below is as of that head and will shift as the deletion lands; the
symbol names are the durable reference.

## Context

`scripts/pr_ready.py` decides whether a pull request is the owner's merge click. Its
whole job is refusing. This branch taught it to accept a bare bot 👍 as a clean verdict,
which added a **granting** path to it: nine commits, `scripts/pr_ready.py` from 640 to
1192 lines, `tests/unit/test_pr_ready.py` from 33 to 89 tests. That path has cost
thirteen blocking findings across three review rounds (four at plan review, six at code
round 1, three at code round 2), eleven of them false READY, and round 2 found a defect
inside round 1's own repair.

The owner has ruled the granting path out. The property it was asked to hold, *no state
produces a spurious grant*, is a universally quantified negative over an unbounded input
space and has no fixed point. *Never grant on a bare thumb* closes. An instrument
reports; a human decides.

**The change:** on a bare 👍 with no comment naming the head, report NOT READY with an
actionable reason. Nothing else about the verdict changes. The refusal-side work this
branch produced stays.

Files that change: `scripts/pr_ready.py`, `tests/unit/test_pr_ready.py`,
`docs/plans/` (one new document, one note beside an existing one). Nothing else in the
repository mentions `pr_ready` or reads the branch-activity endpoint; that was measured,
not assumed (`grep pr_ready` and `grep 'activity?ref='` both reach only these files).

---

## 1. Exactly what is deleted, by file and symbol

### `scripts/pr_ready.py`

| Symbol | Lines at head | Why it is granting-side |
| --- | --- | --- |
| `SHAPE_THUMB`, `SHAPE_COMMENT` and their comment block | 88-92 | the two-shape labels; one shape needs no label |
| `_author` | 216-235 | its only caller is `_unsigned_stamps` |
| `_unsigned_stamps` | 238-248 | its only caller is the `_bare_thumb_clean` call site |
| `_both_reads` | 263-280 | its only consumers are `seen_reviews` / `seen_inline` / `seen_conversation`, which feed only the thumb |
| `_settled_branch` | 345-363 | its only consumer is `head_ref_now`, which feeds only the activity read |
| `_Thumb` and the `NamedTuple` import | 404-415, 47 | the thumb judgement's return type |
| `_bare_thumb_clean` | 418-581 | the thumb judgement itself |
| `_clean_shape` | 584-598 | collapses to `bool(accepted_clean)` |
| `_branch_activity` | 734-767 | the branch-activity read: it exists only to prove the head has not moved since the thumb |
| `headRefName` in `_metadata`'s GraphQL query | 721 | its only consumer was `_settled_branch` |

Inside `_report`, delete: `head_ref` (893); the `final_reactions` read and its assertion
(1174, 1176); `seen_reviews` / `seen_inline` / `seen_conversation` (1184-1186);
`head_ref_now` / `unsettled` and their print (1205-1207); `activity` and its print
(1254-1257); the `_bare_thumb_clean` call (1259-1276); `shape` and the `clean shape`
print (1277-1278); the `+1 not counted` print (1279-1280); the `if bot_thumbs:` failure
(1308-1309). Change the guard at 1282 from `if not shape:` to `if not accepted_clean:`.

Prose to correct, because it now describes machinery that is gone: the module docstring
paragraph at 25-30 (which says the reaction row is "now ANSWERED rather than refused
outright"), the step-2 comment tail at 933-942, and the step-8 comment at 1151-1170.
Each should say instead that a reaction carries no commit id, is evidence only, and was
tried as a grant and withdrawn, with this issue number.

### `tests/unit/test_pr_ready.py`

Delete 38 of the 89 tests. Named:

- `test_DENYING_evidence_takes_the_UNION_of_both_reads` (453) and
  `test_the_two_directions_are_OPPOSITE_rules_over_the_same_identity` (464). The second
  contrasts `_both_reads` with `_still_granted`; with only one rule left the contrast has
  no subject, and `_still_granted` keeps its own direct test (see below).
- `test_the_FINAL_read_names_the_branch_whose_history_may_be_read` (505).
- The whole `shape B: a bare bot thumb` block, lines 572 to 1003, **except**
  `test_confirmation_is_by_ID_where_the_rows_carry_one` (802). That is 31 tests, plus
  the helpers `REF`, `_reaction`, `_activity_row`, `_arrival`, `_shape_b`.
- Four sweep tests: `test_the_bare_thumb_sweep_reports_READY_too` (1122),
  `test_a_bot_review_seen_ONLY_IN_THE_FIRST_READ_still_governs` (1131),
  `test_a_final_read_that_cannot_name_the_HEAD_BRANCH_refuses` (1201),
  `test_a_head_branch_RENAMED_mid_sweep_refuses_too` (1219).

In the `_sweep` harness: delete the `activity?ref=` branch (1100-1101), the `activity`
fact (1069) and the `final_reactions` fact (1068). Keep the `reactions` fact: the
report still reads reactions as evidence.

⚠️ **51 is the plan's expectation of what survives, not a criterion.** The criterion is
the named tests. A file's test count moves for reasons a criterion has nothing to do
with.

### What is LOAD-BEARING for what stays, and must not go with it

- **`_same_row` (251-260) and `_still_granted` (283-297) survive.** They are shared: the
  thumb used them at 489, and **shape A uses them at 1234** to confirm its clean comment
  against the final read. That confirmation is explicitly kept.
  `test_confirmation_is_by_ID_where_the_rows_carry_one` (802) is their direct test and
  moves into the shape-A section, its fixtures re-cut from reactions to comments.
- **The whole T apparatus survives**, because shape A is judged against T:
  `_ready_for_review`, `_both_timelines`, `_round_began`, `_round_start`,
  `_still_current` in its `began` form, and `createdAt` plus `timelineItems` in the
  metadata query. This is #183's fix and it only ever moves T later, which refuses more.
- `_latest_request` and `_request_arrived_mid_sweep` are pre-existing on `main` and stay.
- **`--paginate` on the reactions read (914) stays, and it stays load-bearing.** The
  report still needs to know a bare 👍 exists in order to say so; a 👍 on a later page
  would silently degrade the actionable refusal into the generic one.
- `bot_thumbs` (943) and its evidence line (999-1003) stay.
- The #219 encoding fix in `main()` (1338-1340) stays.
- `_gh`'s `encoding` / `errors` were already on `main`. Untouched.

---

## 2. That no remaining path can return READY on weaker evidence, shown by running

The claim: **after this change `_report` returns True only when a bot-authored
conversation comment matching a clean phrase and naming the head is present in BOTH
reads and postdates a computable T.**

The structure that makes it checkable: `_report` has exactly **one** `return True`
(1317), reached only when `failures` is empty, and the four-branch chain at 1282-1307 is
exhaustive over an empty `accepted_clean` (no clean comment at all / none surviving the
final read / T uncomputable / all superseded by T). So the claim reduces to *`failures`
is non-empty whenever `accepted_clean` is empty*, which is a thing you can run.

The build demonstrates it with five test groups, not with a paragraph:

- **T1, the granting path is gone.** `assert not hasattr(pr_ready, name)` for
  `_bare_thumb_clean`, `_clean_shape`, `_branch_activity`, `_Thumb`, `_settled_branch`,
  `_author`, `_unsigned_stamps`, `_both_reads`, `SHAPE_THUMB`, `SHAPE_COMMENT`. A future
  reintroduction is then a red test rather than a review question.
- **T2, one `return True`.** Read the module source, as
  `test_the_phrase_is_not_written_literally_in_the_source` (43) already does, and assert
  the file contains exactly one `return True`.
- **T3, the near-miss table.** One parametrized sweep that removes exactly one condition
  at a time from the qualifying comment and asserts False for each: not bot-authored; no
  clean phrase; does not name the head; predates T; absent from the final read; arriving
  only in the final read; T uncomputable (`timelineItems: None`); plus a bare 👍 alone
  with a perfect metadata answer, green checks and no unresolved threads. Each is paired
  against the byte-identical positive sweep asserting True, so a harness that refuses for
  an unintended reason cannot pass the table.
- **T4 and T5** are the two surviving round-2 findings below. They are part of this
  demonstration, not separate from it: until they are fixed the claim is **false**.

⚠️ **Two existing sweep tests would pass for the wrong reason after the deletion and
must be re-fixtured, not left alone.**
`test_a_ready_event_that_DISAPPEARS_from_the_final_read_still_moves_T` (1156) and
`test_a_TRIGGER_that_disappears_from_the_final_read_still_moves_T` (1177) both drive
their refusal through a bare 👍 with `conversation=[]`. With the thumb deleted those
sweeps have no clean signal at all, so they return False whatever T does, and the T
regression they exist to catch would be untested while both tests stayed green. Re-cut
each onto shape A: the clean comment at 10:00, the vanishing round-start term at 10:30 or
11:00, paired with the same sweep minus that term asserting True.

---

## 3. Round 2's three findings, verified against the post-deletion code

⛔ The build **quotes each finding verbatim** from the review record when filing or
fixing. The subjects are named here; the wording is the reviewer's.

### 3a. The unreadable trigger timestamp: **SURVIVES. Blocking.**

`_latest_request` (181-187) builds `str(c.get("created_at") or "")` and returns
`max(stamps, default="")`. A trigger comment whose timestamp is absent or null
contributes `""`, and if it is the only trigger comment the function returns `""` **which
is the same value it returns when no round was ever asked for**. T then falls back to the
open time.

Named input on the post-deletion head: a pull request opened 2026-04-02T09:00:00Z; the
bot posts a clean comment naming head `eeee...` at 09:07; a human asks for a new round at
10:00 in a comment the read returns with no `created_at`; no push; the script runs before
the new round publishes anything. T is 09:00, the 09:07 comment postdates it,
`accepted_clean` is non-empty. **Wrong output: READY, on the previous round's verdict.**
`_request_arrived_mid_sweep` is silent too, because both its arguments are `""`.

This is the same three-answer shape `_ready_for_review` already implements: readable /
empty / did not say. The build makes an unreadable trigger timestamp make T unreadable,
so shape A refuses. Mechanism is the build's.

### 3b. The same-second comparison at T: **MOOT if it names a false READY.**

Measured rather than assumed. After the deletion, `began` appears in exactly three
places: `_still_current(standing_clean, began)`, the `if not began` guards, and a print.
`_round_began` combines its terms with `max`. So **every surviving comparison against T is
a strict `>` on granting evidence, and equality drops the grant.** A same-second artifact
is refused, not accepted.

The permissive same-second comparisons were all inside `_bare_thumb_clean`: a push at
exactly T reading as an unmoved branch (535), a bot review, inline or conversation comment
at exactly T reading as bot silence (551-559), an unsigned artifact at exactly T (573).
All three go with the deletion.

**The build's check, in one line:** if the finding's named wrong output is a false READY,
it cannot be reproduced on the post-deletion head and is filed as moot with the reason. If
its named wrong output is a false NOT READY, it survives, does not block under the one
question, and is filed with its rationale. Run the finding's own named input against the
post-deletion head and let that decide; do not decide it from this paragraph.

### 3c. The edited clean comment matched by id: **SURVIVES. Blocking.**

`standing_clean = _still_granted(clean_comments, by_bot(final_conversation))` (1234)
confirms shape A's evidence against the final read using `_same_row`, which compares
**`id`** when either row carries one. `clean_comments` was filtered by the clean phrase
and `_names_the_head`; `by_bot(final_conversation)` is **not filtered at all**. So
identity survives an edit that destroys the content.

Named input: the bot posts a comment at 09:07 with id 4815162342 reading
`Didn't find any major issues. **Reviewed commit:** \`eeeeeeeeee\``; the sweep reads it;
before the verdict the bot edits that same comment into a findings report, or edits the
quoted commit to a different one; the final read returns id 4815162342 with the new body;
every other gate is clean. `_same_row` matches on id, `standing_clean` keeps the **first**
read's row, `accepted_clean` is non-empty. **Wrong output: READY over a body that no
longer carries a clean verdict.**

⚠️ This is the head-on contradiction of section 2's claim, which is why it blocks. The
fix direction: for granting evidence, confirmation is on **content**, not identity. The
final read's row must itself still be bot-authored, still match a clean phrase and still
name the head. Extracting that predicate into one helper applied to both reads is the
obvious shape; the build picks it. `_still_granted` has one caller after the deletion, so
it may be specialised rather than kept generic.

---

## 4. #235 goes moot, and this is measurable

#235 is *a fork's pull request has its branch activity in the fork, not here*. Its entire
subject is the read `repos/randyjreid/gramps-live-api/activity?ref=refs/heads/{branch}`.

Measured: that endpoint appears in exactly one place in the repository's code,
`scripts/pr_ready.py:759`, inside `_branch_activity`; `_branch_activity` has exactly one
caller, `scripts/pr_ready.py:1254`; and that call's result feeds exactly one thing, the
`activity` parameter of `_bare_thumb_clean`. Nothing else in the repository reads it.

**Deleting the thumb deletes the read.** After this change the script never asks about a
branch's activity, in this repository or any fork, so #235 has no defect left to fix.
Close it as obsolete with the reason recorded and the finding left quoted in place. Its
three open questions (whether `gh` can read a fork's activity log, where the head
repository identity comes from, what happens when a fork is deleted) also disappear,
because nothing needs the answers.

#183 and #219 are unaffected: both fixes are on the refusal side and both survive.

**#233 itself is not fixed by this change and must not be closed as if it were.** Its
named defect, a false NOT READY on a bare 👍, is deliberately kept. Post the owner's
ruling and what shipped instead as a comment on #233; leave the open/closed call to the
owner at merge.

---

## 5. What the report says instead

The refusal names what the bot did, what is missing, and what to do.

**Step 2 stays as evidence** and drops its forward reference to a step-8 judgement:

```
       bot +1 on body     : 1  (2026-04-02T09:06:00Z)  (evidence, never a verdict)
```

**Step 8, when a bare 👍 exists and no clean comment qualifies** (this replaces both the
generic first-branch reason and the deleted `the bot's +1 is not a clean verdict on this
head: ...` line, so the reader gets one sentence rather than two):

```
     - the bot left a +1 on the pull request body at 2026-04-02T09:06:00Z and no comment
       naming this head: a reaction carries no commit id, so nothing ties it to
       eeeeeeeeeeee. Re-trigger the bot on this head so it publishes a comment naming
       the commit it reviewed.
```

**With no 👍 either**, the existing first-branch reason gains the same action:

```
     - no CLEAN verdict naming this head -- the bot's clean comment quotes the commit it
       reviewed, and none quoting this one was found. Re-trigger the bot on this head.
```

The other three branches (withdrawn verdict, T uncomputable, verdict predates T) keep
their present wording, which already names the input; append the same re-trigger
sentence to the withdrawn and predates branches only, since a T that cannot be computed
is not fixed by re-triggering.

⛔ **The message must not spell the trigger phrase literally.** `TRIGGER` is assembled
from parts at line 85 precisely so this file never contains it, and
`test_the_phrase_is_not_written_literally_in_the_source` enforces that. **Recommended:
say "re-trigger the bot on this head", which names the action without embedding a live
trigger in output an operator may paste into a pull request comment**, where it would
start a round and would itself be counted by `_latest_request`. The alternative, an
f-string interpolating `TRIGGER` at runtime, keeps the literal out of the source but arms
the output; it is recorded here and not recommended.

---

## 6. Acceptance criteria, mechanically checkable

1. `python -c "import importlib.util, ..."` style attribute check, i.e. test T1, is
   green: none of the ten deleted symbols exists on the module.
2. `scripts/pr_ready.py` contains exactly one `return True` (test T2).
3. The near-miss table (T3) is green: every listed near-miss sweep returns False and its
   paired positive returns True.
4. Findings 3a and 3c each have a named-input sweep asserting False, paired with the
   byte-identical sweep asserting True. Both pairs green.
5. Finding 3b is disposed of in the ledger with its verbatim text and the run that
   decided it, either as moot or as filed.
6. `test_a_ready_event_that_DISAPPEARS_from_the_final_read_still_moves_T` and
   `test_a_TRIGGER_that_disappears_from_the_final_read_still_moves_T` are re-fixtured onto
   shape A, and each fails if its round-start term is removed from the code.
7. The bare-👍 refusal text is asserted with `capsys`: the printed reason contains the
   reaction's timestamp, the head's abbreviated SHA, and the words `re-trigger`.
8. `grep -rn "activity?ref=" scripts/ tests/` returns nothing.
9. `pytest tests/unit/test_pr_ready.py` green; the project's own gates (ruff, mypy, full
   suite) green. Not run on Python 3.14.
10. No existing surviving assertion is edited. Deletions of thumb tests and the two
    re-fixtures named in 6 are the declared exceptions, both recorded above.
11. `docs/plans/pr-ready-refusal.plan.md` added carrying this plan;
    `docs/plans/pr-ready-thumb.plan.md` gains a superseded-by note **above** its existing
    text, with nothing inside it edited. The record of what was tried and withdrawn stays
    readable.
12. Demo, delivery-mode: `python scripts/pr_ready.py <this change's own pull request>` on
    a plain Windows console prints NOT READY naming the missing comment while the bot has
    only reacted, and prints READY once the bot posts a comment naming the head. The
    instrument demonstrates itself on its own pull request, as the previous plan's demo
    did.

---

## 7. Out of scope

- Fixing #233's original complaint. The false NOT READY is accepted friction by the
  owner's ruling; only the wording of the refusal changes.
- Any other way of tying a reaction to a head. There is none that closes, which is the
  finding this change acts on.
- `_names_the_head`'s prefix matching, which counts any 7-hex-or-longer prefix of the head
  anywhere in a lowered body and would match an unrelated string. Pre-existing on `main`,
  untouched by this change, file if not already filed.
- `_round_count` undercounting a clean round that publishes no marker comment. Already
  recorded as out of scope on the previous plan; unchanged here.
- The `#219` tail, the sweep of other `scripts/*.py` for the same encoding defect.
- Renaming the branch, and any reverting of the branch's commits. This lands as a forward
  commit so the history keeps the record of what was tried.

## 8. Questions left to the build, numbered

1. Whether `_latest_request` grows a third answer (`None`) or a separate
   "any trigger unreadable" signal, for finding 3a. Both reach the same refusal;
   `_request_arrived_mid_sweep` consumes the same value and its handling must be stated
   either way.
2. Whether the content confirmation for finding 3c lives in a new predicate helper applied
   to both reads, or `_still_granted` is specialised to comments now that it has one
   caller.
3. Whether the deleted-symbol assertion (T1) names the ten symbols as a literal list or
   asserts against a frozen inventory of the module's callables. The list is simpler; the
   inventory also catches an eleventh symbol nobody thought of.
4. Whether `THUMB_HEAD`, `THUMBED` and `ARRIVED` in the test file are renamed now that no
   thumb decides anything. A rename changes no assertion, and leaving `THUMB_HEAD` naming
   the head in a file whose subject is that thumbs do not grant is a trap for the next
   reader.
5. Whether `bot_thumbs` keeps its own step-2 line or folds into the step-8 refusal only.
   Recommended: keep it, because evidence the report gathered and did not print is
   evidence nobody can check.
6. Whether the single reactions read is confirmed against a second read. Recommended: no.
   Reactions grant nothing now, so a stale read cannot produce a false READY; its only
   cost is that a 👍 deleted mid-sweep is described in a NOT-READY message that is already
   correct in its verdict. Recorded as an accepted residual rather than left unstated.
