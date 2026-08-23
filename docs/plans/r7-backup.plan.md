# R7's backup — build plan

⚠️ **A PLAN, awaiting the owner's approval. Nothing here is built, and nothing in it may be built
before he approves it.** It writes to a tree, so it is FULL tier: this document is the one-page spec
its plan gate needs.

⛔ **The mechanism is settled and is not re-derived here.** See
[`rulings/R7-backup-with-gramps-open.md`](../rulings/R7-backup-with-gramps-open.md) — a **second,
read-only `sqlite3` connection opened on a worker thread**, measured 2026-08-22 against the real tree
with Gramps holding it: **24 MB in 120 ms**, `integrity_check` ok, all ten table counts matching, 19
indexes and 39 metadata rows preserved, no lock preventing a second reader. **No
`_Connection__connection`**, so R7's accepted fragility cost is not incurred at all.

⛔ **CORRECTED after review. An earlier draft said "no GTK callback, so R8's work cap does not
apply", and that was FALSE as written.** Opening the connection on a worker thread does not by
itself take the work off the GTK loop: the call site is `_present`, which runs **inside**
`GLib.idle_add`, so an implementation that *waits* for the backup blocks the main loop for as long
as the backup takes — up to the full budget below. **See §1a: the wait must not happen inside the
callback**, and that is a design obligation rather than a detail.

⭐ **Why this matters more than its size.** R4 approved the guarantee downgrade in these words:

> *"The guarantee changes from unwritable-by-construction to recoverable-after."*

**The backup is the entire replacement guarantee.** Everything below exists to make
*recoverable-after* true rather than asserted.

---

## Acceptance criteria — mechanically checkable

| # | criterion |
|---|---|
| **A1** | A backup of the open tree is taken **before** each write, from a worker thread, and `integrity_check` on the copy returns `ok`. |
| **A2** | ⛔ **If the backup cannot be taken, the host refuses to arm its write path and says so.** No export fallback, no write without a backup, no quiet continuation. |
| **A3** | The backup carries a **page budget** and an **attempt limit**; exceeding either is a failure that routes to A2, not a retry loop. |
| **A4** | The backup's **age relative to the write is visible without archaeology** — R4 precondition 4. |
| **A5** | Restore is **file replacement**, not import, documented as steps the owner performs. |
| **A6** | Every table count and the index count in the copy match the source at the moment it was taken. |

---

## 1. The livelock, and the bound it forces

⛔ **Measured, and not resolved by cleverness: under a continuously committing writer, `backup()` did
not converge in ten minutes.** SQLite restarts the copy when the source is written during it, and a
source written faster than it can be copied never finishes.

⚠️ **Gramps writes in bursts, so this is probably not the real case — and *probably* is not a bound.**

**The bound:**

- **`pages=1024` per step** — ⚠️ **this is the step SIZE, not the budget.** A3's *page budget* is a
  separate number and was missing from an earlier draft, which made that criterion unimplementable:
  a callback that only counts steps has no count at which it fails.
- **Page budget: 4× the source's page count**, read from `PRAGMA page_count` before the copy starts.
  ⭐ Derived rather than picked — a clean copy touches each page about once, so 4× tolerates several
  restarts and still terminates. The progress callback accumulates pages copied and **fails the
  attempt when the budget is exceeded**, routing to A2 exactly as the clock does.
- **Wall-clock budget: 5 seconds.** ⭐ **Derived from the measurement rather than invented**: the real
  tree copies in **120 ms**, so 5 s is roughly 40× headroom. A run that has not finished in 5 s is not
  slow — it is being restarted by a writer, which is the livelock.
- **Attempt limit: 2.** One retry absorbs a single burst. A second failure is a pattern, not bad luck.
- ⛔ **On exhaustion: FAIL. Route to A2 — refuse to arm, and say why.** Never a longer timeout, never a
  partial copy kept, never a write without a backup.
- **The partial destination file is deleted on failure**, so a truncated copy can never be mistaken for
  a backup. ⚠️ Deleting a **failed backup's own temp file** is not the banned tree deletion: it is this
  build's own scratch output, and it is never a tree file.

⚠️ **Falsifier for the 5 s figure:** if a legitimate backup on a larger tree ever exceeds it, the budget
is wrong and must be re-derived from a measurement — not raised by feel.

## 1a. ⛔ The callback must RETURN, not wait

**The backup runs on a worker thread. The decision to write does not.**

`_present` runs inside `GLib.idle_add`. If it starts a worker and blocks on the result, the GTK loop
is frozen for the duration — **up to 10 s under the budget above** — which is precisely the R8 cap
the worker was supposed to respect. ⚠️ **Moving work to a thread and then waiting for it on the main
thread moves nothing.**

**So the flow is an explicit continuation:**

1. `_present` checks the blessing, starts the backup on a worker, and **returns immediately.** The
   GTK loop is free.
2. The worker finishes — success or failure — and **reschedules onto the main thread** with
   `GLib.idle_add`, the same marshalling the host already uses in the other direction.
3. That second callback re-checks the blessing (a tree can close while a backup runs), then opens
   the dialog and performs the write.

⚠️ **The blessing is checked TWICE, deliberately**, for the reason the existing write path already
checks it twice: the first check and the transaction are separated by real time — and now by a
worker as well.

⛔ **No dialog appears before the backup succeeds.** A dialog that opens and then reports *"the
backup failed, nothing was written"* has already spent the owner's attention on a decision that
could not be honoured.

⚠️ **This makes the write path asynchronous in a way it is not today, and that is the largest piece
of work in this slice — larger than the backup itself.** Named here so the plan gate prices it.

## 2. Refuse-to-arm — ⛔ verbatim, and it is what bounds the accepted cost

