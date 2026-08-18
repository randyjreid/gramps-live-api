# Slice 2 — review ledger

**Branch:** `slice2-mcp-server`. One entry per finding, quoted, **never summarised into another
entry** — the concrete input and the concrete wrong output are exactly what summarising loses.

**Round counts, per reviewer.** The five-round backstop is per reviewer, and at five the owner
decides whether to continue.

| Reviewer | Rounds so far |
| --- | --- |
| Codex | **1** |
| Claude `/code-review` | 0 |
| PR bot | 0 |

---

## Codex round 1 — 3 findings, all verified against the code, all BLOCKING

Verified by reading the named lines before dispositioning; none was filed unreproduced.

### C1-1 — [P1] Preserve committed status when read-back cannot launch — `src/gramps_live_api/cli.py`

> On Windows, a note can put the apply environment just under the 32,767-character limit while the
> verification run crosses it because `_one_run` adds `ENV_HANDLES`. The first Gramps process then
> commits the note, the second raises `OSError`, and this catch writes `outcome: failed`;
> `APPROVE_DESCRIPTION` tells the agent that means the write was refused, so a committed note is
> reported as unwritten and may be proposed again. Distinguish failures before the apply marker from
> failures launching read-back and report the latter as committed but unverified.

**Disposition: FIX NOW.** Confirmed: one `except (ApplyError, SchemaError, OSError)` wraps the whole
of `_write_and_verify`, which performs **two** runs, and every failure inside it writes
`outcome: failed`.

⚠️ **This is a demonstrable defect on the risk surface.** A committed note reported as refused is the
exact input that makes an agent propose again — the duplicate-write path slice 2 claims to have
closed for the MCP route. **It is not #66.** #66 stays filed and out of scope; the cap is only how the
state is *reached*. The defect is that the outcome is **misreported**, and it would be reachable by
any post-commit launch failure.

### C1-2 — [P2] Fail the export check when freshness is unreadable — `src/gramps_live_api/cli.py`

> When `os.scandir` or an entry stat fails—for example, an ACL permits access to known files but
> denies directory listing—`_copy_touched` returns `None` and this condition falls through to
> `Check("export", True, ...)`. Thus `check` can print ready even though it could not establish
> export freshness and a newer privacy flag may be hidden; the unknown case must fail the export
> check rather than be treated as current.

**Disposition: FIX NOW.** Confirmed: `_copy_touched` returns `None` on `OSError`, and
`if changed is not None and changed > taken` then falls through to a passing check.

⚠️ **The function's own docstring states the invariant this breaks:** *"this answer has to be wrong
toward re-export, never toward the flag you are reading is current."* Unknown freshness currently
reports **current**. That is the artifact asserting something untrue, not a gap in a property — and
it is a fail-open on ruling 1's privacy boundary.

### C1-3 — [P2] Exclude non-primary roles from a person's birth — `src/gramps_live_api/core/people.py`

> For a valid person reference such as an `eventref` with `role="Witness"` to a Birth event,
> `primary` is empty and this fallback selects the witnessed event as the person's own birth.
> `list_people` consequently reports the baby's year for the witness, similarly for `Family` and
> other explicit roles; only `Primary`, with a narrowly defined legacy fallback for an absent role if
> needed, should populate the person's birth fields.

**Disposition: FIX NOW.** Confirmed: `chosen = primary or [handle for handle, _ in referenced]`. The
existing test asserts Primary is **preferred**; it does not assert non-Primary is **excluded**, and
the fallback fires whenever no Primary ref exists.

Named input → named wrong output: a witness at a birth is listed with the baby's birth year. Since
`list_people` exists to let a person be identified before a note is attached to them, a wrong birth
year is a defect in the tool's entire purpose.

---

## Ruled out of scope — re-finds, not findings

Recorded so a later round does not re-derive them: **#66** (environment-block cap, filed);
**name-level `priv="1"`** (residual — ruling 1 is the person flag); **`outcome_of` not exposed as a
fourth tool** (surface decision, with a use-derived reopening condition); **the stale-`priv`
fail-open** (recorded in `docs/slice2-mcp.md`); **the MCP SDK** (owner-affirmed at a measured 27–30
transitive packages, behind an optional extra).

---

## Fix round 1 — dispositions, and a correction to this ledger

| Finding | Disposition | Commit |
| --- | --- | --- |
| C1-1 | **FIXED** | `8779e8d` |
| C1-2 | **FIXED** | `9b0c175` |
| C1-3 | **FIXED** | `e6038ef` |

Each carries a test that was red before the change and green after. Gates re-run by the conductor on
the fixed head: `ruff` clean · `ruff format` 78 files · `mypy src` 18 files · **1363 passed, 6
skipped** (+7, exactly the tests added) · guard 0 findings over tracked content and over the range.

### ⚠️ CORRECTION — C1-1's entry above overstated the defect, and the overstatement was mine

C1-1's disposition text called the defect *"the exact input that makes an agent propose again — the
duplicate path slice 2 claims to close."* **That is wrong**, and the fixer disputed it rather than
implementing against it.

**A false `failed` cannot produce a second write.** Verified in the code: `store.consume(...,
approved=True)` runs *before* `_write_and_verify`, so a retried `approve` gets `ProposalNotFound`. A
second note requires a fresh `propose_note`, a new console, and **a second human `y`** — which is the
designed behaviour, not a defect.

**What the defect actually breaks**, and what makes it P1 without the stronger claim: **the owner's
knowledge of what is in the tree**, and the recoverability of a write whose handles were reported
nowhere.

The commit message for `8779e8d` repeats this ledger's original wording. It is not being rewritten —
**this entry is the correction of record.** ⚠️ A conductor's framing of a finding gets none of the
scrutiny the finding itself gets, and it reached a prescription and a commit before anyone tested it.

### A worse variant the finding did not name — found by the fix's own test

