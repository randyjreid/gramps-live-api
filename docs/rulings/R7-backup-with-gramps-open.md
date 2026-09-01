# R7 — Backup with Gramps open: SQLite's backup API against the live connection

> ⭐ **STATUS: the decision holds.** It is what makes R4's *recoverable-after*
> true, and why the backup is per write rather than per session.
>
> ⚠️ **The shipped code took the decision and not the mechanism.**
> `src/gramps_live_api/host/backup.py` opens **a second, read-only `sqlite3`
> connection** rather than using Gramps' own, and records why: a backup copies
> pages and needs none of the functions and collations Gramps registers, so it
> does not pay the `db.dbapi._Connection__connection` cost this ruling accepted.
> ⭐ **This page for the decision; that module for what runs.**
> Index: [`README.md`](README.md).


**Ruled 2026-08-21.** This page records a decision. It is not a proposal and it is not argued again
here. The case that was put is in `.claude/decisions/R7-undo-and-backup-with-gramps-open.md`.

⚠️ **When ruled, nothing described below was built.** The host has no write path, no backup path and
no arming check. Everything here is a decision, not a description.

---

## The ruling

**A backup is taken with `sqlite3.Connection.backup()` against the live SQLite connection Gramps
already holds**, reached at `db.dbapi._Connection__connection`.

⭐ **Restore is file replacement, not import.**

## Why this over Gramps' own export

Both costs, recorded:

- **Gramps' export must be restored by importing**, and importing into a tree holding **even one
  person silently regenerates every handle**. So "restore" from an export means "restore into a
  brand-new empty tree" — and every reference this project depends on is a handle.
- **The backup API produces a byte-level copy restored by file replacement**, so the `importxml`
  handle-regeneration finding **never applies to it.** Identity survives, because nothing re-reads
  and re-keys the data.

## The cost accepted

⚠️ **The connection is reachable only through a name-mangled private attribute.**

`class Connection` in `gramps/plugins/db/dbapi/sqlite.py` — Gramps 6.0.8.0, 9,048 bytes, SHA-256
`858b4756f4199f97ce8169fe14b9046c9d7344089d61c112a23b0582b3fe5e52` — publishes twelve methods
(`check_collation`, `execute`, `fetchone`, `fetchall`, `begin`, `commit`, `rollback`,
`table_exists`, `column_exists`, `drop_column`, `close`, `cursor`). **None returns the underlying
`sqlite3.Connection`, and there is no `backup` method.**

The attribute is **assigned once in `__init__` and never reassigned**, which is the stable end of
the fragility spectrum — not a cache, not lazily rebuilt, not swapped on reconnect. **But nothing in
the class's contract promises the name survives a Gramps release.**

### ⛔ The acceptance criterion that makes the cost bounded

> **If the connection cannot be reached, the host refuses to arm its write path and says so. It does
> not fall back to an export, it does not write without a backup, and it does not continue quietly.
> A Gramps upgrade must break this tool loudly rather than remove its safety net silently.**

### ⛔ Why the obvious workaround is not one

> **Gramps registers `create_function("regexp", 2, regexp)` and its collations on that specific
> connection object. A backup route that opens its own second `sqlite3.connect()` to the same file
> gets one without them, and the difference surfaces only when a query uses `regexp`. Opening our own
> connection is not equivalent.**

## Build questions this ruling does NOT settle

**Owed to the build's plan gate, not open as rulings.**

