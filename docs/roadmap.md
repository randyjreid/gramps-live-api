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
> ⭐ **Two of those rulings have since been made, both on 2026-08-19.** **R2 — Gramps stays open.**
> It is the owner's, it reverses a standing ruling of his own, and it is transcribed below under
> *R2 is ruled* rather than argued again. **R8 — the channel is an in-process HTTP host inside
> Gramps**, recorded in full in [`rulings/R8-channel-architecture.md`](rulings/R8-channel-architecture.md)
> and summarised below. R8 **supersedes the process-model half of R2**: R2's conclusion stands, its
> reasoning is replaced. Between them they reshaped the order, **deleted** a slice, un-killed one
> piece of a dead milestone and put another back down — every consequence is marked where it lands.
> **Every other ruling in the table near the end is still owed, and nothing has been built on
> either.**
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

So the current product is a demonstration artifact. **Slice 4 below is what makes it genealogy** —
it used to be *slices 3 and 4*, and R8 deleted slice 3 as planned.

---

## R2 is ruled — 2026-08-19: **Gramps stays open**

⭐ **The mechanism: an in-process component inside Gramps, holding its database handle, reachable
from the MCP server.** That is Option A of R2, and it **reverses** the owner's own standing ruling
that killed it.

> *"I am not reopening a 2,900-person tree every session. That is not friction, it is a reason not
> to use the tool. My advisor recommended B on cost; I am overruling on how I actually work."*

⛔ **What stays dead: the HTTP tool surface.** *"What returns is the channel, not the four-endpoint
API."* The loopback endpoint, its token auth and its four routes are not reopened by this ruling and
are not reopened anywhere below.

⚠️ **R8 sharpens that sentence and it must be read carefully, because R8's channel is loopback HTTP
with a bearer token — the same mechanism Phase 5 specified.** What stays dead is the **agent-facing
API**: the agent reaches this project over **stdio MCP**, as it does today, and no route of Phase 5's
four is reinstated. What returns is HTTP as the **hop between our own two halves** — the MCP server
and the addon inside Gramps. **The transport is the same; the thing on the far end of it is not.**

⭐ **What it un-kills:** the **in-process half of Phase 5**, and the **gramplet of Phase 6**.
⚠️ **R8 has since taken the gramplet back down** — it un-parked because it was a candidate to *host*
the channel, and R8 rules that it cannot be. See the gramplet's row in *What unparks when*.

⚠️ **Nothing here is built.** The channel and the gramplet are **plans**, and the channel does not
have a plan gate yet. Every slice below still describes work not started.

### Why it is better, not merely necessary

1. **Writes go through Gramps' own `DbTxn`** from inside the process that owns the database, so a
   note lands in **Gramps' native undo stack** — the owner's own undo, in the application he is
   already sitting in. ⚠️ **R8 bounds this claim to the session, and it is a real narrowing:**
   `DbGenericUndo.undodb` is a plain Python list, `open()`/`close()` are no-op stubs and the
   `DBUNDOFN` (`undo.db`) path is never used by the DB-API backends. **Gramps' undo is discarded when
   the tree closes**, so this buys the owner undo *while he is sitting there* — and
   `.gramps-live-api-undo`, our own journal, remains **the only durable record**. R8 confirms it as
   required rather than optional.
2. **Approval can happen in a Gramps dialog** rather than a spawned console. ⭐ **R8 rules that it
   does**, on the GTK main thread. ⭐ **That is a stronger trust model, not merely a more convenient
   one:** the owner approves **inside the application that owns the data**, and the agent still holds
   no handle on the approval and learns no outcome from it.
3. **The ~3.4 s spawn per operation disappears** — and that is what **decides the census batch
   case**, where the spawn is paid per operation and one household is many of them. The measured
   figure it replaces is `docs/using.md`'s *"about three and a half seconds — two Gramps cold starts,
   one to write and one to go back and look."*

### The costs, recorded as honestly as the benefits

1. ⚠️ **A listening channel on the owner's own machine needs authentication, and that is a named
   risk surface. FULL tier, no exceptions** — for the channel's plan gate, and for slice 4, which is
   the slice that carries it. ⭐ **R8 names the mechanism** — loopback bind, a random bearer token on
   every request, and rejection of any request carrying an `Origin` header — **and records the
   residual it does not close**: any process running as the owner can read the token.
2. **GTK threading against a database the UI is also touching.** The component lives inside a
   running application that is reading and writing the same handle. ⭐ **R8 answers this with the
   invariant the whole design rests on** — *no Gramps database object and no GTK object is ever
   touched from the HTTP thread* — and requires it be enforced mechanically, by one accessor module
   and a test that a DB helper called off the main thread raises.
3. **The tool is dead whenever Gramps is closed.** Availability becomes the owner's Gramps window
   rather than the machine. **R8 does not soften this; it makes it structural** — the host is a
   plugin loaded at Gramps startup and there is no out-of-process fallback left in the design.

### How the kill got made — the lesson, said plainly

**Phase 5 was killed on the reason *"the MCP server does that job in-process"*, and that reason is
false.** What ships is out-of-process at every step, itemised in the Phase 5 section below: a
standalone stdio process, a read of a hand-made export, and another spawned process for the write.