> **If the backup cannot be taken, the host refuses to arm its write path and says so. It does not fall
> back to an export, it does not write without a backup, and it does not continue quietly.**

**Where it lives:** the write path's existing pre-transaction check, beside `accessor.blessing()` in
`gramps_live_api_host.py::_present` — which already refuses at that point and already tells the owner
through `writer.tell`. ⭐ **The refusal surface exists and is proven**; this adds a second condition to
it rather than inventing a new one.

**Ordering: blessing first, then backup.** A tree that may not be written does not get copied.

## 3. Per-write, not per-session — ⛔ a ruled decision, not a performance choice

R4 §1 keeps this **per-write deliberately**, because #25 defers destructive operations *on the condition
that backup stays per-write* — at per-session cadence, restore **is** batch undo, and destructive
operations jump the queue on that basis.

⭐ **This plan proposes per-write and does not seek to change it.** At **120 ms** there is no performance
case to make: the dialog the owner is reading takes orders of magnitude longer than the backup.

⚠️ **Recorded so a later reader cannot mistake silence for absence of thought:** if per-write ever became
untenable, that is **a change to a ruled decision** and goes back to the owner as one, carrying #25's
coupling with it. It is not a tuning knob.

## 4. Where backups land, retention, and finding the right one

**Location:** `%APPDATA%\gramps-live-api\backups\<tree-name>\`, beside the existing journal directory.
⛔ **Never inside the tree directory** — a file there is one Gramps may enumerate, and the sentinel
precedent already says the tree directory is not ours to litter.

**Naming:** `<UTC-timestamp>-<tree-name>.sqlite`, timestamp first so lexical order is chronological.

⭐ **A4 — the age relative to the write is visible without archaeology.** The journal already records each
write with its UTC timestamp and its approved preview. **The journal entry gains the backup's filename,
the backup's own timestamp, and the tree's object totals at that moment** (see §5 step 4), so *"which backup predates this write"* is answered by reading the
journal entry for that write — not by comparing file mtimes and hoping.

**Retention: keep the last 20 per tree, and never prune the newest.** At 24 MB that is roughly 480 MB,
which is the trade being made explicitly rather than discovered later. ⚠️ Pruning runs **after** a
successful backup, never before, so a failed backup cannot destroy the previous good one.

## 5. Restore — file replacement, in steps the owner performs

⛔ **Not automated, and that is deliberate.** Restore overwrites a tree; a tool that does it unattended is
exactly the destructive operation this project defers. ⛔ **The tool must never perform these steps.**

1. **Close Gramps.** Verify by process, not by window.
2. Confirm there is no `lock` file in the tree directory. ⛔ **Never delete one** — if it is present,
   Gramps is still running.
3. Copy the chosen backup over `sqlite.db` in the tree directory, moving the existing file aside under a
   new name first.
4. Reopen Gramps and check the person count against what the journal says it was.

⚠️ **Step 4 needs a number the journal does not currently record.** `document.journal_record` stores
the created and attached ids and the approved preview — **no total person count** — so as written
that step could not be performed. **The journal entry therefore gains the source tree's object
totals at backup time**, alongside the backup filename and timestamp. ⭐ `accessor.tree_totals()`
already produces exactly that, in O(1), so this is a field to store rather than a walk to add.

⭐ **Handles survive**, because nothing re-reads and re-keys the data — which is the whole reason R7 chose
file replacement over Gramps' export, whose import silently regenerates every handle.

## 6. R4's arming check — ⛔ IN this slice

R4 precondition 3 calls it *"the largest gap between this ruling and anything that could act on it"*, and
that is still true: `src/gramps_live_api/host/` has no sentinel check of its own.

⭐ **It belongs here** because A2 is itself an arming refusal, and building a second refusal beside an
absent first one would leave the sentinel check as the only unbuilt precondition while everything around
it shipped. **One refusal point, two conditions: blessed, and backed up.**

## 7. Out of scope

- ⛔ **Blessing the live tree.** R4 §3 is a sequencing condition — the sentinel does not go on the live
  tree until the backup path works. Shipping this makes that decision *possible*; it remains the owner's,
  on its own day.
- ⛔ **Automated restore.**
- ⛔ **Detecting a bad write.** R4 records *"the damage is noticed"* as unbounded and unowned. This plan
  does not claim it.
- ⛔ **Anything about what may be written** — R3's territory and the operation registry's.

## 8. ⚠️ How this interacts with #103

Both touch `accessor.py`, the module that owns the database boundary.

**They do not collide, and the reason is worth stating:** #103's ratchet asserts that every
`priv`-carrying container **reachable from an accessor path** is gated. **A backup copies pages. It never
reads a container, never renders a field, and never puts anything on the wire** — so it adds no reachable
path, and the ratchet has nothing to say about it.

⛔ **One thing to watch.** If the backup path is written as an accessor function that reads `_DBSTATE.db`
to find the file path, it becomes a function the boundary tests inspect. It must wear `@on_main_thread`
for the path lookup and hand **only a string** to the worker thread. ⚠️ **No database object crosses the
thread boundary** — that is the load-bearing invariant of the entire host, and a backup thread holding a
`db` reference would break it while looking harmless.

**Sequencing:** either order works. #103 is a test-only ratchet; this is a new path the ratchet does not
constrain.

## 9. What this plan does not know

- ⚠️ **No backup has ever been taken by this codebase.** The 120 ms measurement was a standalone probe.
  **The first build that takes a real backup is the first evidence the integrated path works**, and the
  plan gate should expect the build to demo it rather than assert it.
- **Whether 20 backups is the right retention** — a guess, and marked as one.
- **What happens if the tree file sits on a network path**, where a second reader may behave differently.
  Untested, and out of scope until it happens.