1. ⚠️ **How the copy respects R8's cap on work inside `GLib.idle_add`. This is an open problem,
   not a confirmation task.** An earlier draft of this page framed it as *"whether the copy runs
   incrementally via the `pages` and `sleep` arguments"*. ⛔ **That framing is wrong, and it was
   measured rather than argued.**

   > ⭐ **ANSWERED 2026-08-23 — by TAKING the risk, not by removing it.** The copy runs
   > **synchronously inside the callback**. On the owner's tree that is a measured **108 ms**,
   > against the 343–402 ms of main-thread cost this project already accepts for a name search.
   >
   > ⛔ **That measurement does NOT make the work intrinsically small, and it does not satisfy
   > R8's cap.** It is one sample of one tree.
   >
   > ⛔⛔ **And there is NO hard bound on how long the callback can block. This sentence has been
   > written wrong twice already, so here is what the code does:**
   >
   > * `SECONDS_PER_ATTEMPT` — currently five seconds — is checked **only inside SQLite's progress
   >   callback**, which fires between steps of `PAGES_PER_STEP` (1,024) pages. `Connection.backup()`
   >   runs to completion in one call, so raising from that callback is the only way to stop it —
   >   and **a single slow step overruns the deadline with nothing able to interrupt it.**
   > * After the copy returns, `take()` runs `verify()` — `PRAGMA integrity_check` — **on the same
   >   thread, with no deadline at all.** That is issue #116.
   >
   > ⚠️ **So five seconds is a best-effort deadline on the COPY STEP, not a bound on the operation.**
   > Two earlier revisions claimed more: first that the cap "was respected by making the work small
   > enough to be honest about", then that this was a "timeout-bounded blocking risk". **Both read
   > as invariants; neither is one.** What is true: the callback can block for an unbounded time on
   > a large or slow-backed tree, the five-second check makes the common case terminate, and
   > bounding the whole pre-write path is open in #116.
   >
   > ⭐ **Recorded this way deliberately.** Each earlier wording would have let a future change lean
   > on a guarantee that does not exist — which is the failure this ruling page exists to prevent,
   > appearing twice in the page's own account of itself.

   **`Connection.backup()` is synchronous and runs to completion in one call.** `pages` sets the
   size of each internal copy step; it does **not** make the call return partway. `sleep` only
   delays retries when the source is locked. Measured on CPython 3.12 with `pages=1` — the smallest
   possible step — against a 200,000-row database: **one call produced 531 progress callbacks,
   returned with `remaining=0`, and the destination held every row.** ⚠️ **Not re-measured on the
   AIO's 3.14.4**; the semantics are long-standing, and the figure above is the one that was taken.

   ⭐ **So the whole backup lands in a single GTK callback, and R8 caps what one callback may do.**
   Gramps' connection is also thread-bound, so the work cannot simply be moved off the main thread.
   **The build must either find a genuinely resumable mechanism or take the main-loop-blocking risk
   explicitly, with the owner told what it costs.** ⛔ **It may not be recorded as solved by naming
   arguments that do not solve it.**

2. **Where the backup file lands, and its retention.**

## ⭐ The build constraint, measured 2026-08-22

> ⛔ **SUPERSEDED IN PART, 2026-08-23 — read this section with the four below it.**
> The second read-only connection stands and is what ships. **The worker thread
> does not.** The build ran it on a worker, that design produced three
> correctness defects that all needed the interval it created, and it was
> reversed to a synchronous copy on the GTK main thread — see *The asynchronous
> design was tried, and reversed*. ⚠️ The measurements in this section are real
> and are kept; what changed is where the copy runs. **Nothing here should be
> read as the current design without the later sections.**

**The work-cap problem above is solved, and the private-attribute problem goes
with it.** Both fall to one change of mechanism.

⭐ **Back up through a SECOND, read-only `sqlite3` connection to the tree's
database file, opened on a worker thread — not through Gramps' own connection.**

- **No GTK callback**, so R8's cap on work inside `GLib.idle_add` does not apply.
- **No `db.dbapi._Connection__connection`**, so the fragility this page accepts
  as its cost — an unpublished attribute with no public alternative — **is not
  incurred at all.**
- The `create_function`/collation objection **does not apply**: that was about
  *querying* with `regexp`. A backup copies pages.

**Measured against the owner's real tree, with Gramps open and holding it:**