⭐ **What made it plausible was a demo sentence.** Slice 2's demo describes an *experience* — an
agent proposes, one `y` is given, Gramps is written — and says nothing about process topology, so
from the outside the component looked replaced. **This document already names that failure in the
opposite direction**, in slice 4's own text: a reversal of an architecture ruling must be put to the
owner as one, *"with the door named — not implied by a demo sentence."* **It is the same error
twice — once to kill, once nearly to resurrect.** A demo sentence is evidence about what the owner
experiences and no evidence at all about what holds the database handle.

⭐ **And the reversal was made on workflow, not on mechanism.** The owner did not find the cost
argument wrong — he says so inside the ruling itself while overruling it. **Nothing here records the
advisor's Option B as miscosted.** The mechanism was priced correctly and outweighed by how the
owner actually works, and those are different things.

---

## R8 is ruled — 2026-08-19: **an in-process HTTP host inside Gramps**

⭐ **Recorded in full in [`rulings/R8-channel-architecture.md`](rulings/R8-channel-architecture.md).**
That page is the record; this section says what it costs the rest of this document.

**The mechanism.** A Gramps addon inside the Gramps process, registered as a `GENERAL` plugin with
`load_on_reg = True`, hosting a stdlib `http.server` listener bound to `127.0.0.1` on a **daemon
thread**, with all database and GTK access marshalled onto the **GTK main thread** via
`GLib.idle_add`, and **approval taken in a Gramps dialog on the main thread**. The MCP server becomes
a **thin HTTP client containing no Gramps code.**

⛔ **Gramps stays open. There is no export, no copy-to-write, no spawned CLI, no `op.json`.**

⚠️ **Nothing of it is built.** R8 is a ruling; the host, the client and the tests are unwritten.

### ⚠️ The premise it falsifies, and this is what reaches into every slice below

**The Gramps lock never made a second writer impossible.** It is advisory: `DBLOCKFN = "lock"`
(`gramps/gen/db/dbconst.py`) is a text file holding one line, `user@host` — no PID, no timestamp, no
`flock` — `write_lock_file()` (`gramps/gen/db/utils.py`) is called unconditionally in
`DbGeneric.load()` and never checks for an existing lock, every consumer check is
`os.path.isfile(...)` in caller code, `--force-unlock` is `os.unlink`, and
`gramps/plugins/db/dbapi/sqlite.py` opens with a bare `sqlite3.connect()` with no `PRAGMA
locking_mode` and no WAL.

⭐ **The real hazard is elsewhere, and it is worse.** `DbGeneric.load()` pulls `name_formats`,
`researcher`, the bookmark lists, custom types, `surname_list`, gender statistics and **every Gramps
ID counter** (`cmap_index`, `smap_index`, …) into process memory, and `_set_all_metadata()` writes
them back from exactly one call site — `DbGeneric.close()`. **Two processes on one tree are
last-writer-wins on the ID counters: silent duplicate Gramps IDs, with no SQLite conflict at all.**

⭐ **So the one-writer rail stands and its reason is replaced.** Wherever this document leaned on
*the lock forbids it*, the true statement is *two processes corrupt the ID counters*. **The
`--force-unlock` question is moot** — nothing turns on whether we would break a lock that guarantees
nothing.

### What it deletes

**Slice 3 as planned**, the `op.json` channel, the spawned-CLI writer, and the fresh-process
read-back approval. Each is marked where it appears below.

### What it settles that was open

- **The channel's design** — R2 un-killed it and left *what it is* to a plan gate. R8 is that answer,
  so the plan gate is now an implementation gate. ⚠️ **Its risk surface is unchanged: a listening
  socket is FULL tier.**
- **The gramplet is not the host.** `GrampletPane` builds gramplets only when the containing page is
  built and `ViewManager.goto_page()` builds pages lazily; `load_on_reg=True` is passed only for
  `USER_PLUGINS` by `CLIManager.do_reg_plugins()` (`gramps/cli/grampscli.py`) and fires at startup
  with no tree open. **A tool is not viable either** — `runfunc` needs a menu click every session.
- **The copy rule changes form, and keeps its strength.** Not an architecture: **the host refuses to
  arm its write path unless the open tree directory carries `.gramps-live-api-copy`, checked on
  `database-changed`.** One config flag to relax it later.
- **`.gramps-live-api-undo` is required, confirmed from the source.** Gramps' own undo is a
  process-local Python list discarded on close.

### What it leaves owed

**R1, R3, R4, R5 and R6 are untouched.** ⚠️ **R3 in particular: R8 says the injection surface is
unchanged in kind, so the widening ruling is owed exactly as before, at slice 4.** **R7 is reshaped,
not answered** — see its row in the rulings table.

---

## The order

The analysis's amended order, after ruling on the advisor's. At a glance:

⛔ **3** backup — **deleted as planned by R8**; the backup itself survives as ruling **R7** → **4**
the live tree *(mechanism **ruled**: an in-process HTTP host inside Gramps — R2, then R8)* → **4½**
batch ruling and batch spine → **5a** thin read surface → **5** sources and citations → **6** events
and dates → **7** people and relationships → **8** analytics → **9** media → **10** matching → **11**
the census demo.

Four notes on the numbering before the detail:

- **4½, 5a and 9–11 are not new slices.** 4½ and 5a are the two insertions the analysis's ruling on
  Question A produced. 9, 10 and 11 are the first decomposition's slices 8 (media), 9 (matching) and
  11 (the census demo), renumbered into this order.
