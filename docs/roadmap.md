# Roadmap — a proposal

> ⚠️ **This is a PROPOSAL. Nothing in it has been applied.** No milestone has been edited, no issue
> closed or moved, nothing rescheduled, no work started on its account. It transcribes the
> conclusions of `.claude/plans/gap-analysis.md` — an independent decomposition, a critique of the
> advisor's roadmap, and the ruling on its tail — into an order, a set of unparking triggers, and a
> list of rulings the owner owes. **The owner reads it and rules.**
>
> Where the analysis left something as *the owner decides*, this document says so and does not
> choose. Where the analysis could not determine something from the code, this document names the
> measurement and does not guess it.
>
> ⛔ **There are no dates, no estimates and no effort figures anywhere below, because none exist.**

---

## The destination

Everything here is measured against one sentence, the owner's own:

> *"I photograph or transcribe a census record. I want an agent to read it, work out what it says
> about people in my tree, work out what is already recorded and what is not, and make all the
> necessary updates — new people, events, places, the source, the citation, the image attached — as
> ONE thing I review and approve, not twenty."*

The last five words are the load-bearing ones. They are why the batch question sits near the front
of this document rather than near the end.

---

## What works today

**Slice 1** — `docs/using.md`. A note proposed for a person as a JSON file, one sentence shown at a
terminal, `y`, a write through Gramps' own plugin door inside a `DbTxn`, and a read-back from a
second fresh Gramps process. Two undo records left behind.

**Slice 2** — `docs/slice2-mcp.md`. The same write with an agent in front of it: three MCP tools
(`list_people`, `propose_note`, `approve`), the operation never travelling through the agent, and
the approval taken as a `y` at a console the agent holds no handle on and learns no outcome from.

⚠️ **Both demos end in a copy, and that is the honest statement of what shipped.** Every write goes
into a tree the owner blessed by hand with a `.gramps-live-api-copy` sentinel file; the live tree is
unwritable by construction, and **nothing has ever been written to the owner's real genealogy.**

