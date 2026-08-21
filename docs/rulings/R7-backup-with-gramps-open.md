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

1. **Whether the copy runs incrementally**, so it respects R8's cap on work performed inside
   `GLib.idle_add`. ⚠️ **The `pages` and `sleep` arguments are believed to exist and have NOT been
   confirmed on the AIO's Python 3.14.4.** Confirm before relying on them; if they are absent, the
   work-cap question is open on different terms.
2. **Where the backup file lands, and its retention.**

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
- ⚠️ **Nothing is measured.** The route is read from source and reasoned about. No backup has been
  taken, and the first build that takes one is the first evidence this works.
