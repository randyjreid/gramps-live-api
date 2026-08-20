# R8 — Channel architecture: an in-process HTTP host inside Gramps

**Ruled 2026-08-19.** This page records a decision. It is not a proposal and it is not argued again
here.

⚠️ **When ruled, nothing described below was built.** ⭐ **Updated 2026-08-19:** Slice A — the plugin,
the loopback listener, the token and the main-thread boundary — **is built and was run live** (see the
GUI session under *Falsifiers*). **The MCP client half, the write path and the approval dialog are
still unwritten**, and everything the ruling says about them remains a decision rather than a
description.

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

Any one of these falsifies the ruling and it is re-opened. **Three are discharged by measurement; two
are partially measured and stay open.**

### Measured: the AIO probe

A `GENERAL` plugin with `load_on_reg = True` was installed into the user plugin directory and the
**Gramps AIO CLI** was run with `-L` (list plugins), **no tree opened**. The hook fired inside the
AIO's own frozen interpreter and printed:

```
python=3.14.4 (main, Apr 11 2026) [MINGW GCC 15.2.0 64 bit (AMD64)]
uistate=False
http.server=OK  socketserver=OK  socket=OK  ssl=OK
json=OK  secrets=OK  threading=OK  hmac=OK
GLib=OK
```

**No `lock` file was created** by the run, checked against a baseline taken before it. Listing plugins
does not open a tree, which is the whole point of the route: the hook is reachable without touching
anyone's data.

**⛔ Discharged — these two cannot falsify the ruling any more:**

- ~~`load_on_reg` does not fire on the AIO build.~~ **It fired.**
- ~~Both `http.server` and raw `socket` are absent from the frozen stdlib.~~ **Both are present**, and
  so are `socketserver`, `ssl`, `secrets`, `hmac`, `threading` and `GLib` — every import the host
  needs.

**The probe was a CLI run. It said nothing about the three below**, which are exactly the properties
the design rests on at runtime, and which needed a GUI session with a tree loaded. That session has
now been held.

### Measured: the GUI session, 2026-08-19

The three remaining falsifiers were measured in a real Gramps AIO 6.0.8 GUI session against the
**blessed copy** — `RandyReid-Testing`, tree directory `…\grampsdb\6a821852`, the one carrying
`.gramps-live-api-copy`. Raw log: `%APPDATA%\gramps-live-api\falsifiers.txt`, timestamps 08:52:56 to
08:53:09. Every number quoted below is that log's.

#### ⛔ F1 — *`GLib.idle_add` callbacks do not run while a Gramps modal dialog holds a nested main loop.* **DISCHARGED — they do.**

- parent window taken from `uistate`: `ApplicationWindow`
- GLib main-loop depth **before** the dialog: **1**
- the modal dialog held the main thread for **3.004 s** (`response=-7`), **dismissed programmatically
  on a timer**
- the idle callback was scheduled from thread `f1-worker` at **+0.751 s**, and **fired 0.0002 s after
  it was scheduled**
- **the dialog was still up when it fired: True**
- GLib main-loop depth **inside** the callback: **2** — outside the dialog it was 1, so the callback
  genuinely ran under the nested loop

⭐ **This is the one that could have killed R8's approval surface, and it did not.** The ruling puts
approval in a Gramps dialog on the main thread; if `idle_add` had stalled behind that dialog's nested
loop, nothing could have driven the dialog from an HTTP request. **It can.**

#### ⚠️ F2 — *a `DbTxn` write from `idle_add` does not refresh the Gramps UI.* **PARTIALLY measured. NOT discharged.**

**Established — the write crosses and lands:**

- `idle_add` crossed from the worker thread in **0.0002 s**
- the write ran on thread **`MainThread`** (main thread: **True**)
- the transaction committed in **0.0709 s**
- ground truth: the note **reads back = True**, and **it is on the person's note list = True**
- notes in the tree: **before = 60, after = 61**

**Established — the mechanism that drives refresh fires:**

- `note-add` — **1 handle**, carried ours = **True**, on thread **`MainThread`**
- `person-update` — **1 handle**, carried ours = **True**, on thread **`MainThread`**

Both were already heard by the time the transaction closed, and were unchanged when re-read **1.5 s**
after the write.

⚠️ **NOT established: whether a relevant view refreshes in place.** The active page was
**`DashboardView` both before and after** the write, and a dashboard displays neither notes nor
people. The log's three-way answer —

```
refreshed in place: NOTHING
deferred (dirty, will refresh when you navigate back): nothing
unchanged: DashboardView
```

— is therefore **not evidence that a Person view would fail to refresh.** The probe never put a view
that cares about the written objects in front of the write. Every line of that split is about a page
with no reason to react.

**What would settle it:** the same measurement with a **Person or Note view active** at the moment
the transaction commits.

⛔ **F2 stays open.** The mechanism is confirmed; the visible outcome is not, and the ruling does not
claim it.

#### ⚠️ F3 — *a single-person read round trip through the main-thread hop exceeds ~2 s.* **PARTIALLY measured. NOT discharged.**

⛔ **What was measured is the hop, and the hop is not the falsifier.** Slice A's demo run against
the live host, Gramps open on the copy:

- valid token, tree open → `{ok: true, tree: {open: true, name: "RandyReid-Testing", people: 2924}}`
- **bad token → 401** · **a request carrying an `Origin` header → 403**
- **25 iterations:** median **2.2 ms**, min **1.5 ms**, p90 **3.4 ms**, **worst 89.9 ms** — the first
  call, cold

**Against a ~2000 ms budget that is ~22× inside on the worst case and ~900× on the median** — for
**the round trip through the HTTP listener and the `GLib.idle_add` hop**, which is what those 25
iterations exercised.

⚠️ **NOT measured: a single-person read, which is what F3 names.** The only route this slice has is
`/health`, and `tree_status()` reads `get_dbname` — a cached string — and `get_number_of_people`, a
table count. Both are O(1) **by requirement rather than by accident**: `accessor.py` states it, and
says in the same docstring that *"anything that walks people belongs behind a route this slice does
not have."* **So no person was read, and the quantity the ~2 s budget was written about — the cost of
the database work on the GTK main thread — does not appear in these numbers at all.**

⭐ **What the measurement does establish, and it is worth keeping:** the transport works, and its cost
is now a known number — **1.5 to 3.4 ms across 25 warm calls, and 89.9 ms on the cold first one.**
That is the baseline a person read would be added to.

⚠️ **It is a baseline, not a bound.** Nothing here says whether the read or the channel would dominate:
an indexed single-person lookup could land under the 2.2 ms median, and the cold call was 89.9 ms
rather than single-digit. **That comparison waits on the measurement, like the rest of F3.**

**What would settle it:** time a single-person read end to end through the main-thread hop against the
~2 s budget, under the same live-GUI conditions. **Tracked as
[#89](https://github.com/randyjreid/gramps-live-api/issues/89), blocked on the first route that reads
a person** — slice 4 or 5a in `docs/roadmap.md`'s numbering, neither of which is startable today.

⚠️ **Demo step 2 — "close the tree in Gramps, and ask again" — was NOT performed.** It needs a GUI
menu action and nobody was present to click it. **Recorded as unperformed, not as passed.** The *code
path* was reached from the other direction: `host.log` carries
`2026-08-19T08:52:58 INFO database-changed: no tree open` at startup, before the tree was opened.

### ⚠️ Two things the probe established that this ruling did not anticipate

1. **The AIO ships Python 3.14.4.** This repository targets `py310` and CI runs **3.10, 3.11 and
   3.12**. So the host plugin's source **must stay 3.10-compatible** — it is linted and typed against
   that floor — **and will execute on 3.14, an interpreter CI never runs.** Neither end of that range
   is optional and the gap between them is untested by construction. Treat any 3.11+ syntax or any
   behaviour that moved between 3.12 and 3.14 as a defect the gates cannot catch.
2. **`uistate` was `None` and no tree was open** — that is what the `uistate=False` line above
   reports. It is the condition this ruling predicted in *Why `load_on_reg`, not a gramplet*: the hook fires
   unconditionally at startup, before any UI state exists and with `dbstate.db` a `DummyDb`. **Predicted,
   and now measured.**

### Measured against finding 1: the in-situ 3.14 harness

Finding 1's sentence *"the gap between them is untested by construction"* stands as written — it
describes the **gates**, and no gate has changed. What the same GUI session added is a **one-off
in-situ run** of this repository's own tests inside the AIO's frozen 3.14.4 interpreter. Raw log:
`%APPDATA%\gramps-live-api\insitu.txt`.

**Getting the suite to run at all took three attempts, and which one worked is part of the record:**

- **Route 1 (`pytest`) — unavailable.** `pytest` is **not importable in this interpreter**; the AIO
  ships **no `site-packages` at all**.
- **Route 2 (`unittest`) — collected 0.** `unittest.TestLoader` found **0 tests** across the **5**
  modules that imported, because they are plain `test_*` functions with bare asserts and `TestLoader`
  discovers only `TestCase` subclasses.
- **Route 3 — taken.** The real test functions, called directly, behind a minimal `pytest` stand-in
  supplying `raises`, `param` and no-op decorators. The only fixture supplied is `tmp_path`.

**Result on the AIO's 3.14.4: 60 passed, 0 failed, 9 skipped, 0 module errors.** The same harness on
the project's own **3.12: identical — 60 / 0 / 9.**

⭐ **No 3.12 → 3.14 divergence in the surface this harness covers.**

- **`tests/unit/test_host_thread_boundary.py` — the suite carrying the load-bearing invariant above —
  ran 8 of 8, all passing, under 3.14.**
- ⚠️ **`sys.flags.optimize` was checked and is 0.** This matters more than it looks: under `-O` every
  bare assert is stripped and the whole suite would pass **vacuously**. The check is what stops the
  60/0/9 from being meaningless, so it is recorded as part of the result rather than as a detail.
- **The harness was negative-controlled.** A module holding a false assert, a `raises` that does not
  raise, and a `raises` with a wrong `match` reported **1 passed, 3 failed**, with tracebacks — so the
  harness reports failures rather than being decorative.
- **9 skipped, by name** — the tests needing `monkeypatch` or parameters the stand-in does not supply.
  **Nine, not "a few".**

⛔ **This does not mean CI covers 3.14.** It is a **separate in-situ run on one machine, not a gate**,
and it covers only what route 3 could reach. Finding 1's warning is unchanged for every future change.

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