⚠️ **And slice 2 reads a snapshot** — slice 1's `preview`, `apply` and `check` read no export at all,
and its read-back comes from the written tree. `list_people` reads a Gramps XML export the owner
produced by hand, not the database. That has two costs already recorded: the tool cannot see its own writes until the
owner re-exports from inside Gramps (#77), and a `priv="1"` flag set *after* the export was taken is
a **privacy fail-open** — which is why `check` fails rather than warns on a stale export.

So the current product is a demonstration artifact. Slices 3 and 4 below are what make it genealogy.

---

## The order

The analysis's amended order, after ruling on the advisor's. At a glance:

**3** backup → **4** the live tree *(mechanism ruled first)* → **4½** batch ruling and batch spine →
**5a** thin read surface → **5** sources and citations → **6** events and dates → **7** people and
relationships → **8** analytics → **9** media → **10** matching → **11** the census demo.

Three notes on the numbering before the detail:

- **4½, 5a and 9–11 are not new slices.** 4½ and 5a are the two insertions the analysis's ruling on
  Question A produced. 9, 10 and 11 are the first decomposition's slices 8 (media), 9 (matching) and
  11 (the census demo), renumbered into this order.
- **The first decomposition's slice 10, "the live tree, backed up", has dissolved into 3 and 4.**
  It is not dropped; the amended order enacts the graduation at the front instead of holding it as a
  late slice.
- ⚠️ **Two rulings must land before any of this starts** — slice 4's read mechanism and the batch
  shape. They are listed as rulings, further down, and they are not work.

### 3 — "My tree came back from a file."

**Demo.** Ask for a backup, get one, restore it into Gramps as a working tree that opens. The owner
has personally seen his own tree come back.

**What it settles.** Phase 2's own precondition — *no write endpoint ships before this*. Bounded
deliberately: **one backup, one restore, verified by the owner in Gramps.** Not retention, not
scheduling, not incremental anything.

**What it unparks.** Nothing yet. It is what makes slice 4 approvable, and it is the reason #25's
destructive operations can stay later.

**Depends on.** Nothing. **It is startable the moment the owner says go.**

⚠️ **It is a precondition of slice 4 specifically, not only of destructive operations generally.**
Two independent reasons, both from the analysis: at batch scale, hand-undo of *constructive* writes
is already unrealistic (twenty interlinked objects, one undo record shaped for one note), and
`update_*` operations arriving in slices 6–7 **overwrite recorded data** — delete's smaller sibling.

### 4 — "My real tree." *(mechanism ruled first)*

**Demo.** Add a person in Gramps, immediately ask the agent about them, it finds them. Add a note. A
backup is taken automatically first. The note is in the tree the owner actually works in, and he
keeps it.

**What it settles.** Graduation. Every earlier slice's output stops being a rehearsal artifact.

**What it unparks.** #77 (export staleness) dissolves; #76 goes moot rather than deferred, on the
condition that this slice does **not** keep the export reader; most of `core/people.py` goes with
it. A live `priv` flag kills the stale-export privacy fail-open outright rather than detecting it —
a real safety gain, and worth claiming.

**Depends on.** Slice 3. **And on two rulings, neither of which is an implementation detail:**

- ⚠️ **The read mechanism (ruling R2).** *"Ask Claude about them"* is a read of the live tree **while
  Gramps holds it open**, and **every door that exists is closed to it**: the CLI tool door refuses a
  locked tree by design and bans `--force-unlock` "ever"; the in-process channel went down with
  Phase 5, on a reason that covers the endpoint half and **not** this one — see that section below;
  a second-process open of a tree Gramps holds is what the one-writer rail forbids (`docs/using.md`:
  *"we never break Gramps' lock"*). **This slice is "resurrect the live architecture" wearing a
  demo's clothes**, and it must be put to the owner as a reversal of a standing ruling with the door
  named — not implied by a demo sentence.
- ⚠️ **The guarantee downgrade (part of ruling R4).** The sentinel makes the live tree unwritable *by
  construction*; the offered replacement, backup-taken-first, is **weaker in kind, not equivalent**.
  *Unwritable-by-construction* is a guarantee about what can happen; *recoverable-after* is a
  guarantee about what can be undone, and it still costs the owner noticing, choosing, and knowing
  which backup predates the damage. That may be exactly the right trade — it is what "the notes
  count" costs — but **it should be approved as a downgrade, in those words.**

⚠️ **The cost this slice does not otherwise name:** after it, every subsequent vocabulary slice's
first bugs land in the real tree. Mitigated only by auto-backup-before-write — and **only for as
long as the backup stays per-write** rather than per-session.

⭐ **Keep the blessed-copy path alive after this slice as a rehearsal space.** The analysis is precise
about what the copy is good for: it is *misleading* about workflow truths (staleness, the export
dance, what the owner tolerates) and **perfectly sound** about the correctness of new machinery —
renders, validation, the batch linker. First-run defects are cheaper to find there.

### 4½ — "Two notes, one console, one yes."

**Demo.** The agent proposes a batch of two notes — the only writable type today; one console shows
both sentences in full; one `y` writes both inside **one** `DbTxn`; `n` writes neither; one undo
record and one result record naming both notes.

**What it settles.** The whole batch spine on the existing vocabulary: batch digest, batch store
record, batch display, one-transaction apply, batch result and undo shapes. **This is the slice the
target sentence's "not twenty" lives in.**

**What it unparks.** **#66** — the operation currently rides in the Windows environment block, capped
at 32,767 characters, and the batch is what breaks it; the remedy is already designed in #66 (a file
whose path is the variable). **#73** — the write path is being reshaped anyway, so `_write_and_verify`
serving two callers gets answered inside this slice's plan gate rather than before or after it.

**Depends on.** Slice 4, ruling R1 (the batch shape), and the `DbTxn` abort measurement (M1).

⚠️ **This is the ordering decision, and building operation types before it is the single most
expensive mistake available.** #22 and #23 as specified register nine operation types on a reference
model (`object_type` + `handle` + `gramps_id`, **both identifier halves required**) that can only
name objects **already in the tree**. A census batch is mostly about objects that do not exist yet:
the new person's events reference the new person, the citation references the new source, and Gramps
mints those handles and IDs *inside the transaction*. Built in the specified order, all nine types —
reference fields, fixtures, negative tests, renders — get reworked.

