# #106 — making the preview and the write agree by construction

⚠️ **A PLAN, awaiting the owner's approval. Nothing here is built.** ⛔ **And it is deliberately a set
of options with a recommendation, not a design** — the choice belongs to the owner.

## The problem, stated as a class

Three findings in one code path, in three different directions:

| | |
|---|---|
| round 6 | the preview **denied** an addition the writer makes |
| round 5 (open) | the preview **asserted** an addition the writer skips |
| round 7 | the preview **counted** additions the writer collapses |

⭐ **None is a mistake in either implementation alone.** `write` was right all three times; `preview`
was locally reasonable all three times. **What was wrong was the relationship between them**, and
there is no artifact that holds a relationship.

**The property is maintained by two implementations agreeing by hand.** `document.preview` describes
what it *believes* will happen; `writer.write` does what it does. Nothing holds them together.

⚠️ **And it is not cosmetic, because the account IS the undo mechanism.** R7 established that Gramps'
own undo is a process-local list discarded on close, so the journal — which stores **the approved
preview** — is all that survives a session. A preview that overstates an addition produces a journal
entry describing a change the tree never received, and a hand-undo driven from it would try to remove
something that was there before.

## ⛔ The constraint that makes this hard

**`document.py` imports no `gramps` and no `gi`.** That is load-bearing: it is what lets the whole
renderer, the validator and the journal run under CI on an ordinary machine. The writer, by
definition, cannot make that promise.

⭐ **So "one structure both consume" must be something the writer declares or produces without the
renderer needing Gramps to read it.** That single sentence is the entire design problem.

---

## The options

### Option A — the writer emits a PLAN, then executes it

`write` splits into `plan(graph, tree_facts) -> Plan` and `execute(Plan)`. `Plan` is plain data —
dataclasses or dicts, no Gramps types. The preview renders **the Plan**, not the graph.

**What it buys.** The disagreement becomes structurally impossible for anything in the Plan: the
owner reads exactly the decisions the writer will act on, including *"this child is already a member,
nothing to do"*.

⚠️ **What it costs.** `plan()` needs tree facts — which children a family already holds, which ids
resolve — so the split is not free: the read has to happen before the dialog, and its results have to
travel. **`Resolution` already does exactly this for ids**, so this is an extension of a mechanism
that exists rather than a new one.

⛔ **The honest risk:** `execute()` could still diverge from `Plan`, and nothing structural stops it.
The gap narrows from *"two descriptions of an operation"* to *"a description and its execution"*,
which is much smaller but not zero.

### Option B — a dry-run mode on the writer

`write(dbstate, graph, dry_run=True)` performs every decision, records what it *would* do, and
commits nothing. The preview renders that record.

**What it buys.** One code path, so agreement is exact by construction — the strongest guarantee
available.

⛔ **What it costs, and why this is not recommended.** The dry run must execute **inside Gramps on the
main thread, before the dialog opens** — so the preview can no longer be rendered by the MCP server
for `propose_document`, which today renders it with no Gramps at all. ⚠️ **That breaks the approval
binding**: slice 2's whole point is that the dialog renders from the server's stored record. A dry run
also doubles the main-thread work R8 caps, for every proposal.

### Option C — assert agreement in tests rather than in structure

Keep both implementations, and add property tests that run a graph through a fake writer and the
renderer and require the counts to match.

**What it buys.** Cheap, no runtime change, catches the three known directions immediately.

⛔ **What it costs.** It is the enumerated answer. It catches directions somebody thought of — and
this class has already produced three nobody thought of. ⚠️ **It also asserts against a *fake*
writer**, so it can pass while the real one diverges, which is the passes-for-an-unrelated-reason
failure the privacy tests already had to be rescued from once.

---

## ⭐ Recommendation: A, with C's tests as the check on it

**Option A is the only one that removes the class without breaking the approval binding.** The Plan
is plain data, so `document.py` keeps its no-Gramps promise and the MCP server can still render a
preview from a stored record.

**And C is not an alternative to A — it is how A is verified.** The residual risk in A is
`execute()` drifting from `Plan`; a property test that runs both against a fake tree and requires the
Plan to match what execute actually did is exactly the check for that, and it is a *bounded* property
because it compares two concrete outputs rather than quantifying over inputs.

⚠️ **What I am not recommending is doing this before it is worth it.** Two of the three findings are
already fixed and the third is a P2. **The argument for A is not the three bugs — it is that the
class has no fixed point**, and the next feature on this path (#105's family events) adds a fourth
thing for the two implementations to disagree about.

## ⛔ What this plan does not settle

- **The `Plan` shape.** Naming its records is design work and belongs in the build's own gate.
- **Whether the journal stores the Plan instead of the rendered text.** ⭐ It probably should — a
  structured undo record is worth more than prose — but that is a change to the undo mechanism and
  it needs its own decision.
- **Whether this lands before or after #105.** Sequencing is the owner's.