| | |
| --- | --- |
| tree | 24,141,824 bytes, 2,933 people |
| **backup** | **120 ms** |
| `integrity_check` | **ok** |
| all ten table counts | **match the source exactly** |
| indexes / metadata rows preserved | 19 / 39 |
| Gramps lock preventing a second reader | **none** — and no `-wal`, `-shm` or `-journal` file present |

⚠️ **The connection must be opened ON the worker thread.** `sqlite3` refuses an
object created on another one, which is not an obstacle but a reminder that
nothing is shared with Gramps.

### ⛔ The one hazard, and any build must carry a bound for it

**Under a CONTINUOUSLY committing writer, `backup()` did not converge.** Run
against a scratch copy with a writer committing in a tight loop, it was still
restarting after **ten minutes** and was abandoned. SQLite restarts the copy when
the source is written during it, and a source written faster than it can be
copied never finishes.

⚠️ **Gramps writes in bursts rather than continuously, so this is probably not
the real case.** It is recorded because *probably* is not a bound: **a per-write
backup must carry a page budget and an attempt limit, and must say what it does
when it hits them, before it ships.**

⛔ **Nothing was built.** This establishes that the option is viable and what it
costs; the implementation is still owed a plan gate, and it still writes to a
tree, so it is still FULL tier.

## ⭐ The asynchronous design was tried, and reversed — 2026-08-23

**Recorded because the reasoning matters more than the outcome**, and because the
outcome looks arbitrary without it.

The build's first shape ran the copy on a **worker thread** and marshalled the
result back with `GLib.idle_add`, so that no single callback held the GTK loop.
That respected R8's cap. ⛔ **It also produced three correctness defects the
synchronous design cannot have:**

- **two documents approved close together snapshotted the same pre-A database**,
  so the second's backup restored away the first's write — *per-write recovery
  collapsing into batch undo*, which is precisely what R4 §1 says #25's deferral
  of destructive operations depends on not happening;
- **the dialog rendered a resolution taken before the copy** while the writer
  resolved live, so the owner could approve one target and another be written;
- **`totals_before` was counted at a moment unrelated to the snapshot it names**,
  making the documented restore check report a mismatch against a sound backup.

⚠️ **Every one of them needed an interval, and the interval was the asynchrony.**

**The measured cost that bought:** **108 ms** on the owner's real tree — 24 MB,
5,894 pages, one page each, **zero restarts** — against the **343–402 ms** of
main-thread cost this project already accepts for a name search. ⭐ **A third of
an already-accepted cost, once, immediately before a dialog the owner is about to
spend seconds reading.**

**The trade was wrong and is reversed.** The copy runs on the main thread inside
the existing callback, before the dialog.

⚠️ **What did NOT dissolve, stated so the reversal is not read as a cure:** a
crash mid-copy publishing a truncated file, two backups colliding on one name,
retention keyed on something mutable, and **cancelled previews evicting the
pre-write backup** — the dialog still sits between the copy and the write. Those
were fixed on their own terms: temp-name-then-atomic-rename, a collision-free
identity, a digest of the full tree directory, and retention that does not count
a preview nobody accepted.

⭐ **And the page budget was deleted rather than fixed a fourth time.** It was
rewritten three times and never once fired, because it inferred *too long* from
SQLite restart bookkeeping that resets on every restart — **a quantity that resets
cannot accumulate a bound.** A wall clock states the requirement directly.
⚠️ A clock cannot distinguish *slow* from *livelocked*; it does not need to, since
the outcome is identical and the measured workload restarts zero times. The
livelock was only ever produced by an artificial continuous writer on a scratch
copy.

## ⛔ There is no "synchronous" in a GTK application — approvals are serialised

⚠️ **The synchronous move shortened the window and serialised nothing**, and the
next reader will assume otherwise unless this says so. `writer.confirm` spins a
**nested GTK main loop**, so other `GLib.idle_add` callbacks — including another
`_present` — run *inside* it. Moving the copy off its worker removed the interval
before the dialog and left the one inside it untouched.