**The bill, named rather than asserted:** the reference model in `core/schema.py`; every operation
type's fixtures and negative cases; the proposal record shape in `core/proposals.py` (versioned, so
cheap by design); the MCP tool surface in `server.py`; the console display in `cli._approve`; the
apply dispatch and the `Tree` protocol; the undo and result record shapes; and #66's transport. What
limits it is this project's own discipline — the structural tests are registry- and
declaration-derived, so the matrices **regenerate** rather than being rewritten. **The unrecoverable
cost is the fixtures and the tool surface**, nine types wide, and entirely avoidable by ruling first.

**And its own failure mode, stated:** the batch layer is a mini-linker. This project has measured
what happens to small cross-boundary machinery under review — the outcome layer drew five of seven
findings and was deleted. Batch-level validation and reference resolution **will draw rounds.** They
are bounded, though: the rules are enumerable and close.

### 5a — "The tree answers back."

**Demo.** The agent is asked *"what do we already know about her?"* and answers from new read tools:
the events, sources, citations and notes of one person — **with their identifiers.** No writes.

**What it settles.** Query-before-propose, and the evidence surface that matching and duplicate
detection stand on.

**What it unparks.** ⚠️ **It is what stops slices 5–7 re-creating #64.** Citing anything on an event
needs an `ObjectRef` to that event — `object_type`, `handle` and `gramps_id`, all required — and **no
read surface returns an event's identity.** An event's handle is invisible in the Gramps UI *by
design*, which is #64's own premise: the owner cannot supply it and no tool returns it. Without this
fragment, slice 5's demo is the manual handle hunt again, for events.

**Depends on.** ⭐ **Ruling R3 — the injection widening — and nothing else.** `docs/slice2-mcp.md`
records the trigger in exact words: *any tool that returns note, source or citation text.* This is
that tool. The ruling is owed **before** the slice is built, because tools built before it are tools
built against an unrecorded trust model, which is how a guard gets removed later.

⚠️ **If slice 4's live read lands first, the trigger fires there instead** — live reads widen the
channel from two export fields to everything the tree holds. **Whichever tool ships first, that is
where the ruling is owed.**

### 5 — "The record itself enters the tree."

**Demo.** *"I found her in the 1901 census — add the source and cite it on her birth."* `add_source`
and `add_citation` become writable; the transcription is stored as a note **on the source**; the
citation attaches to an event.

**What it settles.** The evidence-side vocabulary, and the citation plumbing every `FACT_ASSERTING`
operation requires. ⭐ **The advisor's line is right and worth keeping verbatim:** `FACT_ASSERTING`
today contains only `add_citation`, which can only *attach* evidence that already exists — **the
provenance rule is real against a vocabulary that cannot create its own evidence.** This is the right
first vocabulary widening.

**What it unparks.** #23 (evidence-side operations), reshaped onto the settled reference model. And
the `add_note` **target** widening — person-only today, and the conventional home of a census
transcription is a note on the *source*, which puts that widening on the critical path.

**Depends on.** 4½ (the demo is a chain — create the source, create the citation *referencing the new
source*, attach it), 5a (the event identity), and the census-line walkthrough, which fixes this
slice's exact row list.

⚠️ **Without 4½ and 5a this demo is not performable as spoken.** Under one-op-per-approval plus the
owner-ruled no-outcome channel, it is three consoles with the owner hand-carrying each minted Gramps
ID from window to transcript between them. One request in, a courier loop out.

### 6 — "An estimated 1867 stays estimated."

**Demo.** A birth event with an estimated date appears on a person, and Gramps displays the estimate
as an estimate.

**What it settles.** The date model, with its ruling already made: **mirror Gramps' own model,
calendar field open, no default, byte-faithful round-trip** — endorsed by the analysis, and
consistent with D1's failed import check.

**What it unparks.** **#21.** ⭐ **Its value-type half is dependency-free and should be built in
parallel during slices 3–4 rather than queued behind them** — the analysis calls the serialisation
behind 3–4 a cheap concurrency loss.

