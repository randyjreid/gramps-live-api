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

1. **An anchor that is not an ANCESTOR of HEAD forces a full walk.** A rebase, a
   force-push, a rewritten branch, a hand-edited anchor file, an empty one, or a
   SHA from a different repository — each produces the whole-history scan, never
   a skip. One test per shape.

   ⛔ **Ancestry, not resolvability, and the difference is the whole criterion.**
   After a rebase or a force-push the old commit usually **remains in the object
   database**, so `git rev-parse --verify` still resolves it — it verifies only
   that the name identifies an object. An anchor that resolves but is no longer
   reachable from `HEAD` would certify a prefix that is not in this history at
   all, and `anchor..HEAD` would then quietly scan the wrong set. **`git
   merge-base --is-ancestor` is the question being asked.**
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
   use the anchor at all.** The optimisation is a development-machine affordance
   and the runner keeps doing the complete thing.

   ⛔ **This is NOT a backstop, and an earlier draft of it read like one.** The
   workflow triggers `on: push`, so GitHub has received and stored the objects
   **before a runner starts** — and on a public repository that is publication.
   **CI detects after the fact; it cannot prevent.** A commit that a wrongly
   skipped local scan waved through is already public when the runner reports it,
   and it stays reachable after a force-push over it.

   ⭐ **What this criterion actually buys** is that the full walk stays
   **exercised**: the complete path keeps running somewhere on every change, so
   the anchor mechanism cannot rot unnoticed and a divergence between anchored
   and full results surfaces. That is worth having and it is a different thing
   from a safety net.

   ⚠️ The gate that prevents publication is the **local** one — see #171 and the
   `pre-push` hook. Nothing in this plan may be justified by "CI would catch it".

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

**2. When is the anchor written, and does it ADVANCE? DECIDED — yes, it advances.**

⛔ **The anchor moves to the scanned HEAD after any run that is provably
covering, and an anchored run can be one.**

An earlier draft said only *"after a full or fully-covering scan"* and left
*fully-covering* to be worked out from criterion 4 three sections away. **Two
sections that must be read together to agree is a plan someone implements from
one of them** — and the reading that loses is the one where the anchor never
moves.

⚠️ **That reading is not merely conservative, it decays back to the defect.** An
anchor frozen at commit A means every later run rescans a growing `A..HEAD` tail,
so the 82 s → ~9 s saving is temporary and the cost climbs back toward a whole-
history walk. The optimisation would quietly stop optimising.

⭐ **So, stated in one place:**

- The anchor advances to the scanned HEAD when **the run covered everything it
  needed to** (criterion 4) **and** the scan was clean. It is then written with
  **the digest in force now**.
- ⛔ **A FULL walk always qualifies, and requiring a digest match would have
  broken the mechanism at both ends.** On a fresh checkout there is no stored
  digest to match, so nothing could ever write the first anchor; and after a
  rules change criterion 2 *deliberately* produces a mismatch, so the recovering
  full walk could not write one either. **The optimisation would never start and
  could never recover** — every run repeating the whole-history walk while
  looking like it was working.
- An **anchored** run advances the anchor only when the digest matched, because
  that is what made skipping the prefix legitimate in the first place.
- ⛔ **The anchor is preserved, not advanced, on any other outcome**: a failed
  coverage assertion, a scan that found something, or a scan that could not
  complete. ⚠️ **A digest mismatch is NOT on that list** — it forces a full walk,
  and a full walk that comes back clean and covering is exactly the run allowed
  to write the new anchor. That is how the mechanism recovers. **An anchor written after a run that did not cover
  everything is how a gap becomes permanent** — the middle is never revisited,
  because nothing afterwards knows to look.

**3. What exactly goes into the rules digest? DECIDED.**

⭐ **The falsifier was tested before approval and it does not fire.** The digest
is three things:

```
{ hash(src/gramps_live_api/core/pii_guard.py),
  hash(the local deny-list, or a marker for its absence),
  unicodedata.unidata_version }
```

⛔ **Hashed from what the scan ACTUALLY LOADED, and checked again when it ends.**
Hashing the files on disk independently of the run certifies whatever they say at
the moment of hashing — and a walk over this repository takes about 82 seconds,
which is ample time for an editor to save, a branch to be switched, or another
process to rewrite the deny-list. The anchor would then record rules that were
never applied to a single commit.

⭐ So the digest is taken **before** the walk, the walk uses those bytes, and the
digest is taken **again afterwards**. If the two disagree the run is not covering
— **the anchor is not written and the next run walks fully.** That is the same
conservative direction every other branch of this design takes.

- **The guard module** carries every pattern, table and severity. One file, one
  hash. ⚠️ Nothing else under `core/` feeds a verdict: `_specified_containers.py`
  is **not imported at runtime** by design — its own docstring and two in-file
  comments say so — and `_unrenderable.py` is not referenced by the guard at all.
- **The deny-list** is never committed (`test_no_denylist_is_committed`) and is
  per-developer, but it lives at a **known path**, so its content — or its
  absence — hashes like anything else. It changes what counts as a finding, so it
  belongs in the digest.
- **`unidata_version`** is the one that looked fatal and is not. The interpreter's
  UCD reaches a verdict through `unicodedata.normalize("NFC", …).casefold()`, and
  that string differs across exactly the interpreters this project supports —
  measured: **3.10 → 13.0.0, 3.11 → 14.0.0, 3.12 → 15.0.0**.

⚠️ **Two caveats, stated because the digest is weaker than it looks.**
`unidata_version` pins the **release**, not the fold behaviour — it is a proxy,
though a conservative one, and the same shape of pin this project already uses
elsewhere. And the UCD reaches a verdict through **one function only**,
`_comparable`, which is called **only** by the deny-list scan — so on a machine
with no deny-list, including CI, it contributes nothing at all.

**4. Should a rules change re-walk immediately, or warn?**
⭐ **Recommendation: re-walk, silently, and say so in the output.** A warning that
tells a developer to run something is a warning they will route around at 82
seconds a time. The re-walk is the correct behaviour and it is self-healing.

## Falsifier

⛔ **The digest falsifier was TESTED before approval, and it does not fire.**
It read: *if the rules digest cannot be computed from a stable, enumerable set of
inputs, criterion 2 is unsatisfiable and this design is wrong.* Every input to a
verdict was enumerated and each one hashes — see question 3, where the digest is
now written in as decided.

⚠️ **The one that looked fatal was the interpreter's UCD**, reached through
`unicodedata.normalize("NFC", …).casefold()`, which is not repository content.
`unicodedata.unidata_version` makes it enumerable: measured **13.0.0 / 14.0.0 /
15.0.0** across the three supported interpreters.

⭐ **So the expiry-based fallback is NOT what gets built.** It was the escape
hatch if the digest proved impossible; the digest did not prove impossible, and
an expiring anchor is weaker — it re-walks on a timer rather than on the thing
that actually changes a verdict. Recording that it was considered and rejected on
evidence, so nobody reaches for it later as an equivalent.

⛔ **What would still falsify this:** a future change that makes a verdict depend
on something outside the three digest inputs — a network fetch, a machine-local
configuration file, an environment variable read at scan time. Any of those
breaks criterion 2 and the design has to be reopened rather than patched.

⚠️ And if the fixed ~7.5 s turns out to be the guard's start-up rather than the
range walk, the saving is real but the ceiling is lower than 82 → 9, and the
trade should be re-argued at that number.
