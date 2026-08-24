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

## The comparison, and what it does not settle

⚠️ **An earlier revision claimed to withdraw the recommendation and left this heading saying
"Recommendation: A".** A reader would reasonably have taken A as the selected design, which is the
same defect this whole document is about: **the stated intent and the actual content disagreeing.**

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
- ⛔ **And A has the SAME race.** Its facts are gathered before the dialog too, so another approval
  can add the child between `Plan` and `execute(Plan)`. Obeying the stale Plan appends a duplicate
  reference; re-checking membership makes the write diverge from the approved preview. ⚠️ **A needs
  serialisation, revalidation or conflict handling exactly as B does** — an earlier revision
  attributed this race to B alone, which was wrong and flattered A.

⚠️ **So the recommendation is now weak, and saying otherwise would be dishonest.** Across three
review rounds, **every one of the four original reasons for preferring A has been removed**: the
approval-binding claim, the `caller_preview` cost, the R7 asynchrony, and now the zero-main-thread
-cost claim. What is left is two options with real costs on both sides and no clear winner on the
axes this plan chose.

⭐ **That is a result, not a failure of the plan.** The honest conclusion is that **the choice between
A and B is a judgement the owner has to make on grounds this document has not established** — and
that a build proceeding on either needs its own measurement of the main-thread cost first, because
that number is now the only thing separating them and nobody has taken it.

**C is not an alternative to either — it is how whichever is chosen gets verified.** A's residual
risk is `execute()` drifting from `Plan`; B's is the dry run and the write observing different facts.
⭐ **In both cases the check is the same shape**: run the two against a fake tree and require their
outputs to match. That is a *bounded* property, because it compares two concrete outputs rather than
quantifying over inputs.

⚠️ **What I am not recommending is doing this before it is worth it.** Two of the three findings are
already fixed and the third is a P2. **The argument for A is not the three bugs — it is that the
class has no fixed point**, and the next feature on this path (#105's family events) adds a fourth
thing for the two implementations to disagree about.

## ⭐ The recommendation: Option B, and the requirement it stands or falls on

**B — the dry run.** Not because the comparison above found a winner on cost; it did not, and that
section stands. **B is recommended on a different axis entirely, and it is the axis this class is
about.**

⛔ **A and C both leave two descriptions of one operation and try to keep them in step.** A adds a
`Plan` and hopes `execute(Plan)` obeys it. C adds a test and hopes the test covers the case that
diverges next. **Both are the current arrangement with more machinery** — and the current
arrangement has produced six instances, each individually a reasonable local decision.

⭐ **B is the only shape in which there is one description.** The writer says what it would do; the
preview renders that. There is no second implementation to disagree with, because there is no second
implementation.

⚠️ **That argument survives everything the review rounds removed.** Three of A's four advantages were
withdrawn as unfounded, but none of the withdrawals touched this: *a derived description cannot
disagree with what it is derived from.* The cost comparison is genuinely open and is the owner's
call; the structural argument is not open, and it points one way.

---

## ⛔ What does this design make possible that shouldn't be?

**This is the question the plan gate exists to ask, and it is why this section is longer than the
recommendation.** For #111 the same question surfaced *"two approvals can be in flight at once"* —
one requirement whose four consequences then cost four review rounds each. Asking it here, of B:

### 1. ⛔ A dry run that writes

**The design puts a code path whose entire purpose is to NOT write inside the writer that does.**
Every branch of `write` must honour the flag; one that forgets is a silent, unapproved mutation —
and it is the branch nobody thought about, because the branches people think about are the ones they
write the flag into.

⚠️ **A boolean parameter is not a bound.** It is the same shape as `_IN_FLIGHT` before #111: a
requirement held by every call site remembering it.

⭐ **So the requirement this design stands or falls on:**

> **The dry run must be incapable of writing BY CONSTRUCTION, not by a flag.** It runs against a
> database object that has no `commit_*` and no `add_*` — a recorder, not the real handle. A branch
> that forgets the flag then **raises** instead of writing, and the failure is loud, immediate, and
> impossible to ship.

⚠️ **If the build cannot achieve that, B is worse than the status quo**, because today the writer
never runs except to write. That is the falsifier for this recommendation, and it should be settled
before anything is built.

### 2. ⛔ The renderer acquiring a Gramps dependency through the back door

`document.py` imports no `gramps` and no `gi`. **That is load-bearing** — it is what lets the whole
renderer run under CI, and it is the constraint that makes this problem hard in the first place.

⚠️ **B threatens it in a way A does not.** If the dry run's output carries Gramps objects — handles,
`EventRoleType`, `Person` — then the renderer must understand Gramps types to render them, and the
import creeps in one field at a time. **Nothing structurally prevents that**; it would arrive as a
convenience in a single field and be discovered when CI stops running the renderer.

**Requirement:** the dry run returns **plain data** — strings, ints, lists, dicts — and a test asserts
`document.py`'s import closure stays free of `gramps` and `gi`. ⭐ *That test already has a precedent
in this repository*: `tests/fixtures/host_sources.py` already decides what counts as host code.

### 3. ⛔ Two observations of a tree that can change between them

The dry run happens before the dialog; the write happens after. **A modal dialog is an unbounded
interval** — `confirm` spins a nested GTK main loop.

⚠️ **This is the one thing B does not fix on its own**, and pretending otherwise would repeat the
mistake this document is about. If another approval adds the child between the dry run and the
write, the writer skips it and **the approved account is wrong again** — the exact class.

⭐ **It is already mitigated, and by something that exists**: #111 serialised approvals, so a second
`_present` is refused rather than interleaved. **B's correctness therefore depends on that guard
continuing to hold**, which is worth stating in the build's own criteria rather than assumed. ⚠️ And
A has this race identically, as the comparison above records — it is not a reason to prefer A.

### 4. ⚠️ A cheap dry run becomes a frequently-called one

If rendering a preview means running the writer, then **every proposal executes the writer's code
path on the GTK main thread**, inside the same `idle_add` callback R8 caps. Today the renderer is
pure and the writer runs once per approved write.

**This is a cost to measure, not a defect** — but it is a cost the current arrangement does not have,
and the comparison above already identifies main-thread cost as the only axis separating the options.
⛔ **It should be measured before the build, not after**, because it is the number the whole
comparison turns on and nobody has taken it.

---

## ⭐ What the answer changes about the recommendation

**Nothing, and that is the point of asking.** B is still the recommendation — but it now comes with
**one requirement that is load-bearing** (§1: unwritable by construction), **one property that must
be defended** (§2: the renderer's import closure), **one dependency on existing work** (§3: approvals
stay serialised), and **one measurement owed before the build** (§4: main-thread cost).

⚠️ **A plan that had described B's mechanism without asking this question would have shipped §1 as an
afterthought** — a boolean flag, honoured everywhere it was thought about. That is what #107 was, and
#107 approved the design that produced most of #111's review rounds.

## ⛔ What this plan does not settle

- **The `Plan` shape.** Naming its records is design work and belongs in the build's own gate.
- **Whether the journal stores the Plan instead of the rendered text.** ⭐ It probably should — a
  structured undo record is worth more than prose — but that is a change to the undo mechanism and
  it needs its own decision.
- **Whether this lands before or after #105.** Sequencing is the owner's.