**Depends on.** Slice 5 — `add_event` is `FACT_ASSERTING`, so it hard-depends on the citation
vocabulary, and that ordering is forced rather than chosen. The *operation* half also waits on 4½'s
reference model.

⚠️ **The demo is deliberately trimmed to a person-attached, placeless event.** The advisor's wider
sentence — *"add her marriage, about 1893, in Cork"* — trips three things this slice does not own: a
marriage attaches canonically to a **Family** object (the `add_family` hole), *"in Cork"* is a
**place** and no slice owns `add_place`, and the citation dependency above.

⚠️ **A requirement on #21 that nobody has stated:** the date model must be **wire-expressible in the
operation vocabulary** — an agent builds it through `propose_*` arguments — not merely constructible
in Python. #21's out-of-scope note assumed a parser would be inherited from Gramps; D1's import check
**failed**, the hand-rolled fallback applies, and **no parser is inherited.** Survivable, because the
extraction agent can emit structured date kinds directly — but only if the wire can express them.

### 7 — "Her son Thomas, and the family he belongs to."

**Demo.** *"Add her son Thomas, born 1895, and link him to the family."*

**What it settles.** The identity-side vocabulary under two criteria the analysis endorses: **an
operation's schema alone determines the write**, and **unknown is a value rather than a default** —
a defaulted relationship kind would assert biological parentage nobody agreed to.

**What it unparks.** **#22**, reshaped. And **`add_family` as a required vocabulary row**: under this
slice's own ruled criterion, a link operation whose apply-code silently creates a Family object
writes something its schema never said. ⚠️ *Which* of those two is Gramps-native is a measurement
this project has not taken (M3).

**Depends on.** 4½, 5, 6.

⚠️ **This demo is the batch problem in its purest form** — `add_person` + `add_event` referencing
*the person being created* + `link_child_to_family` referencing him again and referencing a family
that, under today's vocabulary, nothing ever created. **Provisional identity is not an edge case of
this demo; it is the demo.**

### 8 — "Which of my direct ancestors have no sources?"

**Demo.** The turn from data entry to research assistance: analytics over the tree, read-only.

**What it settles.** Nothing on the census path. ⭐ **It is kept for its own sake — the analysis calls
it genuinely last and plausibly where the long-term value lives.**

**What it unparks.** Nothing.

**Depends on.** 5a's read surface. **This slice is what remains of the advisor's slice 8 after the
split**: the identity-and-evidence fragment moved forward to 5a because slices 5–7 need it; the
analytics stayed here.

### 9 — "The photograph is in the tree."

**Demo.** The census image becomes a Gramps media object attached to the source, and the owner clicks
it open in Gramps.

**What it settles.** Media creation and **file custody** — ⚠️ **the first write in this project that
is outside the database and outside `DbTxn`.**

**What it unparks.** Media as a target of the target sentence — *"the image attached"* is in the
owner's own story and **was in no slice of the advisor's roadmap, LATER included.**

**Depends on.** Slice 5, and **ruling R5**: where the file lives, who copies it there, and what undo
means for a file copy. `add_media_reference` *links* a media object; nothing creates one.

### 10 — "The agent says who is who."

**Demo.** Given a census line and the tree, the agent presents candidate matches with evidence —
including *"nobody in the tree matches; these would be new people."* No writes.

**What it settles.** Person matching, **as agent judgement over 5a's tools rather than as repository
machinery.** Nothing in the write path changes for it.

**What it unparks.** Nothing new. ⚠️ **But the likelier real duplicate is not a person — it is the
record**: the same census proposed twice creates a duplicate source, citation and residence events.
`DUPLICATE_OF_EXISTING` is declared PHASE_3 and undecidable without a tree, so the read surface needs
to answer *"is this source already recorded"* as well as *"is this person."*

**Depends on.** 5a.

### 11 — "A census line becomes a household."

**Demo.** The target, verbatim from the brief: a photograph or transcription in the conversation →
extraction → matching → **one** batch carrying the source, the citation, the place, the people, the
family links, the events, the attributes, the image and the research note → **one** console →
**one** `y` → the owner opens Gramps and the household is there.

**What it settles.** The destination.

**What it unparks.** Everything above, composed.