⭐ **Four review rounds found four different consequences of one missing
requirement:**

| round | what it looked like |
|---|---|
| 1 | two documents snapshotting the same database; the second's backup restored away the first's write |
| 2 | a cancelled preview's backup evicting the pre-write one from retention |
| 3 | re-entry through the dialog's nested loop, writing against a stale backup |
| 4 | an interleaved completion truncating the intent journal |

**They are not four defects. They are one, seen four times** — which is why the
answer is a bound rather than a fourth patch.

**One approval is in flight at a time. A second is REFUSED**, with the reason in
`host.log`, and the flag is cleared in a `finally` so no exit can leave it set —
a stuck flag would refuse every later proposal for the life of the process, which
is worse than the defect it prevents.

⛔ **Refused, not queued.** A queue would preserve the interleaving and merely
reorder it, and a second modal stacked on the dialog the owner is reading is
worse than the refusal it announces.

## ⭐ What serialising approvals left standing — 2026-08-23

**The bound held, and that is a measured result rather than a hope.** The round
that followed it was asked specifically whether two approvals could still
interleave, and answered that the guard *"appears to bound re-entrancy through
both confirmation and informational modal loops"*. **No fifth consequence of
unserialised approvals was found.** Four rounds of one defect ended when it was
bounded instead of patched a fourth time.

**What the round found instead was a different question entirely**, and the
difference is worth recording because it is what tells you a loop has closed:
every finding was about the backup's **lifecycle** and its **durability**, not
about concurrency. The design stopped being the subject.

### A backup is PROVISIONAL until the transaction commits

**Discarding it was one enumerated branch — the owner pressing Cancel.** Every
other pre-write exit kept the copy: the tree closing or swapping inside
`confirm`'s nested loop, the intent record refusing to write, the directory
entry failing to flush, and any exception at all.

⚠️ **Each kept copy is a snapshot of a tree nobody changed, and it is not merely
wasteful — it is corrosive.** `RETAIN` counts **files**. Every abandoned preview
pushes a real, journal-linked, pre-write backup one place closer to the edge of
the window. **Enough declined previews and every recovery point that could undo
a real write has been evicted by copies that protect nothing** — while the
directory looks healthily full, which is the shape of this project's most
expensive defect class.

⭐ **So the rule is *committed or discarded*, decided in one place.** A flag set
only when the writer returns, and a `finally` that discards otherwise. **The
second instance of an enumerated rule standing in for a bound, in one file, in
one week** — bounded rather than patched, and both halves tested: an exit that
leaks fails, and so does a committed write whose backup was removed.

### The completion must replace the intent, never open over it

The completed record re-uses the intent's stem deliberately — it finishes the
file it started rather than sitting beside it as a second record. But
`open(path, "w")` **truncates first**, and ⚠️ **that truncation happens after the
database has already committed.** For the span between it and the `fsync`, the
tree has changed and the only durable link to the backup that precedes it is a
zero-length file. `os.replace` is atomic on POSIX and Windows alike, so the name
holds either the intact intent or the intact completion at every instant — the
same bound the backup's own publication already used, for the same reason.

### ⛔ A verdict nobody reads is worth what not measuring it is worth

The previous round added `directory_synced` to the backup outcome and a
directory sync to the journal writer — **and then read neither result.** A fact
measured, reported honestly, and ignored. **That is class 3 committed while
fixing class 3**, which is the most instructive thing in this whole loop: the
instrument and the defect were the same shape.

Both are now read, and the backup's verdict is read **once, inside
`_take_backup`**, where both callers already pass — not at each call site, which
would have been the enumeration again.

### The Windows trade, stated as a trade

⚠️ **Windows cannot fsync a directory at all.** So the verdict is three-valued,
not two:

| verdict | what it means | what happens |
|---|---|---|
| `synced` | the entry was flushed | proceed |
| `unsupported` | the platform cannot do it | **proceed, and record it** |
| `failed` | a platform that can do it did not | **refuse the write** |

**Refusing on `unsupported` would refuse every write on the owner's only
platform.** That is not a durability guarantee; it is an outage wearing one.
Proceeding while recording which of the three happened is what keeps the claim
falsifiable — the alternative, letting a platform silently stand in for a
guarantee, is exactly what a boolean here did.

⭐ **The falsifier, recorded so it can be exercised rather than argued:** if the
owner would rather a write be refused outright on a platform that cannot make
its directory entry durable, this is wrong and it is a one-line change. It is a
product call about an acceptable failure mode, not a correctness question, and
it was decided rather than asked because refusing every write on Windows could
not have been what the ruling meant.

**And the flush covers every level this run may have created**, not just the
leaf: a tree's first backup creates both `backups/` and `backups/<tree>/`, and
syncing only the inner one leaves its own entry unflushed in the outer.

## ⛔ There is no observable "committed" outside the writer — 2026-08-23

**The backup's lifecycle rule was *committed or discarded*, and "committed" is
not a fact this code can learn.** That is the sharpest thing the review rounds
produced, and it survived two earlier rounds because the words sounded like a
description of what the flag measured.

**Read in the shipped Gramps 6.0.8, not reasoned about.** `dbapi.transaction_commit`
runs `self.dbapi.commit()` — the SQLite COMMIT — and *then* emits object signals,
commits the undo database, and calls `_after_commit`, which invokes
`undo_callback`, `redo_callback` and `undo_history_callback` **unguarded**. The
live UI sets all three, to update the Edit menu.

So there is a real window in which **the tree has durably changed and the call
has not returned.** A flag set after the call reads `False` throughout it.

⚠️ **The consequence was the worst one available:** the `finally` deleted the
only recovery point of a write that had already landed, leaving the intent
record on disk pointing at a file that no longer exists. **R4's guarantee
destroyed by the machinery built to maintain it** — and the test written
alongside it asserted exactly that behaviour, so the suite enforced the defect.

⭐ **The repair is to stop asking the unanswerable question.** Not *did it
commit*, which cannot be known from out here, but *do we know for certain that
nothing was attempted*. The flag is set **before** the call and named for what it
measures. **Keep on unknown.** The costs are not symmetric: keeping a needless
backup spends one retention slot, and discarding a needed one spends the
guarantee.

**This is the general shape of the same error three times on this page** — a
proxy that is true for the wrong reason. `directory_synced` measured and never
read; `unsupported` standing for *the open failed*; and now *returned* standing
for *committed*. **Every one of them read as green.**

## What this settles that was open

**Slice 3's deleted deliverable now has a mechanism.** R8 removed the spawned-CLI writer and left
"backup" as a word rather than a mechanism; this names one that works against an open tree.

**R4 unblocks behind it** — the guarantee downgrade R4 accepts is only payable if a backup can
actually be taken, and now it can be.

## What this does not settle

- **Nothing about when a backup is taken relative to a write.** That is R4's per-write cadence, not
  this page's.
- **Nothing about restore ergonomics** — file replacement is a mechanism, not a procedure someone
  can follow under stress.
- ⚠️ **No backup has been taken through Gramps' live connection, and that is the limitation
  that matters.** ⭐ **Be precise about what the one measurement on this page covers:** it establishes
  the *semantics* of `Connection.backup()` — that it runs to completion in a single call — on a
  standalone SQLite connection. **It says nothing about reaching Gramps' connection, about backing up
  a database Gramps is actively using, or about doing either from a GTK callback.**
- ⚠️ **The route to the connection is read from source and reasoned about, not exercised.** The
  first build that takes a real backup is the first evidence this works.