`NoResultMarker` raised by the **read-back** was not in the set `_approve` caught, so it escaped past
the reporting entirely: the note committed, the console exited, **no report was filed at all**, and
the server then waited out its full timeout and reported `still_open` about a run that had ended.
Same boundary as C1-1, strictly worse outcome. Fixed in `8779e8d`.

### Open questions, answered from sources rather than from memory

- **Absent `role` means Primary.** Read from Gramps 6.0.8 as installed: `grampsxml.dtd` declares
  `role CDATA #IMPLIED`; `importxml.py` only sets a role when the attribute is present; `EventRef`
  defaults to `EventRoleType()`, whose `_DEFAULT` is `PRIMARY`. No fail-closed reading was needed.
  ⚠️ **And the same reading forced a distinction the finding called unanswerable:**
  `set_from_xml_str("")` falls through to `_CUSTOM`, so **`role=""` is a custom role, not Primary** —
  a different document from one with no attribute. The parser no longer collapses them.
- **The outcome token reuses `unverified`** rather than minting `committed_unverified`. `unverified`
  is only ever set after the marker said `ok`, so it already means *committed and not confirmed*, and
  the agent's next action is identical either way. `unknown` (#69's vocabulary) was rejected as
  understating what the operator can act on: here we know it committed.

### Residuals recorded, not fixed

- The post-commit handler enumerates **four** exceptions rather than catching `Exception`. *"No
  post-commit failure is misreported"* is unbounded; the bounded claim is those four.
- `store.write_report(...)` in `_approve` sits outside the try, so a failure writing the report files
  nothing. Pre-existing, and **no report can record its own failure to be written.**

### Round counts after this round

| Reviewer | Rounds |
| --- | --- |
| Codex | **1** (round 2 = scoped delta on this fix, next) |
| Claude `/code-review` | 0 |
| PR bot | 0 |

---

## Codex round 2 — 1 finding, verified, BLOCKING

Scoped delta on fix round 1. **The three round-1 findings were not re-found**, and nothing on the
already-ruled list was re-argued — the ledger did its job.

### C2-1 — [P2] Post-verify I/O becomes a refusal — `src/gramps_live_api/cli.py`

> When both apply and verification markers succeed but the final `out.write` raises `OSError`—for
> example, because the console stream becomes unavailable—this post-commit `try` has already ended.
> The exception reaches `_approve`'s outer handler, which files `outcome: failed` without the handles
> even though the note was committed and verified; printing a disagreement has the same routing. Keep
> these remaining post-marker operations from falling into the pre-commit failure handler.

**Disposition: FIX NOW.** Confirmed by reading: the `try` closes after the verify `_one_run`, and the
`print` calls after it — including the disagreement path — are outside it.

⚠️ **This is inside the batch's own bounded claim, not outside it.** The recorded residual says the
handler covers **four** enumerated exceptions; `OSError` is one of them. So this is not the unbounded
part failing — it is the bounded part not holding where it says it does.

⚠️ **And it falsifies a docstring.** `_write_and_verify` states that C1-1 is answered *"structurally
rather than by care, by putting everything past the marker inside one"* handler. Not everything past
the marker is inside it. **A comment asserting a structural guarantee the structure does not provide
is worse than no comment**, because the next reader stops checking.

**Self-generated surface, and that does not stop the loop here.** This is machinery the artifact
gained in response to C1-1, so diminishing-returns test (a) fires — but on **code** test (a) is not a
stop condition, and this is a **correction** (the artifact asserts something untrue), not a
refinement. Test (b) is silent.

---

## Fix round 2 — disposition

| Finding | Disposition | Commit |
| --- | --- | --- |
| C2-1 | **FIXED** | `f862435` |

Gates re-run by the conductor: `ruff` clean · `ruff format` 78 files · `mypy src` 18 files ·
**1367 passed, 6 skipped** (+4, exactly the tests added) · guard 0 over tracked content, 0 over the
range.

**The chosen shape was neither option offered.** Everything past the marker became **one call**
(`_after_commit`) invoked inside the single `try`, on the reasoning that a block's boundary is *which
statements happen to sit inside it* — a fact about where somebody stopped typing, and precisely what
failed once already. A statement appended to the end of the post-commit body is now inside the handler
**by construction**. Option 2 was rejected on a mechanical ground: the report is a local of a function
that *raised*, so it never reaches `_approve`'s handler without new machinery to carry it.

**A third failure the finding did not name**, found by the fix's own tests: **C1-1's handler printed
its explanation to the console that is the reason it ran.** An exception raised inside an `except`
propagates like the original, so the machinery that exists to prevent `failed` produced it. ⚠️
**Widening the `try` around the two statements C2-1 named would not have touched this one** — which is
the argument for the call boundary, made by the defect rather than by preference.

**The docstring is now true and says what changed**, and its claim is checkable by reading the
statements below it rather than asserting that nothing can fail.

### Recorded, not fixed — and NOT yet verified by the conductor

⚠️ **Filed as a claim awaiting reproduction, not as an issue.** The fixer reports that **closing the
console window on Windows terminates the process rather than making `write` raise**, so no report is
filed either way — *a different and pre-existing hole* from C2-1. It also narrows C2-1's own
reachability: the demonstrable route to an `OSError` on write is redirected or piped stdio
(`approve > log.txt` on a full disk, a broken pipe, a session that goes away), not the console window.
**Unreproduced findings do not become issues** — this needs verification before it is filed.

`_say` suppresses `OSError` only, so a **closed** stream's `ValueError` still escapes to `main`. The
four-exception enumeration is unchanged and neither recorded residual is resolved or widened.

---

## Sequencing — Codex is DISPOSITIONED; reviewer 2 starts now

Every finding Codex has raised is fixed and no blocking finding is outstanding. **Codex round 3 is
NOT run now**, deliberately: the merge invariant is satisfied on **the code that merges** — the final
head — not after every individual fix batch. Fix round 2 will be covered by **one scoped Codex delta
on the final head**, after Claude is dispositioned. Interleaving would cost a full extra pass per fix
batch and buy nothing that terminal delta does not.

