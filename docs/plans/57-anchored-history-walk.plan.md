# Plan — #57: stop re-walking settled history on every run

**FULL tier.** It changes **what the personal-data guard scans**, which is the
publication-of-personal-data surface. ⛔ **Not built. This page is the
deliverable, and it needs the owner's approval before anything is written.**

## ⭐ Read this first: the criterion I was given does not bind the risk

The dispatch criterion was *"findings over the SAME range are byte-identical
before and after; if identity cannot be proven, stop and report."*

**Identity over the same range is provable and it is vacuous.** This change does
not touch the scanner — it changes only **which range** is handed to it. So
"old code over range R" and "new code over range R" are the same call, and the
proof is a tautology.

⚠️ **The property that actually carries the guarantee is COVERAGE**, not
identity:

> every commit this repository publishes has been scanned **by the rules in force
> now** — not by whatever rules were in force when somebody recorded an anchor.

That distinction is not pedantic. It is the whole defect, and it is measured
below.

## ⛔ The fail-open the issue does not list, measured

#57 names two things a fix must get right: an anchor that no longer resolves must
force a full walk, and the full walk must stay reachable. **Both are correct and
neither is this.**

The unstated assumption is *a commit that was clean once stays clean*. That is
true of the commit. **It is not true of the verdict**, because the verdict is a
function of the guard's rules, and those change.

**Measured on this repository, today:**

| | findings |
| --- | --- |
| a 40-commit window from early history, under today's rules | **0** |
| **the same window**, with **one** plausible new rule added | **17** |

The rule added was a single ordinary pattern. An anchor recorded before that rule
landed would have skipped **every one of those 17**, and the suite would have
reported clean.

⚠️ **And this is empirical, not hypothetical.** `src/gramps_live_api/core/pii_guard.py`
has **32 commits** across the repository's 453 — the rules change roughly every
fourteenth commit. A mechanism that silently trusts pre-rule-change verdicts
would have been wrong 32 times already.

## The measurement, controlled

⚠️ One session, one variable, anchors read from `git rev-list` output and never
constructed. This matters because the issue's own recorded figures come from
different machines on different days, which it says itself.

| commits in range | seconds | ms/commit |
| --- | --- | --- |
| 25 | 11.55 | 461.9 |
| 69 | 18.36 | 266.0 |
| 111 | 25.68 | 231.3 |
| 200 | 41.93 | 209.7 |
| 411 | 73.34 | 178.4 |

**The model that fits: ~7.5 s fixed, plus ~160 ms per commit.** It predicts 39.6 s
at 200 against 41.93 measured, and 25.3 s at 111 against 25.68.

**Today's whole walk: 81.59 s over 453 commits**, and the model predicts 80.0.

⭐ **What that means for the fix.** A run scanning ten new commits costs about
**9 s** rather than **82 s**. But the fixed ~7.5 s does not go away, so the honest
claim is *82 s becomes about 9 s*, not *becomes free*.

⚠️ **What it also means: the issue's stated curve is not reproducible as one
curve.** Its recorded 34.6 s at 74 commits and 71.79 s at 193 are both roughly
**1.8×** what this model predicts. Nothing here says those measurements were
wrong — they were taken elsewhere, and per-commit cost depends on how much
content each commit touches, not only on how many there are. **It does mean the
32 ms-per-spawn cost model in #12 is not what dominates**, and a fix reasoned from
it would be tuned against the wrong thing.

## Mechanically checkable acceptance criteria

1. **An anchor that does not resolve forces a full walk.** A rebase, a
   force-push, a rewritten branch, a hand-edited anchor file, an empty one, or a
   SHA from a different repository — each produces the whole-history scan, never
   a skip. One test per shape.
2. ⛔ **An anchor recorded under different guard rules forces a full walk.** The
   anchor record carries a digest of the guard's rule inputs; if the digest does
   not match what is in force now, the anchor is ignored. **This is criterion 1's
   twin and it is the one the issue is missing.**
3. **The digest covers everything that can change a verdict** — the guard module
   and every derived table it reads — and a test fails if a file that feeds the
   guard is not in the digest's input set. An enumeration that nothing checks is
   how this fails quietly.
4. **Coverage is asserted, not assumed:** for any accepted anchor, the commits
   scanned this run **plus** the commits the anchor certifies equal the commits
   reachable from `HEAD`. Asserted by count, and the count is compared against
   `git rev-list --count HEAD`.
5. **Identity, since it was asked for:** for a fixed range, findings before and
   after this change are byte-identical. Cheap, and worth keeping as a regression
   guard even though it does not bind the risk.
6. **The full walk stays reachable and stays run** — a flag, and CI runs it. CI
   pays about ten seconds for the whole suite, so **there is no reason for CI to
   use the anchor at all.** ⭐ That is the cleanest form of this criterion: the
   optimisation is a development-machine affordance, and the runner keeps doing
   the complete thing.

## Out of scope

- Making the scan itself faster. That is #12's cost model, and the measurement
  above says that model is not what dominates — so it needs its own measurement
  first, not a fix bolted onto this one.
- Changing any guard rule, pattern, or severity. ⛔ This plan changes **which
  commits are scanned** and nothing about **what counts as a finding**.
- The `test_pushed_range.py` cost, which the issue notes separately.

## Open questions, with a recommendation

**1. Where does the anchor live?**
It must be per-checkout and never committed — a committed anchor would be shared
between machines whose histories differ, and would arrive in a fresh clone
claiming that history is already scanned.

⭐ **Recommendation:** an ignored file under the existing state directory, holding
the SHA and the rules digest. ⚠️ It must be **ignored by a rule that already
exists or one added in the same change**, because `test_no_path_is_both_untracked_and_unignored`
fails on anything neither tracked nor ignored — which is the test working, and
worth planning for rather than discovering.

**2. When is the anchor written?**
Only after a **full or fully-covering** scan reports clean. Writing it after an
anchored run is how a gap becomes permanent: run A skips to the anchor, writes a
new anchor, and nothing ever revisits the middle.

**3. Should a rules change re-walk immediately, or warn?**
⭐ **Recommendation: re-walk, silently, and say so in the output.** A warning that
tells a developer to run something is a warning they will route around at 82
seconds a time. The re-walk is the correct behaviour and it is self-healing.

## Falsifier

⛔ **If the rules digest cannot be computed from a stable, enumerable set of
inputs** — if the guard reads something whose contribution to a verdict cannot be
hashed — **then criterion 2 is unsatisfiable and this design is wrong.** The
fallback would then be an anchor with an **expiry** (re-walk fully every N runs or
on any change under `src/gramps_live_api/core/`), which is weaker and should be
recognised as weaker rather than presented as equivalent.

⚠️ And if the fixed ~7.5 s turns out to be the guard's start-up rather than the
range walk, the saving is real but the ceiling is lower than 82 → 9, and the
trade should be re-argued at that number.