- **The first decomposition's slice 10, "the live tree, backed up", dissolved into 3 and 4** — and
  with slice 3 deleted, **all of it now sits behind slice 4 and ruling R7.** It is not dropped; the
  amended order still enacts the graduation at the front.
- ⚠️ **Slice 3 no longer opens the order, and nothing has replaced it.** R2 falsified the premise its
  plan rests on and **R8 deleted the plan** — see slice 3 below, and ruling **R7**. Slice 4 still
  needs a backup; **what produces one against a tree Gramps is holding open is unruled, though R8
  hands R7 a mechanism it did not have.**
- ⚠️ **Of the two rulings that had to land before any of this starts, one has.** R2 is ruled — and
  R8 with it, which R2 did not anticipate needing. **R1, the batch shape, is not.** They are listed
  as rulings, further down, and they are not work.

### 3 — "My tree came back from a file." ⛔ **DELETED as planned — R8**

⛔ **Parked by R2 on 2026-08-19 and DELETED by R8 the same day.** It was the one slice startable the
moment the owner said go, and it is now not a slice at all. **What is deleted is the plan, not the
deliverable:** the owner still has to see his tree come back before anything writes to it. That
requirement moved into ruling **R7** and into slice 4's preconditions.

**Why the plan is gone rather than parked.** `.claude/plans/slice3.md` produces the artifact through
a **second registered CLI tool in the plugin door** — a spawned Gramps process — and R8 deletes the
spawned-CLI channel outright. The plan's own §2 answers Phase 2's *"a backup produced from inside a
running Gramps"* with *you cannot*, holding **"only while every write also requires the tree
closed."** ⭐ **R2 removed that condition; R8 removed the mechanism.** Nothing of the plan survives
its own premises.

⚠️ **Its refusal of the obvious alternative still stands, and is the part worth keeping:** a
file-level copy of the tree directory was the only candidate takeable while Gramps holds the tree,
and **a copy of a live SQLite database taken mid-transaction is a torn read with no way to detect
it.** ⚠️ **Read this under R8's finding and it gets worse, not better:** the lock never prevented the
copy — it is advisory — so *"you cannot safely copy an open tree"* was never enforced by anything,
and is a rule we must keep ourselves.

⭐ **What R8 hands R7 that it did not have: a process that already holds the handle.** Gramps' own
XML export driven from **inside** the host — R7's own first candidate — stops being hypothetical the
moment the host exists, because the host *is* code running inside the process that owns the database.
**That is a mechanism, not an answer.** ⚠️ **And it inherits R8's accepted risk 4** — a whole-tree
export is long work, and long work inside `GLib.idle_add` blocks the GTK loop. What a backup is
remains ruling **R7**, and it is owed.

⚠️ **The `importxml` handle finding still governs whatever restores, whichever way R7 goes:**
importing into a tree that holds even one person **silently regenerates every handle** in the
document, so the restore is *"import into a brand-new empty tree"*, and that constraint is part of
the question rather than a consequence of it.

**The deliverable, unchanged and now owned by R7 and slice 4.** Ask for a backup, get one, restore it
into Gramps as a working tree that opens. The owner has personally seen his own tree come back.
Bounded deliberately: **one backup, one restore, verified by the owner in Gramps.** Not retention,
not scheduling, not incremental anything. It is what makes slice 4 approvable, and it is the reason
#25's destructive operations can stay later.

⚠️ **It is a precondition of slice 4 specifically, not only of destructive operations generally.**
Two independent reasons, both from the analysis: at batch scale, hand-undo of *constructive* writes
is already unrealistic (twenty interlinked objects, one undo record shaped for one note), and
`update_*` operations arriving in slices 6–7 **overwrite recorded data** — delete's smaller sibling.
⚠️ **R8 adds a third:** Gramps' own undo is a process-local list discarded on close, so *"undo it in
Gramps"* is only an answer while the tree stays open.

### 4 — "My real tree." *(mechanism **ruled** — R2, then R8)*

**Demo.** Add a person in Gramps, immediately ask the agent about them, it finds them. Add a note. A
backup is taken automatically first. The note is in the tree the owner actually works in, and he
keeps it.

**What it settles.** Graduation. Every earlier slice's output stops being a rehearsal artifact.

**What it unparks.** #77 (export staleness) dissolves; #76 goes moot rather than deferred, on the
condition that this slice does **not** keep the export reader; most of `core/people.py` goes with
it. A live `priv` flag kills the stale-export privacy fail-open outright rather than detecting it —
a real safety gain, and worth claiming. ⭐ **And an in-process host inside Gramps is this slice's core
rather than a LATER nicety** — R2 un-killed it, R8 says what it is: a `GENERAL` plugin loaded with
`load_on_reg = True`, hosting a loopback `http.server` on a daemon thread. ⛔ **It is not the
gramplet.** R2 un-parked the gramplet as a candidate host and **R8 rules it out** —
`GrampletPane` builds gramplets only when the containing page is built, and `ViewManager.goto_page()`
builds pages lazily, so a gramplet may never be constructed at all. **The gramplet keeps no job under
R8**; see its row in *What unparks when*.

**Depends on.** ⚠️ **A backup — which no longer has a slice.** The precondition is unchanged (*no
write to the live tree before the owner has seen one come back*); what changed is that slice 3 is
**deleted** and producing a backup against an open tree is **ruling R7**. **And on rulings — the
first now made twice over, two still owed:**