**Depends on.** 3 through 10.

---

## What unparks when

Every parked item, mapped to what releases it. Rows marked ⚠️ **were on no list at all** — neither
the advisor's parked list nor the owner's gap list — and are the analysis's real finding about the
roadmap.

| Parked item | Released by | Trigger, or why |
| --- | --- | --- |
| **#21** — the date model | **6** (value-type half **now**, in parallel with 3–4) | Slice-scheduled. Its serialisation behind 3–4 is held for no reason. |
| **#22** — identity-side operations | **7**, reshaped | Slice-scheduled, **onto 4½'s settled reference model**, not today's. |
| **#23** — evidence-side operations | **5**, reshaped | Same condition as #22. |
| **#66** — the 32,767-character environment block | **4½** | The batch is what breaks the cap. Whether it *must* land there or can trail is measurement **M2**. |
| **#73** — `_write_and_verify` serves two callers | **4½** | Answered inside the batch slice's plan gate; the write path is being reshaped anyway. |
| **#77** — export staleness unsatisfiable by the documented workflow | **4** | Dissolves with the export reader. |
| **#76** — duplicate eventref handles counted twice | **4**, moot | ⚠️ Conditional on slice 4 **dropping** the export reader — the defect is in that reader (`core/people.py`), so keeping it **preserves** the defect. The analysis says slice 4 does not keep it — so **moot, not deferred**. |
| **#64**'s shape, for events | **5a** | Not the filed issue, its recurrence: no read surface returns an event identity, and the Gramps UI shows none. |
| **#25** — destructive operations | LATER | *"Backup proven in anger."* ⚠️ **Coupled:** the entry holds only as long as backup stays **per-write**. Throttle it to per-session and destructive ops jump the queue, because restore *is* batch undo. |
| **#53** — a name spelled with ZWNJ cannot be previewed | use-derived | A real name trips the render guard. |
| **#75**, **F-1**, **F-2**, **N-1** | use-derived | Someone actually hits them. All recorded residuals, all off the census path. |
| **pii_guard freeze** | use-derived | A demonstrable fail-open on real data. |
| **the gramplet** (Phase 6) | LATER — ⚠️ **conditionally** | *"Use has not asked for it."* **But if ruling R2 names an in-process host as slice 4's read mechanism, the gramplet is not later — it is slice 4's core.** The LATER entry is only safe once that door is named. |
| **multi-user** | LATER | Genuinely. Single-user is the brief's own premise. |
| ⚠️ **the batch / provisional-reference model** | **4½**, and **ruling R1 first** | On no list. The single ordering decision; see 4½. |
| ⚠️ **the injection widening** | **5a** (or **4**, whichever widened read tool ships first), and **ruling R3 first** | On no list, and the trigger is recorded verbatim in `docs/slice2-mcp.md`. |
| ⚠️ **`add_family`** | **7** | On no list. Mandatory under slice 7's *own* criterion — schema alone determines the write. Measurement **M3** decides whether Gramps agrees. |
| ⚠️ **the attribute operation** | **5** / **7**, or **never** | On no list. A census line's columns — occupation, relationship to head, marital status — are recorded partly as events and partly as `Attribute`s, and **no operation touches attributes.** Ruling **R6** decides whether the row exists at all. |
| ⚠️ **media file custody** | **9**, and **ruling R5 first** | On no list. The first write outside the database and outside `DbTxn`. |
| ⚠️ **the census-line walkthrough** | **free today** | On no list. Walk one real census line, column by column, through the operation table as a paper exercise, and **make the resulting list the acceptance test of the vocabulary.** Needs no code and no ruling. |
| ⚠️ **`add_place`** | ⛔ **no owning slice** | On no list, and named as a hole: *"none owns places beyond a demo mention."* The analysis classifies places with the other additive registry rows — after the batch ruling — but assigns them to no slice, and **"places" is in the owner's own destination sentence.** |
| **the proposal TTL and session binding** | **4½**, additively | Fifteen minutes and one server run are tuned for a one-sentence note. A batch representing an hour of extraction work meets both. Constants and record fields. |
| **#52** — #4's remainder, against slice 5's fixtures | ⛔ **undetermined** | Phase 1's own ordering rule — evidence-side fixtures wait for the guard audit — presumably still binds the reshaped slice 5. **How much of #4 remains live beyond #52 could not be determined from the code.** |

