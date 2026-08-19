# R8 — Channel architecture: an in-process HTTP host inside Gramps

**Ruled 2026-08-19.** This page records a decision. It is not a proposal and it is not argued again
here.

⚠️ **Nothing described below is built.** The ruling settles *what* the channel is; the host, the
client and every test are unwritten.

---

## The ruling

The tool is a **Gramps addon running inside the Gramps process**. It registers as a `GENERAL` plugin
with `load_on_reg = True` and hosts a stdlib `http.server` listener bound to `127.0.0.1` on a
**daemon thread**. All database and GTK access is marshalled onto the **GTK main thread** via
`GLib.idle_add`. **Approval happens in a Gramps dialog on the main thread.** The MCP server becomes a
**thin HTTP client containing no Gramps code.**

**Gramps stays open. There is no export, no copy-to-write, no spawned CLI, no `op.json`.**

---

## Why the old reason was wrong

The architecture that R8 replaces was built around Gramps' lock. That premise is false.

The Gramps lock is **advisory and trivially bypassable**:

- `DBLOCKFN = "lock"` (`gramps/gen/db/dbconst.py`) is a text file holding one line, `user@host` —
  **no PID, no timestamp, no `flock`**.
- `write_lock_file()` (`gramps/gen/db/utils.py`) is called **unconditionally** in `DbGeneric.load()`
  and **does not check for an existing lock**.
- Every consumer check is `os.path.isfile(...)` in caller code.
- `--force-unlock` is `os.unlink`.
- `gramps/plugins/db/dbapi/sqlite.py` opens with a bare `sqlite3.connect()` — **no
  `PRAGMA locking_mode`, no WAL**.

A second process can connect, and SQLite permits it.

### ⚠️ The real hazard

`DbGeneric.load()` reads `name_formats`, `researcher`, all nine bookmark lists, custom type sets,
`surname_list`, gender statistics and **every Gramps ID counter** (`cmap_index`, `smap_index`, …)
**into process memory**. That state is written back in exactly one place: `_set_all_metadata()`,
**called only from `DbGeneric.close()`** — it has no other call site.

**Therefore two processes holding the same tree are last-writer-wins on the ID counters:** a person
added by process B is **overwritten when process A closes**, and the next ID Gramps issues
**collides**. **Silent duplicate Gramps IDs, with no SQLite conflict**, because SQLite row locking
says nothing about a value cached in another process's heap. `DbGenericUndo.undodb` is a plain Python
list, so each process also has **its own undo stack blind to the other's writes**.

**In-process dissolves this rather than mitigating it: one process, one cache, one undo stack, one
owner of the counters.**

---

## Why HTTP

On the Gramps AIO (cx_Freeze) build, **loopback TCP is the only available IPC primitive** — the AIO
bundles **no pywin32** (named pipes dead), and Windows offers no usable Unix socket.

**Precedent exists in the official addon collection:** `addons-source/Topola/topola_server.py`
subclasses `threading.Thread`, sets `daemon = True`, binds `HTTPServer(('127.0.0.1', 8156), Handler)`
and calls `serve_forever()` **inside the Gramps process**. This architecture already ships.

⭐ **What returns is HTTP as the hop between our own two halves — not an agent-facing API.** The
agent still reaches this project over stdio MCP. Phase 5's four-route tool surface stays dead; see
*What this supersedes and deletes* below.

## Why `load_on_reg`, not a gramplet

`CLIManager.do_reg_plugins()` (`gramps/cli/grampscli.py`) passes `load_on_reg=True` **only for
`USER_PLUGINS`** — third-party addons are exactly what the hook is for. It fires **unconditionally at
startup with no tree open** (`dbstate.db` is a `DummyDb`); the plugin then subscribes to
`dbstate.connect("database-changed", cb)` — the same mechanism `Gramplet.__init__` uses.

**A gramplet is not viable:** `GrampletPane` constructs gramplets only when the containing page is
built, and `ViewManager.goto_page()` builds pages **lazily**.

**A tool is not viable:** `runfunc` requires a menu click every session.

---

## ⭐ The load-bearing invariant