- ⭐ **The read mechanism — RULED (R2, 2026-08-19; specified by R8 the same day).** *"Ask Claude about
  them"* is a read of the live tree **while Gramps holds it open**, and the ruled answer is an
  **in-process HTTP host inside Gramps**, with the MCP server as a thin client holding no Gramps
  code. ⚠️ **The reason this slice was stuck is not the reason it was recorded as being stuck.** The
  doors were described as closed because *the CLI tool refuses a locked tree and `--force-unlock` is
  banned "ever"*, and **R8 falsifies that framing: the lock is advisory and guarantees nothing.**
  ⭐ **The one-writer rail survives on a stronger reason** — two processes holding one tree are
  last-writer-wins on the in-memory Gramps ID counters, which is silent duplicate IDs with no SQLite
  conflict. `docs/using.md`'s *"we never break Gramps' lock"* stays true of what ships and stays the
  right policy; it was never the thing making a second writer impossible. **The `--force-unlock`
  question is moot.** ⚠️ **The channel is a listening channel on the owner's machine and needs
  authentication: a named risk surface, so this slice's plan gate is FULL tier, no exceptions.**
  ⛔ **Its design is not in this document** — it is in
  [`rulings/R8-channel-architecture.md`](rulings/R8-channel-architecture.md).
- ⚠️ **The guarantee downgrade (part of ruling R4).** The sentinel makes the live tree unwritable *by
  construction*; the offered replacement, backup-taken-first, is **weaker in kind, not equivalent**.
  *Unwritable-by-construction* is a guarantee about what can happen; *recoverable-after* is a
  guarantee about what can be undone, and it still costs the owner noticing, choosing, and knowing
  which backup predates the damage. That may be exactly the right trade — it is what "the notes
  count" costs — but **it should be approved as a downgrade, in those words.** ⚠️ **R7 now sits
  underneath it:** the downgrade cannot be approved as *backup-taken-first* until something can take
  one against an open tree. ⭐ **R8 changes the sentinel's form and not its strength:** it is no
  longer *"the writer can only ever open a blessed tree"* but *"the host refuses to arm its write
  path unless the open tree directory carries `.gramps-live-api-copy`, checked on
  `database-changed`."* **The downgrade R4 must approve is the same downgrade** — the check is now a
  runtime arming condition rather than a property of the process topology, and R8 attaches one config
  flag to relax it later. ⚠️ **That flag contradicts `docs/using.md:52`** — *"there is no flag that
  overrides it, and there is no configuration key that reaches the check"* — **and the contradiction is
  unresolved pending R4.**
- ⚠️ **The injection widening (ruling R3), which R2 moved here.** A live read is a read of everything
  the tree holds — note, source and citation text included — so the trigger recorded verbatim in
  `docs/slice2-mcp.md` fires at **this** slice unless 5a somehow ships first. ⛔ **R8 changes nothing
  about it** and says so in its own words: *injection surface is unchanged in kind; R3 still owed.*
  An HTTP hop between our own halves moves tree prose along a different wire, not into a different
  trust model.

⚠️ **The cost this slice does not otherwise name:** after it, every subsequent vocabulary slice's
first bugs land in the real tree. Mitigated only by auto-backup-before-write — and **only for as
long as the backup stays per-write** rather than per-session, and now only once R7 says what takes
one.

⚠️ **And a cost R2 adds to this slice specifically: the tool is dead whenever Gramps is closed.**
The demo above is performed with Gramps open, which is how the owner says he works — but *"ask the
agent about them"* stops being answerable the moment he quits, and that is a change in what the
product is, not only in how it is built.

⭐ **Keep the blessed-copy path alive after this slice as a rehearsal space.** The analysis is precise
about what the copy is good for: it is *misleading* about workflow truths (staleness, the export
dance, what the owner tolerates) and **perfectly sound** about the correctness of new machinery —
renders, validation, the batch linker. First-run defects are cheaper to find there.

### 4½ — "Two notes, one dialog, one yes."

**Demo.** The agent proposes a batch of two notes — the only writable type today; **one Gramps
dialog** shows both sentences in full; one `y` writes both inside **one** `DbTxn`; `n` writes
neither; one undo record and one result record naming both notes.

⭐ **R8 settles the wording R2 left open.** R2 recorded that approval *can* happen in a Gramps dialog
instead of a spawned console; **R8 rules that it does**, on the GTK main thread, and deletes the
spawned console with the rest of the spawned-CLI path. **What the demo asserts is still *one*
approval for *two* writes** — that never depended on where it is taken. ⚠️ **Every later demo
sentence below that still says "console" is read the same way: it means one approval surface, and
under R8 that surface is a Gramps dialog.**

**What it settles.** The whole batch spine on the existing vocabulary: batch digest, batch store
record, batch display, one-transaction apply, batch result and undo shapes. **This is the slice the
target sentence's "not twenty" lives in.**