⚠️ **Batching the terminal re-validation is fine; SKIPPING it is not.** A Codex pass three fix batches
stale is worth nothing, exactly as a bot review on a stale SHA is worth nothing.

### Round counts

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | **2** | dispositioned — owes one scoped delta on the final head |
| Claude `/code-review` | **0 → starting** | |
| PR bot | 0 | |

### ⚠️ Machinery to watch — two consecutive rounds, one component

`_write_and_verify`'s post-marker split has now drawn a finding in **two consecutive rounds**: C1-1
created it, C2-1 found the gap in it. On code, diminishing-returns test (a) is not a stop condition —
but it does ask *is this machinery worth its surface?* **If a third consecutive round finds a defect
in the same split, the question stops being "harden it" and becomes "delete or redesign it", and that
goes to the owner rather than into another fix round.**

---

## Claude `/code-review` round 1 — 7 confirmed correctness defects, 13 further findings

Official skill, high effort, $42.36. Eight finder agents → 30 raw → 24 deduped → four adversarial
verifiers. **It read this ledger** and correctly refuted five items as already-dispositioned,
including the post-commit `UnicodeEncodeError` route (C2-1's accepted residual) — which is the ledger
doing exactly what it exists for.

Conductor **verified findings 1, 2, 4, 5, 6 and the streaming defect directly against the code**
before dispositioning.

| # | Finding | Where | Disposition |
| --- | --- | --- | --- |
| L1 | truncated/corrupt gzip raises `EOFError`/`zlib.error`, neither caught, so the agent gets a raw internal exception instead of the designed "retake the export" message | `people.py` | **FIX** |
| L2 | `approve` claims the proposal **before** the console-spawn check, so on a host that cannot spawn, every proposal is consumed and orphaned — an infinite propose/approve/burn loop | `server.py` | **FIX** |
| L3 | a naive `created_utc` crashes `claim()` with `TypeError` after `_take`'s rename, stranding the file | `proposals.py` | **FIX** |
| L4 | the doctor's freshness check runs against the **command-line tree**, not the copy — the parameter is named `copy` and receives `resolved` | `cli.py` | **FIX** |
| L5 | `check` now fails a setup **this branch's own `docs/using.md` shows ending "ready"** — a copy-path-only install exits 1 | `cli.py` | **FIX** |
| L6 | the post-commit message promises *"the proposal is consumed, so no second note can arrive this way"* — **false on the `apply` path**, which has no proposal and can write a second note on re-run | `cli.py` | **FIX** |
| L7 | pre-answer console death leaves `still_open` forever; the pre-answer trigger region is unrecorded | `cli.py` | **FIX** |
| L8 | `read_export`'s `else: continue` skips `element.clear()`, so the parse the docstring calls *"one streaming pass … because a real tree is megabytes"* holds the file in memory | `people.py` | **FIX — it falsifies a stated property** |

**Cleanups → FILED, not fixed** (none is a demonstrable defect): full export re-parsed and config
re-loaded on every MCP tool call; the approve-outcome vocabulary hand-spelled with no frozenset
assertion while the same file asserts its others; `Store._durably` duplicating `apply._durably`; the
timeout guess having no config knob; `_approve`/`_apply` duplication; a dead `cap` parameter; fixture
shell duplication; two CI economies.

### ⚠️ The stop rule fires — taken to the owner, not decided here

L6 sits in machinery **C1-1 created**, which C2-1 already found a gap in. That is **three consecutive
rounds touching the post-marker path**, and this ledger recorded in advance that a third goes to the
owner as *delete-or-redesign* rather than into another fix round.

**Being precise about what the rule caught**, because a misread trigger is worth as little as a missed
one: C2-1 was a defect in the **split's structure**; L6 is a **false claim in a message**. They share a
root cause the review named independently — **`_write_and_verify` serves two callers, `_approve` and
`_apply`, whose guarantees differ**, and a message true for one is false for the other.

L6's *message* is fixed in this round. **The design question — should one function serve both callers
at all — is the owner's**, and is not being answered by a fix round.

### Round counts

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | 2 | dispositioned — owes one scoped delta on the final head |
| Claude `/code-review` | **1** | 8 blocking, fix round 3 dispatched |
| PR bot | 0 | |

---

## Fix round 3 — all eight FIXED

Head `7c354fd`. The round hit a session limit after committing all eight and before verifying; a
continuation verified each commit's diff, decided the one uncommitted change, and ran the gates.

| Finding | Commit | Finding | Commit |
| --- | --- | --- | --- |
| L5 | `814dea5` | L4 | `815c7c3` |
| L8 | `72088cd` | L6 | `723635c` |
| L1 | `6f3e817` | L7 | `91d79c7` |
| L2 | `3208fcd` | test hygiene | `7c354fd` |
| L3 | `3ba4324` | | |

Conductor-run gates: `ruff` clean · `ruff format` 78 files · `mypy src` 18 files · **1382 passed,
6 skipped** · guard 0 over tracked content and 0 over the range (27 commits, 68 entries). **The count
reconciles exactly**: 1367 + 15 test functions added = 1382.

### Three answers worth keeping

**L5 — a missing export is `ready`, and the report NAMES the two tools that cannot run.** Slice 1's
three commands read no export; only slice 2's tools do. Failing the doctor over an unconfigured
feature regressed a demo that passed. ⚠️ **The naming is what stops it being a softening** — a passing
report silent about it would be the other half of the same defect. Code and `docs/using.md` verified
string-against-string.

**L8 — measured, and the finding named only half the fix.** Peak allocation during `read_export`,
varying only the bulk walked past:

| file bytes | peak before | peak after |
| --- | --- | --- |
| 645,531 | 1,688,843 | 128,243 |
| 2,565,531 | 6,499,410 | 128,279 |

Before: ~2.5× the file, growing with it. After: **flat**. `element.clear()` empties an element but
`iterparse` leaves the husk in its parent's child list — **unlinking is what actually drops it**, so
clearing alone would not have moved the second column.

**L6 — path-specific, two named constants, not one softened sentence.** The `apply` path now says a
re-run **CAN put a second note on the person**. `_write_and_verify`'s two callers were **not** split —
verified, three call sites, one function. #73 untouched.

### Disputes — recorded, none disputed back

1. `72088cd`'s own gate line says *"+2, exactly the tests added"* where that commit adds **one**; the
   `+2` was cumulative. Nothing rests on it, and the round's aggregate reconciles — flagged as the
   small end of the stale-count hazard: a number that once matched, attached to the wrong subject.
2. ⚠️ **L4 created a second "cannot be established" state that PASSES** — `copy_path` absent returns
   `ok=True`. **One word away from the shape C1-2 forbade.** The distinction argued is real
   (C1-2 is *unknowable because the I/O failed*; this is *unaskable because there is no right-hand
   side*), but it lives **only in a code comment** while C1-2's ruling lives in the docs.
   **Open thread — file or fix.**
3. **L8's fix is broader than the finding and only one axis has evidence.** It also changed the
   `iterparse` event set from `("end",)` to `("start","end")`. Memory is measured and flat;
   **nothing measured time**, and no regression is claimed — because an uncontrolled two-number
   comparison is not a measurement.
4. **L7 left the decline region filing nothing.** Its consequence is downgraded from permanent
   `still_open` to an immediate `unknown`; what is lost is precision, not safety. Same shape as the
   recorded residual *no report can record its own failure to be written*.
5. `Spawner._then` is now written from outside the class by two tests; a public `then` would be
   right, and was left alone as churn outside the eight.
6. `docs/using.md`'s sample wraps the export line across two lines where the code prints one. Words
   match; transcript convention, not a false claim.

### Round counts

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | 2 | **owed: one scoped delta on the final head — dispatched now** |
| Claude `/code-review` | 1 | dispositioned |
| PR bot | 0 | after push |

---

## Codex terminal delta — 2 findings, both verified, BLOCKING

**Round 1's, round 2's and reviewer 2's findings were not re-found**, and nothing on the ruled list
was re-argued.

### D-1 — [P1] A real launch failure still burns the proposal — `src/gramps_live_api_mcp/server.py`

> `require_console` only validates the platform; if the subsequent spawner raises, such as `Popen`
> returning WinError 8, this runs after `store.claim` has renamed the proposal to `.pending.json`. No
> console opens, the exception escapes, and retrying gets `ProposalNotFound`, so the proposal-burn
> loop remains for real launch failures.

**Verified.** The order is `require_console(platform)` → `store.claim(...)` → `self._spawn(...)`.
⚠️ **L2 fixed the "this host cannot spawn consoles" case and left the "the spawn failed" case**, which
produces the identical burn loop.

### D-2 — [P2] Setup failures file nothing, and the server calls that `unknown` — `src/gramps_live_api/cli.py`

> those checks execute before this new `try`; `_approve` exits through `main` without `_filed` or
> `_closed`. The server then polls an exited process with no report and returns `unknown`, saying the
> note may have committed even though the prompt and write path were never reached, while the proposal
> remains consumed.

**Verified.** `config.load`, `discover_runtime` and `apply.authorise` all run **above** the pre-answer
`try`. ⚠️ **`unknown` means *a note may be in the tree*. Here nothing was written and the prompt was
never shown** — the report is not merely absent, it is wrong in the direction that matters.

---

## ⛔ STOP — the owner's pre-set rule fires. Fix round 4 is NOT dispatched.

**This machinery has now drawn findings in four consecutive rounds:**

| Round | In this machinery |
| --- | --- |
| Codex 1 | C1-1 — post-marker reporting |
| Codex 2 | C2-1 — the split's structural gap |
| Claude 1 | L2, L6, L7 — console ordering, path-specific message, pre-answer region |
| Codex delta | **D-1, D-2 — console launch, and setup before the region** |

⚠️ **The shape repeats: each fix closes one stage of the two-process crossing, and the next round
finds the adjacent stage.** L2 closed *cannot spawn here* and left *the spawn failed*. L7 closed
*pre-answer* and left *before pre-answer*. Both fixes were correct as far as they went.

**Taken to the owner as the design question, per the rule set before fix round 3 ran.**

---

## ⭐ OWNER RULING, 2026-08-18 — DELETE the outcome-reporting layer, do not harden it

**The count that decided it:** of the seven findings in this machinery, **five are the
outcome-reporting layer** — C1-1, C2-1, L6, L7, D-2 — and only **two are claim ordering** — L2, D-1.
The contract's own rule is that machinery drawing findings in two consecutive rounds is a **deletion
candidate**, and this project has taken that path correctly every time it arose.

**The layer exists to tell the agent something the human is watching happen.**

**So:** `approve` spawns the console and **returns immediately** — *"a console window has opened;
approve there and tell me what it says."*

**Gone:** polling · timeouts · `still_open` · `unknown` · outcome tokens · the cross-process reporting
whose every stage a reviewer has found.

**Then the invariant on the remainder, which is now small:**

> ⭐ **CLAIMING IS THE LAST IRREVERSIBLE STEP.** Platform, config, runtime, authorisation and spawn
> all happen **before** the claim, and a claim that cannot be followed through is **rolled back.**

That closes D-1 and L2's whole class rather than their instances.

**Handled as a DESIGN CHANGE: plan-gated, plan to the owner.** ⚠️ **Expect a NET DELETION. If the plan
comes back adding code, that is the signal to stop and talk.**

### Round counters RESET — the owner's call, recorded

> *"the artifact being reviewed is materially different afterwards."*

Per the backstop's own terms, a reset requires a reason bigger than the loop's own output — **a
property redefined, a component deleted, a module rewritten.** This is a component deleted, and the
call is the owner's, made when it happened, and recorded here.

| Reviewer | Rounds before | Rounds after |
| --- | --- | --- |
| Codex | 2 + terminal delta | **0** |
| Claude `/code-review` | 1 | **0** |
| PR bot | 0 | 0 |

⚠️ **Everything already dispositioned STAYS dispositioned.** The reset is of the count, not of the
record — re-finding C1-1, C1-2, C1-3, C2-1 or L1–L8 is still a re-find.

### `outcome_of`'s deferral now carries a real trigger

> *if relaying the window's result to Claude annoys me in use, the reporting layer comes back
> **designed** rather than accreted.*

**That is a use-derived trigger, recorded before the fact**, which is the shape this project requires
before hardening work is scheduled.

---

## Codex round 1 (post-reset) — 1 finding, verified, BLOCKING

Head `8a01dc4`. **Nothing dispositioned was re-found** — the reset count did not reset the record and
the reviewer respected it.

### E-1 — [P1] A post-rename read failure strands the claim — `core/proposals.py`

> When the proposal directory permits create/write/rename but denies reading the created files — or a
> Windows sharing lock permits delete but not read — `_take` moves a valid proposal to
> `.pending.json`, then `_parsed` raises `ProposalNotFound`. Because `_claim` runs before this `try`,
> the follow-through never runs and no restoration is attempted, so no console opens and **the same
> filesystem state burns every newly proposed ID**, recreating the loop the last-irreversible-step
> invariant is intended to eliminate.

**Verified.** `claim_then` is `self._claim(...)` followed by `try: follow_through() except Exception:
self._rollback(...)`. `_claim` renames **first** — deliberately, since the rename *is* the mutual
exclusion — then validates. A failure during that validation raises from `_claim`, which is **outside**
the try, so no rollback runs.

⚠️ **The distinction the code cannot currently draw** is between two things that both surface as an
exception out of `_claim`:

| | Burn is | Because |
| --- | --- | --- |
| a **deliberate refusal** — wrong digest, expired, wrong session, corrupt | **accepted, by design** | *"any claim consumes the proposal, including a refused one"* — a one-off cost, and the agent proposes again |
| an **environmental read failure** — ACL, sharing lock | **a loop** | the same filesystem state burns *every* new proposal, forever |

⚠️ **Same shape as C2-1 and D-1: the boundary is one statement off.** `_claim` does two things — an
irreversible rename and a fallible read — and the invariant's protection starts after both.

---

## ⛔ STOP — the owner's stop rule fires again. No fix round is dispatched.

The rule carried forward: **a finding in the console/claim machinery after the deletion comes to the
owner as a design question, not a fix round.**

⚠️ **And the owner's own note on what would make this different applies:** after the deletion that
machinery is **a spawn, a claim and a rollback** — small enough to read in one sitting, which was the
point. **This finding is inside `claim_then`/`_claim`/`_rollback` and nothing else.**

### Round counts (post-reset)

| Reviewer | Rounds |
| --- | --- |
| Codex | **1** |
| Claude `/code-review` | 0 — owed one scoped delta via `--resume` |
| PR bot | 0 |

---

## Owner rulings, 2026-08-18 (evening) — the record corrected

### 1. Line count — the ruling HOLDS, and the measured figures replace the plan's

⚠️ **The plan's headline `−185 source lines` was wrong. Recorded here so the record does not carry a
wrong number.** Measured with `ast` over the three changed source files, independently by the build
and by the conductor, agreeing exactly:

| | code | docstring | comment | blank | total |
| --- | --- | --- | --- | --- | --- |
| before `74faa4e` | 1038 | 677 | 136 | 213 | 2064 |
| after `8a01dc4` | 996 | 727 | 143 | 204 | 2070 |
| **delta** | **−42** | **+50** | **+7** | −9 | **+6** |

The plan counted deleted *line ranges* — `_awaited` at "424–496" is 73 lines, most of it its own
docstring — while the additions are likewise mostly prose. Wrong by ~4.4× on the code axis, inverted
on the raw one.

**Owner's ruling:** *"My condition was about surface a reviewer keeps finding defects in, and that
surface is code."* **−42 executable lines, and the whole outcome-reporting layer is gone — poll,
timeout, report file, outcome vocabulary.** ⭐ **Docstrings growing while code shrinks is the right
direction, not a violation.**

### 2. `ResourceWarning` — the build's deviation is an APPROVED DEVIATION

⚠️ **Recorded with its numbers so nobody "restores" the plan's instruction later.** The approved plan's
verification step 5 said: if the `ResourceWarning` from the discarded `Popen` fires, hold the handle on
the `Tools` instance. **It fires. The build refused, and measured both arms in one session with one
variable changed:**

| | open handles |
| --- | --- |
| at rest | 162 |
| after 40 **discarded** spawns | 164 (**+2**) |
| after 40 more **held** spawns | 244 (**+80**) |

Holding trades a warning that is ignored under default filters and is stderr-only — so it cannot
corrupt the stdio transport — for **two leaked handles per approval for the life of the server**, and
it re-weakens the property the deletion just strengthened: **the server holds no object referring to
that window.**

**Owner's ruling: the deviation STANDS.** *"A controlled measurement beating a plan instruction written
from expectation is the rule working exactly as intended."* ⛔ **Do not reinstate the handle from the
plan text.**

### 3. E-1 — FIX, and NOT by moving the boundary a fourth time

**Owner's ruling, and the reasoning is the deletion's own evidence:** the finding lives in three
functions readable in one sitting, where four rounds ago it was scattered across six places.

⛔ **But not by moving the boundary again.** *"Three consecutive designs have put it one statement off;
a fourth boundary is the wrong shape of answer."*

⭐ **REMOVE THE "BETWEEN".** Read the proposal file **first** — a read failure is environmental and
**must burn nothing** — then decide deliberately:

| Content | Action |
| --- | --- |
| **invalid** (digest, expiry, session, corrupt) | rename to **BURN**, then refuse |
| **valid** | rename to **CLAIM**, then follow through |

**The rename becomes the thing you choose once you know.**

⚠️ **Burn-on-refusal is PRESERVED as a chosen act, not a side effect of ordering.** The owner is
explicit: *"I am not dropping that property."*

**The test asserts the PROPERTY, not the instance: nothing fallible occurs after the irreversible
rename.**

### Stopping rule for the rounds that follow — recorded before they run

⛔ **A finding in the claim machinery AFTER this fix is PARKED, not fixed**, and written up for the
owner as *"is this design worth its surface"*. **Three boundary corrections is the pattern; a fourth
is the answer.**

### Round counts

| Reviewer | Rounds | Owed |
| --- | --- | --- |
| Codex | 1 | to dispositioned |
| Claude `/code-review` | 0 | **one scoped delta via `--resume`**, not a fresh pass |
| PR bot | 0 | after push |

---

## E-1 fix round — build report, 2026-08-18

Head `34441aa` → `5919331`. Five commits, LIGHT tier, plan `.claude/plans/e1.md` (conductor
self-approved, with the open decision taken and the rename-abort amendment in).

### E-1 — **FIXED**

| | commit | what it does |
| --- | --- | --- |
| 1 | `3666b1b` | `_claim` reads at rest and performs **exactly one** rename as its **last statement** |
| 2 | `a7559af` | `ProposalUnreadable`, the half that closes the loop rather than the burn |
| 3 | `b866fec` | the loser of the claim rename is told it lost; one message regression from commit 1 repaired |
| 4 | `9d48a38` | the property tests |
| 5 | `5919331` | `docs/slice2-mcp.md` — the ordering, the ninth refusal, three residuals |

**The regression proof the round owed.** Measured red on `34441aa`, green on `5919331`:

> `assert not Path(made.path_of(proposal.id, ".pending.json")).exists(), "stranded"`
> → `AssertionError: stranded`

and, from the fault-injection sweep, which was told nothing about E-1 and found it anyway:

> `AssertionError: failing builtins.open (step 10 of 50) stranded the proposal`

### The property test asserts the property, and here is how it fails if the property breaks

`Trace` derives what a claim can reach out to **from the module's own imports** — every plain function
in `hashlib`, `json`, `os`, `re`, `secrets`, `core.apply` and `core.schema`, plus `builtins.open`. On
this head that is **54 recorded calls**. Three assertions ride on it:

1. **exactly one rename**, to `.pending.json` when the content is valid and `.refused.json` when it is
   not — the owner's *the rename is the thing you choose once you know*, written mechanically;
2. **the call log after that rename is empty** — the invariant stated directly, so there is no
   fallible step left for a failure to arrive in;
3. **fault injection at all 54 steps** with an exception the store has no handler for, asserting each
   time that the proposal is at `.json` and never at `.pending.json`.

**A statement added after the rename next year joins that log by itself**, because the log is derived
from the imports rather than from a list of today's call sites — and (2) names it, and (3) strands on
it. Nothing has to be remembered.

⚠️ **What it does not cover, said rather than implied:** `datetime.fromisoformat` (a method on a C
type, unpatchable) and `os.path`'s pure string work. Both are reachable only *before* the rename, and
assertion (2) is what actually bounds the tail.

The behavioural table is separate and complementary — **13 rows**, every reachable exit of
`claim_then`, asserting one suffix present and the other two **absent**. Exactly **one** row was red on
`34441aa` (the environmental read), so the table is not over-fitted to the fix; the control row is what
stops the whole table being satisfiable by a store that refuses everything.

### Residuals recorded, all three in `docs/slice2-mcp.md`

1. **Windows `ERROR_SHARING_VIOLATION` on the claim rename** — new to reading first, because `open`
   omits `FILE_SHARE_DELETE`. Transient, self-clearing, safe direction. Traded knowingly.
2. **"Any claim consumes the proposal" is best-effort in one transient case** — the suppressed burn
   rename. Only `ApprovalMismatch` can be affected, being the only refusal that depends on caller
   input.
3. ⚠️ **The loop is closed at the READ, not at the rename.** A Windows ACL denying DELETE while
   permitting create would fail the *claim rename*; every approve gets `ProposalNotFound`, whose
   *propose again* loops — nothing burnt, nothing written, so the cost is an agent retrying rather
   than the owner losing proposals. POSIX cannot produce that ACL. **Not fixed**: the plan and the
   ruling both fix `_take`'s type as `ProposalNotFound`, and a third refusal type here would be the
   fix widening its own claim. It is inside the claim machinery, where the standing rule parks the
   next finding as a design question.

### Disputes and flags from the build

- ⚠️ **Commit 1 introduced a message regression and commit 3 repaired it, inside this round.** Moving
  the rename to the end also moved *where a consumed proposal is noticed*, from `_take` to the read,
  and `_parsed`'s `FileNotFoundError` branch answered with a bare `strerror` — losing the one refusal
  sentence `docs/slice2-mcp.md` quotes and #69's disposition rests on. Caught by writing the test
  before the message change, not by review.
- **`test_every_refusal_says_something_different` does not assert what its name says.** `str(cls("x"))`
  is `"x"` for all of them, so it asserts the class *names* are distinct. Its count moved 6 → 7 with
  the new type and its docstring was corrected to say what it actually checks. **Not repaired** —
  repairing it means rebuilding it around the real sentences, which is a different test and outside
  this round's scope.
- **No dispute with the plan or the ruling.** The shape, the amendment and the new type all held up
  under build.

### Measured line delta — `ast`, code vs docstring vs comment

| | code | docstring | comment | blank | total |
| --- | --- | --- | --- | --- | --- |
| `core/proposals.py` before | 275 | 208 | 5 | 95 | 583 |
| `core/proposals.py` after | 299 | 288 | 5 | 109 | 701 |
| **delta** | **+24** | +80 | 0 | +14 | +118 |
| `tests/unit/test_proposals.py` before | 219 | 79 | 24 | 105 | 427 |
| `tests/unit/test_proposals.py` after | 470 | 200 | 36 | 209 | 915 |
| **delta** | **+251** | +121 | +12 | +104 | +488 |

⚠️ **The plan estimated ~+8 executable lines for the source; the measurement is +24.** The estimate
covered `ProposalUnreadable` alone; the rest is the `was` keyword threaded through four helpers and the
`_parsed` split, which the plan described but did not count. **Ruling 1's subject is *surface a
reviewer keeps finding defects in*, and this removes a defect rather than adding surface** — but the
number is stated as measured rather than as predicted.

### Gates, as run, from the conductor's own shell on `5919331`

| Gate | Result |
| --- | --- |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 78 files already formatted |
| `mypy src` | Success: no issues found in 18 source files |
| `pytest -rs` | **1409 passed, 6 skipped** (baseline 1387 + **22** added; the six skips unchanged) |
| `pii_guard .` | 0 findings over tracked content (83 entries) |
| `pii_guard --range origin/main..HEAD .` | 0 findings (43 commits, 95 entries scanned) |

The 22 added tests: 1 E-1 regression · 1 unreadable-is-not-not-found · 1 retry-sentence · 2
claim-rename losers · 2 renames-once · 1 renames-nothing · 1 fault-injection sweep · 13 table rows.

⚠️ **One interpreter, and CI runs three.** Every number above is 3.12.13 on Windows, from the project
`.venv`, which was left as it was found — no `uv run --python` was issued anywhere. The property test
uses `monkeypatch` and `inspect` rather than `sys.settrace` **deliberately**: a trace-based version
would have made the assertion depend on line-event attribution, which moves between 3.10, 3.11 and
3.12, and that is exactly the *check whose definition comes from where it runs* hazard. **The claim is
still that the matrix has not run.**

### Round counts — unchanged by a build

| Reviewer | Rounds | Owed |
| --- | --- | --- |
| Codex | 1 | to dispositioned — a delta on this fix |
| Claude `/code-review` | 0 | **one scoped delta via `--resume`**, not a fresh pass |
| PR bot | 0 | after push |

---

## Codex round 2 (post-reset) — 2 findings, verified, ⛔ PARKED UNFIXED by the owner's standing rule

E-1's ordering defect is confirmed fixed and claim-rename failures abort correctly. **Both new
findings are in `core/proposals.py` — the claim machinery — so the standing rule applies:**

> *"a finding in the claim machinery AFTER this fix comes to me as 'is this design worth its surface'
> — park it, do not fix it, and write it up. Three boundary corrections is the pattern; a fourth is
> the answer."*

**Neither is fixed. Both are dispositioned as PARKED with the rationale below, and neither blocks the
push — the owner decides.**

### F-1 — [P2] `ProposalUnreadable`'s remedy is impossible for a pending claim

> When the file becomes unreadable after `_claim` has renamed it but before the spawned CLI calls
> `claimed()`, `_parsed(..., was=_PENDING)` reaches this branch. The proposal is already consumed at
> `.pending.json`, yet the exception says it is still approvable, that nothing was consumed, and to
> approve the same id again; **that retry can only hit `ProposalNotFound`.**

**Verified.** The message is unconditional — it never consults `was`. It is **correct for the at-rest
read and false for the pending read**, and the same sentence serves both.

⚠️ **This is the shape the ledger has recorded four times: one message, two states, true for one.**
It is L6 exactly — *"the post-commit message says the true thing for the path it is on"* — arriving in
a different function.

### F-2 — [P2] Invalid UTF-8 escapes the burn path — **and it is a regression the E-1 fix introduced**

> `json.load` raises `UnicodeDecodeError`, which is neither `OSError` nor `JSONDecodeError` and
> therefore misses this refusal… the raw exception leaves the corrupt file at `.json` and every retry
> repeats it, instead of choosing the required BURN rename and raising `ProposalCorrupt`.

**Verified empirically**, not by reading: `UnicodeDecodeError.__mro__` is
`UnicodeError → ValueError → Exception` — **neither `OSError` nor `JSONDecodeError`** — and
`json.load` over `b"\xff"` raises exactly it.

⚠️ **Before E-1, `_take` renamed first, so a corrupt file was burnt on the way past. Reading first
removed that accident**, and the ruling's *"content invalid → rename to BURN"* is therefore
**incomplete in the code**: one class of invalid content is not caught, so it is neither burnt nor
refused.

### Why these are parked rather than fixed — the argument the owner asked for

**Both are one-line-ish fixes.** F-1 makes the message consult `was`; F-2 adds `UnicodeDecodeError` to
the corrupt branch. **That is exactly why the rule exists**: every finding in this machinery has been
a small, obviously-correct, locally-justified change, and there have now been **nine of them across
six rounds**. The rule was set *before* this round precisely so the smallness of the next fix could not
be the argument for making it.

⚠️ **What is genuinely new, and is the owner's question:** F-2 shows the fix that removed one accident
**also removed a protection nobody had named** — burn-on-corrupt was riding on rename-first ordering,
undocumented, and the reordering dropped it. *That* is a fact about the design's surface rather than
about a missing `except` clause.

**Severity, stated plainly so the parking is honest:** neither writes anything, neither loses a
proposal to a burn, and neither can produce an unapproved write. F-1 costs an operator a confusing
sentence in a rare state; F-2 costs an agent a repeating refusal on a file that is already corrupt.
**Both leave the tree untouched.**

### Round counts

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | **2** | E-1 fixed; F-1 and F-2 **parked**, dispositioned, not blocking |
| Claude `/code-review` | 0 | **owed: one scoped delta via `--resume`** — next |
| PR bot | 0 | after push |

---

## Claude `/code-review` scoped delta — ⭐ ZERO new blocking findings

Run through `--resume` on the warm session, as the owner scoped it. **$8.03 against $42.36 for the
cold full-breadth pass** — the contract's own economics, measured on this branch.

**The five priorities were verified against the code, not assumed:**

1. **Nothing reaches a write without a human `y`.** A crafted `proposal_id` dies at `_claim`'s regex
   **before the spawn**, because the spawn is the claim's callee. Every handler in `_approve` routes
   to `_closed`, never to a write.
2. **Displayed vs written** — the same in-memory object is displayed and written; nothing re-reads
   between them. The fingerprint check precedes the session check, as stated.
3. **#69's bounded claim survives the worst race the reviewer could construct:** `Popen` raising
   *after* child creation, rollback restoring `.json`, a retry spawning a second console — **two live
   consoles, both answered `y`, and the second `consume` gets `FileNotFoundError` and dies before the
   write.**
4. **Ruling 1 / `priv`** — `people.py` is untouched in this delta.
5. **The property test has no hole in the property.** One more member of the documented tail found
   (`_ID.fullmatch`, unpatchable, pure computation, pre-rename only). One coverage note: faults are
   never injected *inside* the burn rename, but `_refuse` is structurally rename-then-raise, so
   nothing fallible follows it either.

**F-1 and F-2 were checked and neither is worse than recorded.**

### N-1 — [prose] `_approve`'s docstring asserts a guarantee the structure does not provide — ⛔ PARKED

> *"every region below ends at `_closed` rather than letting an exception reach `main`"* — false for
> six statements: the setup region (`config.load`, the two `ConfigError` raises, `apply.authorise`) and
> both `consume` calls, all of which reach `main`, which prints and returns 1 **with no `_closed`**, so
> the window vanishes with the refusal on it.

**The behaviour is already dispositioned** — D-2's console half, recorded in `docs/slice2-mcp.md`.
**What is new is the sentence claiming the opposite**, and this ledger's own C2-1 disposition sets the
standard: *"a comment asserting a structural guarantee the structure does not provide is worse than no
comment, because the next reader stops checking."*

**PARKED, and two rules agree on it:**

1. ⛔ The owner's standing rule parks findings in this machinery.
2. ⛔ **The conductor's documentation carve-out does NOT reach it.** *"The boundary is the file, not
   the size."* A docstring inside `cli.py` is **source**, and source is never the conductor's. The
   reviewer suggested the carve-out covers it; **it does not**, and taking that offer would have been
   the carve-out widening itself.

**It changes no behaviour and cannot produce a wrong write.** It is one sentence, and it is wrong.

### Round counts — every seat dispositioned

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | 2 | dispositioned — F-1, F-2 parked |
| Claude `/code-review` | **1** (scoped delta) | dispositioned — N-1 parked |
| PR bot | 0 | **next: push** |

**No blocking finding is outstanding on this head. Every finding any reviewer has raised is fixed,
filed or parked with recorded rationale.** The local gates are satisfied; the push follows.

---

## PR bot — 4 rounds on #74, then a conductor-owned diagnostic stop

| Round | Finding | Disposition |
| --- | --- | --- |
| 1 | date qualifiers dropped — an estimated 1856 read as exact | **FIXED** `50895c4` |
| 2 | the label's serialization is not injective | **FILED #75** |
| 3 | surname prefix dropped — *van Ashenmoor* unfindable | **FIXED** `6b6d238`, and it surfaced four more |
| 4 | a duplicate `eventref` counted twice | **FILED #76** |

All four threads answered and resolved. **0 unresolved.**

⚠️ **Round 3's fix is the shape that closes.** Told not to patch the named attribute, it derived the
whole name partition from the DTD — `first`, `call`, `surname*`, `suffix`, `title`, `nick`,
`familynick`, `@prefix`, `@connector` **in**; `group`, the date shape, `noteref`/`citationref`,
`@alt`/`@type`/`@priv`/`@sort`/`@display`/`@prim`/`@derivation` **out, each with a reason** — and
landed a **bounded** claim: *every part of the recorded name a person would type when looking for
someone is searchable*, never *"the name is complete"*.

**And it bound its source honestly:** the installed DTD hashes to `f212866f…` because it is CRLF;
**LF-normalised it is exactly `SOURCE_DIGESTS`' `98a4763424fe…`**, and re-deriving reproduces all three
frozen tables. It also recorded what the frozen table **cannot** answer — `SPECIFIED_ELEMENTS` stores
a content model as a *category*, so `<name>`'s children came from the DTD text — in the test's own
docstring.

### ⛔ Stopped at four, on the diagnostic rather than the count

**The backstop permits five.** The stop is the **conductor-owned** one: the severity gradient is
evidence about the approach. **Round 3 broke the tool's purpose; round 4 makes a hint over-report by
one.** `people.py` reads a DTD-defined format with many optional parts, and *"the reader handles every
declared part correctly"* is close to a claim over a space a reviewer can keep sampling — true every
time, never closing.

**The bounded answer is recorded in #76** and is a scheduling decision for the owner, with four rounds
of use-derived evidence behind it. It belongs after the demo, not in front of it.

### Final state — every seat dispositioned, nothing blocking

| Reviewer | Rounds | State |
| --- | --- | --- |
| Codex | 4 | dispositioned |
| Claude `/code-review` | 2 | dispositioned |
| PR bot | 4 | dispositioned; loop stopped on the diagnostic |

**Dispositioned-not-fixed: F-1, F-2, N-1 (parked by owner rule), #75, #76 (filed). None can reach the
write path.** CI's full matrix green on `6b6d238`. **Decision screen posted; the merge is the owner's.**