> **No Gramps database object and no GTK object is ever touched from the HTTP thread.**

Gramps' SQLite connection is created with a bare `sqlite3.connect()` and **never passes
`check_same_thread`**, so the default `True` applies and cross-thread use raises
`sqlite3.ProgrammingError`. Gramps core dev **prculley, on Discourse (Sept 2025)**:

> *"Threading is not generally used in Gramps because our code is not thread safe. […] Not even a
> little bit."*

`Callback.emit()` also dispatches handlers **synchronously in the emitting thread**.

**Enforce this mechanically: one accessor module owns the boundary, and a test asserts that calling
any DB helper from a non-main thread raises.**

⚠️ **This is the property the whole design rests on and the one a future agent will violate by
accident.**

---

## The copy rule changes form

Writes-only-to-a-copy was the owner's safety rule **doing double duty** as the thing that made a
separate writer survivable. **It no longer needs that job.**

**New form: the host refuses to arm its write path unless the currently-open tree directory carries
`.gramps-live-api-copy`, checked on `database-changed`.** One config flag to relax later.

**Same protection, no architectural cost.**

---

## `.gramps-live-api-undo` is confirmed required

`DbGenericUndo.__init__` does `self.undodb = []`; `open()`/`close()` are **no-op stubs**; the
`DBUNDOFN` (`undo.db`) path is computed in `load()` and **never used** by the DB-API backends.

**Undo is a process-local list discarded on close. Our journal is the only durable record.**

---

## Accepted risks

1. **A listening socket is new attack surface** — bind loopback only, **random bearer token**
   generated at startup written to `%APPDATA%\gramps-live-api\token` with restrictive ACLs,
   **required on every request**, and **reject any request carrying an `Origin`
   header** (defeats DNS-rebinding/CSRF from a page the user has open). **Residual: any process
   running as the owner can read the token; accepted, since such a process could read the tree
   directly.**
2. ⚠️ **`load_on_reg` swallows exceptions** (traceback printed, startup continues) **and the AIO has
   no console, so a failed start is invisible** — the host writes a **startup status line** to a log
   under `%APPDATA%\gramps-live-api\`, and the client must **distinguish "host unreachable" from
   "host errored"**.
3. **`.gpr.py` bodies are `exec`'d unsandboxed every launch** — Gramps' model, not ours; keep the
   plugin dir a hand-created junction.
4. **Long work inside `idle_add` blocks the GTK loop** — cap work per callback, **hard timeout on the
   HTTP side returning 503** rather than hanging.
5. **Injection surface is unchanged in kind; R3 still owed.**

---

## Falsifiers

Any one of these falsifies the ruling and it is re-opened:

- `load_on_reg` does not fire on the AIO build.
- Both `http.server` and raw `socket` are absent from the frozen stdlib.
- `GLib.idle_add` callbacks do not run while a Gramps modal dialog holds a nested main loop.
- A `DbTxn` write from `idle_add` does not refresh the Gramps UI.
- A single-person read round trip through the main-thread hop exceeds **~2 s**.

---

## What this supersedes and deletes

**Supersedes:** the **process-model half of R2** — *its conclusion stands; its reasoning is
replaced.* R2 ruled that Gramps stays open and named an in-process component; R8 says what that
component is, and replaces the lock-shaped reasoning R2 inherited.

**Deletes:**

- **Slice 3 as planned.**
- the `op.json` channel;
- the spawned-CLI writer;
- the fresh-process read-back approval;
- **the `--force-unlock` question, now moot** — the lock never made a second writer impossible, so
  nothing turns on whether we would break it.

⭐ **The one-writer rail stands, and its reason is replaced.** Not *"the lock forbids a second
writer"* — it does not — but *"two processes are last-writer-wins on the ID counters."*

---

## What this does not settle

- **R1** (the batch shape), **R3** (the injection widening), **R4** (graduation and the guarantee
  downgrade), **R5** (media custody) and **R6** (attributes versus events) are untouched and still
  owed.
- **R7** — what takes a backup — is reshaped rather than answered: see `docs/roadmap.md`.
- Nothing about the operation vocabulary, the batch model or the approval *content*.