**What it unparks.** ⛔ **#66 is no longer this slice's to unpark — R8 dissolves it.** The
32,767-character Windows environment block is a property of handing an operation to a **spawned**
process, and R8 deletes the spawned writer; an in-process write has no environment block anywhere in
its path. **The issue closes on the architecture rather than on its designed remedy** (a file whose
path is the variable), and **measurement M2 goes with it.** **#73** — the write path is being
reshaped far more than "anyway", so `_write_and_verify` serving two callers gets answered inside this
slice's plan gate rather than before or after it.

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
cheap by design); the MCP tool surface in `server.py`; the approval display now in `cli._approve`;
the apply dispatch and the `Tree` protocol; and the undo and result record shapes. ⚠️ **#66's
transport has left this list** — R8 dissolves it — **and R8 adds two rows in its place**: the
approval display moves into a Gramps dialog, and the apply dispatch moves behind the
`GLib.idle_add` hop. What limits it is this project's own discipline — the structural tests are registry- and
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
built against an unrecorded trust model, which is how a guard gets removed later. ⚠️ **Under R2 it is
owed earlier still** — slice 4's live read trips the same trigger, so R3 will already have been made
by the time this slice is reached, rather than being this slice's own gate.

⚠️ **Under R2 the trigger fires at slice 4, which comes first** — a live read widens the channel from
two export fields to everything the tree holds, and R2 ruled that slice 4 reads live. **The ruling
is owed at whichever tool ships first, and on the order above that is slice 4, not this slice.**

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
owner-ruled no-outcome channel, it is three separate approvals with the owner hand-carrying each
minted Gramps ID from window to transcript between them. One request in, a courier loop out. ⚠️ **R8
makes them three dialogs instead of three spawned consoles, which is cheaper per approval and changes
nothing about the courier loop** — that comes from one-op-per-approval, not from the approval
surface.

### 6 — "An estimated 1867 stays estimated."

**Demo.** A birth event with an estimated date appears on a person, and Gramps displays the estimate
as an estimate.

**What it settles.** The date model, with its ruling already made: **mirror Gramps' own model,
calendar field open, no default, byte-faithful round-trip** — endorsed by the analysis, and
consistent with D1's failed import check.

**What it unparks.** **#21.** ⭐ **Its value-type half is dependency-free and should be built in
parallel with slice 4 rather than queued behind it** — the analysis calls the serialisation a cheap
concurrency loss. ⚠️ **It read "slices 3–4" before R8 deleted slice 3**; the point is unchanged and
the window is now slice 4's alone.

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

⚠️ **R8 adds a constraint R5 must answer, not merely a consequence:** under an in-process host every
write runs on the **GTK main thread** via `GLib.idle_add`, and R8's accepted risk 4 caps the work one
callback may do. **Copying a photograph is exactly the long work that cap is about.** Where the copy
runs — and it cannot be on the HTTP thread, which the load-bearing invariant forbids from touching
anything Gramps owns — is part of R5's question now.

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

**Depends on.** 4 through 10 — **it read "3 through 10" until R8 deleted slice 3**; the backup it
still depends on arrives through ruling R7 and slice 4.

---

## What unparks when

Every parked item, mapped to what releases it. Rows marked ⚠️ **were on no list at all** — neither
the advisor's parked list nor the owner's gap list — and are the analysis's real finding about the
roadmap.

