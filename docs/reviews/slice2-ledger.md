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
