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

**What it buys.** One code path, so the dry run and the write share every decision.

⛔ **CORRECTED: "exact by construction" was too strong.** The dry run happens before `confirm`, whose
modal dialog spins a nested GTK loop — and R8 establishes that other `GLib.idle_add` callbacks run
during that loop. `_document` schedules approvals without serialisation, so **a second approval can
write while the first dialog is open**, and the first write then sees different membership or
resolution facts than its own dry run did. ⚠️ **B needs serialisation, a post-approval re-check, or
execution of the recorded operations before it can claim exactness** — which makes it a larger build
than "one code path" suggests.

⛔ **CORRECTED after review. An earlier draft rejected this option for a reason that does not exist**,
and the correction matters because it changes the comparison the owner is deciding on.

That draft said a dry run **breaks the approval binding**. It does not. `propose_document` stores the
graph; `approve_document` reloads **the stored graph**; `_present` renders the dialog inside Gramps.
⭐ **The server's `caller_preview` is explicitly not the approval surface** — the dialog has never
rendered from anything an agent passes at approval time. **A dry run performed in `_present`, from the
stored graph, preserves that guarantee exactly.**

**What it actually costs, which is the only objection that survives:**

- ⛔ **It doubles the main-thread work, per proposal.** Gramps' connection is thread-bound, so the
  dry run cannot leave the main thread, and R8 caps what one callback may do.
⛔ **CORRECTED after review. Two costs listed here were not real, and both of them were propping up
the recommendation.**

**It was claimed that B would cost `caller_preview` its ability to describe attachment decisions.**
`caller_preview` cannot do that today: it renders the graph and describes every existing-family node
as *adding children*, unconditionally. The membership check happens later, inside `writer.write`.
⚠️ **So this is not a cost of B at all** — and worse, A only gains that ability by adding a
proposal-time trip to Gramps, which B could equally use to run the dry run there. **The purported
loss was a differentiator that does not exist.**

**It was also claimed that R7 makes the write path asynchronous, so B would get cheaper once R7
lands.** ⚠️ R7's ruling does no such thing: it moves *the backup* onto a worker through a second
read-only connection. `writer.write` still runs inside `GLib.idle_add`, and R8 still requires it to.
**The asynchrony belongs to the backup's own build, not to the write**, and conditioning a
recommendation on it was conditioning it on a mechanism neither planned nor permitted by the cited
ruling.

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

⚠️ **The recommendation is now weaker than it was, and that is the honest position.** Two rounds of
review have removed three of the reasons originally given for preferring A: that B breaks the
approval binding (it does not), that B costs `caller_preview` an ability it has (it has not), and
that R7 would make B cheaper (it would not).

**What actually survives as a difference — and it is less than any earlier draft claimed:**

- ⛔ **A is NOT free of main-thread work either.** `plan()` needs live tree facts — which children a
  family already holds, which ids resolve — and every such read must be marshalled through
  `GLib.idle_add`, exactly as `_document` already does. **Only the Plan's construction, after those
  facts are materialised, leaves the main thread.** So the comparison is A's fact-gathering against
  B's dry run, not "extra work" against "none".
- ⛔ **B is NOT exact by construction**, for the nested-loop reason above.

⚠️ **So the recommendation is now weak, and saying otherwise would be dishonest.** Across three
review rounds, **every one of the four original reasons for preferring A has been removed**: the
approval-binding claim, the `caller_preview` cost, the R7 asynchrony, and now the zero-main-thread
-cost claim. What is left is two options with real costs on both sides and no clear winner on the
axes this plan chose.

⭐ **That is a result, not a failure of the plan.** The honest conclusion is that **the choice between
A and B is a judgement the owner has to make on grounds this document has not established** — and
that a build proceeding on either needs its own measurement of the main-thread cost first, because
that number is now the only thing separating them and nobody has taken it.

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
