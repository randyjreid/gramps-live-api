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