⭐ **Startable today, before any ruling:** #21's value type, the census-line walkthrough, and the
rulings themselves.

---

## The open rulings

**These are rulings, not work.** They cost a conversation each; what they cost if deferred is written
beside them.

| | The ruling | Blocks | If it is not made |
| --- | --- | --- | --- |
| **R2** | ⭐ **Slice 4's live-read mechanism.** How does a read of the live tree happen **while Gramps holds it open**? The named candidates: **un-kill Phase 5/6** (an in-process host — the architecture that was killed), or **open a new, unruled door** (e.g. read-only access beside a live Gramps). The CLI tool door is not a candidate: it refuses a locked tree by design and bans `--force-unlock` "ever". | **4**, and everything after it | ⚠️ **The analysis names this as the single ruling with the most downstream work hanging on it.** Nothing in the tail of the review answered it. It also decides whether the LATER-gramplet entry is safe, and it is a **reversal of a standing owner ruling** — it must be put as one, with the door named. |
| **R1** | **The batch shape.** A — a transaction of the existing small operations, held as an approval unit *outside* the registry, executed in one `DbTxn`, with a provisional-reference spelling added to the reference vocabulary. Or B — one registered composite operation per document kind. **The analysis recommends A** and argues both failure modes; **the owner rules.** Conditional on measurement **M1**. | **4½**, and every vocabulary slice after it | The nine specified operation types get built on a reference model that cannot name what the same batch creates, and then reworked. **The rework bill is itemised under 4½.** |
| **R3** | **The injection widening.** `docs/slice2-mcp.md` records the trigger — *any tool that returns note, source or citation text* — and demands a plan when it fires. What is the trust model for a read tool that returns tree prose? | **5a**, or **4** if its live read ships first | A tool built against an unrecorded trust model, which is how a guard gets removed later. ⚠️ **Rule first, build after** — it is a ruling, not machinery, and it is cheap. |
| **R4** | **Graduation to the live tree.** Is the blessed copy a disposable rehearsal, the future live tree, or something else? ⭐ **The sentinel model already contains the mechanism** — blessing is per-tree-directory, and the rail is *"blessed trees only,"* not *"never the live tree."* **Includes approving the guarantee downgrade in its own words:** unwritable-by-construction → recoverable-after. | **4**, and it decides where slice 3 sits | Every slice's product stays a demonstration artifact, and *"done"* has no meaning for any write slice. |
| **R5** | **Media file custody.** Where does the image live, who copies it there, and what does undo mean for a write that is not in the database? | **9** | Media is in the destination sentence and has no mechanism. |
| **R6** | **Attributes versus events**, in the owner's own recording practice. Occupation is legitimately either. | the row list of **5** and **7** | Decides whether the attribute operation exists at all — a genealogy-practice question, not a code question. |

### Measurements owed

Not rulings — things the analysis could not determine from the code and would not guess.

| | Measurement | Decides |
| --- | --- | --- |
| **M1** | Does a Gramps 6.0.8 `DbTxn` **abort cleanly** when an exception is raised mid-transaction? Needs a run on this box against a scratch tree. | **The all-or-nothing batch claim rests on it, so R1's recommendation is conditional on it.** |
| **M2** | One transcribed census household, serialised as a batch, measured against #66's per-machine headroom. | Whether #66 must land **inside** 4½ or can trail it. |
| **M3** | How Gramps wants households built — is `add_family` a required vocabulary row, or do the link operations legitimately create the Family object? Needs the Gramps db API read on the box, not a guess. | Slice 7's row list. |
| **M4** | How much of #4 remains live beyond what #52 records, against slice 5's fixtures. | Whether Phase 1's evidence-side ordering rule still binds the reshaped slice 5. |

---

## The phase table is retired

⭐ **The eight-phase milestone list is superseded by the slices above, and the honest reason is that
the phase model was overtaken by how the project actually moved.**

