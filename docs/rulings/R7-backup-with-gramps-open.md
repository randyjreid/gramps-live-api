# R7 — Backup with Gramps open: SQLite's backup API against the live connection

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