| Parked item | Released by | Trigger, or why |
| --- | --- | --- |
| **#21** — the date model | **6** (value-type half **now**, in parallel with **4**) | Slice-scheduled. Its serialisation behind the front of the order is held for no reason. ⚠️ **Read "3–4" before R8 deleted slice 3.** |
| **#22** — identity-side operations | **7**, reshaped | Slice-scheduled, **onto 4½'s settled reference model**, not today's. |
| **#23** — evidence-side operations | **5**, reshaped | Same condition as #22. |
| **#66** — the 32,767-character environment block | ⛔ **DISSOLVED by R8** — not released by a slice | The cap is a property of handing an operation to a **spawned** process. **R8 rules the write in-process**, so nothing in the path has an environment block. R2 left this open pending the channel's plan gate; **R8 is that answer, and it decides it.** ⚠️ **#66 closes on the architecture, not on its designed remedy** (a file whose path is the variable) — and **measurement M2 goes with it.** |
| **#73** — `_write_and_verify` serves two callers | **4½** | Answered inside the batch slice's plan gate; the write path is being reshaped anyway — ⚠️ **and under R8 far more than "anyway": the spawned writer it verifies through is deleted.** |
| **#77** — export staleness unsatisfiable by the documented workflow | **4** | Dissolves with the export reader. |
| **#76** — duplicate eventref handles counted twice | **4**, moot | ⚠️ Conditional on slice 4 **dropping** the export reader — the defect is in that reader (`core/people.py`), so keeping it **preserves** the defect. The analysis says slice 4 does not keep it — so **moot, not deferred**. |
| **#64**'s shape, for events | **5a** | Not the filed issue, its recurrence: no read surface returns an event identity, and the Gramps UI shows none. |
| **#25** — destructive operations | LATER | *"Backup proven in anger."* ⚠️ **Coupled:** the entry holds only as long as backup stays **per-write**. Throttle it to per-session and destructive ops jump the queue, because restore *is* batch undo. ⚠️ **And the coupling runs through R7** — a backup nobody can take against an open tree is not a cadence, and this entry rests on one existing at all. ⚠️ **R8 removes the fallback that made this feel softer than it is:** Gramps' own undo is a process-local list discarded on close, so *"undo it in Gramps"* stops working the moment the tree does. |
| **#53** — a name spelled with ZWNJ cannot be previewed | use-derived | A real name trips the render guard. |
| **#75**, **F-1**, **F-2**, **N-1** | use-derived | Someone actually hits them. All recorded residuals, all off the census path. |
| **pii_guard freeze** | use-derived | A demonstrable fail-open on real data. |
| **the gramplet** (Phase 6) | ⛔ **UN-PARKED by R2, then RULED OUT as the host by R8** — back to **use-derived** | R2 un-parked it for one reason: it was a candidate to *host* the channel. **R8 rules that it cannot be** — `GrampletPane` constructs gramplets only when the containing page is built and `ViewManager.goto_page()` builds pages lazily, so a gramplet may never be constructed at all; the host is a `GENERAL` plugin with `load_on_reg = True`. ⚠️ **R8 gives it no other job** — approval is a Gramps dialog on the main thread, which is not a gramplet — **so the reason it un-parked is gone and its old condition returns: use has not asked for it.** |
| ⚠️ **the in-process channel** (Phase 5's surviving half) | ⭐ **UN-KILLED by R2, SPECIFIED by R8** — **4** | Was not a parked item at all; it was **dead**, killed on a false reason. It returns as slice 4's read mechanism, and **R8 says what it is**: a `load_on_reg` `GENERAL` plugin hosting a stdlib `http.server` on `127.0.0.1` on a daemon thread, all DB and GTK work marshalled to the main thread by `GLib.idle_add`. ⛔ **Phase 5's agent-facing four-route API does not return with it** — the agent still speaks stdio MCP; the HTTP is the hop between our own two halves. ⚠️ **Its gate is FULL tier** — a listening socket needing authentication is a named risk surface — **and it is now an implementation gate, not a design one.** |
| ⚠️ **the backup mechanism** | ⛔ **PARKED by R2**, its slice **DELETED by R8**, and **ruling R7 first** | Slice 3's plan assumes Gramps closed **and produces the artifact through a spawned CLI tool R8 deletes**, so the plan is gone rather than held. An open SQLite tree still cannot be safely copied. ⭐ **What R8 adds is a mechanism R7 did not have** — a process that already holds the handle, so Gramps' own export driven from inside it is real rather than hypothetical; ⚠️ **subject to R8's cap on work inside `GLib.idle_add`.** ⚠️ **It still blocks slice 4, which blocks everything after it.** |
| **multi-user** | LATER | Genuinely. Single-user is the brief's own premise. |
| ⚠️ **the batch / provisional-reference model** | **4½**, and **ruling R1 first** | On no list. The single ordering decision; see 4½. |
| ⚠️ **the injection widening** | **4**, and **ruling R3 first** | On no list, and the trigger is recorded verbatim in `docs/slice2-mcp.md`. ⚠️ **R2 settled which slice it lands in:** slice 4 now reads the live tree, so the widened read tool ships there rather than at 5a. ⛔ **R8 changes nothing here** — *"injection surface is unchanged in kind; R3 still owed."* |
| ⚠️ **`add_family`** | **7** | On no list. Mandatory under slice 7's *own* criterion — schema alone determines the write. Measurement **M3** decides whether Gramps agrees. |
| ⚠️ **the attribute operation** | **5** / **7**, or **never** | On no list. A census line's columns — occupation, relationship to head, marital status — are recorded partly as events and partly as `Attribute`s, and **no operation touches attributes.** Ruling **R6** decides whether the row exists at all. |
| ⚠️ **media file custody** | **9**, and **ruling R5 first** | On no list. The first write outside the database and outside `DbTxn`. ⚠️ **R8 adds a constraint R5 must answer:** the file copy is long work, it may not run on the HTTP thread, and R8 caps what one `GLib.idle_add` callback may do on the main thread. |
| ⚠️ **the census-line walkthrough** | **free today** | On no list. Walk one real census line, column by column, through the operation table as a paper exercise, and **make the resulting list the acceptance test of the vocabulary.** Needs no code and no ruling. |
| ⚠️ **`add_place`** | ⛔ **no owning slice** | On no list, and named as a hole: *"none owns places beyond a demo mention."* The analysis classifies places with the other additive registry rows — after the batch ruling — but assigns them to no slice, and **"places" is in the owner's own destination sentence.** |
| **the proposal TTL and session binding** | **4½**, additively | Fifteen minutes and one server run are tuned for a one-sentence note. A batch representing an hour of extraction work meets both. Constants and record fields. |
| **#52** — #4's remainder, against slice 5's fixtures | ⛔ **undetermined** | Phase 1's own ordering rule — evidence-side fixtures wait for the guard audit — presumably still binds the reshaped slice 5. **How much of #4 remains live beyond #52 could not be determined from the code.** |

⭐ **Startable today, before any further ruling:** #21's value type, the census-line walkthrough, the
rulings themselves — **and, newly, the channel host, because R8 is its design ruling.** ⚠️ **Slice 3
has left this list permanently:** R2 removed its premise and R8 deleted its plan. ⚠️ **And building
the host is not building slice 4** — slice 4 is graduation onto the live tree and still waits on R7,
R3 and R4.

---

## The open rulings

**These are rulings, not work.** They cost a conversation each; what they cost if deferred is written
beside them.

⭐ **Two have been made and neither is in this table any longer.** **R2** — *Gramps stays open* —
recorded near the top of this document; it put **R7** into the table. **R8** — *an in-process HTTP
host inside Gramps* — recorded in
[`rulings/R8-channel-architecture.md`](rulings/R8-channel-architecture.md); ⭐ **it adds nothing to
this table and answers none of it**, but it reshapes **R7** and touches **R4** and **R5**, marked in
their rows.

| | The ruling | Blocks | If it is not made |
| --- | --- | --- | --- |
| **R7** | ⛔ **What takes a backup against an open tree.** R2 removed slice 3's premise and **R8 deleted its plan** — the plan produced the artifact through a **spawned CLI tool**, which R8 deletes, and the reason that tool refused was recorded as Gramps' lock check, which **R8 shows guarantees nothing**. The one candidate takeable while Gramps holds the tree — a file copy of the tree directory — is still a torn read of a live SQLite database with no way to detect it. ⭐ **R8 reshapes the question rather than answering it:** the host is code inside the process that owns the handle, so *Gramps' own export driven from inside* stops being hypothetical. SQLite's backup API, or something else, remain open. ⚠️ **Whatever runs it inherits R8's cap on work inside `GLib.idle_add`** — a whole-tree export is long work on the GTK main thread. ⚠️ **Whatever restores it inherits the `importxml` handle finding**: import into a tree holding even one person and every handle is silently regenerated, so *"restore"* means *"into a brand-new empty tree"*. | **4**, therefore everything — ⚠️ **it no longer blocks a slice 3, because there is none** | ⚠️ **The front of the order still has no write slice startable in it.** And R4's guarantee downgrade cannot be approved as *backup-taken-first* while nothing can take one. |
| **R1** | **The batch shape.** A — a transaction of the existing small operations, held as an approval unit *outside* the registry, executed in one `DbTxn`, with a provisional-reference spelling added to the reference vocabulary. Or B — one registered composite operation per document kind. **The analysis recommends A** and argues both failure modes; **the owner rules.** Conditional on measurement **M1**. | **4½**, and every vocabulary slice after it | The nine specified operation types get built on a reference model that cannot name what the same batch creates, and then reworked. **The rework bill is itemised under 4½.** |
| **R3** | **The injection widening.** `docs/slice2-mcp.md` records the trigger — *any tool that returns note, source or citation text* — and demands a plan when it fires. What is the trust model for a read tool that returns tree prose? ⚠️ **R2 made this sooner, not different:** slice 4's read is now a live read of everything the tree holds, so the trigger fires there. ⛔ **R8 makes it neither sooner nor different** — *"injection surface is unchanged in kind; R3 still owed."* | **4**, and 5a behind it | A tool built against an unrecorded trust model, which is how a guard gets removed later. ⚠️ **Rule first, build after** — it is a ruling, not machinery, and it is cheap. |
| **R4** | **Graduation to the live tree.** Is the blessed copy a disposable rehearsal, the future live tree, or something else? ⭐ **The sentinel model already contains the mechanism** — blessing is per-tree-directory, and the rail is *"blessed trees only,"* not *"never the live tree."* ⚠️ **R8 changes the sentinel's form, not this question:** it is no longer a property of which tree a spawned writer may open, but **a check the host makes on `database-changed` before it arms its write path**, with one config flag to relax it. ⚠️ **That flag contradicts `docs/using.md:52` — *"there is no flag that overrides it, and there is no configuration key that reaches the check"* — and the contradiction is unresolved pending R4.** **Includes approving the guarantee downgrade in its own words:** unwritable-by-construction → recoverable-after. ⚠️ **R7 sits under that half** — *recoverable-after* is not approvable until something can take a backup against an open tree. | **4** — ⚠️ **it no longer decides where slice 3 sits; R8 deleted it** | Every slice's product stays a demonstration artifact, and *"done"* has no meaning for any write slice. |
| **R5** | **Media file custody.** Where does the image live, who copies it there, and what does undo mean for a write that is not in the database? ⚠️ **R8 adds a fourth part to the question: on which thread.** The HTTP thread may touch nothing Gramps owns, and the GTK main thread has a per-callback work cap. | **9** | Media is in the destination sentence and has no mechanism. |
| **R6** | **Attributes versus events**, in the owner's own recording practice. Occupation is legitimately either. | the row list of **5** and **7** | Decides whether the attribute operation exists at all — a genealogy-practice question, not a code question. |

### Measurements owed

Not rulings — things the analysis could not determine from the code and would not guess.

| | Measurement | Decides |
| --- | --- | --- |
| **M1** | Does a Gramps 6.0.8 `DbTxn` **abort cleanly** when an exception is raised mid-transaction? Needs a run on this box against a scratch tree. ⚠️ **R8 does not answer it and changes where it runs:** the transaction now runs inside the Gramps process, on the GTK main thread, so the measurement must be taken there rather than in a spawned CLI. | **The all-or-nothing batch claim rests on it, so R1's recommendation is conditional on it.** |
| ~~**M2**~~ | ⛔ **MOOT under R8.** One transcribed census household measured against #66's per-machine headroom — but R8 rules the write in-process, so there is no environment block to overflow. R2 left this conditional on the channel's plan gate; **R8 is that ruling and it decides it.** | Nothing. #66 dissolves with it. |
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

### Phase 5 — ⛔ the endpoint half is dead; ⭐ the in-process half is **ruled back** (R2) and **specified** (R8)

**Phase 5 carried two jobs in one milestone, the kill landed on both, and only one of them deserved
it.**

**The tool surface is dead, and the MCP server is genuinely why.** Phase 5 specified a loopback HTTP
endpoint with token auth and four routes. Slice 2 shipped three tools over **stdio**, with no socket,
no token and no HTTP stack reached. As the way an agent reaches this project, the bridge has no
remaining job. ⛔ **That half of the owner's ruling stands, and this document does not reopen it.**

⚠️ **R8 requires that sentence to be read precisely, because R8's channel is a loopback HTTP listener
with token auth — the mechanism Phase 5 described.** The distinction is what is on the far end. Phase
5's endpoint was **the agent's API**: four routes an agent host would call. R8's listener is **the hop
between our own two halves**, and the agent still reaches this project over stdio MCP. ⭐ **The
milestone stays retired and no route of Phase 5's is reinstated** — but *"no HTTP anywhere"* was never
what died, and this document should not be read as saying it was.

⚠️ **But Phase 5's other job was an in-process channel onto a live tree — a process holding Gramps'
own database handle — and nothing shipped does that job.** What ships is out-of-process at every
step: the agent host launches `gramps_live_api_mcp` as a **standalone stdio process**;
`Tools.list_people` reads the **configured export** rather than a database; and `approve` spawns
**another process again** — a console running `python -m gramps_live_api approve` — for the write.
A snapshot read taken in a separate process is not the job the bridge was hosted inside Gramps to do.

⭐ **So the reason recorded for the kill — *"the MCP server does that job in-process"* — covers the
endpoint and not the channel, and it is false about the channel.** That is the whole of the error,
and it is written up where it belongs, under *R2 is ruled* near the top: a demo sentence describing
an experience was read as evidence about process topology.

⭐ **The channel is ruled back (R2, 2026-08-19): an in-process component inside Gramps holding its
database handle, reachable from the MCP server** — **and specified the same day by R8: a `GENERAL`
plugin loaded with `load_on_reg = True`, hosting a stdlib `http.server` on `127.0.0.1` on a daemon
thread, marshalling every DB and GTK touch onto the main thread with `GLib.idle_add`.** ⛔ **The
agent-facing endpoint half is not reopened with it** — *"what returns is the channel, not the
four-endpoint API."* ⚠️ **And nothing is built:** what returns is a specification and an
implementation that has not started.

⚠️ **The three costs the kill was recorded as having, re-read against the rulings — one is undone,
one is undone and then partly re-taken, and one is not:**

1. ⚠️ **Phase 6's gramplet: un-orphaned by R2, and ruled out again by R8.** It existed to **host the
   bridge**, and with the endpoint dead the GTK shell hosted nothing; R2 gave a shell inside Gramps a
   job again. ⛔ **R8 takes that job back:** `GrampletPane` constructs gramplets only when the
   containing page is built and `ViewManager.goto_page()` builds pages lazily, so a gramplet may never
   be constructed at all — **the host is the `load_on_reg` plugin, not the gramplet.** Approval is a
   Gramps dialog on the main thread, which is not a gramplet either. **The Phase 6 milestone does not
   close, and it has no un-parked work in it.**
2. ⭐ **Snapshot reads are no longer the architecture, and this is the ruling's largest single
   effect.** They had become it *by consequence rather than by decision* — with no live channel,
   query-before-propose, matching and duplicate detection were all going to be built on a manual
   export. R2 is the decision that was missing. ⚠️ **What ships today still reads a snapshot**, and
   will until slice 4 lands; what changed is what it is being built toward.
3. ⚠️ **The README's premise is the one cost the rulings do not undo — they sharpen it.** The
   README's opening sections once described an addon running *inside* a Gramps process, borrowing
   Gramps' own database handle with no staleness; they were rewritten to say what ships — reads from
   a manual snapshot export, writes through a one-shot spawned Gramps process. **R2 makes the old
   description an intention again, and an intention is exactly what #24's defect was made of.** The
   rewritten README stays as it is until the channel exists: **what ships is what gets described.**
   ⚠️ **R8 required one correction to it and no more:** the README's *"where it is going"* section
   named a slice 3 that no longer exists and described the destination in closed-Gramps terms. **Its
   description of what works today is untouched, because nothing shipped changed.**

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
- ⚠️ **That R2 and R8 cost the shipped code nothing.** They are rulings, not builds — but together
  they put a **new component inside Gramps**, with a **listening socket**, in front of everything from
  slice 4 onward, and that is a named risk surface with authentication attached. **The cheapest slice
  in the order is the one they took away**: R2 parked it and R8 deleted its plan.
- ⚠️ **That the shipped write path survives.** ⛔ **R8 deletes the spawned-CLI writer, the `op.json`
  channel and the fresh-process read-back approval** — three mechanisms slice 1 and slice 2 are built
  on and demonstrably work. **What ships keeps working and keeps being described as shipped; it is the
  path forward that no longer runs through it.**
- **That the shipped code is what stands in the way.** It is not. ⭐ **The shipped code is in better
  shape for this target than the roadmap is.** ⭐ **One narrow transport mechanism no longer even needs
  replacing** — #66 is **dissolved** by R8 rather than fixed; see its unpark row. Everything that
  looks restrictive — one write type, one target type, one operation per approval, a closed registry,
  a frozen rule table — is a **named refusal with its widening point prepared.** The danger is in what
  is *specified and unbuilt*, and in what was *unnamed*.