Slices 1 and 2 shipped work belonging to **Phase 3 (core/apply)**, **Phase 4 (core/query)** and
**Phase 7 (mcp)** — a `DbTxn` write path, a reader, and a stdio MCP server registered with
`claude mcp add` — while **Phase 1 (core/schema) is still open with nine issues on it.** All three of
those milestones still show zero closed issues. The work did not arrive in the order the phases
declared, and it will not from here either.

⚠️ **Phase 7's own description says *"full end-to-end verification against the live tree."* That has
not happened and is not close** — it is slice 4. The milestone reads as nearly reached and is not.

**This proposal changes no milestone.** Retiring the table is itself a ruling for the owner.

### ⛔ Phase 5 — the endpoint half is dead; the in-process half is not replaced

**Phase 5 carried two jobs in one milestone, and the kill lands on only one of them.**

**The tool surface is dead, and the MCP server is genuinely why.** Phase 5 specified a loopback HTTP
endpoint with token auth and four routes. Slice 2 shipped three tools over **stdio**, with no socket,
no token and no HTTP stack reached. As the way an agent reaches this project, the bridge has no
remaining job. ⛔ **That half of the owner's ruling stands, and this document does not reopen it.**

⚠️ **But Phase 5's other job was an in-process channel onto a live tree — a process holding Gramps'
own database handle — and nothing shipped does that job.** What ships is out-of-process at every
step: the agent host launches `gramps_live_api_mcp` as a **standalone stdio process**;
`Tools.list_people` reads the **configured export** rather than a database; and `approve` spawns
**another process again** — a console running `python -m gramps_live_api approve` — for the write.
A snapshot read taken in a separate process is not the job the bridge was hosted inside Gramps to do.

⭐ **So the reason recorded for the kill covers the endpoint and not the channel, and the channel's
return is ruling R2** — which is why R2 is a ruling rather than a milestone-hygiene question.

⚠️ **And recording the kill is not the same as recording what it cost:**

1. **Phase 6's gramplet is orphaned.** It existed to **host the bridge** — `GLib.idle_add`
   marshalling into a loopback endpoint. With the endpoint dead, the GTK shell hosts nothing. Either
   it is dead too and the milestone closes, **or it is quietly the future live-read channel** — and
   that is ruling **R2** again.
2. ⭐ **Snapshot reads became the architecture, by consequence rather than by decision.** With no live
   channel, everything downstream — query-before-propose, matching, duplicate detection — gets built
   on a manual export. That is **why slice 4's mechanism is an open ruling rather than an
   implementation detail**: killing Phase 5 did not merely remove a component, it chose a read
   architecture, and nobody ruled on that choice.
3. **The README carried the dead premise, and this document is now where it can recur.** Its opening
   sections described an addon running *inside* a Gramps process, with no staleness, borrowing
   Gramps' own database handle; it has since been rewritten to say what ships — reads from a manual
   snapshot export, writes through a one-shot spawned Gramps process. Same stale-roadmap defect as
   #24, and the fix was to state the architecture rather than the intention.

---

## What this proposal does not claim

- **That the order below slice 4 survives contact with use.** Hold 5–11 as a **pool of specified work
  with rulings attached**, committed one plan gate at a time, re-read after real use.
- ⚠️ **But two things must not be discounted with it.** The **content** of 5–7 — sources, citations,
  events, dates, people, relationships — is the census target's own decomposition and is stable under
  any amount of watching. And ⭐ **the batch ruling must not wait for use to ask**: the need is
  derivable today from the roadmap's own demo sentences, every one of which from slice 5 onward is a
  multi-object chain. It is target-spec, not hardening, so the use-derived-trigger rule does not
  apply to it — and a caveat taken at full strength would be a licence to defer exactly the decision
  whose deferral costs the most.
- **That the shipped code is what stands in the way.** It is not. ⭐ **The shipped code is in better
  shape for this target than the roadmap is.** One narrow transport mechanism needs replacing (#66,
  already filed with its fix shape). Everything that looks restrictive — one write type, one target
  type, one operation per approval, a closed registry, a frozen rule table — is a **named refusal
  with its widening point prepared.** The danger is in what is *specified and unbuilt*, and in what
  was *unnamed*.
