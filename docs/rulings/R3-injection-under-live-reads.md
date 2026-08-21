# R3 — Injection under live reads: bound the damage at the write, fence as defence in depth

**Ruled 2026-08-21.** This page records a decision. It is not a proposal and it is not argued again
here. The case that was put is in `.claude/decisions/R3-injection-under-live-reads.md`.

⚠️ **When ruled, nothing described below was built.** There is no live read tool, no approval dialog
and no write path in the host.

---

## The ruling

**D + A.**

**D — the damage is bounded at the write.** Injected text living in the tree may influence what the
agent **proposes**. It is not treated as preventable at the read, and no attempt is made to
sanitise, detect or classify it on the way in. What it cannot do is reach the tree without a human
having seen exactly what would be written.

**A — structural fencing, as defence in depth.**

### ⛔ A's bound, recorded because getting this wrong is how a guard gets deleted later

> **Structural fencing raises the cost of an attack and closes no class of it. It is never to be
> recorded as though it closed anything.**

### ⛔ The acceptance criterion

> **No byte reaches the tree that was not rendered in full to the human in the approval dialog.**

⭐ **This is the direct regression test for the slice-1 elision defect**, where the approval compared
sentences elided at 60 characters, and everything past the limit was written **without having been
shown**. The criterion is phrased over bytes rather than over sentences for exactly that reason: a
comparison that operates on a shortened rendering is not a comparison of what will be written.

## Two accepted residuals

### 1. D does nothing for egress

**Text that makes the agent emit tree contents is a read-side attack.** Nothing is written, so no
dialog opens, so the write-side bound never engages.

**Three egress bounds exist, and all three live in `src/gramps_live_api/core/people.py`:**

1. **`priv`** — which people may be returned at all;
2. **the required search term** — there is no way to list everybody. `SearchTermRequired` is
   documented as *"a privacy control rather than an ergonomic one"*, because *list everyone* would
   put the whole tree into a model's context in one call;
3. **`RESULT_CAP = 25`** — how many one call returns, documented as *"a cap rather than a page"*.

⚠️ **None of the three exists in `src/gramps_live_api/host/`**, which is what P2 below is about.

### 2. Live reads open an interval that did not exist before

**A person added but not yet flagged is readable until flagged.** Under the export model the flag
necessarily preceded the snapshot, because the snapshot was taken after the fact. Reading the live
tree removes that ordering guarantee — the window is small, real, and inherent to reading live data
rather than a defect in any component.

## ⛔ Two named build preconditions

**Neither is a ruling. Both block the first build that relies on this one.**

### P1 — the console→dialog walk-through

The bounded guarantee is stated in `docs/slice2-mcp.md` in terms of **four mechanisms**: the
operation is rendered by a **separate process**, out of the **claimed file on disk** rather than out
of anything the agent passed to `approve`, into a **console the server holds no handle on**, with
the keystroke read from **that console's own stdin**.

⚠️ **R8 deletes all four.** An in-process HTTP host inside Gramps has no separate process, and an
approval dialog on the GTK main thread is not a console the server holds no handle on.

**The first build that moves approval into a Gramps dialog must walk the four across and record
which survive, which need new machinery, and which are lost.** ⭐ **The ruling does not change based
on the answer; the build does.**

### P2 — the egress bound has no implementation on the live path

**Three mechanisms live in `src/gramps_live_api/core/people.py`** — the export reader, **which
`docs/roadmap.md` says slice 4 dissolves:**

1. **the `priv` exclusion**;
2. **the search-term requirement** — no term, no listing;
3. ⭐ **the result cap** (`RESULT_CAP = 25`). Its own docstring says why it is a bound and not
   pagination: *"A cap rather than a page: every name it returns enters a model's context."*
   `docs/slice2-mcp.md` records the cap as part of what bounds data entering the model, alongside
   the search term and the privacy flag.

⚠️ **Nothing in `src/gramps_live_api/host/` implements any of the three.** **The first live read
tool must carry all three, or R3's egress bound ships with nothing behind it.**

⛔ **Naming all three matters because two of them bound volume rather than membership.** An
implementation can honour `priv` perfectly, return every non-private match, and satisfy a
precondition written as *"carry the privacy flag"* — while a broad search term walks an unbounded
number of records into a model's context. **A bound on WHO may be returned is not a bound on HOW
MANY.**

## Accepted risks

- **An attacker who can write into the tree can shape proposals indefinitely**, and this ruling
  accepts that. What it denies them is a silent write.
- **The human is the last check**, and the residual is item 3 of the original argument: a proposal
  put in front of a tired owner. **No window closes that.**
- **A is explicitly not load-bearing.** If it is ever cited as closing a class of attack, that
  citation is wrong — see A's bound above.

## What this does not settle

- **What the approval dialog looks like**, or how "rendered in full" is satisfied for text longer
  than a dialog. **The criterion is a property, not a design.**
- **Whether the prose surface — note, source and citation text — arrives at slice 4 or slice 5a.**
  The trigger recorded in `docs/slice2-mcp.md` has fired; where the tool lands in the order is the
  roadmap's business.
- **Nothing about `priv` itself** — its semantics, or what happens when a record is flagged after
  being read.
